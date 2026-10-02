#!/usr/bin/env python3
"""deps-check: run whichever dependency vulnerability scanners fit this repo and are installed,
and print one compact summary. Read-only.

Uses: osv-scanner (any ecosystem), pip-audit, npm audit, govulncheck, cargo audit, trivy (images/fs).
"""
import json
import os
import shutil
import subprocess
import sys


def run(cmd):
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        return p.returncode, p.stdout, p.stderr
    except (OSError, subprocess.TimeoutExpired) as e:
        return 99, "", str(e)


def detect():
    have = set(os.listdir("."))
    eco = []
    if have & {"requirements.txt", "pyproject.toml", "poetry.lock", "Pipfile.lock", "uv.lock"}:
        eco.append("python")
    if have & {"package-lock.json", "package.json", "yarn.lock", "pnpm-lock.yaml"}:
        eco.append("node")
    if "go.mod" in have:
        eco.append("go")
    if "Cargo.lock" in have or "Cargo.toml" in have:
        eco.append("rust")
    if any(f.startswith("Dockerfile") for f in have):
        eco.append("container")
    return eco


def main():
    eco = detect()
    plan = []
    if shutil.which("osv-scanner"):
        plan.append(("osv-scanner", ["osv-scanner", "scan", "source", "-r", "."]))
    if "python" in eco and shutil.which("pip-audit"):
        plan.append(("pip-audit", ["pip-audit", "-r", "requirements.txt"] if os.path.exists("requirements.txt") else ["pip-audit"]))
    if "node" in eco and shutil.which("npm") and os.path.exists("package-lock.json"):
        plan.append(("npm audit", ["npm", "audit", "--omit=dev", "--audit-level=high"]))
    if "go" in eco and shutil.which("govulncheck"):
        plan.append(("govulncheck", ["govulncheck", "./..."]))
    if "rust" in eco and shutil.which("cargo-audit"):
        plan.append(("cargo audit", ["cargo", "audit"]))
    if "container" in eco and shutil.which("trivy"):
        plan.append(("trivy fs", ["trivy", "fs", "--severity", "HIGH,CRITICAL", "--exit-code", "1", "--quiet", "."]))

    print(f"deps-check: ecosystems={', '.join(eco) or 'none'}")
    if not plan:
        print("No scanner installed. Install one of: osv-scanner (all ecosystems), pip-audit, npm, govulncheck, cargo-audit, trivy.")
        return 2
    failed = 0
    for name, cmd in plan:
        rc, so, se = run(cmd)
        tail = [l for l in (so + se).strip().splitlines() if l.strip()][-6:]
        status = "PASS" if rc == 0 else "FAIL"
        failed += rc != 0
        print(f"{status:<5} {name}")
        if rc != 0:
            for l in tail:
                print(f"      {l[:200]}")
    print(f"deps-check: {failed} of {len(plan)} scanners reported issues")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
