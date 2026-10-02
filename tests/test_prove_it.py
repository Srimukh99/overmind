import os, sys, shutil, subprocess, tempfile, unittest, io, contextlib
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'build', 'scripts'))
import loop as L, tamper as T

BASE = '''import unittest
from money import add_tax

class T(unittest.TestCase):
    def test_tax(self):
        self.assertEqual(add_tax(1000, 825), 1082)

    def test_zero(self):
        self.assertEqual(add_tax(0, 825), 0)
'''


def run(*a, cwd):
    cmd = list(a)
    try:
        subprocess.run(cmd, cwd=cwd, check=True, capture_output=True)
    except (subprocess.CalledProcessError, OSError):
        if sys.platform == "darwin" and cmd[0] == 'git':
            subprocess.run(['arch', '-arm64'] + cmd, cwd=cwd, check=True, capture_output=True)
        else:
            raise


class Tamper(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); os.makedirs(os.path.join(self.d, 'tests'))
        open(os.path.join(self.d, 'money.py'), 'w').write('def add_tax(c, r):\n    return c + c * r // 10000\n')
        self.t = os.path.join(self.d, 'tests', 'test_money.py'); open(self.t, 'w').write(BASE)
        run('git', 'init', '-q', cwd=self.d)
        run('git', '-c', 'user.email=a@b', '-c', 'user.name=a', 'add', '-A', cwd=self.d)
        run('git', '-c', 'user.email=a@b', '-c', 'user.name=a', 'commit', '-qm', 'b', cwd=self.d)
    def tearDown(self): shutil.rmtree(self.d)
    def rules(self, text):
        open(self.t, 'w').write(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out): T.main(['--repo', self.d, '--json'])
        import json; return {h['rule'] for h in json.loads(out.getvalue())}

    def test_clean(self): self.assertEqual(self.rules(BASE), set())
    def test_skip(self): self.assertIn('skip-added', self.rules(BASE.replace('    def test_tax', '    @unittest.skip("x")\n    def test_tax')))
    def test_weak(self): self.assertIn('weak-assertion', self.rules(BASE.replace('self.assertEqual(add_tax(0, 825), 0)', 'self.assertTrue(True)')))
    def test_deleted(self): self.assertIn('test-deleted', self.rules(BASE.split('    def test_zero')[0]))
    def test_expected_changed(self): self.assertIn('expected-changed', self.rules(BASE.replace('1082)', '1825)')))
    def test_focus_only(self): self.assertIn('skip-added', self.rules(BASE + "\nit." + "only('x', fn)\n"))
    def test_ok_marker(self): self.assertEqual(self.rules(BASE.replace('1082)', '1083)  # prove-it: ok spec')), set())
    def test_swallow(self): self.assertIn('error-swallowed', self.rules(BASE + '\ntry:\n    x()\nexcept Exception: pass\n'))


class Loop(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.d)
    def w(self, rel, text=''):
        p = os.path.join(self.d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text)

    def test_python_focused_finds_related_test(self):
        self.w('pyproject.toml'); self.w('pkg/cart.py'); self.w('tests/test_cart.py')
        stack, fast, focused, full = L.plan(self.d, ['pkg/cart.py'])
        self.assertEqual(stack, 'python'); self.assertTrue(any('test_cart' in c for c in focused))
    def test_node_vitest_related(self):
        self.w('package.json', '{"scripts":{"test":"vitest"},"devDependencies":{"vitest":"1"}}'); self.w('tsconfig.json', '{}')
        stack, fast, focused, full = L.plan(self.d, ['src/a.ts'])
        self.assertEqual(stack, 'node'); self.assertIn('npx tsc --noEmit', fast); self.assertIn('vitest related', focused[0])
    def test_go_packages(self):
        self.w('go.mod', 'module x')
        _, fast, focused, full = L.plan(self.d, ['api/h.go'])
        self.assertEqual(focused, ['go test ./api']); self.assertEqual(full, ['go test ./...'])
    def test_override(self):
        self.w('.overmind/loop.json', '{"fast":["make lint"],"full":["make test"]}')
        self.assertEqual(L.plan(self.d, [])[:2], ('custom', ['make lint']))
    def test_digest_keeps_signal(self):
        out = '\n'.join(['noise'] * 200 + ['tests/a.py:12: AssertionError: 3 != 4', 'FAILED (failures=1)'])
        d = L.digest(out); self.assertTrue(any('3 != 4' in l for l in d)); self.assertLess(len(d), 15)

if __name__ == '__main__': unittest.main()
