---
name: ship
description: Use when about to commit, push or open a PR, say work is done, fixed or passing, merge, deploy, release (including migrations, config and flag changes) or roll back. Runs the quality gate, requires proof from commands run this session, checks a release is safe and reversible, deploys to staging then production while watching health, and finishes the branch.
---

# ship

Read only the part you need.

| Situation | Read |
| --- | --- |
| About to commit, push or open a PR, or when asked whether code is safe to ship. Runs the overmind quality and compliance gate on the changes and the project's own checks. | `references/vibe-check.md` |
| About to say work is done, fixed, passing, deployed, faster or ready, and before any commit, PR or status update. Requires proof from commands run in this session. | `references/receipts.md` |
| All tasks are done and the work is ready to merge, open as a PR, or throw away. Finishes the branch cleanly. | `references/land.md` |
| About to deploy or release to production, including database migrations, config changes, feature flag flips and infrastructure changes. Confirms the change is safe to ship and can be rolled back. | `references/preflight.md` |
| Deploying a change to staging or production, rolling out a new version, or rolling one back. Ships gradually, watches health, and rolls back fast when signals go bad. | `references/deploy.md` |

Order for one change: `references/vibe-check.md` before every commit, `references/receipts.md` before any done, fixed or passing claim, `references/land.md` to finish the branch. For production, `references/preflight.md` then `references/deploy.md`.

Script: `scripts/vibe_check.py` (the ship gate; `--install-hook` makes it block commits).
