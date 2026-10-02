# land

1. Run the full suite and `vibe-check`. Both must pass (`references/receipts.md`).
2. Ask the user which ending they want:
   - Merge into the base branch locally.
   - Push and open a PR.
   - Keep the branch for later.
   - Discard the work (confirm twice; it's destructive).
3. For a PR, write the body: **Why** (problem), **What** (change), **How tested** (commands and results), **Risk and rollback**.
4. Commit messages: imperative summary under 72 characters, body explaining why.
5. Clean up: remove the worktree (`build`) and delete merged local branches.

Never force-push to shared branches or skip commit hooks unless the user explicitly asks.
