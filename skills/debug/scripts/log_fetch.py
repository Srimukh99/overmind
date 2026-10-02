#!/usr/bin/env python3
"""log-fetch: resolve a service to its log backend, run one read-only query,
summarise the result.

Flow:
  1. load or build the service map (.overmind/services.json)
  2. resolve the service name (exact, then fuzzy)
  3. rank backends from repo signals + environment; aggregators win ties
  4. build a query for the chosen backend
  5. run it read-only, cap the output, hand it to log-trace

Never mutates anything. Never calls kubectl. If no backend is usable it prints
the resolved target and the exact command a human can run.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import backends as B           # noqa: E402
import service_map as SM       # noqa: E402

MAX_OUTPUT_BYTES = 200000


def resolve_service(svcs, want):
    if want in svcs:
        return want, svcs[want]
    low = want.lower().replace('_', '-')
    for name in svcs:
        if name.lower().replace('_', '-') == low:
            return name, svcs[name]
    hits = [n for n in svcs if low in n.lower().replace('_', '-')
            or n.lower().replace('_', '-') in low]
    if len(hits) == 1:
        return hits[0], svcs[hits[0]]
    if len(hits) > 1:
        return None, hits
    return None, []


# Workloads a log-shipping agent plausibly scrapes. Serverless runtimes emit
# straight to their cloud's own log service, so an aggregator only wins there
# if its config names the service explicitly.
AGGREGATOR_RUNTIMES = {'kubernetes', 'container', 'ecs', 'ec2', 'code-engine',
                       'container-apps', 'do-app', 'scaleway-container', 'apprunner'}


def aggregator_applies(svc, backend, signals):
    if backend['kind'] != 'aggregator':
        return True, None
    if svc.get('runtime') in AGGREGATOR_RUNTIMES:
        return True, None
    name = svc.get('name', '')
    for path in signals.values():
        if isinstance(path, str) and name and name in path:
            return True, None
    if svc.get('%s_explicit' % backend['key']):
        return True, None
    return False, '%s workloads log to their cloud backend' % (svc.get('runtime') or 'this')


def choose_backend(svc, signals, prefer=None):
    ranked = B.rank(signals, prefer=prefer)
    svc_cloud = svc.get('cloud')
    usable, rejected = [], []
    for conf, b in ranked:
        if b['cloud'] and svc_cloud and b['cloud'] != svc_cloud:
            rejected.append((b, 'service runs on %s' % svc_cloud))
            continue
        ships_to = svc.get('ships_to')
        if prefer != b['key'] and ships_to and b['key'] not in ships_to:
            rejected.append((b, 'shipper %s sends logs to %s' %
                             (svc.get('shipper'), ', '.join(ships_to))))
            continue
        if prefer != b['key'] and not ships_to:
            ok, why = aggregator_applies(svc, b, signals)
            if not ok:
                rejected.append((b, why))
                continue
        missing = [k for k in b.get('needs', []) if not svc.get(k)]
        if missing:
            rejected.append((b, 'missing %s' % ', '.join(missing)))
            continue
        q = b['build'](svc, '1h', 200, None)
        if q is None:
            rejected.append((b, 'not enough detail to build a query'))
            continue
        usable.append((conf, b))
    return usable, rejected


def run_query(backend, query, timeout):
    cmd = backend['command'](query)
    if not cmd:
        return None, None, 'backend has no runnable command'
    exe = cmd[0]
    if not shutil.which(exe):
        return cmd, None, '%s is not installed' % exe
    if any('${' in part for part in cmd):
        return cmd, None, 'query needs credentials from the environment; run it yourself'
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return cmd, None, 'timed out after %ds' % timeout
    except OSError as exc:
        return cmd, None, str(exc)
    out = (p.stdout or '') + (p.stderr or '')
    if p.returncode != 0 and not p.stdout:
        return cmd, None, (p.stderr or '').strip().splitlines()[-1:] or ['exit %d' % p.returncode]
    return cmd, out[:MAX_OUTPUT_BYTES], None


def summarise(text, repo):
    """Hand raw logs to log-trace so the agent reads a summary, not the logs."""
    tracer = os.path.join(HERE, 'log_trace.py')
    if not os.path.exists(tracer):
        return None
    try:
        p = subprocess.run([sys.executable, tracer, '--repo', repo],
                           input=text, capture_output=True, text=True, timeout=60)
        return p.stdout
    except Exception:
        return None


def main(argv=None):
    ap = argparse.ArgumentParser(prog='log-fetch')
    ap.add_argument('service', nargs='?', help='service name to fetch logs for')
    ap.add_argument('--repo', default='.', help='repo root (default: .)')
    ap.add_argument('--since', default='1h', help='lookback window (default: 1h)')
    ap.add_argument('--limit', type=int, default=200, help='max log lines (default: 200)')
    ap.add_argument('--grep', help='filter text to push into the backend query')
    ap.add_argument('--backend', help='force a backend key')
    ap.add_argument('--refresh', action='store_true', help='rebuild the service map first')
    ap.add_argument('--list', action='store_true', help='list services and exit')
    ap.add_argument('--backends', action='store_true', help='list detected backends and exit')
    ap.add_argument('--dry-run', action='store_true', help='print the query, do not run it')
    ap.add_argument('--raw', action='store_true', help='print raw logs instead of a summary')
    ap.add_argument('--timeout', type=int, default=60)
    ap.add_argument('--json', action='store_true')
    args = ap.parse_args(argv)

    repo = args.repo
    data = None if args.refresh else SM.load(repo)
    if data is None:
        data = SM.build(repo)
        SM.save(repo, data)
    svcs = data.get('services', {})
    signals = data.get('signals', {})

    if args.backends:
        ranked = B.rank(signals)
        if not ranked:
            print('no log backend detected in this repo')
            return 1
        print('detected backends (best first):')
        for conf, b in ranked:
            print('  %-18s %-12s confidence %d  %s' % (b['key'], b['kind'], conf, b['label']))
        return 0

    if args.list or not args.service:
        if not svcs:
            print('no services found; is there IaC in %s?' % os.path.abspath(repo))
            return 1
        print('%d services:' % len(svcs))
        for name in sorted(svcs):
            s = svcs[name]
            print('  %-30s %-14s %s' % (name[:30], s.get('runtime', '?'),
                                        s.get('log_group') or s.get('namespace') or ''))
        return 0

    name, svc = resolve_service(svcs, args.service)
    if name is None:
        if svc:
            print('ambiguous: %s' % ', '.join(sorted(svc)[:8]))
        else:
            print('no service matching %r; try --list or --refresh' % args.service)
        return 1

    usable, rejected = choose_backend(svc, signals, prefer=args.backend)
    if not usable:
        print('service: %s  runtime: %s  cloud: %s' %
              (name, svc.get('runtime', '?'), svc.get('cloud') or 'unknown'))
        print('defined at: %s:%s' % (svc.get('iac_file', '?'), svc.get('iac_line', '?')))
        print('no usable log backend.')
        for b, why in rejected[:5]:
            print('  %-18s %s' % (b['key'], why))
        return 2

    conf, backend = usable[0]
    query = backend['build'](svc, args.since, args.limit, args.grep)
    cmd = backend['command'](query)

    header = {
        'service': name,
        'runtime': svc.get('runtime'),
        'cloud': svc.get('cloud'),
        'backend': backend['key'],
        'backend_label': backend['label'],
        'confidence': conf,
        'iac': '%s:%s' % (svc.get('iac_file', '?'), svc.get('iac_line', '?')),
        'source_path': svc.get('source_path'),
        'query': query,
        'command': cmd,
        'alternatives': [b['key'] for _, b in usable[1:4]],
    }

    if args.dry_run:
        if args.json:
            print(json.dumps(header, indent=2))
        else:
            print('service:  %s (%s)' % (name, svc.get('runtime', '?')))
            print('backend:  %s - %s' % (backend['key'], backend['label']))
            print('command:  %s' % ' '.join(cmd) if cmd else 'command:  n/a')
            if header['alternatives']:
                print('also:     %s' % ', '.join(header['alternatives']))
        return 0

    cmd, out, err = run_query(backend, query, args.timeout)
    if err:
        print('service:  %s (%s)' % (name, svc.get('runtime', '?')))
        print('backend:  %s - %s' % (backend['key'], backend['label']))
        print('could not run: %s' % (err if isinstance(err, str) else err[0]))
        if cmd:
            print('run this yourself:')
            print('  %s' % ' '.join(cmd))
        return 3

    if not out or not out.strip():
        print('service:  %s  backend: %s' % (name, backend['key']))
        print('no log lines in the last %s' % args.since)
        return 0

    if args.raw:
        sys.stdout.write(out)
        return 0

    print('service:  %s (%s via %s)' % (name, svc.get('runtime', '?'), backend['key']))
    if svc.get('source_path'):
        print('code:     %s' % svc['source_path'])
    print('')
    summary = summarise(out, repo)
    if summary:
        sys.stdout.write(summary)
    else:
        sys.stdout.write('\n'.join(out.splitlines()[-40:]))
    return 0


if __name__ == '__main__':
    sys.exit(main())
