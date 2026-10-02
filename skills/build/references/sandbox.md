# sandbox

## Steps

1. Pick the directory: use `.worktrees/` if it exists, otherwise create it.
2. Make sure it is ignored: `git check-ignore -q .worktrees || echo ".worktrees/" >> .gitignore`.
3. Create the worktree: `git worktree add .worktrees/<branch> -b <branch>`.
4. `cd` into it and install dependencies with the project's own command.
5. Run the test suite once to record a baseline.
6. If the baseline fails, report the failures before changing anything, so existing breakage isn't blamed on new work.

## Cleanup

When the branch is merged or abandoned (`ship`): `git worktree remove .worktrees/<branch>`.
