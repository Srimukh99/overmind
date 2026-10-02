#!/usr/bin/env python3
"""Code quality eval: does a green test suite predict correct code?

Each task ships a spec, a `visible` suite of the kind an implementer writes from
that spec, a `hidden` acceptance suite covering edge cases the spec implies, and
two candidate implementations:

  thin   passes every visible test and fails hidden ones
  solid  passes both

For each candidate this measures three things an implementer could know *before*
seeing the hidden suite:

  visible   the suite the implementer wrote - the usual definition of "done"
  mutation  of the bugs injectable into the implementation, how many the
            visible suite catches (skills/build/scripts/mutate.py)
  hidden    the acceptance suite, withheld from the implementer - ground truth

The question is which of the first two predicts the third. A methodology that
stops at "visible is green" ships `thin`. One that requires a mutation score
rejects it before anyone sees the hidden suite.

This eval does not involve any model. It scores implementations, so it can score
anything that produces them, including an agent run - that comparison needs a
model API key and lives outside this repository.

Run: python3 evals/code_quality.py [-v]
Stdlib only; no pytest required.
"""
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUBRIC = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(RUBRIC, 'skills', 'build', 'scripts'))
import mutate as M  # noqa: E402

TASKS = {}

# ---------------------------------------------------------------- discount
TASKS['discount'] = {
    'spec': 'apply_discount(cents, code): SAVE10 takes 10% off, FREESHIP takes '
            '500 off and never goes below zero, unknown codes raise ValueError. '
            'Money is integer cents.',
    'module': 'discount',
    'thin': '''def apply_discount(cents, code):
    if code == "SAVE10":
        return cents - cents * 10 / 100
    if code == "FREESHIP":
        return cents - 500
    raise ValueError(code)
''',
    'solid': '''def apply_discount(cents, code):
    if code == "SAVE10":
        return cents - cents * 10 // 100
    if code == "FREESHIP":
        return max(0, cents - 500)
    raise ValueError(code)
''',
    'visible': '''import unittest
from discount import apply_discount


class VisibleTest(unittest.TestCase):
    def test_save10(self):
        self.assertEqual(apply_discount(1000, "SAVE10"), 900)

    def test_freeship(self):
        self.assertEqual(apply_discount(1000, "FREESHIP"), 500)

    def test_unknown_raises(self):
        with self.assertRaises(ValueError):
            apply_discount(100, "NOPE")
''',
    'hidden': '''import unittest
from discount import apply_discount


class HiddenTest(unittest.TestCase):
    def test_freeship_never_negative(self):
        self.assertEqual(apply_discount(300, "FREESHIP"), 0)

    def test_money_stays_integer(self):
        self.assertIsInstance(apply_discount(1000, "SAVE10"), int)

    def test_rounds_down_not_to_float(self):
        self.assertEqual(apply_discount(999, "SAVE10"), 900)

    def test_tiny_amount(self):
        self.assertEqual(apply_discount(1, "SAVE10"), 1)
''',
}

# ---------------------------------------------------------------- overlap
TASKS['overlap'] = {
    'spec': 'overlaps(a_start, a_end, b_start, b_end): do two half-open '
            'intervals [start, end) overlap? Touching intervals do not.',
    'module': 'ranges',
    'thin': '''def overlaps(a_start, a_end, b_start, b_end):
    return a_start <= b_end and b_start <= a_end
''',
    'solid': '''def overlaps(a_start, a_end, b_start, b_end):
    if a_start >= a_end or b_start >= b_end:
        return False
    return a_start < b_end and b_start < a_end
''',
    'visible': '''import unittest
from ranges import overlaps


class VisibleTest(unittest.TestCase):
    def test_clear_overlap(self):
        self.assertTrue(overlaps(0, 10, 5, 15))

    def test_clear_gap(self):
        self.assertFalse(overlaps(0, 5, 10, 15))

    def test_contained(self):
        self.assertTrue(overlaps(0, 10, 2, 4))
''',
    'hidden': '''import unittest
from ranges import overlaps


class HiddenTest(unittest.TestCase):
    def test_touching_is_not_overlap(self):
        self.assertFalse(overlaps(0, 5, 5, 10))

    def test_touching_the_other_way(self):
        self.assertFalse(overlaps(5, 10, 0, 5))

    def test_empty_interval_never_overlaps(self):
        self.assertFalse(overlaps(5, 5, 0, 10))
''',
}

# ---------------------------------------------------------------- pagination
TASKS['pagination'] = {
    'spec': 'page_slice(total, per_page, page) -> (offset, limit): the slice for '
            'a 1-based page. The last page may be short; a page past the end is '
            'empty.',
    'module': 'paging',
    'thin': '''def page_slice(total, per_page, page):
    return ((page - 1) * per_page, per_page)
''',
    'solid': '''def page_slice(total, per_page, page):
    offset = max(0, (page - 1) * per_page)
    if offset >= total:
        return (total, 0)
    return (offset, min(per_page, total - offset))
''',
    'visible': '''import unittest
from paging import page_slice


class VisibleTest(unittest.TestCase):
    def test_first_page(self):
        self.assertEqual(page_slice(100, 10, 1), (0, 10))

    def test_second_page(self):
        self.assertEqual(page_slice(100, 10, 2), (10, 10))

    def test_middle_page(self):
        self.assertEqual(page_slice(100, 10, 5), (40, 10))
''',
    'hidden': '''import unittest
from paging import page_slice


class HiddenTest(unittest.TestCase):
    def test_short_last_page(self):
        self.assertEqual(page_slice(95, 10, 10), (90, 5))

    def test_page_past_the_end_is_empty(self):
        self.assertEqual(page_slice(100, 10, 11), (100, 0))

    def test_fewer_items_than_one_page(self):
        self.assertEqual(page_slice(5, 10, 1), (0, 5))
''',
}


def _suite(workdir, module, impl, tests):
    """Lay out a throwaway package with one implementation and one suite."""
    os.makedirs(os.path.join(workdir, 'tests'), exist_ok=True)
    # unittest's -t . requires tests/ to be an importable package.
    open(os.path.join(workdir, 'tests', '__init__.py'), 'a').close()
    path = os.path.join(workdir, module + '.py')
    with open(path, 'w', encoding='utf-8') as fh:
        fh.write(impl)
    with open(os.path.join(workdir, 'tests', 'test_%s.py' % module), 'w', encoding='utf-8') as fh:
        fh.write(tests)
    return path


def _run(workdir):
    cmd = [sys.executable, '-m', 'unittest', 'discover', '-q', '-s', 'tests', '-t', '.']
    env = {**os.environ, 'PYTHONPATH': workdir, 'PYTHONBREAKPOINT': '0'}
    p = subprocess.run(cmd, cwd=workdir, capture_output=True, text=True, env=env,
                       stdin=subprocess.DEVNULL, timeout=120)
    return p.returncode, (p.stdout or '') + (p.stderr or '')


def _count(output):
    """(ran, failed) from unittest's summary."""
    ran = failed = 0
    for line in output.splitlines():
        if line.startswith('Ran ') and ' test' in line:
            ran = int(line.split()[1])
        if line.startswith('FAILED'):
            inside = line[line.find('(') + 1:line.rfind(')')]
            for part in inside.split(','):
                if '=' in part:
                    failed += int(part.split('=')[1])
    return ran, failed


def score(name, task, variant, verbose=False):
    with tempfile.TemporaryDirectory(prefix='rubric-cq-') as d:
        impl = task[variant]

        # 1. the suite the implementer wrote
        path = _suite(d, task['module'], impl, task['visible'])
        vis_rc, vis_out = _run(d)
        vis_ran, vis_failed = _count(vis_out)

        # 2. how much of that suite is real, measured without the hidden suite
        test_cmd = '%s -m unittest discover -q -s tests -t .' % sys.executable
        mut = M.run(path, test_cmd, d, max_mutants=40, timeout=60)

        # 3. ground truth, withheld from the implementer
        _suite(d, task['module'], impl, task['hidden'])
        hid_rc, hid_out = _run(d)
        hid_ran, hid_failed = _count(hid_out)

        if verbose and hid_failed:
            for line in hid_out.splitlines():
                if line.startswith('FAIL:') or line.startswith('ERROR:'):
                    print('      %s %-6s %s' % (name, variant, line.strip()))

        killed, tested = mut['killed'], max(mut['tested'], 1)
        return {
            'visible_ok': vis_rc == 0,
            'visible': '%d/%d' % (vis_ran - vis_failed, vis_ran),
            'mutation': round(100 * killed / tested),
            'mutants': '%d/%d' % (killed, tested),
            'hidden_ok': hid_rc == 0,
            'hidden': '%d/%d' % (hid_ran - hid_failed, hid_ran),
            'hidden_failed': hid_failed,
        }


def main(argv=None):
    verbose = '-v' in (argv if argv is not None else sys.argv[1:])
    rows = []
    print('Scoring %d tasks x 2 candidates. "visible" is what the implementer' % len(TASKS))
    print('could see; "hidden" is ground truth they could not.\n')
    print('%-12s %-6s %-14s %-18s %s' % ('task', 'cand', 'visible suite', 'mutation score', 'hidden suite'))
    print('-' * 74)
    for name, task in TASKS.items():
        for variant in ('thin', 'solid'):
            r = score(name, task, variant, verbose)
            rows.append((name, variant, r))
            print('%-12s %-6s %-14s %-18s %s' % (
                name, variant,
                '%s %s' % (r['visible'], 'PASS' if r['visible_ok'] else 'FAIL'),
                '%3d%% (%s)' % (r['mutation'], r['mutants']),
                '%s %s' % (r['hidden'], 'PASS' if r['hidden_ok'] else 'FAIL')))

    thin = [r for _, v, r in rows if v == 'thin']
    solid = [r for _, v, r in rows if v == 'solid']
    print()
    print('A green visible suite as a predictor of correctness')
    print('  thin  candidates with a green visible suite: %d of %d' % (
        sum(r['visible_ok'] for r in thin), len(thin)))
    print('  ... of those, how many are actually correct: %d' % sum(
        r['hidden_ok'] for r in thin if r['visible_ok']))
    print('  -> visible-green carries no information about correctness here')
    print()
    print('Mutation score as a predictor')
    print('  thin  mutation scores: %s  (mean %d%%)' % (
        ', '.join('%d%%' % r['mutation'] for r in thin),
        sum(r['mutation'] for r in thin) // len(thin)))
    print('  solid mutation scores: %s  (mean %d%%)' % (
        ', '.join('%d%%' % r['mutation'] for r in solid),
        sum(r['mutation'] for r in solid) // len(solid)))
    sep = min(r['mutation'] for r in solid) > max(r['mutation'] for r in thin)
    print('  -> mutation score separates thin from solid: %s' % ('yes' if sep else 'no, not cleanly'))
    print()
    print('hidden defects a visible-green suite would have shipped: %d' % sum(
        r['hidden_failed'] for r in thin))
    return 0


if __name__ == '__main__':
    sys.exit(main())
