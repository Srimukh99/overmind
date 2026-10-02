import datetime, os, shutil, subprocess, sys, tempfile, unittest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'debug', 'scripts'))
import okf, service_map as SM

TF = ('provider "aws" { region = "us-east-1" }\nresource "aws_lambda_function" "b" { function_name = "billing" }\n'
      'resource "aws_eks_cluster" "m" { name = "prod" }\n')
K8S = 'apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: notify\n  namespace: msg\n'
FLUENT = 'kind: ConfigMap\ndata:\n  output.conf: |\n    [OUTPUT]\n        Name cloudwatch_logs\n        log_group_name /eks/prod/apps\n'


class OKF(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); self.out = os.path.join(self.d, 'docs', 'okf')
        self.w('infra/main.tf', TF); self.w('k8s/n.yaml', K8S); self.w('logging/fluent-bit.yaml', FLUENT)
    def tearDown(self): shutil.rmtree(self.d)
    def w(self, rel, text):
        p = os.path.join(self.d, rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, 'w').write(text)
    def export(self, day=1):
        return okf.export(SM.build(self.d), self.out, datetime.datetime(2026, 10, day, tzinfo=datetime.timezone.utc))
    def read(self, rel): return open(os.path.join(self.out, rel)).read()

    def test_bundle_is_conformant(self):
        self.export(); docs, errors = okf.check(self.out)
        self.assertEqual(errors, []); self.assertGreaterEqual(docs, 9)
    def test_every_doc_has_a_type(self):
        self.export()
        for d, _, fs in os.walk(self.out):
            for f in fs:
                meta, _ = okf.read_meta(os.path.join(d, f)); self.assertTrue(meta and meta.get('type'), f)
    def test_service_doc_says_where_logs_live(self):
        self.export(); t = self.read('services/notify.md')
        self.assertIn('type: "Service"', t); self.assertIn('/eks/prod/apps', t)
        self.assertIn('](../logging/fluent-bit-cloudwatch.md)', t); self.assertIn('](../clusters/prod.md)', t)
    def test_cluster_is_not_a_service(self):
        self.export()
        self.assertFalse(os.path.exists(os.path.join(self.out, 'services', 'prod.md')))
        t = self.read('clusters/prod.md'); self.assertIn('type: "Kubernetes Cluster"', t); self.assertIn('../services/notify.md', t)
    def test_hand_written_docs_survive(self):
        self.export()
        self.w('docs/okf/services/notify-runbook.md', '---\ntype: Runbook\ntitle: Notify runbook\n---\n# Restart\nSteps.\n')
        self.export(2)
        self.assertTrue(os.path.exists(os.path.join(self.out, 'services', 'notify-runbook.md')))
        self.assertIn('notify-runbook.md', self.read('services/index.md'))
    def test_removed_service_is_pruned_and_logged_newest_first(self):
        self.export(1); os.remove(os.path.join(self.d, 'k8s', 'n.yaml')); self.export(2)
        self.assertFalse(os.path.exists(os.path.join(self.out, 'services', 'notify.md')))
        lines = [l for l in self.read('log.md').splitlines() if l.startswith('- ')]
        self.assertTrue(lines[0].startswith('- 2026-10-02') and 'removed notify' in lines[0]); self.assertTrue(lines[1].startswith('- 2026-10-01'))
    def test_check_catches_untyped_doc_and_broken_link(self):
        self.export(); self.w('docs/okf/stray.md', '# no frontmatter\nSee [x](nope.md).\n')
        docs, errors = okf.check(self.out)
        self.assertTrue(any('non-empty type' in e for e in errors)); self.assertTrue(any('nope.md' in e for e in errors))
    def test_cli_flag(self):
        p = subprocess.run([sys.executable, os.path.join(ROOT, 'skills', 'debug', 'scripts', 'service_map.py'), self.d, '--okf', 'kb'],
                           capture_output=True, text=True)
        self.assertIn('conformant', p.stdout); self.assertTrue(os.path.exists(os.path.join(self.d, 'kb', 'index.md')))
    def test_frontmatter_escapes_awkward_values(self):
        path = os.path.join(self.d, 'x.md')
        open(path, 'w').write(okf.frontmatter({'type': 'Service', 'title': 'a: b "c"', 'tags': ['x: y']}) + '# x\n')
        meta, _ = okf.read_meta(path)
        self.assertEqual(meta['title'], 'a: b "c"'); self.assertEqual(meta['tags'], ['x: y'])

if __name__ == '__main__': unittest.main()
