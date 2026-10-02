# hunt

No fix until you can explain the cause.

## 0. Logs first, cheaply

If there is a log or stack trace, run `log-trace (or `log-fetch <service>` when you have no logs yet)` on it before reading any code. It gives the error, the in-repo source line and where the app runs (Lambda, ECS, EKS, ...) in about 20 lines.

## 1. Reproduce

Get the smallest reliable repro. Record the exact command and output. If you can't reproduce it, gather more data (logs, inputs, environment); don't guess.

## 2. Narrow down

- What changed? `git log -p`, `git bisect`, recent deploys and config.
- Compare a working case with a broken one and close the gap.
- Halve the search space each step.

## 3. Explain

Write one hypothesis at a time: "X causes Y because Z". Test it with the smallest possible experiment. If it's wrong, cross it out and move to the next. Keep this log visible in the conversation.

## 4. Fix

Write a failing test that reproduces the bug (`build`). Fix the cause, not the symptom. One change at a time.

## 5. Confirm

The repro now passes and the full suite is green (`ship`).

## Stop rule

Three failed fixes in a row: stop. The assumption or the design is probably wrong. Step back and tell the user what you've learned.

## Production incidents

Mitigate first (roll back, disable the flag, scale up), then hunt.
