#!/usr/bin/env python3
"""team: contract-first delegation with isolated, verified workers.

  init       the goal and the contract (paths every worker builds against and none may change)
  add        a worker: the paths it owns, the tests it must make pass, a one-line task
  drop       remove a worker (and its worktree)
  check      validate the plan: disjoint ownership, contract untouched, every target assigned once
  brief      print one worker's structured brief - send exactly this to the subagent
  spawn      one git worktree and one ratchet per worker, all from the same snapshot
  verify     run each worker's ratchet and compare the worker's claim with the verdict
  integrate  merge verified workers (one wave), run the whole suite once; --apply lands it
  status     plan and last verdicts
  clean      remove worktrees and branches

Workers never share a file, cannot edit the contract, and are judged by checks, not by
what they say. Worktrees live next to the repo in REPO.rubric-team/.
"""
import argparse, fnmatch, json, os, re, shutil, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
RATCHET_DIR = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'ratchet', 'scripts')
RATCHET = os.path.join(RATCHET_DIR, 'ratchet.py')
sys.path.insert(0, RATCHET_DIR)
import ratchet as R  # noqa: E402

STATE = os.path.join('.rubric', 'team')
WILD = re.compile(r'[*?\[]')
TESTDEF = re.compile(r'^\s*(?:async\s+)?def (test_\w+)|^\s*func (Test\w+)\(|^\s*(?:it|test)\(\s*[\'"]([^\'"]+)', re.M)


# ------------------------------------------------------------------ state
def plan_path(root):
    return os.path.join(root, STATE, 'plan.json')


def load(root):
    try:
        with open(plan_path(root), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def save(root, plan):
    os.makedirs(os.path.dirname(plan_path(root)), exist_ok=True)
    with open(plan_path(root), 'w', encoding='utf-8') as fh:
        json.dump(plan, fh, indent=2, sort_keys=True)


def need(root):
    plan = load(root)
    if not plan:
        print('no team plan; start with: team.py init --goal "..." --contract PATH'); sys.exit(2)
    return plan


def team_dir(root):
    root = os.path.realpath(root)
    return os.path.join(os.path.dirname(root), os.path.basename(root) + '.rubric-team')


# ------------------------------------------------------------------ ownership
def literal_prefix(g):
    m = WILD.search(g)
    return g if not m else g[:m.start()]


def matches(path, g):
    return fnmatch.fnmatch(path, g) or path.startswith(g.rstrip('*').rstrip('/') + '/')


def overlap(a, b, files=()):
    """Conservative: True if any path could belong to both globs."""
    if a == b:
        return True
    wa, wb = bool(WILD.search(a)), bool(WILD.search(b))
    if not wa and matches(a, b) or not wb and matches(b, a):
        return True
    if wa and wb:
        pa, pb = literal_prefix(a), literal_prefix(b)
        if pa.startswith(pb) or pb.startswith(pa):
            return True
    return any(matches(f, a) and matches(f, b) for f in files)


def contract_globs(plan):
    out = []
    for c in plan['contract']:
        out += [c, c.rstrip('/') + '/**'] if not WILD.search(c) and not os.path.splitext(c)[1] else [c]
    return out


def repo_files(root):
    return [f for f in R.git(['ls-files', '--cached', '--others', '--exclude-standard'], root).splitlines()
            if not f.startswith('.rubric/')]


def contract_tests(root, plan):
    ids = []
    for f in repo_files(root):
        if any(matches(f, g) for g in contract_globs(plan)) and R.TEST_PATH.search(f):
            try:
                text = open(os.path.join(root, f), encoding='utf-8', errors='replace').read()
            except OSError:
                continue
            ids += ['%s::%s' % (f, next(x for x in m.groups() if x)) for m in TESTDEF.finditer(text)]
    return ids


def validate(root, plan):
    errors, warns = [], []
    files = repo_files(root)
    names = sorted(plan['workers'])
    if not plan['contract']:
        warns.append('no contract paths; workers have nothing frozen to build against')
    for c in plan['contract']:
        if not os.path.exists(os.path.join(root, c)) and not any(matches(f, c) for f in files):
            errors.append('contract path %s does not exist' % c)
    for i, a in enumerate(names):
        wa = plan['workers'][a]
        if not wa['owns']:
            errors.append('%s owns nothing' % a)
        for g in wa['owns']:
            for c in contract_globs(plan):
                if overlap(g, c, files):
                    errors.append('%s owns %s, which overlaps the contract (%s)' % (a, g, c))
            for b in names[i + 1:]:
                for h in plan['workers'][b]['owns']:
                    if overlap(g, h, files):
                        errors.append('%s (%s) and %s (%s) could both edit the same file' % (a, g, b, h))
    seen = {}
    for n in names:
        for t in plan['workers'][n]['targets']:
            if t in seen:
                errors.append('target %s is assigned to both %s and %s' % (t, seen[t], n))
            seen[t] = n
            path, _, name = t.rpartition('::')
            full = os.path.join(root, path)
            if not os.path.exists(full):
                errors.append('%s: target file %s does not exist' % (n, path))
            elif name.split('[')[0] not in open(full, encoding='utf-8', errors='replace').read():
                errors.append('%s: %s is not in %s' % (n, name, path))
        if not plan['workers'][n]['targets']:
            warns.append('%s has no target tests, so it can never be verified as done' % n)
    unassigned = [t for t in contract_tests(root, plan) if t not in seen]
    if unassigned:
        warns.append('contract tests nobody owns: %s' % ', '.join(unassigned[:6]))
    return errors, warns


# ------------------------------------------------------------------ git helpers
def snapshot(root):
    """Commit the working tree (incl. untracked, minus .rubric and junk) without touching branch or index."""
    fd, idx = tempfile.mkstemp(prefix='rubric-team-'); os.close(fd); os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        head = R.git(['rev-parse', '--verify', '-q', 'HEAD'], root)
        if head:
            R.git(['read-tree', 'HEAD'], root, env)
        R.git(['add', '-A', '--', '.'] + R.JUNK, root, env, check=True)
        tree = R.git(['write-tree'], root, env, check=True)
        commit = R.git(['commit-tree', tree, '-m', 'rubric team base'] + (['-p', head] if head else []), root, check=True)
        R.git(['update-ref', 'refs/rubric/team/base-%s' % commit[:12], commit], root, check=True)
        return commit
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def remove_worktree(root, path, branch=None):
    if os.path.isdir(path):
        R.git(['worktree', 'remove', '--force', path], root)
        shutil.rmtree(path, ignore_errors=True)
    R.git(['worktree', 'prune'], root)
    if branch:
        R.git(['branch', '-D', branch], root)


def run_ratchet(wt, *args, timeout=1800):
    p = subprocess.run([sys.executable, RATCHET, '--repo', wt] + list(args), capture_output=True, text=True, timeout=timeout)
    return p.returncode, p.stdout + p.stderr


# ------------------------------------------------------------------ commands
def cmd_init(a, root):
    if not R.git(['rev-parse', '--git-dir'], root):
        print('team needs a git repository'); return 2
    if load(root) and not a.force:
        print('a team plan exists; use --force to replace it, or team.py clean --all first'); return 2
    plan = {'goal': a.goal, 'contract': a.contract or [], 'workers': {}, 'bases': {}, 'created': time.strftime('%Y-%m-%dT%H:%M:%S')}
    save(root, plan)
    print('team plan started: %s' % a.goal)
    print('contract (frozen for every worker): %s' % (', '.join(plan['contract']) or 'none yet'))
    print('next: team.py add NAME --owns PATH --target TEST_ID --task "..."')
    return 0


def cmd_add(a, root):
    plan = need(root)
    w = plan['workers'].get(a.name, {})
    if w.get('worktree') and not a.force:
        print('%s is already spawned; use --force to change it' % a.name); return 2
    plan['workers'][a.name] = {'owns': a.owns or [], 'targets': a.target or [], 'task': a.task or '',
                               'wave': a.wave, 'worktree': None, 'branch': None, 'base': None,
                               'verdict': None, 'claim': None, 'integrated': False, 'reasons': []}
    save(root, plan)
    errors, warns = validate(root, plan)
    mine = [e for e in errors if a.name in e]
    for e in mine:
        print('ERROR', e)
    print('added %s: owns %s, %d target(s)' % (a.name, ', '.join(plan['workers'][a.name]['owns']), len(plan['workers'][a.name]['targets'])))
    return 1 if mine else 0


def cmd_drop(a, root):
    plan = need(root)
    w = plan['workers'].get(a.name)
    if not w:
        print('no worker %s' % a.name); return 2
    if w.get('worktree'):
        remove_worktree(root, w['worktree'], w.get('branch'))
    del plan['workers'][a.name]; save(root, plan)
    print('dropped %s' % a.name); return 0


def cmd_check(a, root):
    plan = need(root)
    errors, warns = validate(root, plan)
    for e in errors:
        print('ERROR', e)
    for w in warns:
        print('WARN ', w)
    print('plan: %d worker(s), %d error(s), %d warning(s)' % (len(plan['workers']), len(errors), len(warns)))
    return 1 if errors else 0


def brief_text(root, plan, name):
    w = plan['workers'][name]
    wt = w.get('worktree') or os.path.join(team_dir(root), name)
    rcmd = 'python3 %s --repo %s' % (RATCHET, wt)
    lines = [
        'TEAM BRIEF - worker %s' % name,
        'Goal: %s' % plan['goal'],
        'Your task: %s' % (w['task'] or 'make your target tests pass'),
        'Work only inside: %s' % wt,
        'You own, and may change, only: %s' % ', '.join(w['owns']),
        'You may add new test files. Do not edit existing tests.',
        'Contract, read-only: %s' % (', '.join(plan['contract']) or 'none'),
        'Done when these pass: %s' % ', '.join(w['targets']),
        'Loop: one small change, then `%s check`. ACCEPT: continue. REJECT: `%s revert`, try another way. '
        'Stop after 3 non-accepts or at DONE.' % (rcmd, rcmd),
        'Return: write %s/.rubric/result.json as {"status": "done" or "blocked", "summary": "one line", '
        '"evidence": "your last ratchet check line"}. Reply in 5 lines or fewer.' % wt,
    ]
    return '\n'.join(lines)


def cmd_brief(a, root):
    plan = need(root)
    if a.name not in plan['workers']:
        print('no worker %s' % a.name); return 2
    print(brief_text(root, plan, a.name))
    return 0


def cmd_spawn(a, root):
    plan = need(root)
    errors, warns = validate(root, plan)
    if errors:
        for e in errors:
            print('ERROR', e)
        print('fix the plan before spawning (team.py check)'); return 1
    names = a.names or [n for n, w in sorted(plan['workers'].items()) if not w.get('worktree') and not w.get('integrated')]
    if not names:
        print('nothing to spawn'); return 0
    base = snapshot(root)
    tdir = team_dir(root); os.makedirs(tdir, exist_ok=True)
    for n in names:
        w = plan['workers'][n]
        wt = os.path.join(tdir, n); branch = 'team/' + n
        if w.get('worktree') or os.path.exists(wt):
            if not a.fresh:
                print('%s already has a worktree; use --fresh to start it over' % n); continue
            remove_worktree(root, wt, branch)
        R.git(['worktree', 'add', '-B', branch, wt, base], root, check=True)
        args = ['start', '--goal', '%s | worker %s: %s' % (plan['goal'], n, w['task'] or 'make the targets pass')]
        for g in w['owns']:
            args += ['--scope', g]
        for t in w['targets']:
            args += ['--target', t]
        if a.no_fast:
            args.append('--no-fast')
        rc, out = run_ratchet(wt, *args)
        if rc != 0:
            print('%s: ratchet failed to start\n%s' % (n, out)); return 1
        if base not in plan['bases']:
            floor = json.load(open(os.path.join(wt, '.rubric', 'ratchet', 'floor.json')))
            plan['bases'][base] = floor['passing']
        w.update({'worktree': wt, 'branch': branch, 'base': base, 'verdict': None, 'claim': None, 'reasons': []})
        tline = next((l.strip() for l in out.splitlines() if l.strip().startswith('targets:')), '')
        print('spawned %-12s %s  (%s)' % (n, wt, tline))
    save(root, plan)
    print('next: send each worker its brief (team.py brief NAME), then team.py verify')
    return 0


def read_claim(wt):
    try:
        with open(os.path.join(wt, '.rubric', 'result.json'), encoding='utf-8') as fh:
            return (json.load(fh).get('status') or 'none').lower()
    except (OSError, ValueError, AttributeError):
        return 'none'


def cmd_verify(a, root):
    plan = need(root)
    names = a.names or [n for n, w in sorted(plan['workers'].items()) if w.get('worktree') and not w.get('integrated')]
    if not names:
        print('no spawned workers to verify'); return 0
    print('%-12s %-8s %-8s %s' % ('worker', 'claims', 'verdict', 'why'))
    ready = 0
    for n in names:
        w = plan['workers'][n]
        rc, out = run_ratchet(w['worktree'], 'check')
        m = re.search(r'ratchet iter \d+: (\w+)', out)
        verdict = m.group(1) if m else 'ERROR'
        reasons = [l.strip() for l in out.splitlines()
                   if re.match(r'\s+(regression|api|drift|tamper|frozen-test|quality)\s', l)]
        changed = R.diff_vs(w['worktree'], w['base'], ['--name-only']).split()
        outside = [f for f in changed if not R.TEST_PATH.search(f) and not any(matches(f, g) for g in w['owns'])]
        if outside and not any(r.startswith('drift') for r in reasons):
            reasons.append('drift      changed files it does not own: %s' % ', '.join(outside[:4]))
            verdict = 'REJECT'
        claim = read_claim(w['worktree'])
        why = '; '.join(r.split(None, 1)[0] + ': ' + r.split(None, 1)[1][:70] for r in reasons) if reasons else \
              next((l.strip() for l in out.splitlines() if l.strip().startswith('targets:')), '')[:80]
        if claim == 'done' and verdict != 'DONE':
            why = 'FALSE CLAIM, says done. ' + why
        w.update({'verdict': verdict, 'claim': claim, 'reasons': reasons, 'changed': changed})
        ready += verdict == 'DONE'
        print('%-12s %-8s %-8s %s' % (n, claim, verdict, why))
    save(root, plan)
    rework = [n for n in names if plan['workers'][n]['verdict'] != 'DONE']
    print('%d ready to integrate, %d need rework' % (ready, len(rework)))
    if rework:
        print('rework: send the reason back to the worker (it continues in its worktree), or team.py spawn NAME --fresh')
    return 0 if not rework else 1


def git_apply(patch, cwd):
    base_cmd = ['git', 'apply', '--whitespace=nowarn', '-']
    p = None
    try:
        p = subprocess.run(base_cmd, cwd=cwd, input=patch, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        pass
    if p is None or (p.returncode != 0 and sys.platform == "darwin"):
        try:
            p2 = subprocess.run(['arch', '-arm64'] + base_cmd, cwd=cwd, input=patch, capture_output=True, text=True)
            p = p2
        except Exception:
            pass
    return p or subprocess.CompletedProcess(base_cmd, 1, stdout='', stderr='git apply failed')


def cmd_integrate(a, root):
    plan = need(root)
    names = a.names or [n for n, w in sorted(plan['workers'].items()) if w.get('verdict') == 'DONE' and not w.get('integrated')]
    names = [n for n in names if plan['workers'][n].get('verdict') == 'DONE' and not plan['workers'][n].get('integrated')]
    if not names:
        print('no verified workers to integrate (run team.py verify)'); return 1
    bases = {plan['workers'][n]['base'] for n in names}
    if len(bases) > 1:
        print('these workers started from different snapshots; integrate one wave at a time'); return 1
    base = bases.pop()
    patches, touched = {}, {}
    for n in names:
        wt = plan['workers'][n]['worktree']
        patches[n] = R.diff_vs(wt, base, ['--binary'])
        for f in R.diff_vs(wt, base, ['--name-only']).split():
            touched.setdefault(f, []).append(n)
    clash = {f: ws for f, ws in touched.items() if len(ws) > 1}
    if clash:
        for f, ws in sorted(clash.items()):
            print('CONFLICT %s changed by %s' % (f, ', '.join(ws)))
        print('ownership was breached; fix the plan and re-run'); return 1
    iwt = os.path.join(team_dir(root), '_integration')
    remove_worktree(root, iwt)
    R.git(['worktree', 'add', '--detach', iwt, base], root, check=True)
    try:
        for n in names:
            if not patches[n].strip():
                continue
            p = git_apply(patches[n], cwd=iwt)
            if p.returncode != 0:
                print('could not apply %s: %s' % (n, p.stderr.strip().splitlines()[-1:])); return 1
        cmd = R.detect_test_cmd(iwt)
        rc, results, out = R.run_tests(iwt, cmd)
        floor = plan['bases'].get(base, [])
        broke = [t for t in floor if results.get(t) != 'pass']
        targets = [t for n in names for t in plan['workers'][n]['targets']]
        missing = [t for t in targets if not any(R.target_matches(t, k) and s == 'pass' for k, s in results.items())]
        ok = not broke and not missing and bool(results)
        print('integration of %s: %d file(s), %d test(s) run' % (', '.join(names), len(touched), len(results)))
        print('  targets:     %d of %d passing' % (len(targets) - len(missing), len(targets)))
        print('  regressions: %s' % (', '.join(broke[:5]) if broke else 'none'))
        if missing:
            print('  failing:     %s' % ', '.join(missing[:5]))
        if not results:
            print('  no per-test results parsed; check the test command')
        if not ok:
            print('NOT READY: fix before landing'); return 1
        if not a.apply:
            print('READY: run team.py integrate --apply to land it in your working tree'); return 0
        combined = ''.join(patches[n] for n in names)
        p = git_apply(combined, cwd=root)
        if p.returncode != 0:
            print('could not land: your working tree changed in the same files since spawn (%s)' % p.stderr.strip().splitlines()[-1:])
            return 1
        for n in names:
            plan['workers'][n]['integrated'] = True
        save(root, plan)
        print('LANDED in %s. Next wave: team.py add ..., team.py spawn' % root)
        return 0
    finally:
        remove_worktree(root, iwt)


def cmd_status(a, root):
    plan = need(root)
    print('goal: %s' % plan['goal'])
    print('contract: %s' % (', '.join(plan['contract']) or 'none'))
    print('%-12s %-26s %-8s %-8s %-6s %s' % ('worker', 'owns', 'claims', 'verdict', 'landed', 'targets'))
    for n, w in sorted(plan['workers'].items()):
        print('%-12s %-26s %-8s %-8s %-6s %d' % (n, ', '.join(w['owns'])[:26], w.get('claim') or '-', w.get('verdict') or '-',
                                                'yes' if w.get('integrated') else 'no', len(w['targets'])))
    return 0


def cmd_clean(a, root):
    plan = load(root) or {'workers': {}}
    tdir = team_dir(root)
    for n, w in plan['workers'].items():
        remove_worktree(root, w.get('worktree') or os.path.join(tdir, n), w.get('branch') or 'team/' + n)
        w.update({'worktree': None, 'branch': None})
    remove_worktree(root, os.path.join(tdir, '_integration'))
    for ref in R.git(['for-each-ref', '--format=%(refname)', 'refs/rubric/team'], root).splitlines():
        R.git(['update-ref', '-d', ref], root)
    if os.path.isdir(tdir) and not os.listdir(tdir):
        os.rmdir(tdir)
    if a.all:
        shutil.rmtree(os.path.join(root, STATE), ignore_errors=True)
        print('removed worktrees, branches and the plan')
    else:
        save(root, plan) if plan.get('goal') else None
        print('removed worktrees and branches (plan kept; --all removes it)')
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='team')
    ap.add_argument('--repo', default='.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('init'); s.add_argument('--goal', required=True); s.add_argument('--contract', action='append')
    s.add_argument('--force', action='store_true')
    s = sub.add_parser('add'); s.add_argument('name'); s.add_argument('--owns', action='append'); s.add_argument('--target', action='append')
    s.add_argument('--task'); s.add_argument('--wave', type=int, default=1); s.add_argument('--force', action='store_true')
    s = sub.add_parser('drop'); s.add_argument('name')
    sub.add_parser('check')
    s = sub.add_parser('brief'); s.add_argument('name')
    s = sub.add_parser('spawn'); s.add_argument('names', nargs='*'); s.add_argument('--fresh', action='store_true')
    s.add_argument('--no-fast', action='store_true', help='skip typecheck/lint in each ratchet')
    s = sub.add_parser('verify'); s.add_argument('names', nargs='*')
    s = sub.add_parser('integrate'); s.add_argument('names', nargs='*'); s.add_argument('--apply', action='store_true')
    sub.add_parser('status')
    s = sub.add_parser('clean'); s.add_argument('--all', action='store_true')
    a = ap.parse_args(argv)
    root = os.path.realpath(a.repo)
    fn = {'init': cmd_init, 'add': cmd_add, 'drop': cmd_drop, 'check': cmd_check, 'brief': cmd_brief, 'spawn': cmd_spawn,
          'verify': cmd_verify, 'integrate': cmd_integrate, 'status': cmd_status, 'clean': cmd_clean}[a.cmd]
    return fn(a, root)


if __name__ == '__main__':
    sys.exit(main())
