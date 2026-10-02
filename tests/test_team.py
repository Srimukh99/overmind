import io, contextlib, json, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'delegate', 'scripts'))
import team as T

CONTRACT = ('import unittest\nfrom adder import add\nfrom multer import mul\n\n\nclass T(unittest.TestCase):\n'
            '    def test_add(self):\n        self.assertEqual(add(2, 3), 5)\n\n'
            '    def test_mul(self):\n        self.assertEqual(mul(2, 3), 6)\n')
FILES = {'adder.py': 'def add(a, b):\n    raise NotImplementedError\n', 'multer.py': 'def mul(a, b):\n    raise NotImplementedError\n',
         'shared.py': 'X = 1\n', 'tests/test_contract.py': CONTRACT,
         'tests/test_shared.py': 'import unittest\nimport shared\n\n\nclass S(unittest.TestCase):\n    def test_x(self):\n        self.assertEqual(shared.X, 1)\n'}


class Team(unittest.TestCase):
    def setUp(self):
        self.base = tempfile.mkdtemp(); self.d = os.path.join(self.base, 'repo')
        for rel, text in FILES.items():
            self.w(rel, text)
        for c in (['init', '-q'], ['add', '-A'], ['commit', '-qm', 'b']):
            cmd = ['git', '-c', 'user.email=a@b', '-c', 'user.name=a'] + c
            try:
                subprocess.run(cmd, cwd=self.d, check=True, capture_output=True)
            except (subprocess.CalledProcessError, OSError):
                if sys.platform == "darwin":
                    subprocess.run(['arch', '-arm64'] + cmd, cwd=self.d, check=True, capture_output=True)
                else:
                    raise
        self.call('init', '--goal', 'add and mul', '--contract', 'tests/test_contract.py')
    def tearDown(self): shutil.rmtree(self.base)
    def w(self, rel, text, root=None):
        p = os.path.join(root or self.d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text)
    def call(self, *a):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): rc = T.main(['--repo', self.d] + list(a))
        return rc, out.getvalue()
    def two_workers(self):
        self.call('add', 'adder', '--owns', 'adder.py', '--target', 'tests/test_contract.py::test_add')
        self.call('add', 'multer', '--owns', 'multer.py', '--target', 'tests/test_contract.py::test_mul')
    def plan(self): return json.load(open(os.path.join(self.d, '.rubric', 'team', 'plan.json')))

    def test_plan_ok(self):
        self.two_workers(); self.assertEqual(self.call('check')[0], 0)
    def test_plan_rejects_overlapping_owners(self):
        self.two_workers(); self.call('add', 'tidy', '--owns', '*.py', '--target', 'tests/test_shared.py::test_x')
        rc, out = self.call('check'); self.assertEqual(rc, 1); self.assertIn('could both edit the same file', out)
    def test_plan_rejects_owning_the_contract(self):
        self.call('add', 'bad', '--owns', 'tests/**', '--target', 'tests/test_contract.py::test_add')
        rc, out = self.call('check'); self.assertEqual(rc, 1); self.assertIn('overlaps the contract', out)
    def test_plan_rejects_shared_target(self):
        self.two_workers(); self.call('add', 'again', '--owns', 'shared.py', '--target', 'tests/test_contract.py::test_add')
        rc, out = self.call('check'); self.assertIn('assigned to both', out)
    def test_plan_warns_unassigned_contract_test(self):
        self.call('add', 'adder', '--owns', 'adder.py', '--target', 'tests/test_contract.py::test_add')
        self.assertIn('nobody owns', self.call('check')[1])
    def test_brief(self):
        self.two_workers(); out = self.call('brief', 'adder')[1]
        self.assertIn('only: adder.py', out); self.assertIn('test_contract.py::test_add', out); self.assertIn('result.json', out)
        self.assertNotIn('%s', out)
    def test_full_flow(self):
        self.two_workers()
        self.assertEqual(self.call('spawn', '--no-fast')[0], 0)
        p = self.plan(); wa, wm = p['workers']['adder']['worktree'], p['workers']['multer']['worktree']
        self.assertTrue(os.path.isdir(wa) and not wa.startswith(self.d + os.sep))
        self.w('adder.py', 'def add(a, b):\n    return a + b\n', wa)
        self.w('multer.py', 'def mul(a, b):\n    return a * b\n', wm); self.w('shared.py', 'X = 2\n', wm)
        self.w('.rubric/result.json', '{"status": "done"}', wm)
        rc, out = self.call('verify')
        self.assertIn('adder', out); self.assertRegex(out, r'adder\s+none\s+DONE'); self.assertRegex(out, r'multer\s+done\s+REJECT')
        self.assertIn('FALSE CLAIM', out)
        rc, out = self.call('integrate', '--apply'); self.assertEqual(rc, 0, out); self.assertIn('LANDED', out)
        self.assertIn('return a + b', open(os.path.join(self.d, 'adder.py')).read())
        self.assertEqual(open(os.path.join(self.d, 'shared.py')).read(), 'X = 1\n')
        self.assertIn('raise NotImplementedError', open(os.path.join(self.d, 'multer.py')).read())
        self.assertTrue(self.plan()['workers']['adder']['integrated'])
    def git(self, *c):
        cmd = ['git'] + list(c)
        p = None
        try:
            p = subprocess.run(cmd, cwd=self.d, capture_output=True, text=True)
        except (subprocess.CalledProcessError, OSError):
            pass
        if p is None or (p.returncode != 0 and sys.platform == "darwin"):
            try:
                p2 = subprocess.run(['arch', '-arm64'] + cmd, cwd=self.d, capture_output=True, text=True)
                p = p2
            except Exception:
                pass
        return p.stdout if p else ''
    def test_parallel_ratchets_keep_separate_refs(self):
        self.two_workers(); self.call('spawn', '--no-fast')
        refs = self.git('for-each-ref', '--format=%(refname)', 'refs/rubric/ratchet').split()
        self.assertEqual(len({r.split('/')[3] for r in refs}), 2)
    def test_clean_removes_worktrees_and_branches(self):
        self.two_workers(); self.call('spawn', '--no-fast'); self.call('clean', '--all')
        wl = self.git('worktree', 'list')
        br = self.git('branch', '--list', 'team/*')
        self.assertEqual(len(wl.strip().splitlines()), 1); self.assertEqual(br.strip(), '')
        self.assertFalse(os.path.exists(os.path.join(self.d, '.rubric', 'team')))
    def test_main_tree_untouched_until_apply(self):
        self.two_workers(); self.call('spawn', '--no-fast')
        wa = self.plan()['workers']['adder']['worktree']; self.w('adder.py', 'def add(a, b):\n    return a + b\n', wa)
        self.call('verify', 'adder'); rc, out = self.call('integrate')
        self.assertIn('READY', out); self.assertIn('NotImplementedError', open(os.path.join(self.d, 'adder.py')).read())

if __name__ == '__main__': unittest.main()
