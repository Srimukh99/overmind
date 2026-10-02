"""The code-quality eval must discriminate, or its numbers mean nothing.

An earlier version of the harness reported "0/0 FAIL" and a 100% mutation score
for every candidate, because unittest could not import the generated tests dir
and every mutant looked killed by the resulting import error. These tests pin
the property that failure violated: a thin candidate fails the hidden suite and
a solid one passes it, with both green on the visible suite.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'evals'))
import code_quality as CQ  # noqa: E402


class CountSummary(unittest.TestCase):
    def test_reads_ran_and_failures(self):
        out = 'Ran 7 tests in 0.01s\n\nFAILED (failures=2)\n'
        self.assertEqual(CQ._count(out), (7, 2))

    def test_reads_errors_too(self):
        out = 'Ran 4 tests in 0.01s\n\nFAILED (failures=1, errors=2)\n'
        self.assertEqual(CQ._count(out), (4, 3))

    def test_clean_run_has_no_failures(self):
        self.assertEqual(CQ._count('Ran 3 tests in 0.01s\n\nOK\n'), (3, 0))


class Discriminates(unittest.TestCase):
    """Uses pagination: the fewest mutants, so this stays fast."""

    def test_visible_suite_is_green_for_both_candidates(self):
        """If visible ever fails, the eval is measuring a broken fixture."""
        for variant in ('thin', 'solid'):
            r = CQ.score('pagination', CQ.TASKS['pagination'], variant)
            self.assertTrue(r['visible_ok'], '%s: visible suite must pass' % variant)
            self.assertEqual(r['visible'], '3/3')

    def test_thin_fails_the_hidden_suite(self):
        r = CQ.score('pagination', CQ.TASKS['pagination'], 'thin')
        self.assertFalse(r['hidden_ok'])
        self.assertGreater(r['hidden_failed'], 0)

    def test_solid_passes_the_hidden_suite(self):
        r = CQ.score('pagination', CQ.TASKS['pagination'], 'solid')
        self.assertTrue(r['hidden_ok'], 'solid candidate must satisfy the spec')
        self.assertEqual(r['hidden_failed'], 0)

    def test_mutation_score_is_measured_not_vacuous(self):
        """A score of exactly 100% on every candidate was the old failure mode."""
        r = CQ.score('pagination', CQ.TASKS['pagination'], 'solid')
        self.assertGreater(r['mutation'], 0)
        self.assertLess(r['mutation'], 100, 'solid pagination has paths the visible suite misses')


class EveryTaskIsWellFormed(unittest.TestCase):
    def test_each_task_has_both_candidates_and_both_suites(self):
        for name, task in CQ.TASKS.items():
            for key in ('spec', 'module', 'thin', 'solid', 'visible', 'hidden'):
                self.assertIn(key, task, '%s is missing %s' % (name, key))
            self.assertNotEqual(task['thin'], task['solid'], '%s: candidates are identical' % name)


if __name__ == '__main__':
    unittest.main()
