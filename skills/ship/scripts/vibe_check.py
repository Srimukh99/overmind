#!/usr/bin/env python3
"""vibe-check: a fast, dependency-free quality and compliance gate.

Scans added lines (staged, a git range, or the whole repo) for secrets,
regulated identifiers, debug leftovers and conflict markers. Exit code 1 on FAIL.

Checks the repo given by --repo, defaulting to the current directory, so the
gate works from any project without being installed into it.
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


def collect(args, root):
    """Return (files, lines) to check."""
    if args.all:
        files = [f for f in git(root, "ls-files", "--", ".").splitlines() if f]
        lines = []
        for f in files:
            full = f if os.path.isabs(f) else os.path.join(root, f)
            if not os.path.isfile(full) or is_binary(full):
                continue
            with open(full, encoding="utf-8", errors="ignore") as fh:
                for i, line in enumerate(fh, 1):
                    lines.append((f, i, line.rstrip("\n")))
        return files, lines
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


def project_checks(root):
    """Detect and run the project's own lint, type and test commands."""
    def at(*parts):
        return os.path.join(root, *parts)

    cmds = []
    makefile = open(at("Makefile"), encoding="utf-8", errors="replace").read() if os.path.isfile(at("Makefile")) else ""
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
        rc = subprocess.run(c, cwd=root).returncode
        results.append(("FAIL" if rc else "PASS", " ".join(c)))
    return results


def extra_checks(root, rel=os.path.join(".overmind", "checks")):
    """Run extra commands listed one per line in .overmind/checks (comments with #)."""
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
        rc = subprocess.run(cmd, shell=True, cwd=root).returncode
        results.append(("FAIL" if rc else "PASS", cmd))
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


def main(argv=None):
    ap = argparse.ArgumentParser(description="overmind quality and compliance gate")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--all", action="store_true", help="scan every tracked file")
    g.add_argument("--range", help="scan a git range, e.g. origin/main...HEAD")
    ap.add_argument("--repo", default=".", help="repo to check (default: .)")
    ap.add_argument("--full", action="store_true", help="also run the project's lint/type/test commands")
    ap.add_argument("--install-hook", action="store_true", help="run vibe-check on every commit")
    # Extra commands (formatters, gitleaks, iac-check, ...) can be listed in .overmind/checks
    args = ap.parse_args(argv)
    root = os.path.abspath(args.repo)

    if args.install_hook:
        return install_hook(root)
    try:
        files, lines = collect(args, root)
    except subprocess.CalledProcessError as e:
        print(f"vibe-check: git failed: {(e.stderr or '').strip() or e}", file=sys.stderr)
        return 2
    except subprocess.TimeoutExpired:
        print(f"vibe-check: git timed out after {GIT_TIMEOUT}s in {root}", file=sys.stderr)
        return 2

    findings = file_findings(files, root)
    for path, lineno, line in lines:
        findings.extend(scan_line(path, lineno, line))

    checks = (project_checks(root) if args.full else []) + extra_checks(root)
    fails = sum(1 for f in findings if f[0] == "FAIL") + sum(1 for c in checks if c[0] == "FAIL")
    warns = sum(1 for f in findings if f[0] == "WARN")

    for level, path, lineno, msg in sorted(findings, key=lambda f: (f[0] != "FAIL", f[1], f[2])):
        loc = f"{path}:{lineno}" if lineno else path
        print(f"{level:<5} {loc}  {msg}")
    for level, cmd in checks:
        print(f"{level:<5} {cmd}")
    print(f"vibe-check: {fails} FAIL, {warns} WARN, {len(lines)} lines scanned")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
