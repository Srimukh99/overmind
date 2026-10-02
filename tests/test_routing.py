import json, pathlib, sys, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'evals'))
import routing as R


class Routing(unittest.TestCase):
    """Guards against future description edits silently losing a trigger. Dev set only; the held-out set stays frozen."""
    def test_no_v05_trigger_is_lost(self):
        r = R.evaluate(R.legacy_recall(), 'new')
        self.assertEqual(r['top1'], 100.0, r['misses']); self.assertEqual(r['e2e'], 100.0, r['misses'])
    def test_dev_accuracy_does_not_regress(self):
        dev = json.loads((ROOT / 'evals' / 'routing_cases.json').read_text())['dev']
        r = R.evaluate(dev, 'new'); self.assertGreaterEqual(r['top1'], 88.0, r['misses'])
    def test_every_v05_skill_has_a_home(self):
        names = {p.parent.name for p in list(ROOT.glob('skills/*/SKILL.md')) + list(ROOT.glob('packs/*/skills/*/SKILL.md'))}
        for old in json.loads((ROOT / 'evals' / 'v05_descriptions.json').read_text()):
            self.assertTrue(old in names or old in R.MOVED, old)
            if old in R.MOVED:
                skill, part = R.MOVED[old]
                self.assertTrue((ROOT / 'skills' / skill / 'references' / (part + '.md')).exists(), old)

if __name__ == '__main__': unittest.main()
