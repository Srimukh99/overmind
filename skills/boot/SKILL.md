---
name: boot
description: Use when starting any coding session or task in a repo. Routes the work to the right rubric skill before you explore, ask questions or begin.
---

# boot

rubric skills are installed. Before acting on a request, pick the skill that fits and follow it. If a skill matches, using it is not optional. Each skill opens with a short table; read only the reference file it points to.

## Route the work

| Situation | Skill |
| --- | --- |
| New feature or behaviour change with nothing specced; an approved design that needs tasks | `design` |
| Writing or changing code; a plan exists; an isolated workspace is needed | `build` |
| A task that takes several attempts, or an agent loop | `ratchet` |
| Several independent tasks or failures; work big enough to split across subagents | `delegate` |
| Bug, failing test, crash or odd output; a log or stack trace; a service failing with no logs yet (query the log backend, never `kubectl logs`) | `debug` |
| Building signup, checkout, subscriptions, email, SMS, uploads or tracking for users | `legal-traps` |
| Work finished, before merge; review comments received; auth, secrets, uploads or personal data | `review` |
| About to commit, say done, merge, deploy or roll back | `ship` |
| Production is down or degraded; postmortem | `firefight` |
| New service needs logs, metrics, alerts; SLOs, error budgets, runbooks | `observe` |
| Terraform, CloudFormation, manifests, Dockerfiles | `iac-check` |
| New or upgraded dependencies, CVEs | `deps-check` |
| Creating or editing a skill | `forge` |

## Packs

Install only what the work needs: `./install.sh --pack NAME`. If a task matches a pack skill that is not installed, tell the user which pack in one line and carry on with the core skills.

| Pack | Skills | For |
| --- | --- | --- |
| regulated | `reg-phi` `reg-pci` `reg-money` `reg-audit` | health data, card data, money, audit trails |
| data | `pg-explain` `pg-migrate` `mongo-index` `snow-perf` `dbx-perf` | Postgres, MongoDB, Snowflake, Databricks |
| k8s | `k8s-triage` `drift` `crd-check` | pod and rollout trouble, git versus live, CRDs and cluster upgrades |
| apis-agents | `api-pick` `agent-tools` | REST versus GraphQL, tools and MCP servers for agents |

## Ground rules

1. Read before you write. Check existing code, tests and conventions (`AGENTS.md`, `CONTRIBUTING.md`, `Makefile`, `package.json`) first.
2. Work in small steps and verify each one.
3. No success claim without command output from this session (`ship`).
4. Run `vibe-check` before every commit.
5. Regulated data (health, payments, personal identifiers, money) means the matching `reg-` skill from the regulated pack applies on top of everything else.
6. If the user explicitly says to skip a skill, skip it, and state in one line what risk that leaves.
7. Save tokens: when a rubric script exists for the job (`loop`, `tamper`, `ratchet`, `team`, `log-fetch`, `log-trace`, `legal-traps`, `iac-check`, `crd-check`, `drift`, `deps-check`, `vibe-check`), run it and read its summary instead of reading raw logs, manifests or whole files.
