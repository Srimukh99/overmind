# overmind

**The mind above your agents. Ship like a senior team.** · v0.7

overmind is a lean set of skills that gives your coding agent senior-engineer habits: design before code, test first, debug from evidence, review before merge, and prove it works before saying it's done. It ships 14 core skills that cover the whole job for a small team, plus optional packs for regulated finance and healthcare work, Postgres, MongoDB, Snowflake and Databricks, Kubernetes, and API and agent design.

Small scripts do the heavy lifting, not the model. Logs, manifests and IaC are scanned locally, so the agent reads a 20-line summary instead of thousands of lines. That keeps token use low.

It works with any agent that supports the open [Agent Skills](https://agentskills.io) format: Claude Code, Codex, Kiro, Cursor, GitHub Copilot, Gemini CLI and more.

## Install

**Any agent, one command** (auto-detects your agent):

```bash
npx skills add Srimukh99/overmind
```

**From a clone** (Claude Code, Codex, Kiro):

```bash
git clone https://github.com/Srimukh99/overmind
cd your-project
/path/to/overmind/install.sh --agent all            # this project only
/path/to/overmind/install.sh --agent all --scope user   # every project
/path/to/overmind/install.sh --agent all --pack regulated,data   # add packs (or --pack all)
```

Core skills always install. Packs are opt-in — `regulated`, `data`, `k8s`, `apis-agents` — but `npx skills add` takes everything it finds, packs included.

**Claude Code plugin**:

```text
/plugin marketplace add Srimukh99/overmind
/plugin install overmind@overmind
/plugin install overmind-regulated@overmind     # optional packs: overmind-data, overmind-k8s, overmind-apis-agents
```

Then work as usual. The agent picks skills by matching your request to their descriptions, and `boot` routes whatever is left.

## Works with

The agent app loads skills, not the model, so any model works inside an app that supports the open Agent Skills format.

| Agent | Install | Folder it reads |
| --- | --- | --- |
| Claude Code | `--agent claude` | `.claude/skills/` |
| Codex, Kimi Code | `--agent codex` | `.agents/skills/` |
| Kiro | `--agent kiro` | `.kiro/skills/` |
| Qwen Code | `--agent qwen` | `.qwen/skills/` |
| Cursor | `--agent cursor` | `.cursor/skills/` (also reads `.claude/skills/` and `.agents/skills/`) |
| Gemini CLI, GitHub Copilot, OpenCode, Roo Code, Goose and others | `npx skills add Srimukh99/overmind` | each agent's own folder |

`--agent all` covers Claude Code, Codex, Kimi Code, Kiro and Qwen Code. Install Cursor with `--agent cursor` alone: it reads several of these folders and would otherwise list every skill twice. The scripts need an agent that can run shell commands, plus Python 3 and git.

## The flow

```text
design → build (ratchet, delegate) → review → ship
something breaks: debug (logs → source line → cause → fix)        outage: firefight
```

## Core skills (14)

Each skill opens with a short table of situations pointing to one reference file, so the agent reads only what the moment needs.

| Skill | Use it for |
| --- | --- |
| `boot` | Routing every task to the right skill |
| `design` | A fuzzy ask into an approved design, then small verifiable tasks with exact files and checks |
| `build` | Isolated worktree, test-first loop built for agents, tiered checks, mutation testing, a guard that catches skipped or weakened tests, plan execution |
| `ratchet` | Every iteration must improve the code without breaking what works or drifting from the goal: anchors the goal, freezes existing tests, checks each step against a rising floor, reverts bad steps |
| `delegate` | Contract-first delegation: you write the shared contract, each worker owns its own files and works in its own worktree under `ratchet`, results are verified rather than trusted, and work lands in waves |
| `debug` | Paste a log to get the error and its source line, or name a service: it finds the runtime, cloud and log shipper, then queries the right backend (9 clouds, 7 aggregators, never kubectl). From there, evidence-based debugging and tracing bad data to its origin. Exports the service map as an Open Knowledge Format bundle any agent can read |
| `review` | Independent review ranked by severity, security review of risky changes, handling feedback on its merits |
| `ship` | The quality and compliance gate, before commit and in CI; proof before "done"; a release checklist with a rollback plan; gradual rollout; clean merge or PR |
| `legal-traps` | For vibe coders and new PMs: COPPA, HIPAA pixels, wiretap claims, Google Fonts in the EU, unsubscribe and postal address, hidden fees, auto-renew consent, DMCA agent |
| `iac-check` | Public databases, open security groups, public buckets, wildcard IAM, privileged pods, secrets in images |
| `deps-check` | Vulnerable dependencies across Python, Node, Go, Rust and images |
| `observe` | Logs, RED metrics, traces, health checks, alerts, SLIs, SLOs, error budgets, runbooks |
| `firefight` | Incident triage, mitigation and blameless postmortems |
| `forge` | Writing new skills that actually help |

## Packs (install what you need)

| Pack | Skills | Use it for |
| --- | --- | --- |
| `regulated` | `reg-phi` `reg-pci` `reg-money` `reg-audit` | Health data and HIPAA, PCI DSS card data, money math and ledgers, audit trails and SOX or SOC 2 change control |
| `data` | `pg-explain` `pg-migrate` `mongo-index` `snow-perf` `dbx-perf` | Slow Postgres queries, zero-downtime schema changes, MongoDB indexes, Snowflake cost, Spark tuning |
| `k8s` | `k8s-triage` `drift` `crd-check` | CrashLoopBackOff and stuck rollouts, git versus live state, CRD validation and cluster upgrades |
| `apis-agents` | `api-pick` `agent-tools` | REST vs GraphQL vs gRPC, tools and MCP servers agents use well |

## Upgrading from 0.5

<!-- upgrade:start -->
Version 0.5 had 41 skills. Nothing was deleted: the instructions moved into `references/` files and every script is unchanged. Old names map like this.

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

Script paths changed with their skills, for example `skills/prove-it/scripts/loop.py` is now `skills/build/scripts/loop.py`.
<!-- upgrade:end -->

## The ship gate

`vibe-check` (in the `ship` skill) blocks secrets, private keys, card numbers, SSNs, committed `.env` files, debugger leftovers, focused tests and conflict markers. No dependencies, just Python 3.

```bash
python3 skills/ship/scripts/vibe_check.py                 # staged changes in the current repo
python3 skills/ship/scripts/vibe_check.py --repo ../myapp  # ... or another repo
python3 skills/ship/scripts/vibe_check.py --range origin/main...HEAD
python3 skills/ship/scripts/vibe_check.py --full          # + your lint, types and tests
python3 skills/ship/scripts/vibe_check.py --install-hook  # run on every commit
```

Add your own commands (formatters, gitleaks, `iac-check`, anything) one per line in `.overmind/checks`; each fails the gate on a non-zero exit. Those are shell commands from the repo, so read the file before running the gate somewhere you don't control. The CI workflow in `.github/workflows/ci.yml` runs it on every pull request.

## Scripts at a glance

```bash
kubectl logs pod/api-7d9f --previous | python3 skills/debug/scripts/log_trace.py --repo .
python3 skills/debug/scripts/service_map.py .            # once: map services, clouds, shippers
python3 skills/debug/scripts/service_map.py . --okf      # also export the map as an Open Knowledge Format bundle in docs/okf
python3 skills/debug/scripts/log_fetch.py notification-service --since 2h
python3 skills/legal-traps/scripts/legal_traps.py .            # consumer-app legal traps
python3 skills/build/scripts/loop.py fast                   # typecheck+lint; then focused, then full
python3 skills/build/scripts/tamper.py                      # catch skipped, deleted or weakened tests
python3 skills/build/scripts/loop.py mutate                 # inject bugs into changed code; report the ones no test catches
python3 skills/ratchet/scripts/ratchet.py start --goal "..." --scope 'src/x/**' --target tests/test_x.py::test_y
python3 skills/ratchet/scripts/ratchet.py check                # ACCEPT / REJECT / STALL / DONE; revert on reject
python3 skills/delegate/scripts/team.py init --goal "..." --contract tests/contract   # then add, check, spawn, brief
python3 skills/delegate/scripts/team.py verify                 # each worker's claim vs its ratchet verdict
python3 skills/delegate/scripts/team.py integrate --apply      # merge verified workers, run the suite once, land it
python3 skills/iac-check/scripts/iac_check.py infra/ deploy/
python3 packs/k8s/skills/crd-check/scripts/crd_check.py deploy/ --target 1.30     # needs PyYAML
python3 packs/k8s/skills/drift/scripts/drift_check.py --k8s-dir deploy/ -n prod   # read-only
python3 packs/k8s/skills/drift/scripts/drift_check.py --history
python3 skills/deps-check/scripts/deps_check.py
```

Most of these only read. The ones that write say so: `ratchet` keeps state in `.overmind/` and checkpoints under `refs/overmind/`, `team` creates worktrees and applies patches, `loop.py mutate` edits changed files and restores them, `service_map.py --okf` writes `docs/okf`, and `vibe_check.py --install-hook` writes a commit hook. `drift_check.py` never writes to your cluster, only a local history file. All need just Python 3 (plus PyYAML for `crd-check`) and print compact summaries.

## Token budget

Only skill names and descriptions sit in context until a skill is used. The 14 core descriptions total about 910 tokens (version 0.5's 41 were about 1,900); the four packs add about 620 more. Opening a skill loads its short table (200 to 460 tokens) and then one reference file. `python3 tools/lint_skills.py` reports the current numbers.

## Roadmap

- `idx`: a local repo index so agents look up symbols instead of reading whole files.
- A context-compression harness for tool output.
- More packs: deeper Snowflake, MongoDB, Postgres and agentic skills.
- An eval arena that proves each skill beats no skill.

## Important

The `reg-*` skills are engineering guardrails, not legal or compliance advice. Your compliance, privacy and security teams set policy. `vibe-check`, `iac-check` and the other scripts reduce risk; they don't guarantee a system is secure or compliant.

## Credits

Inspired by the skills-as-workflow idea popularized by [obra/superpowers](https://github.com/obra/superpowers). All overmind skill names and text are original.

## License

MIT
