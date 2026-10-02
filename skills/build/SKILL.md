---
name: build
description: Use when writing or changing code (features, bug fixes, refactors), starting feature work without disturbing the current checkout, or executing an approved plan task by task with check-ins after each batch. Isolated worktree, test-first loop with tiered checks, mutation testing, and a guard against skipped or weakened tests.
---

# build

Read only the part you need. Run checks with the scripts and read their summaries, not raw test output.

| Situation | Read |
| --- | --- |
| Starting feature work or executing a plan that shouldn't disturb the current checkout. Creates an isolated git worktree on a new branch and confirms a clean baseline. | `references/sandbox.md` |
| Writing or changing production code - features, bug fixes, refactors. Test-first loop built for agents - types first, failing test, smallest change, checks in fast-to-slow tiers, and a guard that catches weakened or skipped tests. | `references/prove-it.md` |
| Executing an existing plan task by task. Keeps work in order, checks in after each batch, and stops when reality doesn't match the plan. | `references/build.md` |

Order: `references/sandbox.md` for an isolated branch, `references/prove-it.md` for every piece of code, `references/build.md` to work through an existing plan. A task that takes several attempts runs under `ratchet`.

Scripts: `scripts/loop.py` (tiered checks and mutation testing), `scripts/tamper.py` (catches skipped, deleted or weakened tests), `scripts/mutate.py` (used by loop).
