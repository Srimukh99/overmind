# evals

Reproducible checks of what the overmind tooling claims. They test the scripts,
not agent behaviour: the cheating diffs and agent mistakes are scripted.

| Eval | Run | Result at v0.5 |
| --- | --- | --- |
| Layout integrity | `python3 tools/check_layout.py` | 14 scripts each in one skill and mentioned; no dangling path or retired name |
| Routing, v0.5 vs v0.6 | `python3 evals/routing.py` (add `--held-out` once, never tune on it) | dev 90% to 93%; held-out 71% to 73%; every v0.5 trigger still routes (100%) |
| Delegation: trust vs old rules vs contract-first | `python3 evals/delegation.py` (`-v` for the full log) | original contract tests passing 2 / 7 / 8 of 8; bad changes landed 4 / 1 / 0 |
| Tamper guard | `python3 evals/tamper_guard.py` | 19 of 19 cheats flagged; 0 of 12 honest changes failed |
| Passing tests vs real checks | `sh evals/mutation/run.sh` | weak suite 24%, strong suite 100%; both pass |
| ratchet vs naive gate | `python3 evals/ratchet_vs_naive.py` | ratchet 7 of 7 correct; naive gate 2 of 7 |

Token savings from `loop.py` (pytest, 153 tests): ~513 tokens raw to ~129 with 2 failures
(all values and file:line kept); ~1,958 to ~199 with 12 failures (all 12 named).

Still missing: a with-and-without comparison of real agents on real tasks.
That needs a model API key; contributions welcome.

## Routing eval: what it is and is not

`routing.py` is a lexical stand-in (TF-IDF over skill names and descriptions) for an agent choosing a skill.
It is not a language model. It shows whether descriptions are distinctive and whether any trigger wording was
lost in a refactor; it cannot predict how a real agent behaves. `routing_cases.json` holds a `dev` set
(fine to tune against) and a `held_out` set (frozen: run it once, then write new cases rather than tuning on it).
Cases were written by the author, so treat absolute numbers loosely and compare layouts only.
