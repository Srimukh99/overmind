---
name: delegate
description: Use when a plan has independent tasks, several unrelated failures to fix, or work big enough to split across subagents.
---

# delegate

Split work only when the pieces are independent: different files, no interface still being designed,
each checkable by its own tests. Otherwise do it yourself, one task at a time. Parallel work costs more
tokens in total; it buys speed, and only for independent pieces. One level only: you are the lead and
workers do not delegate further. If your agent can't start subagents, follow the same flow and do each
brief yourself.

## Flow

1. **Contract first.** Write the shared pieces yourself: interfaces, types, and one acceptance test per
   behaviour. They are frozen for every worker.
2. **Plan.** Run `python3 skills/delegate/scripts/team.py init --goal "..." --contract PATH` (repeat
   `--contract`), then for each worker
   `team.py add NAME --owns PATH --target TEST_ID --task "one line"`, then `team.py check`.
   Fix every ERROR: two workers owning the same file, a worker owning the contract, a target assigned twice.
3. **Spawn.** `team.py spawn` gives each worker a git worktree next to the repo and starts a `ratchet`
   in it, all from one snapshot. Your branch and working tree are not touched.
4. **Brief.** `team.py brief NAME` prints about ten lines. Send exactly that to the worker, nothing else
   from this conversation. Add any `reg-*` rules that apply to its task line.
5. **Verify, don't trust.** `team.py verify` runs each worker's ratchet and compares its claim with the
   verdict. Only DONE counts. Send a REJECT or FALSE CLAIM back with its reason (the worker continues in
   its worktree), or start it over with `team.py spawn NAME --fresh`.
6. **Integrate.** `team.py integrate` merges the verified workers in a scratch worktree and runs the
   whole suite once. `team.py integrate --apply` lands it in your working tree.
7. **Next wave.** Re-plan with what you learned, `team.py add`, `team.py spawn`, repeat.
   `team.py clean --all` removes worktrees, branches and the plan at the end.

## Rules

- Every file has at most one owner. Workers may add new test files; they never edit existing tests.
- Briefs and returns stay short: the worker replies in five lines and writes `.overmind/result.json`.
- Judge workers by `verify`, never by their summary.
- If your agent lets you pick models, mechanical worker tasks can use a cheaper one; keep planning and
  integration on the strongest.
- `team.py status` shows the plan and the last verdicts.
