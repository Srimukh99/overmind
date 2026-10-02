#!/usr/bin/env python3
"""tamper: catch test cheating in a diff.

Flags tests that were skipped, deleted (lines or whole files), focused, weakened,
commented out, loosened (tolerances, broader exceptions) or had expected values
bent. Judges weak assertions in context: a weak check that REPLACES a strong one
is cheating; a guard check next to a strong one is fine; a new test with only
weak checks is a warning. Mark a reviewed line with `prove-it: ok`.
"""
import argparse, json, os, re, subprocess, sys

TEST_PATH = re.compile(r'(^|/)(tests?|__tests__|spec)/|(^|/)test_[^/]+\.py$|_test\.(py|go)$|'
                       r'\.(test|spec)\.[jt]sx?$|Tests?\.(java|kt|cs)$|_spec\.rb$')
TEST_DEF = re.compile(r'^\s*(async\s+)?def test_|^\s*(it|test)(\.(each|skip|only|todo|concurrent)(\(.*?\))?)?\s*\(|'
                      r'^\s*x?(it|test)\s*\(|^\s*func Test\w+\(|@Test\b|^\s*#\[test\]')
SKIP = re.compile(r'@pytest\.mark\.(skip|xfail)|pytest\.skip\(|unittest\.skip|\.skip\(|'
                  r'\b(xit|xdescribe|xtest)\(|\.todo\(|\bt\.Skip(Now|f)?\(|@Disabled|@Ignore|'
                  r'#\[ignore\]|\.only\(|\bfit\(|\bfdescribe\(')
ASSERT = re.compile(r'\bassert\w*\b|\bexpect\s*\(|\bshould\b|\brequire\.\w+\(|\bt\.(Error|Fatal)f?\(|'
                    r'\bassertThat\(|\bverify\(|\.raises\(|assertRaises|toThrow')
WEAK = re.compile(r'toBeTruthy\(\)|toBeDefined\(\)|not\.toBeNull\(\)|not\.toBeUndefined\(\)|expect\.anything\(\)|'
                  r"\.not\.toBe\((''|\"\"|null|undefined|0)\)|\.not\.toEqual\(\[\]\)|"
                  r'assert\s+True\b|assertTrue\(\s*True\s*\)|assertIsNotNone\(|assert\s+.+\s+is\s+not\s+None\s*$|'
                  r'toBeGreaterThan\(0\)|assert\s+.+>\s*0\s*$|assert\s+isinstance\(|assertIsInstance\(|'
                  r'isNotNull\(\)|assert\s+\w+\s*$|!=\s*None\s*$')
TOLERANCE = re.compile(r'assertAlmostEqual|approx\(|toBeCloseTo|InDelta|InEpsilon|\bdelta\s*=|\babs\s*=|\brel\s*=|isCloseTo')
BROAD_EXC = re.compile(r'assertRaises\(\s*(Exception|BaseException)\s*\)|raises\(\s*(Exception|BaseException)\s*\)|'
                       r'toThrow\(\s*\)|assertThrows\(\s*(Exception|Throwable)\.class')
SWALLOW = re.compile(r'except(\s+\w+)?\s*:\s*pass|catch\s*\([^)]*\)\s*\{\s*\}|catch\s*\{\s*\}')
COMMENT = re.compile(r'^\s*(#|//|/\*|\*)\s*')
LIT = re.compile(r'"[^"]*"|\'[^\']*\'|\b\d+(\.\d+)?\b|\bTrue\b|\bFalse\b|\btrue\b|\bfalse\b|\bNone\b|\bnull\b')
CALL = re.compile(r'\b([A-Za-z_]\w*)\s*\(')
NOT_TARGET = {'assert', 'expect', 'assertEqual', 'assertAlmostEqual', 'approx', 'toBe', 'toEqual',
              'toBeCloseTo', 'raises', 'assertRaises', 'self', 'pytest', 'len', 'sum'}
OK = 'prove-it: ok'


def git(args, cwd):
    p = None
    try:
        p = subprocess.run(['git'] + args, cwd=cwd, capture_output=True, text=True)
    except (FileNotFoundError, OSError):
        pass
    if p is None or (p.returncode != 0 and sys.platform == "darwin"):
        try:
            p2 = subprocess.run(['arch', '-arm64', 'git'] + args, cwd=cwd, capture_output=True, text=True)
            p = p2
        except Exception:
            pass
    if p is None:
        return 1, ''
    return p.returncode, p.stdout


def base_ref(cwd, given):
    if given:
        return given
    rc, head = git(['rev-parse', 'HEAD'], cwd)
    for b in ('origin/main', 'origin/master', 'main', 'master'):
        rc, out = git(['merge-base', 'HEAD', b], cwd)
        if rc == 0 and out.strip() and out.strip() != head.strip():
            return out.strip()
    return 'HEAD'


def parse(diff):
    files, cur, old = {}, None, None
    for line in diff.splitlines():
        if line.startswith('--- '):
            old = line[6:] if line.startswith('--- a/') else None
        elif line.startswith('+++ '):
            new = line[6:] if line.startswith('+++ b/') else None
            cur = new or old
            if cur:
                files[cur] = {'add': [], 'rem': [], 'deleted': new is None}
        elif cur and line.startswith('+'):
            files[cur]['add'].append(line[1:])
        elif cur and line.startswith('-'):
            files[cur]['rem'].append(line[1:])
    return files


def is_assert(l):
    return bool(ASSERT.search(l)) and not COMMENT.match(l)


def targets(l):
    return {c for c in CALL.findall(l) if c not in NOT_TARGET and not c.startswith('assert') and not re.match(r'to[A-Z]', c)}


def untracked_test_names(root):
    rc, out = git(['ls-files', '--others', '--exclude-standard'], root)
    names = set()
    for f in out.split():
        if TEST_PATH.search(f):
            try:
                names |= {m.group(0).strip() for m in map(TEST_DEF.search, open(os.path.join(root, f), errors='replace').read().splitlines()) if m}
                names |= set(re.findall(r'(?:def |func )(Test\w+|test_\w+)', open(os.path.join(root, f), errors='replace').read()))
            except OSError:
                pass
    return names


def check(files, root=None):
    out = []
    def hit(level, rule, f, detail):
        out.append({'level': level, 'rule': rule, 'file': f, 'detail': detail[:160]})
    moved_into = untracked_test_names(root) if root else set()
    for f, d in files.items():
        if f.endswith('.snap') or '__snapshots__' in f:
            if d['add'] or d['rem']:
                hit('INFO', 'snapshot-updated', f, 'confirm the new snapshot is correct, not just regenerated')
            continue
        if not TEST_PATH.search(f):
            continue
        all_add, rem = d['add'], d['rem']
        if d['deleted']:
            names = set(re.findall(r'(?:def |func )(Test\w+|test_\w+)', '\n'.join(rem)))
            if names and names <= moved_into:
                hit('INFO', 'test-file-moved', f, 'tests found in a new untracked file')
            else:
                n = sum(bool(TEST_DEF.search(l)) for l in rem)
                hit('FAIL', 'test-file-deleted', f, '%d test(s) in a deleted file' % n)
            continue
        add = [l for l in all_add if OK not in l]
        rem_strong = [l for l in rem if is_assert(l) and not WEAK.search(l)]
        rem_targets = set().union(*[targets(l) for l in rem_strong]) if rem_strong else set()
        for l in add:
            if SKIP.search(l):
                hit('FAIL', 'skip-added', f, l.strip())
            if SWALLOW.search(l):
                hit('FAIL', 'error-swallowed', f, l.strip())
            if COMMENT.match(l) and ASSERT.search(l):
                hit('FAIL', 'assertion-commented', f, l.strip())
            if TOLERANCE.search(l) and targets(l) & rem_targets:
                hit('FAIL', 'tolerance-added', f, l.strip())
            if BROAD_EXC.search(l):
                specific_gone = any(re.search(r'assertRaises\(\s*\w+|raises\(\s*\w+|toThrow\(\s*\S', r) and not BROAD_EXC.search(r) for r in rem)
                hit('FAIL' if specific_gone else 'WARN', 'exception-broadened', f, l.strip())
        # weak assertions, judged per test function
        groups, cur = {None: []}, None
        for l in add:
            if TEST_DEF.search(l):
                cur = l.strip(); groups[cur] = []
                l = TEST_DEF.sub('', l)  # one-line tests: keep the assertion on the same line
            if is_assert(l):
                groups[cur].append(l)
        for g, lines in groups.items():
            weak = [l for l in lines if WEAK.search(l)]
            strong = [l for l in lines if not WEAK.search(l)]
            if not weak:
                continue
            replaced = any(targets(w) & rem_targets for w in weak) or (g is None and rem_strong and not strong)
            if replaced:
                for w in weak:
                    hit('FAIL', 'weak-assertion', f, w.strip())
            elif not strong:
                hit('WARN', 'weak-only-test', f, (g or weak[0]).strip())
        dt = sum(bool(TEST_DEF.search(l)) for l in rem) - sum(bool(TEST_DEF.search(l)) for l in all_add)
        if dt > 0:
            hit('FAIL', 'test-deleted', f, '%d test(s) removed' % dt)
        da = sum(is_assert(l) for l in rem) - sum(is_assert(l) for l in all_add)
        if da > 0 and dt <= 0:
            hit('WARN', 'assertions-dropped', f, '%d fewer assertion(s)' % da)
        norm_rem = {}
        for l in rem:
            if is_assert(l):
                norm_rem.setdefault(LIT.sub('_', l).strip(), l.strip())
        for l in add:
            if is_assert(l):
                k = LIT.sub('_', l).strip()
                if k in norm_rem and norm_rem[k] != l.strip():
                    hit('WARN', 'expected-changed', f, '%s  ->  %s' % (norm_rem[k], l.strip()))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(prog='tamper')
    ap.add_argument('--repo', default='.')
    ap.add_argument('--base', help='git ref to compare against (default: merge-base with main)')
    ap.add_argument('--json', action='store_true')
    a = ap.parse_args(argv)
    root = os.path.abspath(a.repo)
    base = base_ref(root, a.base)
    rc, diff = git(['diff', '--unified=0', '--no-color', base, '--'], root)
    if rc != 0:
        print('tamper: not a git repo or bad base %r' % base)
        return 2
    hits = check(parse(diff), root)
    fails = sum(h['level'] == 'FAIL' for h in hits)
    if a.json:
        print(json.dumps(hits, indent=2))
        return 1 if fails else 0
    print('tamper: %d FAIL, %d WARN, %d INFO  (vs %s)' % (
        fails, sum(h['level'] == 'WARN' for h in hits), sum(h['level'] == 'INFO' for h in hits), base[:12]))
    for h in hits:
        print('%-4s %-19s %s' % (h['level'], h['rule'], h['file']))
        print('     %s' % h['detail'])
    if fails:
        print('fix: revert the test change, or tell the user why the test was wrong and mark it `%s`' % OK)
    return 1 if fails else 0


if __name__ == '__main__':
    sys.exit(main())
