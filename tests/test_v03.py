import os, sys, shutil, tempfile, unittest, io, contextlib
from unittest import mock
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'debug', 'scripts'))
sys.path.insert(0, os.path.join(ROOT, 'skills', 'legal-traps', 'scripts'))
import service_map as SM, log_fetch as LF, legal_traps as LT
import backends as B


def w(root, rel, text):
    p = os.path.join(root, rel); os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as fh: fh.write(text)

TF = '''provider "aws" { region = "us-east-1" }
resource "aws_lambda_function" "b" { function_name = "billing" }
resource "aws_ecs_service" "c" { name = "checkout" }
resource "aws_eks_cluster" "m" { name = "prod" }
'''
K8S = '''apiVersion: apps/v1
kind: Deployment
metadata:
  name: notify
  namespace: msg
'''
FLUENT = '''kind: ConfigMap
data:
  output.conf: |
    [OUTPUT]
        Name cloudwatch_logs
        log_group_name /eks/prod/apps
'''


class LogFetch(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp(); w(self.d, 'infra/main.tf', TF); w(self.d, 'k8s/n.yaml', K8S)
        # Backend detection scores installed CLIs and cloud env vars on top of repo
        # signals, so an `aws` binary on PATH (every GitHub runner has one) takes
        # _aws_detect to 3 and outranks the aggregator bonus these tests are about.
        # Pin both to absent so only the signals each test passes in decide.
        for p in (mock.patch.object(B, '_cli', lambda name: False),
                  mock.patch.object(B, '_env_any', lambda *names: False)):
            p.start(); self.addCleanup(p.stop)
    def tearDown(self): shutil.rmtree(self.d)
    def svc(self, name): return SM.build(self.d)['services'][name]

    def test_lambda_log_group(self): self.assertEqual(self.svc('billing')['log_group'], '/aws/lambda/billing')
    def test_ecs_log_group(self): self.assertEqual(self.svc('checkout')['log_group'], '/ecs/checkout')
    def test_bare_k8s_inherits_cluster_cloud(self):
        s = self.svc('notify'); self.assertEqual(s['cloud'], 'aws'); self.assertIn('/aws/containerinsights/prod', s['log_group'])
    def test_fluentbit_sets_destination(self):
        w(self.d, 'logging/fluent-bit.yaml', FLUENT); s = self.svc('notify')
        self.assertEqual(s['shipper'], 'fluent-bit'); self.assertEqual(s['ships_to'], ['cloudwatch'])
        self.assertEqual(s['log_group'], '/eks/prod/apps')
    def test_cluster_shipper_skips_ecs(self):
        w(self.d, 'logging/fluent-bit.yaml', FLUENT); self.assertNotIn('shipper', self.svc('checkout'))
    def test_vector_detected(self):
        w(self.d, 'logging/vector.toml', '[sinks.out]\ntype = "loki"\n')
        self.assertEqual(self.svc('notify')['ships_to'], ['loki'])
    def test_map_ignores_own_cache(self):
        w(self.d, '.overmind/services.json', '{"x": "promtail"}')
        self.assertNotIn('agent_promtail', SM.build(self.d)['signals'])
    def pick(self, name, signals):
        data = SM.build(self.d); usable, _ = LF.choose_backend(data['services'][name], signals)
        return usable[0][1]['key'] if usable else None
    def test_serverless_stays_native_with_aggregator(self):
        self.assertEqual(self.pick('billing', {'provider_aws': 'x', 'agent_loki': 'y'}), 'cloudwatch')
    def test_container_prefers_aggregator(self):
        self.assertEqual(self.pick('notify', {'provider_aws': 'x', 'agent_loki': 'y'}), 'loki')
    def test_shipper_beats_aggregator_signal(self):
        w(self.d, 'logging/fluent-bit.yaml', FLUENT)
        self.assertEqual(self.pick('notify', {'provider_aws': 'x', 'agent_loki': 'y'}), 'cloudwatch')
    def test_fuzzy_resolve(self):
        self.assertEqual(LF.resolve_service({'notification-service': {}}, 'notification')[0], 'notification-service')
    def test_dry_run_never_executes(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out): rc = LF.main(['billing', '--repo', self.d, '--dry-run'])
        self.assertEqual(rc, 0); self.assertIn('aws logs tail /aws/lambda/billing', out.getvalue())


class LegalTraps(unittest.TestCase):
    def setUp(self): self.d = tempfile.mkdtemp()
    def tearDown(self): shutil.rmtree(self.d)
    def rules(self): return {h['rule'] for h in LT.scan(self.d)}

    def test_google_fonts(self):
        w(self.d, 'a.html', '<link href="https://fonts.googleapis.com/css2?family=Inter">'); self.assertIn('remote-google-fonts', self.rules())
    def test_ignore_comment(self):
        w(self.d, 'a.html', '<link href="https://fonts.googleapis.com/x"> <!-- legal-traps: ignore -->'); self.assertNotIn('remote-google-fonts', self.rules())
    def test_session_replay(self):
        w(self.d, 'a.html', '<script src="https://static.hotjar.com/c.js"></script>'); self.assertIn('session-replay', self.rules())
    def test_uploads_need_dmca(self):
        w(self.d, 'u.html', '<input type="file">'); self.assertIn('uploads-no-dmca', self.rules())
        w(self.d, 'dmca.html', 'Our DMCA designated agent'); self.assertNotIn('uploads-no-dmca', self.rules())
    def test_email_unsubscribe_and_address(self):
        w(self.d, 'm.ts', "resend.emails.send({html:'hi'})"); r = self.rules()
        self.assertIn('email-no-unsubscribe', r); self.assertIn('email-no-address', r)
    def test_subscription_cancel(self):
        w(self.d, 'b.ts', 'stripe.subscriptions.create({})'); self.assertIn('subscription-no-cancel', self.rules())
        w(self.d, 'p.ts', 'stripe.billingPortal.sessions.create({})'); self.assertNotIn('subscription-no-cancel', self.rules())
    def test_prechecked_age(self):
        w(self.d, 'a.html', '<input type="checkbox" checked> I am over 13'); self.assertIn('prechecked-age', self.rules())
    def test_docs_do_not_trigger(self):
        w(self.d, 'README.md', 'we use fonts.googleapis.com and hotjar'); self.assertEqual(self.rules(), set())

if __name__ == '__main__': unittest.main()
