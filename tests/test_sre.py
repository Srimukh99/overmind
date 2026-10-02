"""Tests for log-trace, iac-check, crd-check, drift and vibe-check extra checks."""
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
HOME = {"log-trace": "skills/debug", "vibe-check": "skills/ship", "iac-check": "skills/iac-check",
        "crd-check": "packs/k8s/skills/crd-check", "drift": "packs/k8s/skills/drift"}


def load(skill, module):
    spec = importlib.util.spec_from_file_location(module, ROOT / HOME[skill] / "scripts" / f"{module}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


lt = load("log-trace", "log_trace")
iac = load("iac-check", "iac_check")
crd = load("crd-check", "crd_check")
drift = load("drift", "drift_check")
vc = load("vibe-check", "vibe_check")


def write(root, files):
    for name, content in files.items():
        p = pathlib.Path(root, name)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(textwrap.dedent(content))


class LogTraceTests(unittest.TestCase):
    def test_python_lambda(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"app/handlers/orders.py": "x=1\n",
                      "infra/lambda.tf": 'resource "aws_lambda_function" "o" {\n  function_name = "orders-api"\n}\n'})
            log = ("START RequestId: 8f3a1c2e-1111-2222-3333-444455556666 Version: $LATEST\n"
                   "[ERROR] KeyError: 'DB_HOST'\nTraceback (most recent call last):\n"
                   '  File "/var/runtime/bootstrap.py", line 60, in handle\n'
                   '  File "/var/task/app/handlers/orders.py", line 42, in get_order\n'
                   "logGroup=/aws/lambda/orders-api\n")
            r = lt.analyze(log, d)
            self.assertEqual(r["runtime"], "lambda")
            self.assertEqual(r["error"]["type"], "KeyError")
            self.assertIn("config/missing", r["categories"])
            self.assertEqual(r["start_here"]["repo_path"], "app/handlers/orders.py")
            self.assertEqual(r["app"]["name"], "orders-api")
            self.assertTrue(r["app"]["iac"].startswith("infra/lambda.tf"))

    def test_java_kubernetes_oom(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"src/main/java/com/acme/pay/Ledger.java": "class Ledger{}\n",
                      "deploy/app.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: payments\n"})
            log = ("payments-7d9f8b6c5d-x2k9p Exception in thread main java.lang.OutOfMemoryError: Java heap space\n"
                   "\tat com.acme.pay.Ledger.post(Ledger.java:88)\n\tat java.base/java.util.ArrayList.add(ArrayList.java:455)\n"
                   "Last State: Terminated Reason: OOMKilled\n")
            r = lt.analyze(log, d)
            self.assertEqual(r["runtime"], "kubernetes")
            self.assertIn("out-of-memory", r["categories"])
            self.assertEqual(r["start_here"]["repo_path"], "src/main/java/com/acme/pay/Ledger.java")
            self.assertEqual(r["app"]["name"], "payments")
            self.assertTrue(any("OOMKilled" in s for s in r["next_steps"]))

    def test_node_ecs_connection(self):
        with tempfile.TemporaryDirectory() as d:
            write(d, {"src/db.js": "//\n", "infra/ecs.tf": 'resource "aws_ecs_service" "api" {}\n'})
            log = ("Error: connect ECONNREFUSED 10.0.1.5:5432\n    at connect (/usr/src/app/src/db.js:14:11)\n"
                   "    at node:internal/process/task_queues:95:5\nlogGroup=/ecs/api\n")
            r = lt.analyze(log, d)
            self.assertEqual(r["runtime"], "ecs")
            self.assertIn("connection", r["categories"])
            self.assertEqual(r["start_here"]["repo_path"], "src/db.js")


class IacCheckTests(unittest.TestCase):
    def rules(self, files):
        with tempfile.TemporaryDirectory() as d:
            write(d, files)
            findings, _ = iac.scan([d])
            return {(f["level"], f["rule"]) for f in findings}

    def test_terraform_public_exposure(self):
        r = self.rules({"main.tf": """
            resource "aws_security_group" "db" {
              ingress {
                from_port   = 22
                to_port     = 22
                cidr_blocks = ["0.0.0.0/0"]
              }
            }
            resource "aws_db_instance" "m" {
              publicly_accessible = true
            }
            resource "aws_iam_policy" "p" {
              policy = jsonencode({ Statement = [{ "Action": "*", Resource = "*" }] })
            }
            """})
        self.assertIn(("FAIL", "sg-open-sensitive"), r)
        self.assertIn(("FAIL", "rds-public"), r)
        self.assertIn(("FAIL", "iam-wildcard-action"), r)

    def test_public_https_is_only_ok(self):
        r = self.rules({"lb.tf": """
            resource "aws_security_group" "web" {
              ingress {
                from_port   = 443
                to_port     = 443
                cidr_blocks = ["0.0.0.0/0"]
              }
            }
            """})
        self.assertFalse(any(rule.startswith("sg-") for _, rule in r))

    def test_k8s_and_docker(self):
        r = self.rules({
            "k.yaml": "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: a\nspec:\n  template:\n    spec:\n      containers:\n        - name: a\n          image: a:latest\n          securityContext:\n            privileged: true\n",
            "Dockerfile": "FROM python:3.12\nENV API_TOKEN=abc123456\n"})
        self.assertIn(("FAIL", "k8s-privileged"), r)
        self.assertIn(("WARN", "k8s-latest-tag"), r)
        self.assertIn(("FAIL", "docker-secret"), r)
        self.assertIn(("WARN", "docker-root"), r)

    def test_ignore_marker(self):
        r = self.rules({"x.tf": 'resource "aws_db_instance" "m" {\n  # iac-check: ignore  (sandbox)\n  publicly_accessible = true\n}\n'})
        self.assertEqual(r, set())


CRD = """
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: widgets.example.com
spec:
  group: example.com
  scope: Namespaced
  names: {plural: widgets, singular: widget, kind: Widget}
  versions:
    - name: v1
      served: true
      storage: true
      subresources: {status: {}}
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: [size]
              properties:
                size: {type: integer}
                tier: {type: string, enum: [gold, silver]}
            status: {type: object}
"""


class CrdCheckTests(unittest.TestCase):
    def findings(self, files, target="1.31"):
        with tempfile.TemporaryDirectory() as d:
            write(d, files)
            f, _, _ = crd.scan([d], target)
            return {(x["level"], x["rule"]) for x in f}

    def test_valid_crd_and_cr(self):
        cr = "apiVersion: example.com/v1\nkind: Widget\nmetadata: {name: w}\nspec:\n  size: 3\n  tier: gold\n"
        self.assertEqual(self.findings({"crd.yaml": CRD, "cr.yaml": cr}), set())

    def test_cr_typo_enum_required_version(self):
        cr = ("apiVersion: example.com/v1\nkind: Widget\nmetadata: {name: w}\nspec:\n  sise: 3\n  tier: bronze\n---\n"
              "apiVersion: example.com/v2\nkind: Widget\nmetadata: {name: w2}\n")
        f = self.findings({"crd.yaml": CRD, "cr.yaml": cr})
        self.assertIn(("WARN", "cr-unknown-field"), f)
        self.assertIn(("FAIL", "cr-enum"), f)
        self.assertIn(("FAIL", "cr-required"), f)
        self.assertIn(("FAIL", "cr-unknown-version"), f)

    def test_bad_crd(self):
        bad = CRD.replace("name: widgets.example.com", "name: widget.example.com").replace("storage: true", "storage: false")
        f = self.findings({"crd.yaml": bad})
        self.assertIn(("FAIL", "crd-name"), f)
        self.assertIn(("FAIL", "crd-storage"), f)

    def test_removed_api_depends_on_target(self):
        m = {"cj.yaml": "apiVersion: batch/v1beta1\nkind: CronJob\nmetadata: {name: x}\n"}
        self.assertIn(("FAIL", "k8s-removed-api"), self.findings(m, "1.25"))
        self.assertIn(("WARN", "k8s-removed-api"), self.findings(m, "1.24"))


class DriftTests(unittest.TestCase):
    def test_parse_tf_plan(self):
        plan = ("Note: Objects have changed outside of Terraform\n"
                "  # aws_security_group.web has changed\n"
                "  # aws_instance.api will be updated in-place\n"
                "  # aws_db_instance.main must be replaced\n"
                "Plan: 1 to add, 1 to change, 1 to destroy.\n")
        r = drift.parse_tf_plan(plan)
        self.assertEqual(r["actions"]["update"], ["aws_instance.api"])
        self.assertEqual(r["actions"]["replace"], ["aws_db_instance.main"])
        self.assertIn("aws_security_group.web", r["actions"]["changed-outside-terraform"])
        self.assertTrue(r["outside_changes"])

    def test_workloads_desired_vs_current(self):
        data = {"items": [
            {"kind": "Deployment", "metadata": {"name": "api", "namespace": "prod", "generation": 5},
             "spec": {"replicas": 3},
             "status": {"observedGeneration": 5, "readyReplicas": 1, "updatedReplicas": 3,
                        "conditions": [{"type": "Progressing", "reason": "ProgressDeadlineExceeded"}]}},
            {"kind": "Deployment", "metadata": {"name": "ok", "namespace": "prod", "generation": 2},
             "spec": {"replicas": 2}, "status": {"observedGeneration": 2, "readyReplicas": 2, "updatedReplicas": 2}}]}
        p = drift.summarize_workloads(data)
        self.assertEqual(len(p), 1)
        self.assertIn("1/3 ready", p[0]["issues"])
        self.assertIn("rollout stuck (ProgressDeadlineExceeded)", p[0]["issues"])

    def test_pods_and_gitops(self):
        pods = {"items": [{"metadata": {"name": "api-1", "namespace": "prod"}, "status": {"phase": "Running",
                 "containerStatuses": [{"restartCount": 7, "state": {"waiting": {"reason": "CrashLoopBackOff"}},
                                        "lastState": {"terminated": {"reason": "OOMKilled"}}}]}}]}
        bad = drift.summarize_pods(pods)
        self.assertIn("CrashLoopBackOff", bad[0]["issues"])
        self.assertIn("OOMKilled (last restart)", bad[0]["issues"])
        argo = {"items": [{"metadata": {"name": "web"}, "status": {"sync": {"status": "OutOfSync"}, "health": {"status": "Healthy"}}}]}
        self.assertEqual(drift.summarize_gitops(argo, None)[0]["resource"], "argocd/web")

    def test_kubectl_diff_parse(self):
        text = "diff -u -N /tmp/LIVE-123/apps.v1.Deployment.prod.api /tmp/MERGED-123/apps.v1.Deployment.prod.api\n"
        self.assertEqual(drift.parse_kubectl_diff(text), ["apps.v1.Deployment.prod.api"])


class VibeExtraChecksTests(unittest.TestCase):
    def test_extra_checks_run_and_fail(self):
        with tempfile.TemporaryDirectory() as d:
            pathlib.Path(d, "checks").write_text("# comment\ntrue\nfalse\n")
            r = vc.extra_checks(d, "checks")  # path is resolved against the repo root
            self.assertEqual(r, [("PASS", "true"), ("FAIL", "false")])


if __name__ == "__main__":
    unittest.main()
