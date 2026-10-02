# second-look

## Prepare

Base SHA, head SHA, the plan or requirements, and a two-line summary of the change.

## Review

If your agent supports subagents, give a reviewer only the items above. Otherwise, do a fresh pass yourself: read the diff top to bottom as if a stranger wrote it.

## Checklist

- Meets every requirement in the plan.
- Tests cover new behaviour, edge cases and error paths.
- Errors handled; no swallowed exceptions.
- No secrets, personal or regulated data in code, logs or fixtures.
- Performance: N+1 queries, unbounded loops or loads, missing indexes.
- Migrations safe on live data (`pg-migrate`).
- Logs, metrics and traces for anything new.
- Names and structure readable without the author explaining them.

## Output

Findings as **Blocker**, **Should fix** or **Nit**, each with `file:line` and a suggested fix. Fix all Blockers before `ship`.
