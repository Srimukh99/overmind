"""The claim-guard eval must measure the two halves it claims to measure.

Both numbers are regression guards on this repo:
  - naming: receipts.md keeps a row for every scripted claim, so thinning the
    red-flag list or dropping the delegation row fails here
  - enforcement: the Stop hook really exits 2 on each planted mistake, and
    really does not block clean work or loop on itself

The scorer is also tested for the way it could flatter the prose: a row that
names an excuse without saying what to do instead must not count.
"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'evals'))
import claim_guard as CG  # noqa: E402


def score(text):
    """Which cases a snippet scores, through the real scanner."""
    with tempfile.TemporaryDirectory() as d:
        rel = os.path.join('skills', 'ship', 'references', 'receipts.md')
        os.makedirs(os.path.join(d, os.path.dirname(rel)))
        with open(os.path.join(d, rel), 'w') as fh:
            fh.write(text)
        return set(CG.naming(d, CG.guidance_files(d)))


class GuidanceIsFound(unittest.TestCase):
    def test_receipts_is_the_file_this_scores(self):
        self.assertIn('skills/ship/references/receipts.md', CG.guidance_files(ROOT))

    def test_every_claim_is_named(self):
        named = CG.naming(ROOT, CG.guidance_files(ROOT))
        missing = sorted(c['id'] for c in CG.CASES if c['id'] not in named)
        self.assertEqual(missing, [], 'receipts.md stopped naming: %s' % missing)


class ScorerRejectsHalfAnswers(unittest.TestCase):
    def test_doubting_the_subagent_is_not_enough(self):
        """The delegation row has to send you to the diff, not just cast doubt."""
        self.assertNotIn('subagent_said_done',
                         score('| "A subagent reported it done" | Be sceptical of that. |\n'))

    def test_delegation_row_needs_the_diff(self):
        self.assertIn('subagent_said_done',
                      score('| "A subagent reported it done" | Read the VCS diff yourself. |\n'))

    def test_requirements_row_needs_the_request(self):
        self.assertNotIn('everything_asked', score('| "I did everything that was asked" | Sure. |\n'))
        self.assertIn('everything_asked',
                      score('| "I did everything asked" | Re-read the request, tick each requirement |\n'))

    def test_unrelated_prose_scores_nothing(self):
        self.assertEqual(score('Run the tests and read the output before you report.\n'), set())


class HookEnforcesWhatItCan(unittest.TestCase):
    """The enforcement half, run for real against planted repos."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='rubric-claim-test-')
        cls.stopped = CG.enforcement(cls.tmp.name)
        cls.rc_clean, cls.rc_loop = CG.controls(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_planted_mistake_blocks_the_turn(self):
        unblocked = sorted(i for i, (blocked, _) in self.stopped.items() if not blocked)
        self.assertEqual(unblocked, [], 'the gate let these through: %s' % unblocked)

    def test_the_planted_set_is_not_empty(self):
        """A fixture that stopped planting anything would score 5/12 vacuously."""
        self.assertEqual(len(self.stopped), 5)

    def test_clean_work_is_not_blocked(self):
        self.assertEqual(self.rc_clean, 0)

    def test_the_loop_guard_holds(self):
        self.assertEqual(self.rc_loop, 0)

    def test_the_gap_between_prose_and_script_is_reported(self):
        """The eval's point is the claims no script can see; keep them countable."""
        self.assertEqual(len(CG.CASES) - len(self.stopped), 7)


class EvalRuns(unittest.TestCase):
    def test_main_exits_zero(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = CG.main(['--quiet'])
        self.assertEqual(rc, 0)
        self.assertIn('12/12', buf.getvalue())
        self.assertIn('5/12', buf.getvalue())


if __name__ == '__main__':
    unittest.main()
