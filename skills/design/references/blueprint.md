# blueprint

Write the plan for a capable engineer who has never seen this codebase.

## Each task has

- **Goal** in one sentence.
- **Files** to create or change, with paths.
- **Test first**: the test to write and what it asserts.
- **Verify**: the exact command and the expected result.
- **Size**: 2–10 minutes of work. Split anything bigger.

## Plan rules

1. Order tasks by dependency. Mark tasks that share no files as `[parallel]`.
2. Put risky or uncertain tasks first so surprises surface early.
3. Include migration, config, docs and observability tasks; they are part of the work.
4. For regulated systems, add the `reg-*` checks as explicit tasks.
5. Save to `docs/plans/YYYY-MM-DD-<topic>.md` with checkboxes.

## Done when

The plan is saved and the user approved it. Next: `build`, or `delegate` for `[parallel]` tasks.
