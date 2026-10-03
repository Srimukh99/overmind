"""Tests for the vibe-check gate. Fake secrets are built by concatenation so this file passes the gate."""
import contextlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest
import unittest.mock

HERE = pathlib.Path(__file__).resolve().parent
SCRIPT = HERE.parent / "skills" / "ship" / "scripts" / "vibe_check.py"
sys.path.insert(0, str(SCRIPT.parent))
import vibe_check as vc  # noqa: E402


def levels(line, path="app.py"):
    return [(f[0], f[3]) for f in vc.scan_line(path, 1, line)]


class ScanLineTests(unittest.TestCase):
    def test_aws_key_fails(self):
        self.assertIn(("FAIL", "AWS access key"), levels("key = '" + "AKIA" + "ABCDEFGHIJKLMNOP" + "'"))

    def test_openrouter_key_fails(self):
        self.assertIn(("FAIL", "OpenRouter API key"), levels("key = '" + "sk-or-v1-" + "a" * 64 + "'"))

    def test_anthropic_key_fails(self):
        self.assertIn(("FAIL", "Anthropic API key"), levels("key = '" + "sk-ant-" + "a" * 32 + "'"))

    def test_openai_key_fails(self):
        self.assertIn(("FAIL", "OpenAI API key"), levels("key = '" + "sk-proj-" + "a" * 24 + "'"))

    def test_huggingface_token_fails(self):
        self.assertIn(("FAIL", "HuggingFace token"), levels("key = '" + "hf_" + "a" * 34 + "'"))

    def test_private_key_fails(self):
        self.assertTrue(levels("-----BEGIN " + "RSA PRIVATE KEY-----"))

    def test_real_looking_card_fails(self):
        card = "4539" + "1488" + "0343" + "6467"  # Luhn-valid, not a published test card
        self.assertIn(("FAIL", "Card number (Luhn-valid)"), levels("pan = " + card))

    def test_processor_test_card_allowed(self):
        self.assertEqual(levels("pan = " + "4242" + "4242" + "4242" + "4242"), [])

    def test_non_luhn_number_allowed(self):
        self.assertEqual(levels("order_id = 1234567890123456"), [])

    def test_ssn_fails(self):
        self.assertIn(("FAIL", "US SSN pattern"), levels("ssn: " + "123-45-" + "6789"))

    def test_debugger_and_focused_test_fail(self):
        self.assertIn(("FAIL", "Debugger statement"), levels("    breakpoint()"))
        self.assertIn(("FAIL", "Focused test"), levels("it." + "only('works', () => {})", "a.test.js"))

    def test_conflict_marker_fails(self):
        self.assertIn(("FAIL", "Conflict marker"), levels("<" * 7 + " HEAD"))

    def test_generic_secret_warns_but_placeholder_ok(self):
        self.assertIn(("WARN", "Hard-coded secret-looking value"), levels('password = "' + "q8Zr2LmVx9Tw" + '"'))
        self.assertEqual(levels('password = "changeme-please-now"'), [])

    def test_ignore_marker(self):
        self.assertEqual(levels("ssn " + "123-45-" + "6789  # vibe-check: ignore"), [])


class GitIntegrationTests(unittest.TestCase):
    def run_git(self, cmd, cwd, env=None):
        try:
            return subprocess.run(["git", *cmd], cwd=cwd, check=True, capture_output=True, text=True, env=env)
        except (subprocess.CalledProcessError, FileNotFoundError) as err:
            if sys.platform == "darwin":
                try:
                    return subprocess.run(["arch", "-arm64", "git", *cmd], cwd=cwd, check=True, capture_output=True, text=True, env=env)
                except subprocess.CalledProcessError:
                    pass
            raise err

    def run_in_repo(self, files, *args, run_from=None):
        """Stage `files` in a throwaway repo and run the gate. run_from sets the cwd."""
        with tempfile.TemporaryDirectory() as d:
            env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
            self.run_git(["init", "-q"], cwd=d)
            for name, content in files.items():
                p = pathlib.Path(d, name)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_text(content)
            self.run_git(["add", "-A"], cwd=d, env=env)
            args = [a.replace("{repo}", d) for a in args]
            r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=run_from or d, capture_output=True, text=True, env=env)
            return r.returncode, r.stdout

    def test_clean_staged_changes_pass(self):
        rc, out = self.run_in_repo({"app.py": "print('hello')\n"})
        self.assertEqual(rc, 0, out)
        self.assertIn("1 lines scanned", out)  # the staged line was really read

    def test_staged_secret_and_env_file_fail(self):
        rc, out = self.run_in_repo({"app.py": "k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n", ".env": "X=1\n"})
        self.assertEqual(rc, 1)
        self.assertIn("app.py:1", out)
        self.assertIn("Sensitive file committed", out)

    def test_env_example_allowed(self):
        rc, out = self.run_in_repo({".env.example": "API_URL=\n"})
        self.assertEqual(rc, 0, out)
        self.assertNotIn("Sensitive file committed", out)
        self.assertIn("1 lines scanned", out)

    def test_repo_flag_scans_that_repo_not_the_cwd(self):
        """The gate must follow --repo, not the directory it was launched from."""
        rc, out = self.run_in_repo(
            {"app.py": "k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n"},
            "--repo", "{repo}", run_from=str(HERE),
        )
        self.assertEqual(rc, 1, out)
        self.assertIn("AWS access key", out)

    def test_scans_cwd_repo_when_launched_from_elsewhere(self):
        """Default --repo is the cwd, so an installed copy still scans the project."""
        rc, out = self.run_in_repo({"app.py": "k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n"})
        self.assertEqual(rc, 1, out)
        self.assertIn("AWS access key", out)


class StopHookTests(unittest.TestCase):
    """The Stop hook: what it scans, where it reports, and how it stops looping."""

    def repo(self, commit="app.py"):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        env = {**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
               "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"}
        self.env = env
        self.git(["init", "-q", "."], d)
        if commit:
            pathlib.Path(d, commit).write_text("x = 1\n")
            self.git(["add", "-A"], d)
            self.git(["commit", "-qm", "base"], d)
        return d

    def git(self, args, cwd):
        return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                              text=True, env=getattr(self, "env", None))

    def gate(self, cwd, *args, payload=""):
        r = subprocess.run([sys.executable, str(SCRIPT), *args], cwd=cwd, input=payload,
                           capture_output=True, text=True, env=getattr(self, "env", None))
        return r.returncode, r.stdout, r.stderr

    def test_unstaged_change_blocks_the_turn(self):
        d = self.repo()
        pathlib.Path(d, "app.py").write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n")
        rc, out, err = self.gate(d, "--stop-hook")
        self.assertEqual(rc, 2, err)
        self.assertIn("AWS access key", err)
        self.assertIn("not provably done", err)

    def test_findings_go_to_stderr_only(self):
        """A blocking Stop hook hands the agent stderr; stdout is not read back."""
        d = self.repo()
        pathlib.Path(d, "app.py").write_text("    breakpoint()\n")
        rc, out, err = self.gate(d, "--stop-hook")
        self.assertEqual(rc, 2)
        self.assertEqual(out, "")
        self.assertIn("Debugger statement", err)

    def test_new_untracked_file_is_scanned(self):
        d = self.repo()
        pathlib.Path(d, "new.py").write_text("ssn = '" + "123-45-" + "6789'\n")
        rc, _, err = self.gate(d, "--stop-hook")
        self.assertEqual(rc, 2, err)
        self.assertIn("US SSN pattern", err)

    def test_gitignored_file_is_not_scanned(self):
        d = self.repo()
        pathlib.Path(d, ".gitignore").write_text("secrets.py\n")
        pathlib.Path(d, "secrets.py").write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n")
        rc, _, err = self.gate(d, "--stop-hook")
        self.assertEqual(rc, 0, err)

    def test_clean_work_is_not_blocked(self):
        d = self.repo()
        pathlib.Path(d, "app.py").write_text("x = 2\n")
        rc, _, err = self.gate(d, "--stop-hook")
        self.assertEqual(rc, 0, err)
        self.assertIn("0 FAIL", err)

    def test_stop_hook_active_does_not_loop(self):
        """Second time round the hook stands down, however bad the diff is."""
        d = self.repo()
        pathlib.Path(d, "app.py").write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n")
        rc, out, err = self.gate(d, "--stop-hook", payload='{"stop_hook_active": true}')
        self.assertEqual(rc, 0)
        self.assertEqual((out, err), ("", ""))

    def test_malformed_hook_input_still_scans(self):
        d = self.repo()
        pathlib.Path(d, "app.py").write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n")
        rc, _, err = self.gate(d, "--stop-hook", payload="not json at all")
        self.assertEqual(rc, 2, err)

    def test_repo_with_no_commit_yet(self):
        d = self.repo(commit=None)
        pathlib.Path(d, "first.py").write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n")
        rc, _, err = self.gate(d, "--stop-hook")
        self.assertEqual(rc, 2, err)
        self.assertIn("AWS access key", err)

    def test_full_runs_make_check_and_reports_its_output(self):
        d = self.repo()
        pathlib.Path(d, "Makefile").write_text('check:\n\t@echo "3 != 4"; exit 1\n')
        pathlib.Path(d, "app.py").write_text("x = 3\n")
        rc, out, err = self.gate(d, "--stop-hook", "--full")
        self.assertEqual(rc, 2, err)
        self.assertIn("FAIL  make check", err)
        self.assertIn("3 != 4", err)  # the failing output itself, not just the verdict
        self.assertEqual(out, "")

    def test_explicit_scope_wins_over_the_default(self):
        d = self.repo()
        pathlib.Path(d, "app.py").write_text("k = '" + "AKIA" + "ABCDEFGHIJKLMNOP'\n")
        rc, _, err = self.gate(d, "--stop-hook", "--range", "HEAD...HEAD")
        self.assertEqual(rc, 0, err)  # --range asked for committed history, which is clean

    def test_missing_command_skips_instead_of_failing(self):
        d = self.repo()
        pathlib.Path(d, "Makefile").write_text("check:\n\t@true\n")
        with unittest.mock.patch.object(vc.shutil, "which", lambda name: None):
            self.assertEqual(vc.project_checks(d), [("SKIP", "make check  (not installed)")])


class InstallStopHookTests(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.d, True)
        self.path = pathlib.Path(self.d, ".claude", "settings.json")

    def install(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
            rc = vc.install_stop_hook(self.d)
        return rc, buf.getvalue()

    def hooks(self):
        return json.loads(self.path.read_text())["hooks"]["Stop"]

    def test_creates_the_hook(self):
        rc, _ = self.install()
        self.assertEqual(rc, 0)
        cmd = self.hooks()[0]["hooks"][0]
        self.assertIn("--stop-hook --full", cmd["command"])
        self.assertIn("vibe_check.py", cmd["command"])
        self.assertEqual(cmd["timeout"], vc.STOP_HOOK_TIMEOUT)

    def test_is_idempotent(self):
        self.install()
        rc, out = self.install()
        self.assertEqual(rc, 0)
        self.assertIn("already configured", out)
        self.assertEqual(len(self.hooks()), 1)

    def test_keeps_existing_settings_and_hooks(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({
            "permissions": {"allow": ["Bash(ls)"]},
            "hooks": {"Stop": [{"hooks": [{"type": "command", "command": "echo hi"}]}],
                      "PreToolUse": [{"matcher": "Bash", "hooks": []}]},
        }))
        self.assertEqual(self.install()[0], 0)
        data = json.loads(self.path.read_text())
        self.assertEqual(data["permissions"], {"allow": ["Bash(ls)"]})
        self.assertIn("PreToolUse", data["hooks"])
        self.assertEqual(data["hooks"]["Stop"][0]["hooks"][0]["command"], "echo hi")
        self.assertIn("--stop-hook", data["hooks"]["Stop"][1]["hooks"][0]["command"])

    def test_refuses_to_clobber_unreadable_settings(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{ not json")
        rc, out = self.install()
        self.assertEqual(rc, 2)
        self.assertIn("by hand", out)
        self.assertEqual(self.path.read_text(), "{ not json")

    def test_refuses_an_unexpected_hook_shape(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text(json.dumps({"hooks": {"Stop": "python3 whatever.py"}}))
        rc, out = self.install()
        self.assertEqual(rc, 2)
        self.assertIn("by hand", out)
        self.assertEqual(json.loads(self.path.read_text())["hooks"]["Stop"], "python3 whatever.py")


if __name__ == "__main__":
    unittest.main()
