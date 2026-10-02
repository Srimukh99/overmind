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

## Boundaries worth a test
Agents test the happy path and stop, which is why a green suite and a correct
implementation are different things. Before a behaviour counts as tested, walk
this list and write a test for every row that applies. Most defects that reach
production live at an edge, not in the middle of the range.

| Class | Ask | Bug it catches |
| --- | --- | --- |
| Boundary | Is the range half-open or closed? What happens exactly at the edge? | off-by-one; touching intervals treated as overlapping |
| Empty | What does an empty list, string, interval or slice do? | a zero-length range matching everything |
| Clamp | Can the result go below zero or above a cap? Does it floor, wrap or raise? | a discount making a total negative |
| Numeric type | Integer or float? Which way does it round? Money in integer cents? | floating-point drift turning 999 into 899.1 |
| Partial last | May the final page, chunk or batch be short? | a short last page reporting a full count |
| Out of range | What does input past the end return? | page 11 of 10 returning data |
| Duplicates | Repeated keys, repeated items, the same call twice | a retry charging twice |
| Null and missing | What does None, null or an absent field do - default, raise, or propagate? | a missing field read as a valid empty value |
| Large input | What happens at 10x the expected size? Is there a cap, and is it tested? | a large payload timing out past a limit nobody set |
| Encoding and time | Non-ASCII, time zones, DST, leap days | a name truncated mid-codepoint |

Two shortcuts: one property test over the input space (see "Pick the mode
first") covers several rows at once and is cheaper than eight examples; and for
each row you skip, you should be able to say why it cannot apply.

This table stops at defects a unit test can reach. Races, locale and resource
exhaustion are real and are not here: they need the service running, so they
belong to `observe` and `firefight`, not to the inner loop. A checklist that
lists everything gets skipped.

`loop.py mutate` does not substitute for this. It measures whether your suite
exercises the code you wrote, so a thin implementation with few branches can
score higher than a careful one with guards your tests never reach. It tells you
whether a suite is real; it cannot tell you whether the code is right.

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
New tests failed first and pass now, every applicable row of "Boundaries worth a
test" has a test or a stated reason it cannot apply, `loop.py full` is green,
`tamper.py` is clean, and for logic-heavy code `loop.py mutate` reports no
uncaught bugs in the change.
Show both outputs (`ship`).
