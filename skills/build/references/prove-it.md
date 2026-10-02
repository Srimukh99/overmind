# prove-it

TDD's core, fixed for how agents fail: they cheat tests when stuck, write tests
that mirror the code, miss edge cases, and burn tokens rerunning everything.
Read script summaries, never raw test output.

## Pick the mode first
- New behaviour: example test.
- Logic over many inputs (parsing, money, dates, validation, serialization): add one property test (Hypothesis, fast-check, gopter, jqwik, proptest). One property covers what ten examples miss.
- Changing code that has no tests: characterization test first. Pin what it does today, then change it.
- Bug: a test that reproduces it, failing for the reported reason.

## Loop
1. **Shape**: write the types, signature or interface. Run `loop.py fast`. The compiler is the cheapest test.
2. **Red**: one test for the next behaviour. It fails, for the expected reason (an assertion, not an import error).
3. **Green**: the smallest change that passes.
4. **Check in tiers**:
   - `python3 skills/build/scripts/loop.py fast` after every edit (typecheck, lint; seconds).
   - `loop.py focused` when green (only tests related to changed files).
   - `loop.py full` once, before calling it done.
   - `loop.py mutate` on logic-heavy changes: injects small bugs into the changed
     functions. Each one reported as "not caught" needs a test that fails for it.
5. **Guard**: `python3 skills/build/scripts/tamper.py`. Any FAIL: revert that test change, or stop and tell the user why the test itself was wrong.
6. **Clean**: rename and restructure with `focused` still green.

## Tests that actually test
- Assert specific outcomes the user would care about: exact values, not truthiness. `toEqual(42)`, not `toBeDefined()`.
- Test behaviour through public interfaces, not which internal functions were called.
- One behaviour per test, named for the behaviour.
- Mock only slow or external boundaries: network, clock, third-party APIs.
- Passing tests prove little on their own: a weak suite and a strong one can both be green. `loop.py mutate` tells them apart.
- Import names that don't exist yet inside the test, not at the top of the file, so one missing name doesn't hide every other result.
- Synthetic data only. Never real patient, card, SSN or customer data.

## Never
- Edit, skip or delete a test to make it pass. If the test is wrong, say so explicitly first.
- Write code before its test, then retrofit a test around it.
- Run the full suite in the inner loop.

## Iterating
For anything that takes several attempts, run it under `ratchet`: each step is
kept only if nothing broke, nothing drifted and something improved.

## When stuck
Three failed attempts at the same failure: stop. Report what you tried, what the
output says, and your best hypothesis. Don't try a fourth variation blind.

## Commands
`loop.py` detects the stack (Python, Node, Go, Rust, Java). Override in
`.overmind/loop.json`: `{"fast": ["..."], "focused": ["..."], "full": ["..."]}`.
`--dry-run` prints commands without running them.
`tamper.py` compares test files against the merge-base with main. Mark a reviewed
line with a `prove-it: ok` comment.

## Exceptions
Throwaway spikes (deleted after), generated code, pure config. Say when you use one.

## Done when
New tests failed first and pass now, `loop.py full` is green, `tamper.py` is clean,
and for logic-heavy code `loop.py mutate` reports no uncaught bugs in the change.
Show both outputs (`ship`).
