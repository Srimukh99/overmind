# Methodology depth: design

Date: 2026-10-02 · Status: awaiting review · Scope: v0.8

## Intent

Make overmind demonstrably strong on methodology depth, which is the one
dimension where a measured comparison against superpowers currently favours
superpowers. Two workstreams, chosen by the maintainer:

- **A. Extend the adversarial evals** to the script-backed skills that have no
  outcome eval, so more mechanisms can be *shown* to beat the naive path.
- **B. Deepen the reference prose** for the skills that are thinnest, so the
  guidance holds up when someone actually reads it.

Success means: every script-backed mechanism has a reproducible eval showing it
beats the obvious alternative, and the four thinnest methodology skills carry
reference material a working engineer would not find shallow. Both without
moving the always-loaded budget.

### What is already true

Measured at v0.7, not asserted:

| | superpowers | overmind |
| --- | --- | --- |
| Always loaded | 576 tok | 683 tok |
| Cost per skill opened | ~2,800 tok | ~506 tok |
| Session cost, 2 skills opened | 5,988 tok | 1,963 tok |
| Routing | not measured here | 98% top-1, 100% top-3 |

Four mechanisms already have outcome evals and reproduce their published
numbers: contract-first delegation (8/8 vs 2/8), rising-floor iteration (7/7 vs
2/7), the tamper guard (19/19 cheats, 0/12 false failures), and mutation testing
(100% vs 24%, both suites green). Those were repaired and surfaced in `f7702b6`.

### The depth gap, per skill

Tokens of SKILL.md plus references, against the nearest superpowers
counterpart. This is the evidence the priority order rests on.

| overmind skill | table | refs | total | superpowers counterpart | total | ratio |
| --- | --- | --- | --- | --- | --- | --- |
| `forge` | 371 | 0 | 371 | writing-skills | 22,745 | **61.3x** |
| `delegate` | 637 | 0 | 637 | subagent-driven-development, dispatching-parallel-agents | 14,605 | **22.9x** |
| `design` | 230 | 449 | 679 | brainstorming, writing-plans | 10,827 | **15.9x** |
| `build` | 373 | 1,225 | 1,598 | TDD, executing-plans, using-git-worktrees | 11,204 | 7.0x |
| `boot` | 777 | 0 | 777 | using-superpowers | 5,141 | 6.6x |
| `review` | 284 | 725 | 1,009 | requesting/receiving-code-review | 3,893 | 3.9x |
| `debug` | 471 | 1,897 | 2,368 | systematic-debugging | 8,414 | 3.6x |
| `ship` | 428 | 1,412 | 1,840 | verification-before-completion, finishing-a-branch | 2,831 | 1.5x |
| `firefight` | 362 | 0 | 362 | none | — | — |

`ship` is already at near-parity, which is consistent with the shipping gate
being overmind's strongest area. The gap is concentrated in `forge`,
`delegate` and `design` — the skills that carry the *thinking*, which is
exactly where the depth verdict was lost.

## Goals

1. Every skill with a script has a reproducible eval comparing it to the naive
   alternative, with published catch and false-positive counts - except
   `deps-check`, deferred under A5 for the reason stated there. That is 8 of
   14 core skills, not all 14.
2. `forge`, `delegate`, `design` and `review` carry reference material deep
   enough that the depth ratio against superpowers falls below 3x.
3. The always-loaded budget stays at 683 tokens or less.
4. Per-skill on-open cost (the SKILL.md table) stays within 10% of today.
5. Routing stays at 98% top-1 and 100% on legacy triggers.

## Non-goals

- **Agent-based evals.** Comparing real agents with and without overmind needs
  a model API key, and `AGENTS.md` forbids committing LLM API integrations to
  this repository unless explicitly requested as a feature. `evals/README.md`
  already names this as the honest missing piece. It stays named, not built.
- **Growing the core past 14 skills.** `forge` caps it; new capability goes in
  a pack or a reference.
- **Merging or removing skills.** Out of scope; the maintainer declined it.
- **Session self-diagnosis.** The one capability superpowers has that overmind
  lacks. The maintainer declined it for now; recorded here so it is not lost.

## Workstream A: adversarial evals

### Pattern

Follow `evals/tamper_guard.py` exactly, because it is the idiom that already
works: build a fixture, apply a list of named adversarial cases and a list of
named honest cases, run the real script over each, and report catches against
false positives. Scripted adversaries, deterministic output, no model calls.
Each new eval uses `evals/_eval_git.py` for any git work.

### Priority and content

**A1. `ship` / `vibe_check.py` — highest value, lowest effort.**
This is the mechanism the bake-off called decisive, and it has no eval. Pure
text in, findings out, so no git fixture is needed beyond a staged diff.
- Adversarial: a live-looking key per provider rule (10 rules), a private key
  block, a Luhn-valid card, an SSN, a committed `.env`, `.pem`, `id_rsa`, a
  `breakpoint()`, a `debugger;`, a focused-test marker, a conflict marker.
  ~20 cases. (Spelling that marker out here trips the gate on this very file,
  which is itself a finding - see the note under A1's acceptance criteria.)
- Honest: published processor test cards, `.env.example`, a non-Luhn 16-digit
  order id, a placeholder password, an `AKIA`-shaped string inside a test
  fixture carrying `vibe-check: ignore`, a legitimate `describe(`. ~10 cases.
- Asserts: every adversarial case is FAIL; no honest case is FAIL.
- Naive comparison: grep for the word `secret`, which is what a project without
  a gate actually does. Report both catch rates.

**A2. `iac-check` / `iac_check.py`.** Planted public database, open security
group, public bucket, wildcard IAM, privileged pod, secret baked into an image,
each paired with a safe equivalent of the same resource. Asserts the risky one
is flagged and the safe one is not.

**A3. `legal-traps` / `legal_traps.py`.** Planted COPPA age gate, HIPAA pixel,
missing unsubscribe and postal address, drip pricing, auto-renew without
consent, remote font load, missing DMCA agent — each against a compliant
version of the same page.

**A4. `debug` / `log_trace.py` and `service_map.py`.** A fixture repo plus
captured log text; asserts the reported source line matches the planted one,
and that the service map identifies the right runtime, cloud and shipper.
Accuracy over a fixture set rather than catch-versus-false-positive.

**A5. `deps-check` / `deps_check.py`.** Deferred. Needs offline lockfile
fixtures pinned to known-vulnerable versions, which rot as advisory databases
change. Lowest value per unit of maintenance; revisit after A1–A4.

### Acceptance criteria

- Each eval runs offline, needs no API key, and exits 0 while printing counts.
- Each is registered in `evals/README.md` with its v0.8 numbers.
- Each is added to the `evals` CI job.
- `tools/check_layout.py` and `tools/lint_skills.py` stay at 0 errors.

### A note the gate produced about itself

Writing this spec tripped `vibe_check.py`: naming a focused-test marker in prose
is indistinguishable, to the leftover rules, from leaving one in code. The gate
scans every text file, so any document describing its own rules fails it.

That is worth fixing narrowly rather than broadly. Secret, key, card and SSN
rules should keep applying to Markdown, because a credential pasted into a
README is a real leak. The *leftover* rules - debugger statements and focused
tests - describe code constructs and cannot be left behind in prose. A
conflict marker in Markdown is still a genuine bad merge, so it stays.

Proposed, to be confirmed while building A1: skip only the debugger-statement
and focused-test rules for files with a prose extension, and add both a
positive and a negative case for it to A1's fixture set. The `vibe-check:
ignore` marker is the escape hatch today, but needing it to write documentation
is a sign the rule is slightly too broad, not that the document is wrong.

### Honest limit

Six core skills are prose-only — `boot`, `design`, `firefight`, `forge`,
`observe`, `review` — and cannot get a script eval. Workstream A raises
mechanism coverage from 4 of 14 to 8 of 14 and stops there. The remaining six
are reachable only by the agent-based eval that is a non-goal above. The
Evidence section of the README must say so rather than implying full coverage.

## Workstream B: reference depth

### Constraint that makes this safe

References load only when a skill's table points to them. Deepening references
therefore costs nothing on the always-loaded budget and nothing on the on-open
cost of the table. The cost is paid only by the reader who needed that depth.
This is the architecture working as intended, and it is why this workstream
does not threaten the efficiency result.

**Therefore: no SKILL.md table grows. All new material lands in
`references/`.** Any table edit is limited to adding one row pointing at a new
reference file.

### Priority and content

**B1. `forge` (371 tok, 61.3x behind).** Today it is a single page with no
references, which is indefensible for the skill that defines how every other
skill is written. Add:
- `references/writing-a-skill.md` — the full format contract, naming, the
  description-as-trigger-surface argument with the v0.7 measurement as the
  worked example, and the token arithmetic of always-loaded against on-open.
- `references/proving-a-skill.md` — the trigger-test method (3 should-fire, 2
  should-not), how to use `evals/routing.py` as the guard, and how to add an
  adversarial eval in the `tamper_guard.py` idiom.
- `references/skill-review.md` — what to reject in a skill PR, with examples.

**B2. `delegate` (637 tok, 22.9x behind).** Has a strong script and an eval but
no prose. Add:
- `references/contract-first.md` — how to write the shared contract, how to
  partition file ownership so `team.py check` passes, and why ownership is
  enforced before work starts rather than at merge.
- `references/verifying-workers.md` — reading a worker's claim against its
  ratchet verdict, the four failure modes the delegation eval already scripts - scope
  wander, false claim, goalpost move, overlapping work - and what to do with each.
- `references/waves.md` — integrating in waves, handling a rejected worker.

**B3. `design` (679 tok, 15.9x behind).** Add:
- `references/from-ask-to-design.md` — the question sequence that turns a vague
  ask into something approvable, and when to stop asking.
- `references/task-breakdown.md` — what makes a task verifiable: exact files,
  the test that proves it, the command that shows it.

**B4. `review` (1,009 tok, 3.9x behind).** Add:
- `references/severity.md` — ranking findings so the important one is not
  third in a list of nine.
- Extend the existing feedback reference with judging a suggestion on merit,
  including when to disagree with a reviewer and how to say so.

### Acceptance criteria

- Each new reference is under 200 lines, per `forge`.
- All wording original; no text adapted from another project.
- Each new reference is reachable from exactly one row of its skill's table,
  and `tools/check_layout.py` reports no dangling path.
- Depth ratio for `forge`, `delegate`, `design`, `review` falls below 3x, measured
  by `tools/weigh_depth.py`, which this workstream must commit as its first
  deliverable. The table above was produced by a throwaway script; an acceptance
  criterion that cannot be re-run is not a criterion. The tool takes a path to a
  second skill library and prints the per-skill table, so the comparison is
  reproducible by anyone, against any library.
- Always-loaded stays at or under 683 tokens; `lint_skills.py` confirms.

## Verification plan

Run after each change, not at the end:

```bash
python3 tools/lint_skills.py                 # 0 errors, <= 683 tok core
python3 tools/check_layout.py                # 0 errors, no dangling paths
python3 -m unittest discover -s tests        # all green
python3 evals/routing.py                     # 98% top-1, 100% legacy
python3 skills/build/scripts/tamper.py --repo .   # no weakened tests
python3 skills/ship/scripts/vibe_check.py    # 0 FAIL
```

Plus the new evals from workstream A as they land, and a re-run of the depth
measurement script to confirm the B targets are met.

## Risks

| Risk | Mitigation |
| --- | --- |
| Deeper references tempt table growth, eroding the on-open win | Hard rule: tables gain at most one row; `lint_skills.py` and the per-skill table measurement both checked every change |
| A1's honest cases produce false positives, making the gate look bad | That is the eval doing its job. Fix the gate, do not soften the case. A false positive found here is strictly better than one found by a user |
| New reference prose restates the table instead of adding depth | Each reference must answer a question the table only names. Review criterion, not a test |
| Writing depth for `forge` while editing skills creates circularity | Write `forge`'s references last in B, after B2–B4 have exercised the rules in practice |
| Workstream A implies full mechanism coverage | Evidence section states 8 of 14 explicitly, and names the agent-based eval as missing |

## Sequence

A1 first: it is the highest-value mechanism, the cheapest eval to write, and it
tests the thing most likely to be relied on. Then B2 and B3, which are the
depth gaps attached to skills that already have working machinery. Then A2 and
A3. Then B4, then B1. A4 and A5 last.

Each item is independently shippable and independently verifiable.

This spec is deliberately larger than one implementation plan. Expect it to
decompose: A1 alone is a plan, B2 and B3 together are a plan, and the tail
(A2-A4, B1, B4) is a third. Planning should follow that split rather than
attempt all nine items in one pass.
