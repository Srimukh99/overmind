"""The claim-guard eval must measure the two halves it claims to measure.

Both numbers are regression guards on this repo:
  - naming: receipts.md keeps a row for every scripted claim, so thinning the
    red-flag list or dropping the delegation row fails here
  - enforcement: the Stop hook really exits 2 on each planted mistake and on
    each red-flag closing message, and really does not block honest work,
    a message that only quotes the words, or loop on itself

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
    """The enforcement half, run for real: planted repos, and closing messages."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='rubric-claim-test-')
        cls.rows = CG.enforcement(cls.tmp.name)
        cls.ctl = CG.controls(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_every_planted_mistake_blocks_the_turn(self):
        planted = {i: r['repo'] for i, r in self.rows.items() if r['repo']}
        self.assertEqual(len(planted), 5, 'a fixture stopped planting; 5 repo catches would be vacuous')
        self.assertEqual(sorted(i for i, (ok, _) in planted.items() if not ok), [])

    def test_the_message_alone_blocks_what_it_should(self):
        """On a clean repo, only the transcript can trip the hook."""
        by_msg = sorted(i for i, r in self.rows.items() if r['message'][0])
        self.assertEqual(by_msg, sorted([
            'should_work', 'looks_right', 'confident',                    # red-flag wording
            'passed_before', 'too_hard_to_test', 'types_check', 'subagent_said_done',
            'celebrates', 'regression_unseen', 'partial_check', 'last_step',
            'unhedged_done', 'invented_receipt', 'checked_then_edited',   # success with no backing
        ]))

    def test_claims_that_assert_nothing_pass_the_message_check(self):
        """No success claimed and no red-flag word: the check must not overreach."""
        for i in ('one_line_change', 'docs_only', 'everything_asked', 'ci_will_catch', 'worked_earlier'):
            self.assertFalse(self.rows[i]['message'][0], i)

    def test_honest_work_is_never_blocked_and_the_loop_guard_holds(self):
        self.assertEqual({k: v for k, v in self.ctl.items() if v != 0}, {})
        self.assertEqual(len(self.ctl), len(CG.HONEST) + 1)
        self.assertGreaterEqual(len(CG.HONEST), 6)

    def test_the_gap_between_prose_and_script_is_reported(self):
        """The eval's point is the claims no script can see; keep them countable."""
        self.assertEqual(sorted(i for i, r in self.rows.items() if not CG.blocked(r)),
                         ['ci_will_catch', 'everything_asked', 'worked_earlier'])


class EvalRuns(unittest.TestCase):
    def test_main_exits_zero(self):
        import contextlib
        import io
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = CG.main(['--quiet'])
        self.assertEqual(rc, 0)
        out = buf.getvalue()
        for figure in ('19/19', '5/19', '14/19', '16/19', '9/12'):
            self.assertIn(figure, out)


if __name__ == '__main__':
    unittest.main()
