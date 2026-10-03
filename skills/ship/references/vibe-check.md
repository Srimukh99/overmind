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

List extra commands, one per line, in `.rubric/checks`. Each runs on every vibe-check, in the repo root, and fails the gate on a non-zero exit. These are shell commands from the repo, so treat `.rubric/checks` as code: read it before running the gate in a repo you don't control. For example:

```text
# .rubric/checks
ruff format --check .
gitleaks protect --staged --no-banner
python3 <iac-check skill folder>/scripts/iac_check.py infra/ deploy/
```

## Make it automatic

- Commit hook: `python3 <this skill folder>/scripts/vibe_check.py --install-hook` (won't overwrite an existing hook).
- Stop hook, so a turn cannot end on an unproven claim: `python3 <this skill folder>/scripts/vibe_check.py --install-stop-hook` adds it to `.claude/settings.json` and leaves any hook already there alone.
- CI: see `.github/workflows/ci.yml` in the rubric repo for a ready job.

Never bypass commit hooks (`--no-verify`) unless the user explicitly asks.

## The Stop hook

The commit hook catches what reaches a commit. The Stop hook catches the turn
that ends with "done" and nothing committed at all.

```json
{"hooks": {"Stop": [{"hooks": [
  {"type": "command",
   "command": "python3 <this skill folder>/scripts/vibe_check.py --stop-hook --full",
   "timeout": 600}
]}]}}
```

| Behaviour | Why |
| --- | --- |
| Scans staged **and** unstaged changes plus new untracked files | At the end of a turn the work is usually uncommitted, and the riskiest file is the one just created |
| Reads the closing message and FAILs on the `references/receipts.md` red-flag words ("should work", "I'm confident"), ignoring quotes and code | A prediction is not a receipt; quoting a phrase to discuss it is allowed. `--no-claim-check` turns this off |
| Reports on stderr, not stdout | Only stderr is handed back to the agent when a Stop hook blocks |
| Exits 2 on FAIL | Exit 2 returns the turn with the findings; exit 1 would only log them |
| Stands down when the hook input carries `stop_hook_active` | It blocks once and hands back the output, rather than looping on itself |
| Prints SKIP for a command the host does not have | A missing linter is not a pass; read the SKIP lines |

`--full` runs the project's lint, type and test commands on every turn end, so
it costs what those commands cost. Three ways to tune it: drop `--full` to keep
the scan alone, change `timeout` (seconds, and a timed-out hook blocks nothing),
or point a `make check` target at the subset worth paying for every turn.
