import os, pathlib, shutil, sys, tempfile, unittest
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'tools'))
import check_layout as CL, lint_skills as LS


class Layout(unittest.TestCase):
    def test_repo_layout_is_clean(self):
        errors, scripts = CL.run(ROOT)
        self.assertEqual(errors, [])
        on_disk = len(list(ROOT.glob('skills/*/scripts/*.py')) + list(ROOT.glob('packs/*/skills/*/scripts/*.py')))
        self.assertEqual(scripts, on_disk)
    def test_lint_is_clean(self): self.assertEqual(LS.main(), 0)
    def test_core_is_at_most_14(self): self.assertLessEqual(len(list((ROOT / 'skills').glob('*/SKILL.md'))), 14)
    def test_every_pack_skill_is_in_a_pack(self):
        names = {p.parent.name for p in (ROOT / 'packs').glob('*/skills/*/SKILL.md')}
        self.assertEqual(len(names), 14); self.assertFalse(names & {p.parent.name for p in (ROOT / 'skills').glob('*/SKILL.md')})

    def copy(self):
        d = tempfile.mkdtemp(); shutil.copytree(ROOT, d + '/r', ignore=shutil.ignore_patterns('.git', '__pycache__', '.rubric'))
        self.addCleanup(shutil.rmtree, d); return pathlib.Path(d) / 'r'
    def test_detects_retired_name(self):
        r = self.copy(); p = r / 'skills' / 'delegate' / 'SKILL.md'; p.write_text(p.read_text() + '\nRun `hunt` first.\n')
        self.assertTrue(any('retired skill `hunt`' in e for e in CL.run(r)[0]))
    def test_detects_unreachable_script(self):
        r = self.copy(); (r / 'skills' / 'review' / 'scripts').mkdir(); (r / 'skills' / 'review' / 'scripts' / 'orphan.py').write_text('x = 1\n')
        self.assertTrue(any('orphan.py is never mentioned' in e for e in CL.run(r)[0]))
    def test_detects_duplicate_script(self):
        r = self.copy(); (r / 'skills' / 'review' / 'scripts').mkdir(); (r / 'skills' / 'review' / 'scripts' / 'loop.py').write_text('x = 1\n')
        self.assertTrue(any('exists in both' in e for e in CL.run(r)[0]))
    def test_detects_dangling_path(self):
        r = self.copy(); p = r / 'AGENTS.md'; p.write_text(p.read_text() + '\nRun skills/nope/scripts/x.py\n')
        self.assertTrue(any('skills/nope/scripts/x.py' in e for e in CL.run(r)[0]))
    def test_detects_unlisted_reference(self):
        r = self.copy(); (r / 'skills' / 'review' / 'references' / 'extra.md').write_text('# extra\n')
        import io, contextlib
        old = LS.BASE; LS.BASE = r
        try:
            with contextlib.redirect_stdout(io.StringIO()) as out: rc = LS.main()
        finally: LS.BASE = old
        self.assertEqual(rc, 1); self.assertIn('extra.md is not linked', out.getvalue())

if __name__ == '__main__': unittest.main()
