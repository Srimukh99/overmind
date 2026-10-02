# evals

Reproducible checks of what the overmind tooling claims. They test the scripts,
not agent behaviour: the cheating diffs and agent mistakes are scripted.

| Eval | Run | Result at v0.7 |
| --- | --- | --- |
| Layout integrity | `python3 tools/check_layout.py` | 16 scripts each in one skill and mentioned; no dangling path or retired name |
| Routing, v0.5 layout vs v0.6 layout | `python3 evals/routing.py` (add `--held-out` once, never tune on it) | dev 90% to 98% top-1, 100% top-3; every v0.5 trigger still routes (100%) |
| Delegation: trust vs old rules vs contract-first | `python3 evals/delegation.py` (`-v` for the full log) | original contract tests passing 2 / 7 / 8 of 8; bad changes landed 4 / 1 / 0 |
| Tamper guard | `python3 evals/tamper_guard.py` | 19 of 19 cheats flagged (15 as FAIL); 0 of 12 honest changes failed |
| Passing tests vs real checks | `sh evals/mutation/run.sh` | weak suite 24% (8 of 33 bugs caught), strong suite 100% (33 of 33); both suites pass |
| ratchet vs naive gate | `python3 evals/ratchet_vs_naive.py` | ratchet 7 of 7 correct; naive gate 2 of 7 |
| Code quality: does a green suite mean correct code? | `python3 evals/code_quality.py` (`-v` to name each hidden failure) | 6 of 6 candidates pass their own suite; 3 are wrong; 10 hidden defects would have shipped. Mutation score does **not** separate them |

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

## Routing eval: what it is and is not

`routing.py` is a lexical stand-in (TF-IDF over skill names and descriptions) for an agent choosing a skill.
It is not a language model. It shows whether descriptions are distinctive and whether any trigger wording was
lost in a refactor; it cannot predict how a real agent behaves. `routing_cases.json` holds a `dev` set
(fine to tune against) and a `held_out` set (frozen: run it once, then write new cases rather than tuning on it).
Cases were written by the author, so treat absolute numbers loosely and compare layouts only.
