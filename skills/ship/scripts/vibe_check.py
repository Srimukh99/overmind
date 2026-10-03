#!/usr/bin/env python3
"""vibe-check: a fast, dependency-free quality and compliance gate.

Scans added lines (staged, uncommitted, a git range, or the whole repo) for
secrets, regulated identifiers, debug leftovers and conflict markers. Exit code
1 on FAIL.

Checks the repo given by --repo, defaulting to the current directory, so the
gate works from any project without being installed into it.

--stop-hook runs it as an agent Stop hook: it scans the uncommitted work, reads
the agent's closing message for wording that predicts instead of proves ("should
work", "I'm confident"), prints to stderr so the findings reach the agent, and
exits 2 to send the turn back instead of letting it end on an unproven claim.
"""
import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys

IGNORE_MARK = "vibe-check: ignore"
MAX_BYTES = 5 * 1024 * 1024
GIT_TIMEOUT = 120
STOP_HOOK_TIMEOUT = 600
STOP_REASON = (
    "vibe-check failed, so this work is not provably done. Fix every FAIL above, "
    "re-run the gate, and report the result as a receipt (command -> key output "
    "line). A closing message that predicts (\"should work\", \"I'm confident\") "
    "needs the command run and its output quoted instead. If a check cannot be run "
    "here, say \"unverified\" and why rather than claiming it passed."
)
# Wording that predicts a result instead of reporting one. The same list, in the
# same order, is in references/receipts.md; tests/test_vibe_check.py keeps them equal.
RED_FLAGS = [
    "should work", "should be fine", "looks right", "looks correct", "I think it works",
    "I think it's fixed", "probably", "must be working", "seems to work",
    "basically done", "mostly working", "in theory", "by inspection",
    "obviously correct", "simple enough that", "I'm confident",
]
APOSTROPHES = str.maketrans({"\u2019": "'", "\u2018": "'"})
RED_FLAG_RX = re.compile(r"(?<![\w'])(%s)(?![\w'])" % "|".join(re.escape(f) for f in RED_FLAGS), re.I)
# Quoting a phrase is talking about it, not claiming with it.
QUOTED = re.compile(r"```.*?```|`[^`\n]*`|\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d", re.S)

SECRET_RULES = [
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP |ENCRYPTED )?PRIVATE KEY-----")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}\b")),
    ("Slack token", re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b")),
    ("Stripe live key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("OpenRouter API key", re.compile(r"\bsk-or-v1-[a-f0-9]{64}\b")),
    ("Anthropic API key", re.compile(r"\bsk-ant-[a-zA-Z0-9_\-]{32,}\b")),
    ("OpenAI API key", re.compile(r"\bsk-proj-[a-zA-Z0-9_\-]{20,}\b")),
    ("HuggingFace token", re.compile(r"\bhf_[a-zA-Z0-9]{34,}\b")),
]
GENERIC_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?key|secret|passwd|password|access[_-]?token|auth[_-]?token)\b\s*[:=]\s*['\"]([^'\"\s]{12,})['\"]"
)
PLACEHOLDER = re.compile(r"(?i)example|changeme|dummy|placeholder|your[_-]|xxx|<|\$\{|test")
SSN = re.compile(r"\b(?!000|666|9\d\d)\d{3}-(?!00)\d{2}-(?!0000)\d{4}\b")
CARD = re.compile(r"(?<![\d.])(?:\d[ -]?){12,18}\d(?![\d.])")
TEST_CARDS = {
    "4242424242424242", "4111111111111111", "4000056655665556", "5555555555554444",
    "2223003122003222", "5105105105105100", "378282246310005", "371449635398431",
    "6011111111111117", "3056930009020004", "36227206271667", "3566002020360505",
}
LEFTOVER_RULES = [
    ("Debugger statement", re.compile(r"^\s*(?:debugger;?\s*$|breakpoint\(\)|import i?pdb\b|i?pdb\.set_trace\(\)|binding\.pry)")),
    ("Focused test", re.compile(r"\b(?:it|describe|test|context)\.only\(|\bf(?:it|describe)\(")),
    ("Conflict marker", re.compile(r"^(?:<{7}|>{7})(?: |$)|^={7}$")),
]
BAD_FILES = re.compile(r"(?:^|/)(?:\.env(?:\.[\w-]+)?|id_rsa|id_ed25519|.*\.pem|.*\.p12|.*\.pfx|.*\.keystore)$")
OK_FILES = re.compile(r"\.env\.(?:example|sample|template)$")


def luhn(digits):
    total, alt = 0, False
    for ch in reversed(digits):
        d = int(ch)
        if alt:
            d *= 2
            if d > 9:
                d -= 9
        total += d
        alt = not alt
    return total % 10 == 0


def scan_line(path, lineno, line):
    findings = []
    if IGNORE_MARK in line:
        return findings
    for name, rx in SECRET_RULES:
        if rx.search(line):
            findings.append(("FAIL", path, lineno, name))
    m = GENERIC_SECRET.search(line)
    if m and not PLACEHOLDER.search(m.group(1)):
        findings.append(("WARN", path, lineno, "Hard-coded secret-looking value"))
    if SSN.search(line):
        findings.append(("FAIL", path, lineno, "US SSN pattern"))
    for cm in CARD.finditer(line):
        digits = re.sub(r"\D", "", cm.group(0))
        if 13 <= len(digits) <= 19 and digits not in TEST_CARDS and luhn(digits) and len(set(digits)) > 2:
            findings.append(("FAIL", path, lineno, "Card number (Luhn-valid)"))
            break
    for name, rx in LEFTOVER_RULES:
        if rx.search(line):
            findings.append(("FAIL", path, lineno, name))
    return findings


def git(root, *args):
    p = None
    try:
        p = subprocess.run(["git", *args], cwd=root, capture_output=True, text=True,
                           errors="replace", timeout=GIT_TIMEOUT)
    except (FileNotFoundError, OSError):
        pass
    if p is None or (p.returncode != 0 and sys.platform == "darwin"):
        try:
            p2 = subprocess.run(["arch", "-arm64", "git", *args], cwd=root, capture_output=True,
                                text=True, errors="replace", check=True, timeout=GIT_TIMEOUT)
            return p2.stdout
        except subprocess.CalledProcessError as err:
            if p is not None:
                raise subprocess.CalledProcessError(p.returncode, ["git", *args], p.stdout, p.stderr)
            raise err
    if p.returncode != 0:
        raise subprocess.CalledProcessError(p.returncode, ["git", *args], p.stdout, p.stderr)
    return p.stdout


def added_lines_from_diff(diff_text):
    path, lineno = None, 0
    for raw in diff_text.splitlines():
        if raw.startswith("+++ "):
            p = raw[4:]
            path = None if p == "/dev/null" else p[2:] if p.startswith("b/") else p
        elif raw.startswith("@@"):
            m = re.search(r"\+(\d+)", raw)
            lineno = int(m.group(1)) if m else 0
        elif raw.startswith("+") and path:
            yield path, lineno, raw[1:]
            lineno += 1
        elif not raw.startswith("-") and path:
            lineno += 1


def is_binary(path):
    try:
        with open(path, "rb") as fh:
            return b"\0" in fh.read(8000)
    except OSError:
        return True


def read_lines(root, rel):
    """Every line of one file, or nothing when it is missing or binary."""
    full = rel if os.path.isabs(rel) else os.path.join(root, rel)
    if not os.path.isfile(full) or is_binary(full):
        return []
    with open(full, encoding="utf-8", errors="ignore") as fh:
        return [(rel, i, line.rstrip("\n")) for i, line in enumerate(fh, 1)]


def head_exists(root):
    try:
        git(root, "rev-parse", "--verify", "-q", "HEAD")
        return True
    except subprocess.CalledProcessError:
        return False


def uncommitted(root):
    """Staged and unstaged changes plus new untracked files.

    This is the scope at the end of an agent turn: the work often sits unstaged,
    and the riskiest file is usually one that was just created.
    """
    scope = ["HEAD"] if head_exists(root) else ["--cached"]
    names = git(root, "diff", "--name-only", "--diff-filter=ACMR", *scope, "--", ".")
    diff = git(root, "diff", "-U0", "--diff-filter=ACMR", *scope, "--", ".")
    new = [f for f in git(root, "ls-files", "--others", "--exclude-standard", "--", ".").splitlines() if f]
    lines = list(added_lines_from_diff(diff))
    for f in new:
        lines.extend(read_lines(root, f))
    return [n for n in names.splitlines() if n] + new, lines


def collect(args, root):
    """Return (files, lines) to check."""
    if args.all:
        files = [f for f in git(root, "ls-files", "--", ".").splitlines() if f]
        lines = []
        for f in files:
            lines.extend(read_lines(root, f))
        return files, lines
    if args.uncommitted:
        return uncommitted(root)
    if args.range:
        names = git(root, "diff", "--name-only", "--diff-filter=ACMR", args.range, "--", ".")
        diff = git(root, "diff", "-U0", "--diff-filter=ACMR", args.range, "--", ".")
    else:
        names = git(root, "diff", "--cached", "--name-only", "--diff-filter=ACMR", "--", ".")
        diff = git(root, "diff", "--cached", "-U0", "--diff-filter=ACMR", "--", ".")
    return [n for n in names.splitlines() if n], list(added_lines_from_diff(diff))


def file_findings(files, root):
    out = []
    for f in files:
        if BAD_FILES.search(f) and not OK_FILES.search(f):
            out.append(("FAIL", f, 0, "Sensitive file committed"))
        full = f if os.path.isabs(f) else os.path.join(root, f)
        if os.path.isfile(full) and os.path.getsize(full) > MAX_BYTES:
            out.append(("WARN", f, 0, "File larger than 5 MB"))
    return out


def run_check(cmd, root, out=None, shell=False):
    """Run one project check. Returns its exit code, or None when it cannot run.

    With `out` set, the command's output is captured and its tail echoed there:
    a Stop hook only reaches the agent through its own stderr, so a failing
    suite has to be reprinted rather than streamed to an unread stdout.
    """
    name = cmd if shell else cmd[0]
    if not shell and not shutil.which(name):
        return None
    try:
        if out is None:
            return subprocess.run(cmd, cwd=root, shell=shell).returncode
        p = subprocess.run(cmd, cwd=root, shell=shell, capture_output=True, text=True, errors="replace")
    except OSError as err:
        print(f"vibe-check: cannot run {name}: {err}", file=sys.stderr)
        return None
    if p.returncode:
        for line in (p.stdout + p.stderr).strip().splitlines()[-40:]:
            print(line, file=out)
    return p.returncode


def project_checks(root, out=None):
    """Detect and run the project's own lint, type and test commands."""
    def at(*parts):
        return os.path.join(root, *parts)

    cmds = []
    makefile = ""
    if os.path.isfile(at("Makefile")):
        with open(at("Makefile"), encoding="utf-8", errors="replace") as fh:
            makefile = fh.read()
    if re.search(r"^check:", makefile, re.M):
        cmds.append(["make", "check"])
    elif os.path.isfile(at("package.json")):
        with open(at("package.json"), encoding="utf-8") as fh:
            scripts = json.load(fh).get("scripts", {})
        for s in ("lint", "typecheck", "test"):
            if s in scripts:
                cmds.append(["npm", "run", "--silent", s])
    if os.path.isfile(at("pyproject.toml")) or os.path.isfile(at("pytest.ini")) or os.path.isdir(at("tests")):
        if shutil.which("pytest") and not cmds:
            cmds.append(["pytest", "-q"])
    if os.path.isfile(at("go.mod")):
        cmds += [["go", "vet", "./..."], ["go", "test", "./..."]]
    if os.path.isfile(at("Cargo.toml")):
        cmds.append(["cargo", "test", "--quiet"])
    results = []
    for c in cmds:
        rc = run_check(c, root, out)
        label = "SKIP" if rc is None else "FAIL" if rc else "PASS"
        results.append((label, " ".join(c) + ("  (not installed)" if rc is None else "")))
    return results


def extra_checks(root, rel=os.path.join(".rubric", "checks"), out=None):
    """Run extra commands listed one per line in .rubric/checks (comments with #)."""
    path = os.path.join(root, rel)
    if not os.path.isfile(path):
        return []
    results = []
    with open(path, encoding="utf-8") as fh:
        lines = fh.readlines()
    for raw in lines:
        cmd = raw.strip()
        if not cmd or cmd.startswith("#"):
            continue
        rc = run_check(cmd, root, out, shell=True)
        results.append(("SKIP" if rc is None else "FAIL" if rc else "PASS", cmd))
    return results


def install_hook(root):
    hooks = git(root, "rev-parse", "--git-path", "hooks").strip()
    if not os.path.isabs(hooks):
        hooks = os.path.join(root, hooks)
    target = os.path.join(hooks, "pre-commit")
    if os.path.exists(target):
        print(f"A commit hook already exists at {target}; add this line to it:\n  python3 {os.path.abspath(__file__)}")
        return 0
    os.makedirs(hooks, exist_ok=True)
    with open(target, "w") as fh:
        fh.write(f'#!/bin/sh\nexec python3 "{os.path.abspath(__file__)}"\n')
    os.chmod(target, os.stat(target).st_mode | stat.S_IEXEC)
    print(f"Installed vibe-check commit hook at {target}")
    return 0


def hook_payload():
    """Hook input is JSON on stdin. Missing or malformed input is not fatal."""
    try:
        raw = "" if sys.stdin is None or sys.stdin.isatty() else sys.stdin.read()
    except OSError:
        return {}
    try:
        data = json.loads(raw) if raw.strip() else {}
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {}


def closing_message(payload):
    """The agent's last words this turn: the assistant text after the last user entry.

    Claude Code passes `transcript_path`, a JSONL file with one content block per
    line. Tool results arrive as `user` entries, so text written before the last
    tool call is not part of the closing message.
    """
    if isinstance(payload.get("last_assistant_message"), str):
        return payload["last_assistant_message"]
    path = payload.get("transcript_path")
    if not isinstance(path, str) or not os.path.isfile(os.path.expanduser(path)):
        return ""
    parts = []
    with open(os.path.expanduser(path), encoding="utf-8", errors="replace") as fh:
        for raw in fh:
            try:
                entry = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("type") == "user":
                parts = []
            elif entry.get("type") == "assistant":
                content = (entry.get("message") or {}).get("content")
                if isinstance(content, str):
                    parts.append(content)
                for block in content if isinstance(content, list) else []:
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block.get("text") or "")
    return "\n".join(parts)


def claim_findings(text):
    """FAIL for each red-flag phrase used, outside code and quotes, in the closing message."""
    plain = QUOTED.sub(" ", text.translate(APOSTROPHES))
    seen = []
    canonical = {f.lower(): f for f in RED_FLAGS}
    for m in RED_FLAG_RX.finditer(plain):
        phrase = canonical[m.group(1).lower()]
        if phrase not in seen:
            seen.append(phrase)
    return [("FAIL", "closing message", 0, f'Predicts instead of proves: "{p}"') for p in seen]


def install_stop_hook(root, rel=os.path.join(".claude", "settings.json")):
    """Add a Stop hook so a turn cannot end while the gate is failing."""
    path = os.path.join(root, rel)
    cmd = 'python3 "%s" --stop-hook --full' % os.path.abspath(__file__)
    settings = {}
    if os.path.isfile(path):
        try:
            with open(path, encoding="utf-8") as fh:
                settings = json.load(fh)
        except ValueError as err:
            print(f"{path} is not valid JSON ({err}); add the hook by hand:\n  {cmd}", file=sys.stderr)
            return 2
    hooks = settings.setdefault("hooks", {}) if isinstance(settings, dict) else None
    stop = hooks.setdefault("Stop", []) if isinstance(hooks, dict) else None
    if not isinstance(stop, list):
        print(f"{path} already defines hooks in a shape this cannot extend; add the hook by hand:\n  {cmd}",
              file=sys.stderr)
        return 2
    for entry in stop:
        for h in (entry.get("hooks") or []) if isinstance(entry, dict) else []:
            if "--stop-hook" in str(h.get("command", "")):
                print(f"A vibe-check Stop hook is already configured in {path}")
                return 0
    stop.append({"hooks": [{"type": "command", "command": cmd, "timeout": STOP_HOOK_TIMEOUT}]})
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    print(f"Installed vibe-check Stop hook in {path}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="rubric quality and compliance gate")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="scan every tracked file")
    g.add_argument("--range", help="scan a git range, e.g. origin/main...HEAD")
    g.add_argument("--uncommitted", action="store_true",
                   help="scan staged and unstaged changes plus new untracked files")
    ap.add_argument("--repo", default=".", help="repo to check (default: .)")
    ap.add_argument("--full", action="store_true", help="also run the project's lint/type/test commands")
    ap.add_argument("--install-hook", action="store_true", help="run vibe-check on every commit")
    ap.add_argument("--stop-hook", action="store_true",
                    help="run as an agent Stop hook: scan uncommitted work, report on stderr, exit 2 on FAIL")
    ap.add_argument("--install-stop-hook", action="store_true",
                    help="add the Stop hook to .claude/settings.json")
    ap.add_argument("--no-claim-check", action="store_true",
                    help="with --stop-hook, skip reading the closing message for red-flag wording")
    # Extra commands (formatters, gitleaks, iac-check, ...) can be listed in .rubric/checks
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo)

    if args.install_hook:
        return install_hook(root)
    if args.install_stop_hook:
        return install_stop_hook(root)

    out = sys.stdout
    claims = []
    if args.stop_hook:
        payload = hook_payload()
        # The agent is already being sent back once; blocking again would loop.
        if payload.get("stop_hook_active"):
            return 0
        if not args.no_claim_check:
            claims = claim_findings(closing_message(payload))
        # Only stderr reaches the agent when a Stop hook blocks.
        out = sys.stderr
        if not (args.all or args.range):
            args.uncommitted = True
    try:
        files, lines = collect(args, root)
    except subprocess.CalledProcessError as e:
        print(f"vibe-check: git failed: {(e.stderr or '').strip() or e}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print(f"vibe-check: git timed out after {GIT_TIMEOUT}s in {root}", file=sys.stderr)
        return 2

    findings = file_findings(files, root) + claims
    for path, lineno, line in lines:
        findings.extend(scan_line(path, lineno, line))

    stream = out if args.stop_hook else None
    checks = (project_checks(root, stream) if args.full else []) + extra_checks(root, out=stream)
    fails = sum(1 for f in findings if f[0] == "FAIL") + sum(1 for c in checks if c[0] == "FAIL")
    warns = sum(1 for f in findings if f[0] == "WARN")

    for level, path, lineno, msg in sorted(findings, key=lambda f: (f[0] != "FAIL", f[1], f[2])):
        loc = f"{path}:{lineno}" if lineno else path
        print(f"{level:<5} {loc}  {msg}", file=out)
    for level, cmd in checks:
        print(f"{level:<5} {cmd}", file=out)
    print(f"vibe-check: {fails} FAIL, {warns} WARN, {len(lines)} lines scanned", file=out)
    if args.stop_hook and fails:
        print(STOP_REASON, file=out)
        return 2
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
