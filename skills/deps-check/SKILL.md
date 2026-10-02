---
name: deps-check
description: Use when adding or upgrading dependencies, before a release, or when asked about vulnerable packages, CVEs, or supply-chain risk in Python, Node, Go, Rust or container images.
---

# deps-check

## Do

1. Run `python3 <this skill folder>/scripts/deps_check.py`. It detects the ecosystems in the repo and runs whichever scanners are installed (osv-scanner, pip-audit, npm audit, govulncheck, cargo audit, trivy), then prints one summary.
2. If no scanner is installed, suggest `osv-scanner`; it covers every ecosystem.
3. For each finding: upgrade to the fixed version, or document why it isn't reachable and set a review date.

## Rules for new dependencies

- Prefer the standard library or an existing dependency.
- Check maintenance (recent releases, open issues), licence compatibility and download count.
- Pin versions with a lockfile and commit the lockfile.
- Watch for typo-squatted names (`reqeusts`, `lodahs`).
- Regulated systems: keep a software bill of materials (for example `syft` or `trivy sbom`).
