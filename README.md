# rubric

**The standard your coding agent is held to.** · v0.8

rubric is an engineering methodology for coding agents, delivered as a library of composable skills. It gives an agent the habits a senior team takes for granted: establish a design before writing code, drive implementation with tests, debug from evidence rather than guesswork, review a change before merging it, and prove work is finished before claiming it is.

What separates it from a document of good intentions is that the important parts are executable. A gate blocks secrets and debug leftovers before a commit. A guard detects a test that was weakened to make a build pass. An iteration loop reverts any step that regresses. None of that depends on a model remembering to be careful.

Fourteen core skills cover the delivery cycle. Four optional packs add depth for regulated domains, data platforms, Kubernetes, and API and agent design.

## Table of Contents

- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
  - [Claude Code](#claude-code)
  - [Codex, Kiro and Qwen Code](#codex-kiro-and-qwen-code)
  - [Cursor](#cursor)
  - [Other agents](#other-agents)
  - [Agent support matrix](#agent-support-matrix)
- [The workflow](#the-workflow)
- [Evidence](#evidence)
- [What's inside](#whats-inside)
  - [Core skills](#core-skills)
  - [Packs](#packs)
  - [Scripts](#scripts)
- [The ship gate](#the-ship-gate)
- [Token budget](#token-budget)
- [Upgrading](#upgrading)
- [Contributing](#contributing)
- [Support](#support)
- [Roadmap](#roadmap)
- [Scope and limitations](#scope-and-limitations)
- [License](#license)

## How it works

Skills activate from the request itself. Ask for a feature and `design` turns a vague ask into an agreed design, then into small tasks with named files and explicit checks. Ask for a fix and `debug` reaches for evidence before it reaches for a patch. The `boot` skill routes anything that does not match a skill directly, so there is no command to remember and no mode to enter.

Deterministic work belongs in code, not in the model. Logs, manifests, infrastructure definitions and dependency trees are parsed by small Python scripts that emit a compact summary, and the agent reads that summary instead of thousands of raw lines. Token use drops and the answers stop drifting between runs.

The process is built around the two failure modes that cost the most. Work that takes several attempts runs under `ratchet`, which anchors the goal, freezes the tests that already pass, measures each iteration against a floor that only rises, and reverts any step that regresses. Work split across parallel agents runs under `delegate`, which is contract-first: the lead defines the shared contract, each worker owns a disjoint set of files in its own worktree, and results are verified against each worker's own test verdict rather than accepted on its word.

Nothing is reported as complete without evidence. The `ship` skill requires command output from the current session before a claim of done, fixed or passing, and its gate blocks secrets, regulated identifiers and debugging leftovers before a commit lands.

## Requirements

- An agent that supports the open [Agent Skills](https://agentskills.io) format and can run shell commands
- Python 3 and git
- PyYAML, for the `crd-check` skill in the `k8s` pack only

## Installation

Install rubric separately for each agent you use. Core skills always install; packs are opt-in.

### Claude Code

As a plugin, from the marketplace in this repository:

```text
/plugin marketplace add Srimukh99/rubric
/plugin install rubric@rubric
```

Packs are published as separate plugins:

```text
/plugin install rubric-regulated@rubric
/plugin install rubric-data@rubric
/plugin install rubric-k8s@rubric
/plugin install rubric-apis-agents@rubric
```

### Codex, Kiro and Qwen Code

Clone the repository and run the installer from the project you want to equip:

```bash
git clone https://github.com/Srimukh99/rubric
cd your-project

/path/to/rubric/install.sh --agent all                        # this project
/path/to/rubric/install.sh --agent all --scope user           # every project
/path/to/rubric/install.sh --agent all --pack regulated,data  # with packs
```

`--agent all` installs for Claude Code, Codex, Kimi Code, Kiro and Qwen Code. Full options:

| Flag | Values |
| --- | --- |
| `--agent` | `claude`, `codex`, `kiro`, `qwen`, `cursor`, `all` |
| `--scope` | `project` (default), `user` |
| `--pack` | `regulated`, `data`, `k8s`, `apis-agents`, `all` |
| `--target` | directory to install into (default: current) |

### Cursor

Install with `--agent cursor` alone. Cursor reads `.cursor/skills/`, `.claude/skills/` and `.agents/skills/`, so installing for several agents at once would list every skill more than once.

```bash
/path/to/rubric/install.sh --agent cursor
```

### Other agents

One command, which detects the agent and installs everything it finds, packs included:

```bash
npx skills add Srimukh99/rubric
```

### Agent support matrix

| Agent | Install | Skills directory |
| --- | --- | --- |
| Claude Code | `--agent claude` | `.claude/skills/` |
| Codex, Kimi Code | `--agent codex` | `.agents/skills/` |
| Kiro | `--agent kiro` | `.kiro/skills/` |
| Qwen Code | `--agent qwen` | `.qwen/skills/` |
| Cursor | `--agent cursor` | `.cursor/skills/` (also reads `.claude/skills/`, `.agents/skills/`) |
| Gemini CLI, GitHub Copilot, OpenCode, Roo Code, Goose and others | `npx skills add Srimukh99/rubric` | the agent's own directory |

Skills are loaded by the agent application rather than the model, so any model works inside an application that supports the format.

## The workflow

```text
design → build (ratchet, delegate) → review → ship
something breaks: debug (logs → source line → cause → fix)        outage: firefight
```

1. **design** — Activates on a feature or behaviour change with nothing specced. Turns the ask into an agreed design, then into tasks small enough to verify, each with exact files and checks.

2. **build** — Activates once a plan exists. Creates an isolated worktree, runs a test-first loop built for agent speed, and escalates checks in tiers: typecheck and lint on every edit, related tests when those pass, the full suite before done.

3. **ratchet** — Activates when work takes several attempts. Anchors the goal and scope, freezes passing tests as a floor, and accepts an iteration only if it raises that floor. Rejected steps revert to the last accepted checkpoint.

4. **delegate** — Activates when a plan has independent tasks. The lead writes the shared contract and assigns each worker files no other worker may touch; overlapping ownership is rejected before any work starts. Verified workers land in waves.

5. **review** — Activates when a change is ready. Reviews the diff independently, ranks findings by severity, and treats incoming feedback on its merits rather than implementing it on sight.

6. **ship** — Activates before any commit, merge or deploy. Runs the gate, requires command output as proof of every claim, checks a release is reversible, and finishes the branch.

Skills are checked before the task begins, not offered afterwards.

## Evidence

Each mechanism is measured against the alternative, using scripted adversaries rather than argument. Every figure is reproducible on your machine; `evals/README.md` has the method and the caveats, and CI runs all five on every push.

| Mechanism | rubric | The alternative |
| --- | --- | --- |
| **Contract-first delegation** (`delegate`) | **8 of 8** contract tests passing, **0** bad changes reached main | trust each worker's claim: 2 of 8, and **4** bad changes landed |
| **Rising-floor iteration** (`ratchet`) | **7 of 7** iterations judged correctly | a "the failing count did not rise" gate: 2 of 7 |
| **Test-tampering guard** (`build`) | **19 of 19** cheats flagged, **0 of 12** honest changes wrongly failed | nothing stops a skipped or weakened test |
| **Mutation testing** (`build`) | a strong suite kills **33 of 33** injected bugs | a green suite that kills **8 of 33** — and still reports every test passing |
| **Skill routing** (`boot`) | **98%** top-1, **100%** top-3, 76% on a frozen held-out set, every legacy trigger preserved | 3.6% by chance across 28 skills |
| **Boundary guidance** (`build`) | names **6 of 6** defect classes the acceptance suites exercise, and **10 of 10** real defects are reachable from it | a green suite: **6 of 6** candidates pass their own tests and **3 are wrong** |

```bash
python3 evals/delegation.py          # needs pytest
python3 evals/ratchet_vs_naive.py    # needs pytest
python3 evals/tamper_guard.py
sh evals/mutation/run.sh             # needs pytest + hypothesis
python3 evals/routing.py
python3 evals/code_quality.py
python3 evals/guidance_coverage.py
```

Two results are worth dwelling on, because both are uncomfortable.

**A green test run proves nothing on its own.** In `evals/mutation`, two suites both pass; one catches 24% of injected bugs and the other 100%. In `evals/code_quality.py`, all six candidate implementations pass the tests their author wrote, three are wrong, and ten defects would have shipped.

**Mutation score does not grade your code.** The same eval found it anti-correlated across implementations: thin candidates averaged 83%, careful ones 62%, because a thin implementation has fewer branches for a shallow suite to miss. Mutation score tells you whether a suite is real. It cannot tell you whether the code is right, and `--min` will not catch a thin implementation.

### What these evals do not show

The adversaries are scripted, not live agents. These measure whether the tooling catches known mistakes — not whether an agent using rubric writes better code than one without it. That comparison needs a model API key and is deliberately not built here. The boundary-guidance figures carry a further caveat: the defect taxonomy was derived from the same acceptance suites the guidance was then written against, so read the four classes drawn from outside those tasks as the honest signal rather than the headline number.

## What's inside

### Core skills

**Routing**
- **boot** — Routes every task to the right skill before exploration begins

**Design and implementation**
- **design** — A fuzzy ask into an approved design, then small verifiable tasks
- **build** — Isolated worktree, test-first loop, tiered checks, a boundary-case table, mutation testing, and a guard that catches skipped or weakened tests
- **ratchet** — Iterations that must improve the code without breaking what works or drifting from the goal
- **delegate** — Contract-first parallel work with disjoint file ownership and verified, not trusted, results

**Diagnosis**
- **debug** — A log in, the error and its source line out; or a service name in, and it identifies the runtime, cloud and log shipper and queries the right backend across 9 clouds and 7 aggregators, never `kubectl`. Exports the service map as an Open Knowledge Format bundle
- **firefight** — Incident triage, mitigation and blameless postmortems

**Review and release**
- **review** — Independent severity-ranked review, plus security review of risky changes
- **ship** — The quality and compliance gate, proof before "done", a release checklist with a rollback plan, gradual rollout, and clean merge or PR

**Risk and compliance**
- **legal-traps** — COPPA, HIPAA pixels, wiretap claims, EU font loading, unsubscribe and postal address, hidden fees, auto-renew consent, DMCA agent
- **iac-check** — Public databases, open security groups, public buckets, wildcard IAM, privileged pods, secrets in images
- **deps-check** — Vulnerable dependencies across Python, Node, Go, Rust and container images

**Operations**
- **observe** — Logs, RED metrics, traces, health checks, alerts, SLIs, SLOs, error budgets and runbooks

**Meta**
- **forge** — Creating and editing skills, with a standard for proving one changes behaviour

Each skill opens with a short table of situations pointing to a single reference file, so the agent reads only what the moment requires.

### Packs

| Pack | Skills | Domain |
| --- | --- | --- |
| `regulated` | `reg-phi` `reg-pci` `reg-money` `reg-audit` | Health data and HIPAA, PCI DSS card data, money arithmetic and ledgers, audit trails for SOX and SOC 2 change control |
| `data` | `pg-explain` `pg-migrate` `mongo-index` `snow-perf` `dbx-perf` | Slow Postgres queries, zero-downtime schema changes, MongoDB indexes, Snowflake cost, Spark tuning |
| `k8s` | `k8s-triage` `drift` `crd-check` | CrashLoopBackOff and stuck rollouts, git versus live state, CRD validation across cluster upgrades |
| `apis-agents` | `api-pick` `agent-tools` | REST against GraphQL against gRPC, and tool design agents use well |

### Scripts

Sixteen scripts carry the deterministic work. Fourteen run standalone and print a compact summary; `mutate.py` and `backends.py` are imported by `loop.py` and `log_fetch.py`. The commands you invoke directly:

```bash
kubectl logs pod/api-7d9f --previous | python3 skills/debug/scripts/log_trace.py --repo .
python3 skills/debug/scripts/service_map.py .            # map services, clouds and shippers
python3 skills/debug/scripts/service_map.py . --okf      # export that map as an OKF bundle in docs/okf
python3 skills/debug/scripts/log_fetch.py notification-service --since 2h
python3 skills/legal-traps/scripts/legal_traps.py .
python3 skills/build/scripts/loop.py fast                # then focused, then full
python3 skills/build/scripts/loop.py mutate              # inject bugs; report the ones no test catches
python3 skills/build/scripts/tamper.py                   # catch skipped, deleted or weakened tests
python3 skills/ratchet/scripts/ratchet.py start --goal "..." --scope 'src/x/**' --target tests/test_x.py::test_y
python3 skills/ratchet/scripts/ratchet.py check          # ACCEPT / REJECT / STALL / DONE
python3 skills/delegate/scripts/team.py init --goal "..." --contract tests/contract
python3 skills/delegate/scripts/team.py verify           # each worker's claim against its ratchet verdict
python3 skills/delegate/scripts/team.py integrate --apply
python3 skills/iac-check/scripts/iac_check.py infra/ deploy/
python3 skills/deps-check/scripts/deps_check.py
python3 packs/k8s/skills/crd-check/scripts/crd_check.py deploy/ --target 1.30
python3 packs/k8s/skills/drift/scripts/drift_check.py --k8s-dir deploy/ -n prod
```

Most of these only read. The ones that write say so: `ratchet` keeps state in `.rubric/` and checkpoints under `refs/rubric/`, `team` creates worktrees and applies patches, `loop.py mutate` edits changed files and restores them, `service_map.py --okf` writes `docs/okf`, and `vibe_check.py --install-hook` writes a commit hook. `drift_check.py` never writes to a cluster, only to a local history file.

## The ship gate

`vibe-check`, in the `ship` skill, blocks cloud keys and private keys, card numbers, US SSN patterns, committed `.env` files, debugger statements, focused tests and merge conflict markers. It has no dependencies beyond Python 3.

```bash
python3 skills/ship/scripts/vibe_check.py                  # staged changes in the current repo
python3 skills/ship/scripts/vibe_check.py --repo ../myapp  # or another repo
python3 skills/ship/scripts/vibe_check.py --range origin/main...HEAD
python3 skills/ship/scripts/vibe_check.py --full           # and the project's lint, types and tests
python3 skills/ship/scripts/vibe_check.py --install-hook   # run on every commit
```

| Finding | Level |
| --- | --- |
| Cloud keys, private keys, provider tokens (AWS, GitHub, Slack, Stripe, Google, OpenAI, Anthropic) | FAIL |
| `.env`, `.pem`, `.p12`, `id_rsa` and similar files committed | FAIL |
| Luhn-valid card numbers, excluding published processor test cards | FAIL |
| US SSN patterns | FAIL |
| Debugger statements and focused tests | FAIL |
| Merge conflict markers | FAIL |
| Hard-coded secret-looking assignments | WARN |
| Files over 5 MB | WARN |

A deliberate false positive can carry `vibe-check: ignore` on the line, used sparingly and explained in the pull request.

Project-specific commands go one per line in `.rubric/checks`, and each fails the gate on a non-zero exit. Those are shell commands read from the repository, so review that file before running the gate somewhere you do not control. The workflow in `.github/workflows/ci.yml` runs skill lint, the layout check, the unit suite and the gate on every push and pull request, and a second job runs all five evals.

## Token budget

Only skill names and descriptions occupy context until a skill is used. The 14 core descriptions total roughly 680 tokens; the four packs add roughly 620 more. Opening a skill loads its table, between 200 and 460 tokens, and then one reference file — so a working session reads far less than a library that keeps its guidance in prose. Run `python3 tools/lint_skills.py` for the current figures, and `python3 evals/routing.py` to confirm that a description edit has not cost any routing accuracy.

## Upgrading

### From overmind

This project was called overmind through v0.7. The name collided with four separate projects over 500 stars, including a 3,747-star Procfile manager, so v0.8 renames it.

| Was | Now |
| --- | --- |
| `.overmind/` | `.rubric/` |
| `refs/overmind/` | `refs/rubric/` |
| `REPO.overmind-team/` | `REPO.rubric-team/` |
| `overmind@overmind`, `overmind-regulated`, … | `rubric@rubric`, `rubric-regulated`, … |

Skill names, script names and script paths are unchanged. To carry existing state across:

```bash
git mv .overmind .rubric            # project state, loop.json, checks
```

A ratchet in progress is simplest to restart, since its checkpoints live under the old ref namespace. Reinstall the Claude plugins under their new names. The GitHub repository keeps a permanent redirect, so `npx skills add Srimukh99/overmind` continues to work.

### From 0.5

<!-- upgrade:start -->
Version 0.5 had 41 skills. Nothing was removed: instructions moved into `references/` files and every script is unchanged. Old names map as follows.

| 0.5 name | Now |
| --- | --- |
| `shape`, `blueprint` | `design` |
| `build`, `prove-it`, `sandbox` | `build` |
| `hunt`, `trace-back`, `log-trace`, `log-fetch` | `debug` |
| `second-look`, `weigh-in`, `threat-check` | `review` |
| `vibe-check`, `receipts`, `land`, `preflight`, `ship` | `ship` |
| `observe`, `slo` | `observe` |
| `reg-*`, `pg-*`, `mongo-index`, `snow-perf`, `dbx-perf`, `k8s-triage`, `drift`, `crd-check`, `api-pick`, `agent-tools` | the matching pack, same names |
| the rest | unchanged |

Script paths moved with their skills: `skills/prove-it/scripts/loop.py` is now `skills/build/scripts/loop.py`.
<!-- upgrade:end -->

## Contributing

1. Read `skills/forge/SKILL.md`, which defines the format and the standard for proving a skill helps.
2. One skill per pull request, with the three should-trigger and two should-not prompts you tested in the description.
3. CI must pass: skill lint, layout check, unit tests, the gate, and the evals.
4. Core stays at 14 skills or fewer. A new specialist skill belongs in a pack under `packs/NAME/skills/`; a new job inside an existing skill belongs in its `references/` directory.
5. Original wording only, in skills and in references.
6. Regulated-domain skills need a source for every rule and must stay labelled as engineering guidance rather than legal advice.

See `CONTRIBUTING.md` for the full process.

## Support

Questions, defects and feature requests belong in [GitHub Issues](https://github.com/Srimukh99/rubric/issues).

## Roadmap

- Real agents on real tasks, measured with and without rubric, to go beyond the scripted evals above
- `idx` — a local repository index so agents look up symbols instead of reading whole files
- A context-compression harness for tool output
- Adversarial evals for the remaining script-backed skills: `ship`, `iac-check`, `legal-traps`, `debug`
- Deeper reference material for `forge`, `delegate` and `design`, the thinnest skills in the library

## Scope and limitations

The `reg-*` skills are engineering guardrails, not legal or compliance advice. Your compliance, privacy and security teams set policy. `vibe-check`, `iac-check` and the other scripts reduce risk; they do not guarantee that a system is secure or compliant.

## License

MIT. See `LICENSE`.
