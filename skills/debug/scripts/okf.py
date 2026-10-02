#!/usr/bin/env python3
"""Export the service map as an Open Knowledge Format (OKF v0.1) bundle, and check a bundle.

OKF is Google Cloud's open format for knowledge agents read: a folder of markdown
files with YAML frontmatter. The only hard rule is a non-empty `type` field; title,
description, resource, tags and timestamp are common optional fields, markdown links
form the graph, and index.md / log.md are optional entry points.

Bundle written:
  index.md                  entry point
  services/index.md         every service, one line each
  services/NAME.md          type: Service  (runtime, cloud, IaC location, where its logs are)
  clusters/NAME.md          type: Kubernetes Cluster
  logging/index.md          log shippers
  logging/KIND.md           type: Log Shipper  (config file, where it sends logs)
  log.md                    newest-first history of exports

Generated files carry `generator: overmind`; only those are rewritten or pruned, so
hand-written docs (runbooks, notes) can live in the same bundle.

  python3 okf.py check DIR      conformance: every doc typed, every link resolves
"""
import datetime, json, os, re, sys

GEN = 'overmind'
LINK = re.compile(r'\]\(([^)\s#]+\.md)(?:#[^)]*)?\)')


def slug(s):
    return re.sub(r'[^a-z0-9._-]+', '-', str(s).lower()).strip('-.') or 'item'


def frontmatter(fields):
    lines = ['---']
    for k, v in fields.items():
        if v is None or v == [] or v == '':
            continue
        if isinstance(v, list):
            lines.append('%s: [%s]' % (k, ', '.join(json.dumps(str(x)) for x in v)))
        else:
            lines.append('%s: %s' % (k, json.dumps(str(v))))
    lines.append('---')
    return '\n'.join(lines) + '\n'


def read_meta(path):
    try:
        text = open(path, encoding='utf-8').read()
    except OSError:
        return None, ''
    m = re.match(r'---\n(.*?)\n---\n', text, re.S)
    if not m:
        return None, text
    meta = {}
    for line in m.group(1).splitlines():
        k, _, v = line.partition(':')
        v = v.strip()
        try:
            v = json.loads(v) if v.startswith(('"', '[')) else v
        except ValueError:
            pass
        meta[k.strip()] = v
    return meta, text[m.end():]


def generated(path):
    meta, _ = read_meta(path)
    return bool(meta) and meta.get('generator') == GEN


def logs_line(s, shipper_links):
    parts = []
    if s.get('log_group'):
        p = 'CloudWatch log group `%s`' % s['log_group']
        if s.get('log_stream_prefix'):
            p += ', streams starting `%s`' % s['log_stream_prefix']
        parts.append(p)
    if s.get('gcp_resource_type'):
        parts.append('Cloud Logging, resource type `%s`' % s['gcp_resource_type'])
    if s.get('loki_selector') and (s.get('ships_to') in (None, []) or 'loki' in (s.get('ships_to') or [])):
        parts.append('Loki selector `%s`' % s['loki_selector'])
    if s.get('azure_table'):
        parts.append('Azure Monitor table `%s`' % s['azure_table'])
    if shipper_links:
        parts.append('shipped by ' + ', '.join(shipper_links))
    return '; '.join(parts) or 'not found in the repo'


def export(data, out_dir, now=None):
    """Write the bundle. Returns (files_written, added, removed)."""
    now = now or datetime.datetime.now(datetime.timezone.utc).replace(microsecond=0)
    stamp = now.strftime('%Y-%m-%dT%H:%M:%SZ')
    svcs = data.get('services', {})
    shippers = data.get('shippers', [])
    clusters = {n: s for n, s in svcs.items() if s.get('kind') == 'cluster'}
    svcs = {n: s for n, s in svcs.items() if s.get('kind') != 'cluster'}
    sdir, ldir, cdir = (os.path.join(out_dir, d) for d in ('services', 'logging', 'clusters'))
    for d in (sdir, ldir, cdir):
        os.makedirs(d, exist_ok=True)

    before = {os.path.splitext(f)[0] for f in os.listdir(sdir)
              if f.endswith('.md') and f != 'index.md' and generated(os.path.join(sdir, f))}
    names = {slug(n): n for n in svcs}
    written = []

    def put(path, fields, body):
        fields = dict(fields, generator=GEN, timestamp=stamp)
        with open(path, 'w', encoding='utf-8') as fh:
            fh.write(frontmatter(fields) + '\n' + body.rstrip() + '\n')
        written.append(path)

    # log shippers
    ship_slug = {}
    for sh in shippers:
        k = slug(sh['kind'] + ('-' + '-'.join(sh['sinks']) if sh['sinks'] else ''))
        ship_slug[sh['kind']] = k
        users = sorted(n for n, s in svcs.items() if s.get('shipper') == sh['kind'] or
                       (isinstance(s.get('shipper'), list) and sh['kind'] in s['shipper']))
        body = ['# %s' % sh['kind'], '',
                '| Field | Value |', '| --- | --- |',
                '| Config | `%s` |' % sh['config'],
                '| Sends logs to | %s |' % (', '.join(sh['sinks']) or 'unknown'),
                '| Log group | %s |' % ('`%s`' % sh['log_group_hint'] if sh.get('log_group_hint') else '-'), '']
        if users:
            body += ['## Services it ships', ''] + ['- [%s](../services/%s.md)' % (u, slug(u)) for u in users]
        put(os.path.join(ldir, k + '.md'),
            {'type': 'Log Shipper', 'title': sh['kind'], 'description': 'Collects container logs and sends them to %s.' % (', '.join(sh['sinks']) or 'an unknown destination'),
             'tags': ['logging', sh['kind']] + sh['sinks']}, '\n'.join(body))

    # clusters
    for n, c in sorted(clusters.items()):
        on = sorted(x for x, s in svcs.items() if s.get('cluster') == n)
        body = ['# %s' % n, '', '| Field | Value |', '| --- | --- |',
                '| Cloud | %s |' % (c.get('cloud') or 'unknown'), '| Defined in | `%s:%s` |' % (c.get('iac_file', '?'), c.get('iac_line', '?')),
                '| Default log group | %s |' % ('`%s`' % c['log_group'] if c.get('log_group') else '-'), '']
        if on:
            body += ['## Workloads on it', ''] + ['- [%s](../services/%s.md)' % (x, slug(x)) for x in on]
        put(os.path.join(cdir, slug(n) + '.md'),
            {'type': 'Kubernetes Cluster', 'title': n, 'description': 'Managed Kubernetes cluster on %s.' % (c.get('cloud') or 'an unknown cloud'),
             'tags': [t for t in ('kubernetes', c.get('cloud'), 'cluster') if t]}, '\n'.join(body))

    # services
    for sl, n in sorted(names.items()):
        s = svcs[n]
        kinds = s.get('shipper') or []
        kinds = kinds if isinstance(kinds, list) else [kinds]
        links = ['[%s](../logging/%s.md)' % (k, ship_slug[k]) for k in kinds if k in ship_slug]
        where = '%s:%s' % (s.get('iac_file', '?'), s.get('iac_line', '?'))
        rows = [('Runtime', s.get('runtime') or 'unknown'), ('Cloud', s.get('cloud') or 'unknown'),
                ('Defined in', '`%s`' % where), ('Source', '`%s`' % s['source_path'] if s.get('source_path') else '-'),
                ('Cluster', '[%s](../clusters/%s.md)' % (s['cluster'], slug(s['cluster'])) if s.get('cluster') in clusters else s.get('cluster')),
                ('Namespace', s.get('namespace')), ('Workload', s.get('workload')),
                ('Logs', logs_line(s, links))]
        body = ['# %s' % n, '', '| Field | Value |', '| --- | --- |'] + \
               ['| %s | %s |' % (k, v) for k, v in rows if v] + \
               ['', '## Get its logs', '', '```bash', 'python3 skills/debug/scripts/log_fetch.py %s --since 1h' % n, '```']
        put(os.path.join(sdir, sl + '.md'),
            {'type': 'Service', 'title': n,
             'description': '%s service on %s.' % (s.get('runtime') or 'Unknown', s.get('cloud') or 'an unknown cloud'),
             'tags': [t for t in (s.get('runtime'), s.get('cloud'), 'service') if t],
             'runtime': s.get('runtime'), 'cloud': s.get('cloud'), 'iac': where}, '\n'.join(body))

    # prune generated docs for services that no longer exist (hand-written docs are never touched)
    removed = sorted(before - set(names))
    for sl in removed:
        os.remove(os.path.join(sdir, sl + '.md'))
    for d in (ldir, cdir):
        for f in os.listdir(d):
            p = os.path.join(d, f)
            if f.endswith('.md') and f != 'index.md' and p not in written and generated(p):
                os.remove(p)

    # indexes (progressive disclosure)
    def index_lines(d, label):
        out = []
        for f in sorted(os.listdir(d)):
            if f.endswith('.md') and f != 'index.md':
                meta, _ = read_meta(os.path.join(d, f))
                if meta and meta.get('type'):
                    out.append('- [%s](%s) - %s' % (meta.get('title') or f[:-3], f, meta.get('description') or meta['type']))
        return out or ['- none found']
    put(os.path.join(sdir, 'index.md'), {'type': 'Index', 'title': 'Services', 'description': 'Every service found in the repo IaC.'},
        '# Services\n\n' + '\n'.join(index_lines(sdir, 'services')))
    put(os.path.join(cdir, 'index.md'), {'type': 'Index', 'title': 'Clusters', 'description': 'Managed Kubernetes clusters in the repo IaC.'},
        '# Clusters\n\n' + '\n'.join(index_lines(cdir, 'clusters')))
    put(os.path.join(ldir, 'index.md'), {'type': 'Index', 'title': 'Logging', 'description': 'Log shippers and where they send logs.'},
        '# Logging\n\n' + '\n'.join(index_lines(ldir, 'logging')))
    root_name = os.path.basename(os.path.realpath(data.get('root', '.'))) or 'repo'
    put(os.path.join(out_dir, 'index.md'),
        {'type': 'Index', 'title': '%s system map' % root_name,
         'description': 'Services, runtimes and where their logs live, generated from the repo by overmind.'},
        '# %s system map\n\n- [Services](services/index.md) - %d service(s)\n- [Clusters](clusters/index.md) - %d cluster(s)\n- [Logging](logging/index.md) - %d log shipper(s)\n- [History](log.md)\n\n'
        'Generated by `python3 skills/debug/scripts/service_map.py . --okf`. Hand-written docs in this folder are kept; generated ones are rewritten.\n'
        % (root_name, len(names), len(clusters), len(shippers)))

    # log.md, newest first
    added = sorted(set(names) - before)
    lp = os.path.join(out_dir, 'log.md')
    _, old = read_meta(lp)
    entries = [l for l in old.splitlines() if l.startswith('- ')]
    note = '%d service(s)' % len(names)
    if added and before:
        note += ', added %s' % ', '.join(names[a] for a in added)
    if removed:
        note += ', removed %s' % ', '.join(removed)
    entries.insert(0, '- %s: exported %s' % (now.strftime('%Y-%m-%d'), note))
    put(lp, {'type': 'Log', 'title': 'History', 'description': 'Newest-first record of map exports.'},
        '# History\n\n' + '\n'.join(entries[:200]))
    return written, [names[a] for a in added], removed


def check(out_dir):
    """OKF conformance: every markdown doc has frontmatter with a non-empty type; every relative link resolves."""
    errors, docs = [], 0
    for d, _, files in os.walk(out_dir):
        for f in files:
            if not f.endswith('.md'):
                continue
            docs += 1
            p = os.path.join(d, f); rel = os.path.relpath(p, out_dir)
            meta, body = read_meta(p)
            if not meta or not str(meta.get('type', '')).strip():
                errors.append('%s: missing frontmatter with a non-empty type' % rel)
            for link in LINK.findall(open(p, encoding='utf-8').read()):
                if '://' in link:
                    continue
                target = os.path.join(out_dir, link.lstrip('/')) if link.startswith('/') else os.path.join(d, link)
                if not os.path.exists(os.path.normpath(target)):
                    errors.append('%s: link to %s does not resolve' % (rel, link))
    return docs, errors


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2 or argv[0] != 'check':
        print('usage: okf.py check DIR'); return 2
    docs, errors = check(argv[1])
    for e in errors:
        print('ERROR', e)
    print('okf: %d doc(s), %d error(s)%s' % (docs, len(errors), ', conformant' if not errors and docs else ''))
    return 1 if errors or not docs else 0


if __name__ == '__main__':
    sys.exit(main())
