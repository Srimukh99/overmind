# evals

Reproducible checks of what the rubric tooling claims. They test the scripts,
not agent behaviour: the cheating diffs and agent mistakes are scripted.

| Eval | Run | Result at v0.7 |
| --- | --- | --- |
| Layout integrity | `python3 tools/check_layout.py` | 16 scripts each in one skill and mentioned; no dangling path or retired name |
| Routing, v0.5 layout vs v0.6 layout | `python3 evals/routing.py` (add `--held-out` once, never tune on it) | dev 90% to 98% top-1, 100% top-3; every v0.5 trigger still routes (100%) |
| Delegation: trust vs old rules vs contract-first | `python3 evals/delegation.py` (`-v` for the full log) | original contract tests passing 2 / 7 / 8 of 8; bad changes landed 4 / 1 / 0 |
| Tamper guard | `python3 evals/tamper_guard.py` | 19 of 19 cheats flagged (15 as FAIL); 0 of 12 honest changes failed |
| Passing tests vs real checks | `sh evals/mutation/run.sh` | weak suite 24% (8 of 33 bugs caught), strong suite 100% (33 of 33); both suites pass |
| ratchet vs naive gate | `python3 evals/ratchet_vs_naive.py` | ratchet 7 of 7 correct; naive gate 2 of 7 |
| Guidance coverage and defect reachability | `python3 evals/guidance_coverage.py` | rubric 6/6 core, 2/4 extended, 10/10 defects reachable; superpowers 2/6, 1/4, 3/10 |
| Code quality: does a green suite mean correct code? | `python3 evals/code_quality.py` (`-v` to name each hidden failure) | 6 of 6 candidates pass their own suite; 3 are wrong; 10 hidden defects would have shipped. Mutation score does **not** separate them |
| Claim guard: unproven "done" claims, named vs. stopped | `python3 evals/claim_guard.py` (`--lib NAME=PATH` to score another library) | `receipts.md` names 12 of 12; the Stop hook stops the 5 of 12 a script can see; clean work not blocked, no loop |

Every row above was re-run at v0.7. `delegation.py`, `ratchet_vs_naive.py` and
`mutation/run.sh` need `pytest` (mutation also needs `hypothesis`) and print a
`SKIPPED` line and exit 0 when it is missing. The held-out routing figure
(71% to 73% when first measured) has **not** been re-measured since the v0.7
description tightening: that set is frozen on purpose, so re-run it deliberately
rather than as part of a loop.

Token savings from `loop.py` (pytest, 153 tests): ~513 tokens raw to ~129 with 2 failures
(all values and file:line kept); ~1,958 to ~199 with 12 failures (all 12 named).

Still missing: a with-and-without comparison of real agents on real tasks.
That needs a model API key; contributions welcome.

## Code quality eval: a negative result worth keeping

`code_quality.py` gives three tasks a `visible` suite of the kind an implementer
writes from the spec, and a `hidden` acceptance suite they never see. Each task
has a thin candidate and a solid one. Both pass the visible suite.

Two findings, and the second one is inconvenient:

**A green suite carries no information about correctness.** All six candidates
pass their own tests; three are wrong, with 10 hidden failures between them.
That is the same point `mutation/run.sh` makes, from the other direction.

**Mutation score does not predict correctness across implementations, and here
it is anti-correlated.** Thin candidates averaged 83%, solid ones 62%; in every
task the thin implementation scored at least as high.

| task | thin | solid |
| --- | --- | --- |
| discount | 100% | 93% |
| overlap | 50% | 33% |
| pagination | 100% | 60% |

The reason is structural: a thin implementation has fewer mutation sites, and
the visible suite covers a larger share of them. A solid implementation adds
guards - `max`, `min`, emptiness checks - that the visible suite never
exercises, so those mutants survive.

This does not invalidate `mutation/run.sh`. That eval holds one implementation
fixed and varies the suite, which is the question mutation testing answers:
*is my suite real?* `code_quality.py` varies the implementation and holds the
suite style fixed, asking *is my code right?* Mutation score does not answer
the second question, and a `--min` threshold on it will not catch a thin
implementation. Treat the score as a property of a suite, never as a grade for
the code.

What did separate thin from solid: nothing in the toolchain. Only the hidden
suite, which is to say only writing the boundary cases in the first place.
That is a guidance gap, not a tooling gap, and it is the target for the
reference-depth work in `docs/specs/2026-10-02-methodology-depth-design.md`.

## Guidance coverage: what the score does and does not mean

`code_quality.py` showed that no tool in the box separates a thin
implementation from a solid one. `guidance_coverage.py` measures the thing that
does: whether the advice given at the moment tests are written names each
defect class. Two scores, and the second is the honest one.

**Core classes** are derived from `code_quality.py`'s hidden suites. rubric
scores 6/6 against superpowers' 2/6 - but that taxonomy came from the same
three tasks the guidance was then written against, so read it as a floor on
what the guidance covers, not as a measure of breadth.

**Extended classes** are canonical categories *not* derived from those tasks:
null handling, large input, concurrency, locale. rubric scores 2/4 and
superpowers 1/4. That narrow lead is the trustworthy number.

**Defect reachability** is the third number and the one that answers the
original question. It runs the thin candidates, collects the hidden tests that
actually fail, and asks for each one whether a library's guidance points you at
it. rubric reaches 10 of 10, superpowers 3 of 10. The failing set is measured
on every run rather than hardcoded, and a stale mapping prints a warning and
fails `tests/test_guidance_coverage.py`.

Note what reachability does *not* fix: the classes still came from these three
tasks. It weights the score by real defects instead of class count, which is
better, but it cannot escape that circularity. The extended classes remain the
only un-circular comparison here.

Neither score says the guidance works. The metric checks that a class is
*named*, which is necessary and not sufficient; whether naming it changes what
an agent writes needs the agent comparison this directory still lacks.

The metric is gameable by listing keywords, so it prints the matched line for
every hit - read them. Six measurement defects were found and fixed while
building it, each of which would have changed the verdict: "Mock only slow or
external boundaries" scoring as boundary-value guidance, "improve beyond the
test" as out-of-range, "Partial mocks fail silently" as a partial last chunk,
`\bevery` matching "everything", a genuine superpowers line ("zero, empty, nil
... input") being missed, and - worst - a sentence saying locale is out of
scope scoring as locale coverage. `tests/test_guidance_coverage.py` keeps all
six fixed.

Concurrency and locale were deliberately left out of rubric's table rather
than added to raise the score; `prove-it.md` states why in the file.

## Claim guard: words and enforcement, measured apart

`claim_guard.py` scripts twelve turns that end in a claim with nothing behind
it - a red-flag phrase ("should work", "looks right", "I'm confident") or an
excuse for skipping the check ("it's one line", "a subagent said it was done",
"CI will catch it"). It scores two different things, and only one of them is
worth much.

**Named** asks whether the library's completion guidance names that phrase or
excuse. rubric scores 12 of 12, and that number is close to meaningless on its
own: the cases and `receipts.md` were written in the same change, so this is a
floor on what the prose covers, not evidence it is broad. It is kept as a
regression guard - thinning the red-flag list or dropping the delegation row
fails `tests/test_claim_guard.py`. Two rows carry a second pattern so a
half-answer cannot score: the delegation row only counts if it sends you to the
diff, and the requirements row only if it sends you back to the request.

**Stopped** is measured, not asserted. Each of five cases plants a real mistake
in a throwaway repo - a leftover `breakpoint()`, a cloud key in a file that was
never staged, a `.env` added beside a one-line change, conflict markers in a
"docs only" edit, a red suite - and runs `vibe_check.py --stop-hook` against it.
A case counts only when the gate exits 2. Two controls run every time: clean
work must not be blocked, and a payload carrying `stop_hook_active` must exit 0,
since a Stop hook that re-blocks its own output loops forever.

The gap is the finding: **5 of 12**. The other seven are judgement claims - a
subagent's report taken on trust, a requirement no one wrote down, "the types
check, so it works" - and no pattern in a scanner sees them. That is why the
prose half exists, and why the prose half cannot be graded by the same
measurement that grades the hook. Comparing another library is `--lib
NAME=PATH`; it scans the role-named completion guidance under that library's
`skills/` and prints which files it read, so a 0 that came from a file-naming
mismatch is visible rather than silent.

## Routing eval: what it is and is not

`routing.py` is a lexical stand-in (TF-IDF over skill names and descriptions) for an agent choosing a skill.
It is not a language model. It shows whether descriptions are distinctive and whether any trigger wording was
lost in a refactor; it cannot predict how a real agent behaves. `routing_cases.json` holds a `dev` set
(fine to tune against) and a `held_out` set (frozen: run it once, then write new cases rather than tuning on it).
Cases were written by the author, so treat absolute numbers loosely and compare layouts only.
