import io, contextlib, json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'ratchet', 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'build', 'scripts'))
import ratchet as R, tamper as T, mutate as M, loop as L

PRICING = 'def apply(c, code):\n    if code == "A":\n        return c - 10\n    raise ValueError(code)\n'
TESTS = ('import unittest\nfrom shop import apply\nclass T(unittest.TestCase):\n'
         '    def test_a(self): self.assertEqual(apply(100, "A"), 90)\n'
         '    def test_bad(self):\n        with self.assertRaises(ValueError): apply(1, "Z")\n')
TARGET = ('import unittest\nclass N(unittest.TestCase):\n'
          '    def test_b(self):\n        from shop import apply\n        self.assertEqual(apply(100, "B"), 50)\n')
GOOD = PRICING.replace('    raise', '    if code == "B":\n        return c // 2\n    raise')


class Ratchet(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.w('shop.py', PRICING); self.w('other.py', 'X = 1\n'); self.w('tests/test_shop.py', TESTS)
        for c in (['init', '-q'], ['add', '-A'], ['commit', '-qm', 'b']):
            cmd = ['git', '-c', 'user.email=a@b', '-c', 'user.name=a'] + c
            try:
                subprocess.run(cmd, cwd=self.d, check=True, capture_output=True)
            except (subprocess.CalledProcessError, OSError):
                if sys.platform == "darwin":
                    subprocess.run(['arch', '-arm64'] + cmd, cwd=self.d, check=True, capture_output=True)
                else:
                    raise
        self.w('tests/test_new.py', TARGET)
        self.call('start', '--goal', 'add coupon B', '--scope', 'shop.py', '--no-fast',
                  '--test-cmd', '%s -m unittest discover -v -s tests' % sys.executable,
                  '--target', 'tests/test_new.py::test_b')
    def tearDown(self): shutil.rmtree(self.d)
    def w(self, rel, text):
        p = os.path.join(self.d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text)
    def call(self, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): rc = R.main(['--repo', self.d] + list(a))
        return rc, out.getvalue()
    def verdict(self):
        rc, out = self.call('check'); return out.split('\n')[0].split(': ')[1], out

    def test_floor_counts_existing_tests(self):
        floor = json.load(open(os.path.join(self.d, '.rubric/ratchet/floor.json')))
        self.assertEqual(len(floor['passing']), 2); self.assertEqual(floor['targets'], {'tests/test_new.py::test_b': False})
    def test_done_on_good_change(self):
        self.w('shop.py', GOOD); self.assertEqual(self.verdict()[0], 'DONE')
    def test_regression_rejected(self):
        self.w('shop.py', GOOD.replace('    raise ValueError(code)', '    return c'))
        v, out = self.verdict(); self.assertEqual(v, 'REJECT'); self.assertIn('test_bad', out)
    def test_drift_rejected(self):
        self.w('shop.py', GOOD); self.w('other.py', 'X = 2\n')
        v, out = self.verdict(); self.assertEqual(v, 'REJECT'); self.assertIn('other.py', out)
    def test_api_change_rejected(self):
        self.w('shop.py', GOOD.replace('def apply(c, code)', 'def apply(c, codes)').replace('code ==', 'codes ==').replace('(code)', '(codes)'))
        v, out = self.verdict(); self.assertEqual(v, 'REJECT'); self.assertIn('public API changed', out)
    def test_frozen_target_rejected(self):
        self.w('shop.py', PRICING.replace('    raise', '    if code == "B":\n        return 40\n    raise'))
        self.w('tests/test_new.py', TARGET.replace('50)', '40)'))
        v, out = self.verdict(); self.assertEqual(v, 'REJECT'); self.assertIn('frozen-test', out)
    def test_new_tests_allowed(self):
        self.w('shop.py', GOOD); self.w('tests/test_more.py', 'import unittest\nclass M(unittest.TestCase):\n    def test_m(self): self.assertEqual(1, 1)\n')
        self.assertEqual(self.verdict()[0], 'DONE')
    def test_stall_and_strikes(self):
        self.w('shop.py', PRICING + '# note\n')
        for i in range(3):
            v, out = self.verdict()
        self.assertEqual(v, 'STALL'); self.assertIn('STOP', out)
    def test_revert_restores_exactly(self):
        self.w('shop.py', 'broken'); self.w('other.py', 'X = 9\n'); self.w('stray.py', 'Y = 1\n')
        self.verdict(); self.call('revert', '--clean')
        self.assertEqual(open(os.path.join(self.d, 'shop.py')).read(), PRICING)
        self.assertEqual(open(os.path.join(self.d, 'other.py')).read(), 'X = 1\n')
        self.assertFalse(os.path.exists(os.path.join(self.d, 'stray.py')))
        self.assertTrue(os.path.exists(os.path.join(self.d, 'tests/test_new.py')))
    def test_amend_scope(self):
        self.w('shop.py', GOOD); self.w('other.py', 'X = 2\n')
        self.call('amend', '--scope', 'other.py', '--reason', 'user approved')
        self.assertEqual(self.verdict()[0], 'DONE')
    def git(self, *c):
        cmd = ['git'] + list(c)
        try:
            return subprocess.run(cmd, cwd=self.d, capture_output=True, text=True).stdout
        except (subprocess.CalledProcessError, OSError):
            if sys.platform == "darwin":
                return subprocess.run(['arch', '-arm64'] + cmd, cwd=self.d, capture_output=True, text=True).stdout
            raise
    def test_index_and_branch_untouched(self):
        head = self.git('rev-parse', 'HEAD')
        self.w('shop.py', GOOD); self.verdict()
        st = self.git('diff', '--cached', '--name-only')
        self.assertEqual(st, ''); self.assertEqual(head, self.git('rev-parse', 'HEAD'))


class TamperV2(unittest.TestCase):
    def hits(self, rem, add, path='tests/test_x.py'):
        return {(h['level'], h['rule']) for h in T.check({path: {'add': add, 'rem': rem, 'deleted': False}})}
    def test_tolerance(self):
        self.assertIn(('FAIL', 'tolerance-added'), self.hits(['    self.assertEqual(total(x), 350)'], ['    self.assertAlmostEqual(total(x), 350, delta=1000)']))
    def test_commented(self):
        self.assertIn(('FAIL', 'assertion-commented'), self.hits(["    expect(f('a')).toBe('b')"], ["    // expect(f('a')).toBe('b')"]))
    def test_broadened(self):
        self.assertIn(('FAIL', 'exception-broadened'), self.hits(['    with self.assertRaises(ValueError):'], ['    with self.assertRaises(Exception):']))
    def test_guard_then_exact_clean(self):
        self.assertEqual(self.hits([], ['def test_x():', '    item = find(1)', '    assert item is not None', '    assert item.price == 3']), set())
    def test_weak_only_new_test_warns(self):
        self.assertIn(('WARN', 'weak-only-test'), self.hits([], ['def test_x():', '    assert f() is not None']))
    def test_deleted_file(self):
        out = T.check({'tests/test_x.py': {'add': [], 'rem': ['def test_a():', '    assert 1 == 1'], 'deleted': True}})
        self.assertEqual(out[0]['rule'], 'test-file-deleted')


class MutateAndDigest(unittest.TestCase):
    def test_changed_ranges(self):
        self.assertEqual(M.changed_ranges('@@ -3,0 +4,2 @@\n+a\n+b\n@@ -9 +11 @@\n'), [(4, 5), (11, 11)])
    def test_sites_limited_to_changed_function(self):
        import ast
        tree = ast.parse('def a(x):\n    return x + 1\n\ndef b(y):\n    return y * 2\n')
        self.assertTrue(all(s[2].lineno == 5 for s in M.sites(tree, [(5, 5)])))
    def test_many_failures_one_line_each(self):
        raw = '\n'.join(['noise'] * 50 + ['FAILED tests/t.py::test_%d - assert %d == 0' % (i, i) for i in range(12)] + ['== 12 failed =='])
        d = L.digest(raw)
        self.assertEqual(sum('FAILED' in l for l in d), 12)

if __name__ == '__main__': unittest.main()
