"""The evals must actually run, or the numbers they publish cannot be reproduced.

On an Apple Silicon Mac with an x86_64 Python, git's xcrun shim cannot load its
arm64-only dylib, so every git an eval spawns fails. The skill scripts all carry
a fallback for this; these tests pin the same behaviour for the eval harness.
"""
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'evals'))
import _eval_git as G  # noqa: E402


class EvalGitShim(unittest.TestCase):
    def test_init_a_repo_on_this_machine(self):
        """git init must succeed whatever architecture the interpreter is."""
        with tempfile.TemporaryDirectory() as d:
            p = G.git(['init', '-q'], cwd=d)
            self.assertEqual(p.returncode, 0, p.stderr)
            self.assertTrue(os.path.isdir(os.path.join(d, '.git')))

    def test_commit_with_identity(self):
        """The evals commit as a fixed identity; that path must work too."""
        with tempfile.TemporaryDirectory() as d:
            G.git(['init', '-q'], cwd=d)
            open(os.path.join(d, 'a.txt'), 'w').write('x\n')
            G.git(['add', '-A'], cwd=d)
            G.git(G.IDENT + ['commit', '-qm', 'base'], cwd=d)
            out = G.git(['log', '--oneline'], cwd=d).stdout
            self.assertIn('base', out)

    def test_check_false_returns_instead_of_raising(self):
        with tempfile.TemporaryDirectory() as d:
            p = G.git(['rev-parse', 'HEAD'], cwd=d, check=False)
            self.assertNotEqual(p.returncode, 0)

    def test_check_true_raises_on_failure(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(subprocess.CalledProcessError):
                G.git(['rev-parse', 'HEAD'], cwd=d)

    def test_reports_whether_pytest_is_importable(self):
        """Evals that need pytest must be able to skip with a clear message."""
        self.assertIsInstance(G.have_module('pytest'), bool)
        self.assertTrue(G.have_module('unittest'))
        self.assertFalse(G.have_module('a_module_that_does_not_exist_1234'))


if __name__ == '__main__':
    unittest.main()
