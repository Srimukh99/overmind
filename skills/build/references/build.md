# build

## Before starting

Read the whole plan. Raise gaps, wrong assumptions or missing tasks now, not halfway through. If not already isolated, use `references/sandbox.md`.

## Loop

For each task, in order:

1. Follow `references/prove-it.md` for the code; for multi-attempt work, run it under `ratchet`.
2. Run the task's **Verify** command and read the output.
3. Tick the checkbox in the plan file.

After every 3 tasks, post a checkpoint: what changed, verify output, anything surprising. Continue only when the user says so, unless they asked you to run the whole plan.

## When reality differs

Stop and say so if a file, API or behaviour isn't what the plan assumed. Never quietly change the plan. Update the plan file with the change and the reason.

## Done when

All tasks are ticked, `loop.py full` passes and `tamper.py` is clean. Next: `review`, then `ship`.
