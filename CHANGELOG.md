# Changelog

## 0.7.0
- `service_map.py --okf` exports the service map as an Open Knowledge Format (OKF v0.1) bundle: one typed document per service, cluster and log shipper, linked, with `index.md` files and a newest-first `log.md`. Only generated files are rewritten or pruned. `okf.py check` validates any bundle. Clusters are now recorded as clusters, not services.
- Installer: `--agent qwen` (Qwen Code) and `--agent cursor`; `all` now includes Qwen Code. README lists which agent reads which folder.
- Renamed from lockin to overmind. Project state now lives in `.overmind/`, checkpoints under `refs/overmind/`, worktrees in `REPO.overmind-team/`.
- `delegate` becomes contract-first, with a new `team.py`. The lead writes the shared contract, assigns each worker files no one else may touch, and `team.py check` rejects overlapping ownership, owned contracts and double-assigned targets before any work starts. Each worker gets its own git worktree and `ratchet`, all from one snapshot. `verify` compares each worker's claim with its ratchet verdict and flags false claims. `integrate` merges only verified workers in a scratch worktree, runs the suite once, and `--apply` lands it. Work proceeds in waves.
- `ratchet` checkpoints now use one ref namespace per working folder, so parallel ratchets in worktrees never overwrite each other.
- `evals/delegation.py`: five scripted workers, four with typical mistakes. Original contract tests passing at the end: trust the claims 2 of 8, the old delegate rules 7 of 8, contract-first 8 of 8. Bad changes that landed: 4, 1, 0.

## 0.6.0
- 41 skills become 14 core skills plus four optional packs. Related skills merged: `design` (shape, blueprint), `build` (build, prove-it, sandbox), `debug` (hunt, trace-back, log-trace, log-fetch), `review` (second-look, weigh-in, threat-check), `ship` (vibe-check, receipts, land, preflight, ship), `observe` (observe, slo). Each opens with a short table and points to one `references/` file, so the agent reads only what it needs.
- Nothing deleted. 19 instruction files moved with 24 of about 410 lines updated (skill-name and path references only). All 14 scripts are unchanged except two path lookups.
- Packs: `regulated` (reg-phi, reg-pci, reg-money, reg-audit), `data` (pg-explain, pg-migrate, mongo-index, snow-perf, dbx-perf), `k8s` (k8s-triage, drift, crd-check), `apis-agents` (api-pick, agent-tools). `install.sh --pack NAME[,NAME]|all`; one Claude plugin per pack.
- Always-loaded descriptions fall from about 1,900 to about 870 tokens. Opening a merged skill costs about 310 more tokens on average because of its table.
- The installer rewrites script paths in installed docs so commands run from the project root.
- `tools/check_layout.py`: every script in exactly one skill and mentioned, no dangling paths, no retired names, boot lists every skill.
- `evals/routing.py` with a frozen held-out set; guard tests so future description edits cannot lose a trigger.

## 0.5.0
- `ratchet`: iterate without breaking or drifting. Anchors the goal, scope and acceptance tests; records a floor of passing tests, public API and lint status; each `check` returns ACCEPT (floor rises, checkpoint saved), REJECT (regression, API change, out-of-scope file, edited pre-existing test, tampering, quality drop), STALL or DONE. Stops after three non-accepts. Checkpoints are git objects outside your branch and index; `revert` restores exactly.
- `loop.py mutate`: built-in mutation testing on changed Python functions, and Stryker, go-mutesting, cargo-mutants or PIT for other stacks. Reports each uncaught bug with file, line and the change made.
- `loop.py` lists one line per failure when more than three fail.
- `tamper.py`: catches deleted test files, commented-out assertions, added tolerances and broadened exceptions; judges weak assertions per test (a guard next to a strong check is fine); recognises moved test files. On the evaluation corpus: 19 of 19 cheats flagged, 0 of 12 honest changes failed.

## 0.4.0
- `prove-it` replaces `red-green`. Test-first loop built for agents: pick a mode (example, property, characterization or reproduction test), write types first, then a failing test, then the smallest change. Stop and report after three failed attempts at the same failure.
- `loop.py`: runs checks in tiers (fast: typecheck and lint; focused: tests related to changed files; full: whole suite) for Python, Node, Go, Rust and Java, and prints only the failing lines. Override in `.overmind/loop.json`.
- `tamper.py`: flags tests skipped, deleted, focused or weakened, swallowed errors, changed expected values and updated snapshots, against the merge-base with main.

## 0.3.0
- `log-fetch`: resolves a service to its runtime, cloud and log backend from IaC and queries it read-only, then summarises through `log-trace`. Backends: CloudWatch, Cloud Logging, Azure Monitor, Oracle, IBM, Alibaba SLS, DigitalOcean, Scaleway, OVH, Loki, Datadog, Splunk, Elastic/OpenSearch, New Relic, Honeycomb, OpenTelemetry. Never calls kubectl.
- Service map in `.overmind/services.json`, built once per repo. Detects log shippers (Fluent Bit, Fluentd, Vector, Promtail, Alloy, CloudWatch agent) and reads their output config; shipper evidence beats every other signal. Serverless stays on its cloud's native backend; aggregators win for container workloads.
- `legal-traps`: skill and scanner for COPPA, health data, wiretap claims, remote fonts, CAN-SPAM, TCPA, drip pricing, auto-renewal consent and cancellation, DMCA, BIPA, account deletion and privacy-policy gaps.

## 0.2.0
- New SRE and infrastructure skills: `log-trace`, `iac-check`, `crd-check`, `drift`, `k8s-triage`, `deps-check`, `preflight`, `ship`, `observe`, `slo`, `firefight`.
- Scripts for log triage (error, in-repo source line, Lambda/ECS/EKS detection), IaC risk checks, CRD and API validation, desired-vs-live drift with a state log, and dependency scanning.
- `vibe-check` runs extra commands listed in `.overmind/checks`.
- `hunt` now starts with `log-trace`; `boot` routes all new skills and prefers scripts over reading raw files.

## 0.1.0
- First release: core workflow, regulated (`reg-*`) and data/API/agent starter skills, `vibe-check` gate, installer.
