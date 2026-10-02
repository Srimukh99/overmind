#!/usr/bin/env python3
"""ratchet: every iteration must improve the code without breaking what works
or drifting from the goal. Turns one way only.

  start   write the anchor (goal, scope, targets), measure the floor, checkpoint
  check   measure now vs the floor: ACCEPT raises the floor, REJECT/STALL do not
  revert  restore the last accepted checkpoint
  amend   widen scope or allow an API change, with a recorded reason
  status  iteration history

State lives in .overmind/ratchet/. Checkpoints are git objects under
refs/overmind/ratchet/ - your branch, index and history are never touched.
"""
import argparse, fnmatch, glob, hashlib, json, os, re, subprocess, sys, tempfile, time
import xml.etree.ElementTree as ET

HERE = os.path.dirname(os.path.abspath(__file__))
PROVE = os.path.join(os.path.dirname(os.path.dirname(HERE)), 'build', 'scripts')
STATE = os.path.join('.overmind', 'ratchet')
MANIFESTS = re.compile(r'(^|/)(package\.json|requirements[^/]*\.txt|pyproject\.toml|setup\.(py|cfg)|go\.mod|'
                       r'Cargo\.toml|pom\.xml|build\.gradle(\.kts)?|Gemfile|composer\.json)$')
TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|'
                       r'\.(test|spec)\.[jt]sx?$|Tests?\.(java|kt)$')
SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', '__pycache__', 'dist', 'build', '.overmind', 'vendor', 'target'}
MAX_STRIKES = 3
JUNK = [':(exclude,glob)**/__pycache__/**', ':(exclude,glob)**/*.pyc', ':(exclude,glob)**/.pytest_cache/**',
        ':(exclude,glob)**/node_modules/**', ':(exclude,glob)**/.DS_Store', ':(exclude,glob)**/coverage/**',
        ':(exclude,glob)**/*.egg-info/**', ':(exclude,glob).overmind/**']


# ------------------------------------------------------------------ helpers
def git(args, cwd, env=None, check=False, strip=True):
    base_cmd = ['git', '-c', 'user.name=overmind', '-c', 'user.email=overmind@local'] + args
    p = None
    try:
        p = subprocess.run(base_cmd, cwd=cwd, capture_output=True, text=True, env=env)
    except (FileNotFoundError, OSError):
        pass
    if p is None or (p.returncode != 0 and sys.platform == "darwin"):
        try:
            p2 = subprocess.run(['arch', '-arm64'] + base_cmd, cwd=cwd, capture_output=True, text=True, env=env)
            p = p2
        except Exception:
            pass
    if p is None:
        if check:
            raise RuntimeError('git %s: command not found' % ' '.join(args))
        return ''
    if check and p.returncode != 0:
        raise RuntimeError('git %s: %s' % (' '.join(args), p.stderr.strip()))
    if p.returncode != 0:
        return ''
    return p.stdout.strip() if strip else p.stdout


def git_bytes(args, cwd, env=None):
    base_cmd = ['git', '-c', 'user.name=overmind', '-c', 'user.email=overmind@local'] + args
    p = None
    try:
        p = subprocess.run(base_cmd, cwd=cwd, capture_output=True, env=env)
    except (FileNotFoundError, OSError):
        pass
    if p is None or (p.returncode != 0 and sys.platform == "darwin"):
        try:
            p2 = subprocess.run(['arch', '-arm64'] + base_cmd, cwd=cwd, capture_output=True, env=env)
            p = p2
        except Exception:
            pass
    return p.stdout if p and p.returncode == 0 else b''


def sh(cmd, cwd, timeout=900):
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout or '') + (p.stderr or '')
    except subprocess.TimeoutExpired:
        return 124, 'timed out'


def sdir(root):
    d = os.path.join(root, STATE); os.makedirs(d, exist_ok=True); return d


def load(root, name, default=None):
    try:
        with open(os.path.join(root, STATE, name), encoding='utf-8') as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save(root, name, data):
    with open(os.path.join(sdir(root), name), 'w', encoding='utf-8') as fh:
        json.dump(data, fh, indent=2, sort_keys=True)


def log(root, entry):
    with open(os.path.join(sdir(root), 'log.jsonl'), 'a', encoding='utf-8') as fh:
        fh.write(json.dumps(entry, sort_keys=True) + '\n')


def history(root):
    try:
        return [json.loads(l) for l in open(os.path.join(root, STATE, 'log.jsonl'), encoding='utf-8') if l.strip()]
    except OSError:
        return []


# ------------------------------------------------------------------ checkpoints
def checkpoint(root, n):
    """Snapshot the working tree (incl. untracked, minus ignored and .overmind) without touching the index."""
    fd, idx = tempfile.mkstemp(prefix='overmind-idx-'); os.close(fd); os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        head = git(['rev-parse', '--verify', '-q', 'HEAD'], root)
        if head:
            git(['read-tree', 'HEAD'], root, env)
        git(['add', '-A', '--', '.'] + JUNK, root, env, check=True)
        git(['rm', '-r', '-q', '--cached', '--ignore-unmatch', '.overmind'], root, env)
        tree = git(['write-tree'], root, env, check=True)
        commit = git(['commit-tree', tree, '-m', 'ratchet %d' % n] + (['-p', head] if head else []), root, check=True)
        # one namespace per working folder: worktrees share refs, so parallel ratchets must not collide
        space = hashlib.sha1(os.path.realpath(root).encode()).hexdigest()[:10]
        git(['update-ref', 'refs/overmind/ratchet/%s/%d' % (space, n), commit], root, check=True)
        return commit
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def tree_files(root, commit):
    return set(git(['ls-tree', '-r', '--name-only', commit], root).splitlines())


def current_files(root):
    out = git(['ls-files', '--cached', '--others', '--exclude-standard'], root).splitlines()
    junk = re.compile(r'(^|/)(__pycache__|\.pytest_cache|node_modules|coverage)/|\.pyc$|\.DS_Store$|\.egg-info/')
    return {f for f in out if not f.startswith('.overmind/') and not junk.search(f) and os.path.exists(os.path.join(root, f))}


# ------------------------------------------------------------------ test results
def detect_test_cmd(root):
    has = lambda *n: any(os.path.exists(os.path.join(root, x)) for x in n)
    junit = os.path.join(STATE, 'junit.xml')
    if has('package.json'):
        pkg = open(os.path.join(root, 'package.json'), encoding='utf-8').read()
        if 'vitest' in pkg:
            return 'npx vitest run --reporter=junit --outputFile=%s' % junit
        if 'jest' in pkg:
            return 'npx jest --ci --json --outputFile=%s' % os.path.join(STATE, 'jest.json')
        return 'npm test'
    if has('go.mod'):
        return 'go test -json ./...'
    if has('Cargo.toml'):
        return 'cargo test 2>&1'
    if has('pom.xml'):
        return 'mvn -q test'
    if has('build.gradle', 'build.gradle.kts'):
        return ('./gradlew' if has('gradlew') else 'gradle') + ' -q test'
    try:
        import pytest  # noqa: F401
        return '%s -m pytest -q -p no:cacheprovider --continue-on-collection-errors --junitxml=%s' % (sys.executable, junit)
    except ImportError:
        tdir = next((d for d in ('tests', 'test') if os.path.isdir(os.path.join(root, d))), None)
        cmd = '%s -m unittest discover -v' % sys.executable
        if tdir:
            cmd += ' -s %s' % tdir + (' -t .' if os.path.exists(os.path.join(root, tdir, '__init__.py')) else '')
        return cmd


def parse_junit(path):
    res = {}
    for f in ([path] if os.path.isfile(path) else glob.glob(os.path.join(path, '*.xml'))):
        try:
            tree = ET.parse(f)
        except (ET.ParseError, OSError):
            continue
        for tc in tree.iter('testcase'):
            cls, name = tc.get('classname', '') or tc.get('file', ''), tc.get('name', '')
            if tc.find('failure') is not None or tc.find('error') is not None:
                st = 'fail'
            elif tc.find('skipped') is not None:
                st = 'skip'
            else:
                st = 'pass'
            res['%s::%s' % (cls, name)] = st
    return res


def parse_output(out):
    res = {}
    for m in re.finditer(r'^(\w+) \(([\w.]+)\)\s*(?:\n.*?)?\.\.\. (ok|FAIL|ERROR|skipped|expected failure|unexpected success)', out, re.M):
        st = {'ok': 'pass', 'expected failure': 'pass'}.get(m.group(3), 'skip' if m.group(3) == 'skipped' else 'fail')
        cls = m.group(2).rsplit('.', 1)[0] if m.group(2).endswith('.' + m.group(1)) else m.group(2)
        res['%s::%s' % (cls, m.group(1))] = st
    for line in out.splitlines():                      # go test -json
        if line.startswith('{') and '"Test"' in line:
            try:
                e = json.loads(line)
            except ValueError:
                continue
            if e.get('Action') in ('pass', 'fail', 'skip') and e.get('Test'):
                res['%s::%s' % (e.get('Package', ''), e['Test'])] = e['Action']
    for m in re.finditer(r'^test (\S+) \.\.\. (ok|FAILED|ignored)', out, re.M):  # cargo
        res['rust::' + m.group(1)] = {'ok': 'pass', 'FAILED': 'fail'}.get(m.group(2), 'skip')
    return res


def run_tests(root, cmd):
    for f in ('junit.xml', 'jest.json'):
        p = os.path.join(root, STATE, f)
        if os.path.exists(p):
            os.unlink(p)
    sdir(root)
    rc, out = sh(cmd, root)
    res = parse_junit(os.path.join(root, STATE, 'junit.xml'))
    jp = os.path.join(root, STATE, 'jest.json')
    if os.path.exists(jp):
        for suite in json.load(open(jp)).get('testResults', []):
            for a in suite.get('assertionResults', []):
                res['%s::%s' % (os.path.relpath(suite['name'], root), a['fullName'])] = \
                    {'passed': 'pass', 'failed': 'fail'}.get(a['status'], 'skip')
    for d in ('target/surefire-reports', 'build/test-results/test'):
        if os.path.isdir(os.path.join(root, d)):
            res.update(parse_junit(os.path.join(root, d)))
    if not res:
        res = parse_output(out)
    return rc, res, out


def target_matches(target, test_id):
    """'tests/test_cart.py::test_x' matches junit 'tests.test_cart::test_x' and unittest 'test_cart.T::test_x'."""
    path, _, name = target.rpartition('::')
    stem = os.path.splitext(os.path.basename(path))[0] if path else ''
    tid_name = test_id.rpartition('::')[2]
    return (tid_name == name or tid_name.endswith('.' + name) or tid_name.split('[')[0] == name) and \
           (not stem or stem in test_id)


# ------------------------------------------------------------------ public API
PY_SKIP = re.compile(r'(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.py$|(^|/)(setup|conftest)\.py$')


def py_sig(fn):
    a = fn.args
    parts = [x.arg for x in a.posonlyargs + a.args]
    if a.vararg: parts.append('*' + a.vararg.arg)
    parts += ['%s=' % x.arg for x in a.kwonlyargs]
    if a.kwarg: parts.append('**' + a.kwarg.arg)
    return '(%s)/%d' % (', '.join(parts), len(a.defaults))


def api_surface(root, files):
    import ast
    api = {}
    for f in files:
        full = os.path.join(root, f)
        try:
            src = open(full, encoding='utf-8', errors='replace').read()
        except OSError:
            continue
        if f.endswith('.py') and not PY_SKIP.search(f):
            try:
                tree = ast.parse(src)
            except SyntaxError:
                api['%s::<syntax error>' % f] = 'broken'; continue
            for n in tree.body:
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and not n.name.startswith('_'):
                    api['%s::%s' % (f, n.name)] = py_sig(n)
                elif isinstance(n, ast.ClassDef) and not n.name.startswith('_'):
                    api['%s::%s' % (f, n.name)] = 'class'
                    for m in n.body:
                        if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and (not m.name.startswith('_') or m.name == '__init__'):
                            api['%s::%s.%s' % (f, n.name, m.name)] = py_sig(m)
        elif re.search(r'\.(ts|tsx|js|jsx|mjs)$', f) and not TEST_PATH.search(f):
            for m in re.finditer(r'export\s+(?:default\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)', src):
                api['%s::%s' % (f, m.group(1))] = '(%s)' % re.sub(r'\s+', ' ', m.group(2)).strip()
            for m in re.finditer(r'export\s+(?:default\s+)?(?:const|let|class|interface|type|enum)\s+(\w+)', src):
                api.setdefault('%s::%s' % (f, m.group(1)), 'export')
        elif f.endswith('.go') and not f.endswith('_test.go'):
            for m in re.finditer(r'^func\s+(\([^)]*\)\s*)?([A-Z]\w*)\s*\(([^)]*)\)', src, re.M):
                recv = re.sub(r'[\s()*]', '', (m.group(1) or '').split()[-1] if m.group(1) else '')
                api['%s::%s%s' % (f, recv + '.' if recv else '', m.group(2))] = '(%s)' % re.sub(r'\s+', ' ', m.group(3))
    return api


def source_files(root):
    out = []
    for d, ds, fs in os.walk(root):
        ds[:] = [x for x in ds if x not in SKIP_DIRS and not x.startswith('.')]
        for f in fs:
            if re.search(r'\.(py|ts|tsx|js|jsx|mjs|go)$', f):
                out.append(os.path.relpath(os.path.join(d, f), root))
    return out


# ------------------------------------------------------------------ measure
def fast_tier(root):
    rc, out = sh('%s %s fast --repo .' % (sys.executable, os.path.join(PROVE, 'loop.py')), root, 300)
    return rc in (0, 2)  # 2 = nothing to run


def mutation_score(root):
    rc, out = sh('%s %s mutate --repo .' % (sys.executable, os.path.join(PROVE, 'loop.py')), root, 1800)
    m = re.search(r'score (\d+)%', out)
    return int(m.group(1)) if m else None


def measure(root, anchor):
    rc, tests, out = run_tests(root, anchor['test_cmd'])
    m = {
        'tests': tests,
        'passing': sorted(t for t, s in tests.items() if s == 'pass'),
        'targets': {t: any(target_matches(t, k) and s == 'pass' for k, s in tests.items()) for t in anchor['targets']},
        'api': api_surface(root, source_files(root)),
        'fast_ok': fast_tier(root) if anchor.get('fast', True) else True,
        'mutation': mutation_score(root) if anchor.get('mutate') else None,
        'suite_rc': rc,
    }
    unseen = [t for t in anchor['targets'] if not any(target_matches(t, k) for k in tests)]
    if unseen and tests:
        files = sorted({t.rpartition('::')[0] or t for t in unseen})
        m['note'] = ('target(s) never ran - %s probably fails to import (a name that does not exist yet?). '
                     'Import new names inside each test so partial progress counts.' % ', '.join(files))
    if not tests:
        m['note'] = 'no per-test results parsed; set --test-cmd to one that emits JUnit XML'
        m['raw_tail'] = out.strip().splitlines()[-5:]
    return m


def changed_since(root, base):
    files = set(git(['diff', '--name-only', base], root).splitlines()) if base else set()
    files |= set(git(['ls-files', '--others', '--exclude-standard'], root).splitlines())
    return {f for f in files if f and not f.startswith('.overmind/')}


def in_scope(f, scope):
    return TEST_PATH.search(f) or any(fnmatch.fnmatch(f, g) or f.startswith(g.rstrip('*').rstrip('/') + '/') for g in scope)


def diff_vs(root, commit, args):
    """git diff of the current working tree (incl. untracked, minus .overmind) against a snapshot."""
    fd, idx = tempfile.mkstemp(prefix='overmind-idx-'); os.close(fd); os.unlink(idx)
    env = dict(os.environ, GIT_INDEX_FILE=idx)
    try:
        git(['read-tree', commit], root, env)
        git(['add', '-A', '--', '.'] + JUNK, root, env)
        git(['rm', '-r', '-q', '--cached', '--ignore-unmatch', '.overmind'], root, env)
        return git(['diff', '--cached', '--no-color'] + args + [commit], root, env, strip=False)
    finally:
        if os.path.exists(idx):
            os.unlink(idx)


def diff_size(root, commit):
    out = diff_vs(root, commit, ['--numstat'])
    n = 0
    for line in out.splitlines():
        a, b, _ = (line.split('\t') + ['', ''])[:3]
        n += (int(a) if a.isdigit() else 0) + (int(b) if b.isdigit() else 0)
    return n


# ------------------------------------------------------------------ verdict
def judge(root, anchor, floor, now):
    reasons, gains = [], []
    # 1. nothing that worked may break
    broke = [t for t in floor['passing'] if now['tests'].get(t) != 'pass']
    if broke:
        what = {t: now['tests'].get(t, 'missing') for t in broke}
        reasons.append(('regression', '%d test(s) that passed now %s: %s' % (
            len(broke), '/'.join(sorted(set(what.values()))), ', '.join(broke[:5]))))
    lost = [t for t, ok in floor['targets'].items() if ok and not now['targets'].get(t)]
    if lost:
        reasons.append(('regression', 'target(s) passed before, fail now: %s' % ', '.join(lost)))
    # 2. public API holds
    allow = set(anchor.get('allow_api', []))
    allowed = lambda k: any(k.endswith('::' + a) or k.endswith('.' + a) or k == a for a in allow)
    removed = [k for k in floor['api'] if k not in now['api'] and not allowed(k)]
    changed = [k for k in floor['api'] if k in now['api'] and now['api'][k] != floor['api'][k] and not allowed(k)]
    if removed:
        reasons.append(('api', 'public API removed: %s' % ', '.join(removed[:5])))
    if changed:
        reasons.append(('api', 'public API changed: %s' % ', '.join(
            '%s %s -> %s' % (k.split('::')[-1], floor['api'][k], now['api'][k]) for k in changed[:4])))
    # 3. no drift
    origin = anchor['origin']
    files = set(diff_vs(root, origin, ['--name-only']).split())
    if anchor['scope']:
        out = sorted(f for f in files if not in_scope(f, anchor['scope']))
        if out:
            reasons.append(('drift', 'outside scope %s: %s' % (anchor['scope'], ', '.join(out[:5]))))
    else:
        dep = sorted(f for f in files if MANIFESTS.search(f))
        if dep:
            reasons.append(('drift', 'dependency manifest changed with no scope set: %s' % ', '.join(dep)))
    # 4. no test cheating, and tests that existed at the start are frozen
    sys.path.insert(0, PROVE)
    import tamper as T
    parsed = T.parse(diff_vs(root, origin, ['--unified=0']))
    bad = [h for h in T.check(parsed, root) if h['level'] == 'FAIL']
    if bad:
        reasons.append(('tamper', '; '.join('%s %s' % (h['rule'], h['file']) for h in bad[:4])))
    at_start = tree_files(root, origin)
    unfrozen = set(anchor.get('unfrozen', []))
    edited = sorted(f for f, d in parsed.items()
                    if TEST_PATH.search(f) and f in at_start and d['rem'] and f not in unfrozen)
    if edited:
        reasons.append(('frozen-test', 'tests that existed at start were changed: %s (add new tests instead; '
                                       'changing these needs the user and ratchet.py amend --unfreeze)' % ', '.join(edited[:4])))
    # 5. checks that were clean stay clean
    if floor['fast_ok'] and not now['fast_ok']:
        reasons.append(('quality', 'typecheck/lint passed before, fails now (run loop.py fast)'))
    if floor.get('mutation') is not None and now.get('mutation') is not None and now['mutation'] < floor['mutation']:
        reasons.append(('quality', 'mutation score fell %d%% -> %d%%' % (floor['mutation'], now['mutation'])))
    # progress: something must get measurably better
    t_was, t_now = sum(floor['targets'].values()), sum(now['targets'].values())
    if t_now > t_was:
        gains.append('targets %d -> %d of %d' % (t_was, t_now, len(now['targets'])))
    p_was, p_now = len(floor['passing']), len(now['passing'])
    if p_now > p_was:
        gains.append('passing tests %d -> %d' % (p_was, p_now))
    if now['fast_ok'] and not floor['fast_ok']:
        gains.append('typecheck/lint now clean')
    if floor.get('mutation') is not None and (now.get('mutation') or 0) > floor['mutation']:
        gains.append('mutation score %d%% -> %d%%' % (floor['mutation'], now['mutation']))
    return reasons, gains


# ------------------------------------------------------------------ commands
def cmd_start(a, root):
    if not git(['rev-parse', '--git-dir'], root):
        print('ratchet needs a git repository (git init)'); return 2
    anchor = {
        'goal': a.goal, 'scope': a.scope or [], 'targets': a.target or [], 'allow_api': [],
        'test_cmd': a.test_cmd or detect_test_cmd(root), 'max_iter': a.max_iter,
        'fast': not a.no_fast, 'mutate': a.mutate, 'base': git(['rev-parse', '--verify', '-q', 'HEAD'], root) or None,
        'started': time.strftime('%Y-%m-%dT%H:%M:%S'), 'amendments': [],
    }
    for f in ('log.jsonl',):
        p = os.path.join(root, STATE, f)
        if os.path.exists(p):
            os.unlink(p)
    save(root, 'anchor.json', anchor)
    floor = measure(root, anchor)
    floor['checkpoint'] = checkpoint(root, 0)
    floor['iteration'] = 0
    anchor['origin'] = floor['checkpoint']
    save(root, 'anchor.json', anchor)
    save(root, 'floor.json', floor)
    log(root, {'iter': 0, 'verdict': 'START', 'passing': len(floor['passing']),
               'targets': sum(floor['targets'].values()), 'checkpoint': floor['checkpoint']})
    print('ratchet started')
    print('  goal:     %s' % anchor['goal'])
    print('  scope:    %s' % (', '.join(anchor['scope']) or 'not set (drift only checked on dependency manifests)'))
    print('  floor:    %d passing test(s), %d public API item(s), lint/typecheck %s%s' % (
        len(floor['passing']), len(floor['api']), 'clean' if floor['fast_ok'] else 'NOT clean',
        ', mutation %s%%' % floor['mutation'] if floor.get('mutation') is not None else ''))
    print('  targets:  %d of %d passing' % (sum(floor['targets'].values()), len(floor['targets'])))
    for t, ok in floor['targets'].items():
        print('            %s %s' % ('pass' if ok else 'FAIL', t))
    if floor.get('note'):
        print('  warning:  %s' % floor['note'])
    if not anchor['targets']:
        print('  warning:  no --target tests; progress can only come from new passing tests')
    return 0


def cmd_check(a, root):
    anchor, floor = load(root, 'anchor.json'), load(root, 'floor.json')
    if not anchor or not floor:
        print('no ratchet in progress; run: ratchet.py start --goal "..."'); return 2
    hist = history(root)
    it = max([h['iter'] for h in hist] + [0]) + 1
    now = measure(root, anchor)
    reasons, gains = judge(root, anchor, floor, now)
    size = diff_size(root, floor['checkpoint'])
    targets_done = now['targets'] and all(now['targets'].values())
    if reasons:
        verdict = 'REJECT'
    elif not gains:
        verdict = 'DONE' if targets_done else 'STALL'
    else:
        verdict = 'DONE' if targets_done else 'ACCEPT'
    strikes = 0
    for h in reversed(hist):
        if h['verdict'] == 'REVERT':
            continue
        if h['verdict'] in ('REJECT', 'STALL'):
            strikes += 1
        else:
            break
    if verdict in ('REJECT', 'STALL'):
        strikes += 1
    entry = {'iter': it, 'verdict': verdict, 'reasons': reasons, 'gains': gains, 'diff_lines': size,
             'passing': len(now['passing']), 'targets': sum(now['targets'].values())}
    if verdict in ('ACCEPT', 'DONE') and (gains or targets_done):
        now['checkpoint'] = checkpoint(root, it)
        now['iteration'] = it
        save(root, 'floor.json', now)
        entry['checkpoint'] = now['checkpoint']
    log(root, entry)
    # report: goal first, every time
    print('ratchet iter %d: %s' % (it, verdict))
    print('  goal:      %s' % anchor['goal'])
    for kind, msg in reasons:
        print('  %-10s %s' % (kind, msg))
    for g in gains:
        print('  gained     %s' % g)
    print('  targets:   %d of %d passing   tests: %d passing   change: %d lines since last checkpoint' % (
        sum(now['targets'].values()), len(now['targets']), len(now['passing']), size))
    if size > a.budget:
        print('  warning:   iteration is large (%d lines > %d); smaller steps are easier to keep' % (size, a.budget))
    if now.get('note'):
        print('  warning:   %s' % now['note'])
    pending = [t for t, ok in now['targets'].items() if not ok]
    if verdict == 'DONE':
        print('next: all targets pass. Run loop.py full and tamper.py, then second-look.')
    elif verdict == 'ACCEPT':
        print('next: checkpoint %d saved, floor raised. Smallest change toward: %s' % (it, pending[0] if pending else 'the goal'))
    elif strikes >= MAX_STRIKES:
        print('STOP: %d iterations in a row without progress. Revert, then report to the user what you tried and what blocks you.' % strikes)
    elif verdict == 'REJECT':
        print('next: ratchet.py revert, then a different approach (strike %d of %d). Never fix a regression by editing its test.' % (strikes, MAX_STRIKES))
    else:
        print('next: nothing measurably improved (strike %d of %d). Revert or make a change that moves a target.' % (strikes, MAX_STRIKES))
    if it >= anchor.get('max_iter', 8) and verdict != 'DONE':
        print('LIMIT: %d iterations reached. Report progress to the user before continuing.' % it)
    return 0 if verdict in ('ACCEPT', 'DONE') else 1


def cmd_revert(a, root):
    floor = load(root, 'floor.json')
    if not floor:
        print('no ratchet in progress'); return 2
    commit = floor['checkpoint']
    keep = tree_files(root, commit)
    git(['restore', '--source=%s' % commit, '--worktree', '--', '.'], root)
    for f in keep:                                   # restore files git restore skips (untracked at checkpoint)
        data = git_bytes(['show', '%s:%s' % (commit, f)], root)
        p = os.path.join(root, f)
        try:
            if not os.path.exists(p) or open(p, 'rb').read() != data:
                os.makedirs(os.path.dirname(p) or '.', exist_ok=True)
                open(p, 'wb').write(data)
        except OSError:
            pass
    extra = sorted(current_files(root) - keep)
    for f in extra:
        if a.clean:
            os.unlink(os.path.join(root, f))
    log(root, {'iter': max([h['iter'] for h in history(root)] + [0]), 'verdict': 'REVERT', 'to': floor['iteration']})
    print('reverted to checkpoint %d' % floor['iteration'])
    if extra:
        print('%s files created since then: %s' % ('removed' if a.clean else 'left in place (use --clean to remove)',
                                                   ', '.join(extra[:10])))
    return 0


def cmd_amend(a, root):
    anchor = load(root, 'anchor.json')
    if not anchor:
        print('no ratchet in progress'); return 2
    if not a.reason:
        print('amend needs --reason, and the user should have approved it'); return 2
    for g in a.scope or []:
        anchor['scope'].append(g)
    for n in a.allow_api or []:
        anchor['allow_api'].append(n)
    for t in a.target or []:
        anchor['targets'].append(t)
    anchor.setdefault('unfrozen', []).extend(a.unfreeze or [])
    anchor['amendments'].append({'scope': a.scope, 'allow_api': a.allow_api, 'target': a.target, 'unfreeze': a.unfreeze,
                                 'reason': a.reason, 'at': time.strftime('%Y-%m-%dT%H:%M:%S')})
    save(root, 'anchor.json', anchor)
    if a.target:
        floor = load(root, 'floor.json')
        for t in a.target:
            floor['targets'][t] = any(target_matches(t, k) and s == 'pass' for k, s in floor['tests'].items())
        save(root, 'floor.json', floor)
    print('amended: %s' % a.reason)
    return 0


def cmd_status(a, root):
    anchor, hist = load(root, 'anchor.json'), history(root)
    if not anchor:
        print('no ratchet in progress'); return 2
    print('goal: %s' % anchor['goal'])
    for h in hist:
        why = '; '.join('%s' % r[0] for r in h.get('reasons', [])) or ', '.join(h.get('gains', []))
        print('  %3s  %-7s targets %-3s tests %-4s %s' % (h['iter'], h['verdict'], h.get('targets', ''),
                                                        h.get('passing', ''), why[:70]))
    for m in anchor.get('amendments', []):
        print('  amended: %s' % m['reason'])
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog='ratchet')
    ap.add_argument('--repo', default='.')
    sub = ap.add_subparsers(dest='cmd', required=True)
    s = sub.add_parser('start'); s.add_argument('--goal', required=True)
    s.add_argument('--scope', action='append', help='glob of paths this task may change (repeatable)')
    s.add_argument('--target', action='append', help='acceptance test id, e.g. tests/test_x.py::test_y (repeatable)')
    s.add_argument('--test-cmd'); s.add_argument('--max-iter', type=int, default=8)
    s.add_argument('--mutate', action='store_true', help='also ratchet the mutation score (slower)')
    s.add_argument('--no-fast', action='store_true', help='skip typecheck/lint')
    c = sub.add_parser('check'); c.add_argument('--budget', type=int, default=400)
    r = sub.add_parser('revert'); r.add_argument('--clean', action='store_true')
    m = sub.add_parser('amend'); m.add_argument('--scope', action='append'); m.add_argument('--allow-api', action='append')
    m.add_argument('--target', action='append'); m.add_argument('--unfreeze', action='append')
    m.add_argument('--reason')
    sub.add_parser('status')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.repo)
    return {'start': cmd_start, 'check': cmd_check, 'revert': cmd_revert, 'amend': cmd_amend, 'status': cmd_status}[a.cmd](a, root)


if __name__ == '__main__':
    sys.exit(main())
