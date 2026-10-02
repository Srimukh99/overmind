# vibe-check

## Steps

1. Run the gate on staged changes, from the repo being checked:
   `python3 <this skill folder>/scripts/vibe_check.py`
   It checks the current directory's repo. From anywhere else, point it at one: `--repo /path/to/project`.
   In CI, or to check a branch: `--range origin/main...HEAD`. Whole repo: `--all`.
2. Run the project's own checks too: add `--full` to auto-detect and run lint, type checks and tests (`make check`, npm scripts, pytest, go, cargo). Prefer commands listed in `AGENTS.md` if present.
3. Fix every **FAIL**. Each **WARN** gets a fix or a one-line reason.
4. Report the summary with `references/receipts.md`.

## What it catches

| Check | Level |
| --- | --- |
| Cloud keys, private keys, tokens (AWS, GitHub, Slack, Stripe, Google) | FAIL |
| `.env`, `.pem`, `.p12`, `id_rsa` files committed | FAIL |
| Card numbers (Luhn-valid, known test cards allowed) | FAIL |
| US SSN patterns | FAIL |
| Debugger statements, focused tests (`.only`, `fit`) | FAIL |
| Merge conflict markers | FAIL |
| Hard-coded secret-looking assignments | WARN |
| Files over 5 MB | WARN |

A line that is a deliberate false positive can carry `vibe-check: ignore` in a comment. Use it rarely and explain why in the PR.

## Add your own checks

List extra commands, one per line, in `.overmind/checks`. Each runs on every vibe-check, in the repo root, and fails the gate on a non-zero exit. These are shell commands from the repo, so treat `.overmind/checks` as code: read it before running the gate in a repo you don't control. For example:

```text
# .overmind/checks
ruff format --check .
gitleaks protect --staged --no-banner
python3 <iac-check skill folder>/scripts/iac_check.py infra/ deploy/
```

## Make it automatic

- Commit hook: `python3 <this skill folder>/scripts/vibe_check.py --install-hook` (won't overwrite an existing hook).
- CI: see `.github/workflows/ci.yml` in the overmind repo for a ready job.

Never bypass commit hooks (`--no-verify`) unless the user explicitly asks.
