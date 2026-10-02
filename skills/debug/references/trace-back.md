# trace-back

1. Start at the symptom. Note the bad value and where it was observed.
2. Ask: who passed this value in? Move one caller up (stack traces, search, the repo index).
3. At each boundary, check whether the value is already wrong. Add temporary logging with the value and its caller if needed.
4. Stop at the first place the value goes wrong. That is the origin.
5. Fix it there, with a test (`build`).
6. Add validation where the bad data entered the system, so the next one fails loudly and early.
7. Remove the temporary logging.

Never log secrets or regulated data while tracing. Log IDs, not contents.
