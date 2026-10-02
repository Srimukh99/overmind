#!/usr/bin/env python3
"""loop: run checks in tiers and print a short summary, not raw output.

  fast     typecheck + lint             (every edit)
  focused  tests related to changes     (when green)
  full     whole suite                  (before done)

Stack is detected from the repo. Override with .overmind/loop.json.
"""
import argparse, json, os, re, shutil, subprocess, sys, time

KEY = re.compile(r'error|fail|assert|exception|traceback|panic|expected|received|'
                 r'\.(py|ts|tsx|js|jsx|go|rs|java|kt):\d+', re.I)
NOISE = re.compile(r'^\s*(at |File "/usr|node_modules|site-packages|\s*$)')


# A leftover breakpoint() would drop the child into pdb and hold the run until
# the timeout expires. Neutralise it so the suite reports; vibe-check still
# FAILs the leftover at the gate.
NO_BREAK = {'PYTHONBREAKPOINT': '0'}


def sh(cmd, cwd, timeout):
    t = time.time()
    try:
        p = subprocess.run(cmd, cwd=cwd, shell=True, capture_output=True, text=True, timeout=timeout,
                           env={**os.environ, **NO_BREAK})
        return p.returncode, (p.stdout or '') + (p.stderr or ''), time.time() - t
    except subprocess.TimeoutExpired:
        return 124, 'timed out after %ds' % timeout, time.time() - t


def git(args, cwd):
    p = None
    try:
        p = subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True, timeout=20)
    except Exception:
        pass
    if p is None or (p.returncode != 0 and sys.platform == "darwin"):
        try:
            p2 = subprocess.run(['arch', '-arm64', 'git'] + args, cwd=cwd, capture_output=True, text=True, timeout=20)
            if p is None or p2.returncode == 0:
                return p2.stdout if p2.returncode == 0 else ''
        except Exception:
            pass
    if p is None:
        return ''
    return p.stdout if p.returncode == 0 else ''


def changed_files(root):
    out = git(['diff', '--name-only', 'HEAD'], root) + git(['ls-files', '--others', '--exclude-standard'], root)
    junk = re.compile(r'__pycache__|\.pyc$|(^|/)(node_modules|\.overmind|target|dist|build)/')
    return sorted({f for f in out.split() if os.path.exists(os.path.join(root, f)) and not junk.search(f)})


def has(root, *names):
    return any(os.path.exists(os.path.join(root, n)) for n in names)


def read(root, name):
    try:
        return open(os.path.join(root, name), encoding='utf-8').read()
    except OSError:
        return ''


def q(files):
    return ' '.join("'%s'" % f.replace("'", "'\\''") for f in files)


def python_plan(root, changed):
    py = [f for f in changed if f.endswith('.py')]
    cfg = read(root, 'pyproject.toml') + read(root, 'setup.cfg')
    fast = []
    if shutil.which('ruff'):
        fast.append('ruff check %s' % (q(py) if py else '.'))
    if shutil.which('mypy') and (has(root, 'mypy.ini', '.mypy.ini') or '[tool.mypy]' in cfg or '[mypy]' in cfg):
        fast.append('mypy %s' % (q(py) if py else '.'))
    elif shutil.which('pyright') and (has(root, 'pyrightconfig.json') or '[tool.pyright]' in cfg):
        fast.append('pyright %s' % q(py))
    if not fast:
        fast.append('%s -m compileall -q %s' % (sys.executable, q(py) if py else '.'))
    pytest = shutil.which('pytest') is not None
    runner = 'pytest -q' if pytest else '%s -m unittest -q' % sys.executable
    tests = set()
    for f in py:
        base = os.path.basename(f)
        if base.startswith('test_') or base.endswith('_test.py'):
            tests.add(f)
            continue
        stem = base[:-3]
        for d, ds, fs in os.walk(root):
            ds[:] = [x for x in ds if x not in ('.git', 'node_modules', '.venv', 'venv')]
            for t in fs:
                if t in ('test_%s.py' % stem, '%s_test.py' % stem):
                    tests.add(os.path.relpath(os.path.join(d, t), root))
    if tests and pytest:
        focused = ['pytest -q %s' % q(sorted(tests))]
    elif tests:
        mods = [t[:-3].replace(os.sep, '.') for t in sorted(tests)]
        focused = ['%s -m unittest -q %s' % (sys.executable, ' '.join(mods))]
    else:
        focused = []
    tdir = next((d for d in ('tests', 'test') if os.path.isdir(os.path.join(root, d))), None)
    disc = '%s -m unittest discover -q' % sys.executable
    if tdir:
        pkg = os.path.exists(os.path.join(root, tdir, '__init__.py'))
        disc += ' -s %s' % tdir + (' -t .' if pkg else '')
    full = [runner if pytest else disc]
    return fast, focused, full


def node_plan(root, changed):
    try:
        pkg = json.loads(read(root, 'package.json') or '{}')
    except ValueError:
        pkg = {}
    scripts = pkg.get('scripts', {})
    deps = dict(pkg.get('dependencies', {}), **pkg.get('devDependencies', {}))
    pm = 'pnpm' if has(root, 'pnpm-lock.yaml') else 'yarn' if has(root, 'yarn.lock') else 'npm'
    run = (pm + ' run') if pm == 'npm' else pm
    src = [f for f in changed if re.search(r'\.(ts|tsx|js|jsx|mjs|cjs|vue|svelte)$', f)]
    fast = []
    if 'typecheck' in scripts:
        fast.append('%s typecheck' % run)
    elif has(root, 'tsconfig.json'):
        fast.append('npx tsc --noEmit')
    if 'lint' in scripts:
        fast.append('%s lint' % run)
    elif src and ('eslint' in deps):
        fast.append('npx eslint %s' % q(src))
    if 'vitest' in deps:
        focused = ['npx vitest related --run %s' % q(src)] if src else []
    elif 'jest' in deps:
        focused = ['npx jest --findRelatedTests %s' % q(src)] if src else []
    else:
        focused = []
    full = ['%s test' % (pm if pm != 'npm' else 'npm')] if 'test' in scripts else []
    return fast, focused, full


def go_plan(root, changed):
    pk = sorted({'./' + (os.path.dirname(f) or '.') for f in changed if f.endswith('.go')})
    return (['go vet %s' % (' '.join(pk) or './...')],
            ['go test %s' % ' '.join(pk)] if pk else [], ['go test ./...'])


def rust_plan(root, changed):
    return ['cargo check -q', 'cargo clippy -q'] if shutil.which('cargo-clippy') else ['cargo check -q'], [], ['cargo test -q']


def java_plan(root, changed):
    if has(root, 'gradlew', 'build.gradle', 'build.gradle.kts'):
        g = './gradlew' if has(root, 'gradlew') else 'gradle'
        return ['%s -q compileJava compileTestJava' % g], [], ['%s -q test' % g]
    return ['mvn -q compile test-compile'], [], ['mvn -q test']


def plan(root, changed):
    over = read(root, os.path.join('.overmind', 'loop.json'))
    if over:
        try:
            o = json.loads(over)
            return 'custom', o.get('fast', []), o.get('focused', []), o.get('full', [])
        except ValueError:
            pass
    for name, files, fn in [('node', ('package.json',), node_plan), ('go', ('go.mod',), go_plan),
                            ('rust', ('Cargo.toml',), rust_plan),
                            ('java', ('pom.xml', 'build.gradle', 'build.gradle.kts'), java_plan),
                            ('python', ('pyproject.toml', 'setup.py', 'setup.cfg', 'requirements.txt'), python_plan)]:
        if has(root, *files):
            return (name,) + fn(root, changed)
    def shallow_py(depth=3):
        for d, ds, fs in os.walk(root):
            if d[len(root):].count(os.sep) >= depth:
                ds[:] = []
            ds[:] = [x for x in ds if not x.startswith('.') and x not in ('node_modules', 'venv')]
            if any(f.endswith('.py') for f in fs):
                return True
        return False
    if any(f.endswith('.py') for f in changed) or shallow_py():
        return ('python',) + python_plan(root, changed)
    return 'unknown', [], [], []


PER_FAILURE = re.compile(r'^(FAILED |ERROR |--- FAIL:|FAIL: |ERROR: |\s*(✕|×|●) )')


def digest(out, n=12):
    lines = [l.rstrip() for l in out.splitlines()]
    per = [l.strip()[:200] for l in lines if PER_FAILURE.match(l)]
    if len(per) > 3:
        # many failures: one line each beats tracebacks for the first few
        seen, res = set(), []
        for l in per:
            if l not in seen:
                seen.add(l); res.append(l)
        tail = [l for l in lines if l.strip()][-1:]
        shown = res[:40]
        if len(res) > 40:
            shown.append('... %d more' % (len(res) - 40))
        return shown + [t[:220] for t in tail if t[:220] not in shown]
    keep = [l for l in lines if KEY.search(l) and not NOISE.match(l)]
    seen, res = set(), []
    for l in keep:
        if l not in seen:
            seen.add(l); res.append(l[:220])
    tail = [l for l in lines if l.strip()][-1:]
    res = res[:n]
    if tail and tail[0][:220] not in res:
        res.append(tail[0][:220])
    return res


def mutate_tier(root, stack, changed, test_cmds, a):
    """Mutate only the changed functions; report bugs no test would catch."""
    if stack != 'python' and stack != 'custom':
        tools = {'node': ('@stryker-mutator/core', 'npx stryker run --mutate %s'),
                 'go': ('go-mutesting', 'go-mutesting %s'),
                 'rust': ('cargo-mutants', 'cargo mutants --file %s'),
                 'java': ('pitest', 'mvn -q org.pitest:pitest-maven:mutationCoverage')}
        tool, cmd = tools.get(stack, (None, None))
        src = [f for f in changed if not TEST_FILE.search(f)]
        print('loop mutate: %s stack, %d changed source file(s)' % (stack, len(src)))
        if not tool:
            print('no mutation tool known for this stack'); return 2
        line = cmd % ' '.join(src) if '%s' in cmd else cmd
        print('run: %s   (needs %s)' % (line, tool))
        return 0 if a.dry_run else sh(line, root, a.timeout * 10)[0] and 1
    import mutate as M
    src = [f for f in changed if f.endswith('.py') and not TEST_FILE.search(f)]
    print('loop mutate: %d changed python file(s)' % len(src))
    if not src:
        print('nothing to mutate'); return 0
    cmd = ' && '.join(failfast(c) for c in test_cmds)
    if a.dry_run:
        print('  would mutate: %s\n  test command: %s' % (', '.join(src), cmd)); return 0
    rc, out, _ = sh(cmd, root, a.timeout)
    if rc != 0:
        print('FAIL tests must pass before mutation testing:')
        for l in digest(out, a.lines):
            print('      ' + l)
        return 1
    tot_t = tot_k = 0
    survivors = []
    for f in src:
        diff = git(['diff', '--unified=0', 'HEAD', '--', f], root)
        ranges = M.changed_ranges(diff) if diff else None  # untracked: whole file
        r = M.run(os.path.join(root, f), cmd, root, ranges, a.max_mutants, max(30, a.timeout // 4))
        tot_t += r['tested']; tot_k += r['killed']
        survivors += [(f,) + s for s in r['survivors']]
    score = 100 * tot_k // max(tot_t, 1)
    print('%s score %d%%: %d of %d injected bugs caught' % ('PASS' if score >= a.min else 'FAIL', score, tot_k, tot_t))
    for f, ln, desc, code in survivors[:8]:
        print('      not caught  %s:%d  %s   %s' % (f, ln, desc, code[:70]))
    if len(survivors) > 8:
        print('      ... %d more' % (len(survivors) - 8))
    if survivors:
        print('      add a test that fails for each of these, then rerun')
    return 0 if score >= a.min else 1


TEST_FILE = re.compile(r'(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$')


def failfast(cmd):
    if cmd.startswith('pytest'):
        return cmd.replace('pytest', 'pytest -x -p no:cacheprovider', 1)
    if '-m unittest' in cmd:
        return cmd.replace('-m unittest', '-m unittest -f', 1)
    return cmd


def main(argv=None):
    ap = argparse.ArgumentParser(prog='loop')
    ap.add_argument('tier', nargs='?', default='fast', choices=['fast', 'focused', 'full', 'mutate'])
    ap.add_argument('--min', type=int, default=0, help='mutate: fail below this score')
    ap.add_argument('--max-mutants', type=int, default=60)
    ap.add_argument('--repo', default='.')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--timeout', type=int, default=600)
    ap.add_argument('--lines', type=int, default=12)
    a = ap.parse_args(argv)
    root = os.path.abspath(a.repo)
    changed = changed_files(root)
    stack, fast, focused, full = plan(root, changed)
    if a.tier == 'mutate':
        return mutate_tier(root, stack, changed, focused or full, a)
    cmds = {'fast': fast, 'focused': focused or full, 'full': full}[a.tier]
    note = '' if a.tier != 'focused' or focused else '  (no related tests found; running full)'
    print('loop %s: %s stack, %d changed file(s)%s' % (a.tier, stack, len(changed), note))
    if not cmds:
        print('no %s commands detected; add them to .overmind/loop.json' % a.tier)
        return 2
    if a.dry_run:
        for c in cmds:
            print('  would run: %s' % c)
        return 0
    worst = 0
    for c in cmds:
        rc, out, dt = sh(c, root, a.timeout)
        print('%s %5.1fs  %s' % ('PASS' if rc == 0 else 'FAIL', dt, c[:120]))
        if rc != 0:
            worst = rc
            for l in digest(out, a.lines):
                print('      ' + l)
            break  # stop at the first failing tier step; fix it before running slower ones
    return 1 if worst else 0


if __name__ == '__main__':
    sys.exit(main())
