---
name: ratchet
description: Use when iterating on code over several attempts - a feature, a fix that keeps failing, an agent loop - so every accepted step improves it without regressions or scope creep.
---

# ratchet

A ratchet turns one way. Each iteration is measured against a floor of what
already works; it is kept only if nothing broke, nothing drifted, and something
measurably improved. Bad steps cost one revert, not a debugging session.

## Start (once per task)
1. Write the acceptance tests first (`build`). They should fail now.
   Import new, not-yet-existing names *inside* each test, so one missing name
   doesn't hide progress on the others.
2. Anchor it:
   ```
   python3 skills/ratchet/scripts/ratchet.py start \
     --goal "One sentence, in the user's words" \
     --scope 'src/cart/**' \
     --target tests/test_x.py::test_new_behaviour --target ...
   ```
   Scope is the smallest set of paths this task should touch. Tests are always in scope.
   Add `--mutate` to also ratchet the mutation score.

## Each iteration
1. Read the goal line from the last output. Pick the first failing target.
2. Make one small change toward it.
3. `python3 skills/ratchet/scripts/ratchet.py check`
4. Act on the verdict:
   - **ACCEPT**: floor raised, checkpoint saved. Next target.
   - **REJECT**: `ratchet.py revert`, then a different approach. Don't patch over it.
   - **STALL**: nothing improved. Revert or make a change that moves a target.
   - **DONE**: all targets pass. Run `loop.py full`, `tamper.py`, then `review`.
   - **STOP** (3 non-accepts in a row) or **LIMIT** (max iterations): revert and report
     to the user what you tried, what the output said, and what blocks you.

## What REJECT means
- **regression**: a test that passed at the floor fails, errors, is skipped or is gone.
- **api**: a public function, class or signature was removed or changed.
- **drift**: a file outside scope changed, or a dependency manifest with no scope set.
- **frozen-test**: a test that existed at start was edited. Add new tests instead.
- **tamper**: a test was skipped, deleted, weakened or loosened.
- **quality**: lint or typecheck went from clean to failing, or the mutation score fell.

## Never
- Edit `.rubric/ratchet/` files, or restart the ratchet to escape a REJECT.
- Fix a regression by editing the test that caught it.
- Widen scope, allow an API change or unfreeze a test on your own. Ask the user, then:
  `ratchet.py amend --scope 'src/billing/**' --reason "user approved: ..."`
  (also `--allow-api NAME`, `--unfreeze PATH`, `--target ID`). Amendments are logged.

## Other commands
`ratchet.py status` shows the iteration history. `revert --clean` also removes files
created since the checkpoint. Checkpoints are git objects under `refs/rubric/ratchet/`;
your branch, index and commits are never touched. Override the test command with
`--test-cmd` (anything that writes JUnit XML to `.rubric/ratchet/junit.xml` works).
Add `.rubric/ratchet/` to `.gitignore`.
