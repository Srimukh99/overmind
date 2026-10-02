"""The guidance-coverage metric must not count noise.

Six measurement defects were found and fixed while building it, and every one
would have changed the verdict:
  - "Mock only slow or external boundaries" scored as boundary-value guidance
  - "improve beyond the test" scored as out-of-range guidance
  - "Partial mocks fail silently" scored as partial-last-chunk guidance
  - "every change" / "everything" matched an \\bevery clause
  - "zero, empty, nil ... input" was MISSED, under-crediting superpowers
  - "locale is out of scope" scored as locale coverage
These tests keep each one fixed.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'evals'))
import guidance_coverage as GC  # noqa: E402


def hits(text, classes=None):
    """Which classes a snippet scores, via the real scanner."""
    import tempfile
    with tempfile.TemporaryDirectory() as d:
        os.makedirs(os.path.join(d, 'skills', 'build', 'references'))
        open(os.path.join(d, 'skills', 'build', 'SKILL.md'), 'w').close()
        with open(os.path.join(d, 'skills', 'build', 'references', 'prove-it.md'), 'w') as fh:
            fh.write(text)
        found = GC.scan(d, GC.LIBS['rubric'], classes)
    return {k for k, v in found.items() if v}


class RejectsNoise(unittest.TestCase):
    def test_mock_boundaries_is_not_boundary_guidance(self):
        self.assertNotIn('boundary', hits('Mock only slow or external boundaries: network, clock.\n'))

    def test_beyond_the_test_is_not_out_of_range(self):
        self.assertNotIn('out_of_range', hits('Do not improve beyond the test.\n'))

    def test_partial_mocks_is_not_partial_last_chunk(self):
        self.assertNotIn('partial_last', hits('Partial mocks fail silently downstream.\n'))

    def test_everything_does_not_match(self):
        self.assertEqual(hits('Manual does not prove edge cases; retest everything.\n'), set())

    def test_excluded_class_does_not_score(self):
        text = ('This table stops at what a unit test can reach. Races, locale and\n'
                'resource exhaustion are real and are not here: they belong to observe.\n')
        self.assertNotIn('locale', hits(text, GC.EXTENDED))


class AcceptsRealGuidance(unittest.TestCase):
    def test_boundary_case_counts(self):
        self.assertIn('boundary', hits('Test each argument, boundary case, or broken contract.\n'))

    def test_zero_empty_nil_input_counts(self):
        """The line that my first metric wrongly missed in superpowers."""
        self.assertIn('empty', hits('- Missing validation for zero, empty, nil, or malformed input\n'))

    def test_half_open_counts(self):
        self.assertIn('boundary', hits('| Boundary | Is the range half-open or closed? |\n'))

    def test_rounding_counts(self):
        self.assertIn('numeric_type', hits('| Numeric type | Which way does it round? Money in integer cents? |\n'))


class RubricCoversTheCoreClasses(unittest.TestCase):
    def test_prove_it_names_every_core_class(self):
        """Regression guard: prove-it.md's boundary table must not be thinned out."""
        found = GC.scan(ROOT, GC.LIBS['rubric'])
        missing = [c for c in GC.CLASSES if not found[c]]
        self.assertEqual(missing, [], 'prove-it.md stopped naming: %s' % missing)


if __name__ == '__main__':
    unittest.main()


class ReachabilityMappingIsCurrent(unittest.TestCase):
    """The defect->class mapping must describe the suites as they are now."""

    def test_every_failing_hidden_test_is_mapped(self):
        failing = GC.real_defects()
        self.assertTrue(failing, 'the thin candidates stopped failing; the fixture is broken')
        unmapped = sorted({n for _, n in failing if n not in GC.DEFECT_CLASS})
        self.assertEqual(unmapped, [], 'unmapped failing tests: %s' % unmapped)

    def test_every_mapped_class_exists_in_the_taxonomy(self):
        unknown = sorted({c for c in GC.DEFECT_CLASS.values() if c not in GC.CLASSES})
        self.assertEqual(unknown, [], 'mapping references unknown classes: %s' % unknown)

    def test_rubric_guidance_reaches_every_measured_defect(self):
        """Regression guard for the boundary table's practical coverage."""
        found = GC.scan(ROOT, GC.LIBS['rubric'])
        failing = GC.real_defects()
        missed = sorted({GC.DEFECT_CLASS[n] for _, n in failing
                         if not found.get(GC.DEFECT_CLASS[n])})
        self.assertEqual(missed, [], 'guidance no longer names: %s' % missed)
