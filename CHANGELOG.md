# Changelog

## 0.8.0
- `ship/references/receipts.md` now covers the claim itself, not only the proof:
  a list of phrases that mean the command has not been run ("should work",
  "looks right", "I'm confident"), an excuse-and-reality table for the nine
  reasons a check gets skipped, a delegation row that sends you to the VCS diff
  instead of a subagent's report, and a requirements checklist built from the
  original request rather than from memory of it. The idea came from the
  Superpowers library's completion guidance; the rows and wording are rubric's,
  and the README credits it.
- New: `vibe_check.py --stop-hook`, a gate for the end of an agent turn, which
  neither library had. It scans the uncommitted work - staged, unstaged **and**
  new untracked files, where a just-created secret hides - reports on stderr
  because that is the only stream handed back to an agent, and exits 2 so the
  turn returns with the findings instead of ending on an unproven claim. It
  stands down on `stop_hook_active`, so it blocks once rather than looping.
  `--install-stop-hook` merges it into `.claude/settings.json` without touching
  hooks already there, `--uncommitted` exposes the new scope on its own, and
  this repo ships its own hook in `.claude/settings.json` with a `make check`
  target for it to run.
- `--full` no longer crashes or lies when a detected command is missing: a tool
  that is not installed prints `SKIP`, not `PASS`, and a failing check's output
  is echoed into the hook's stderr rather than streamed to a stdout no agent
  reads.
- New eval, `evals/claim_guard.py`: twelve turns that end in a claim with no
  receipt. `receipts.md` names 12 of 12; the Stop hook, run for real against
  five planted repos, stops 5 of 12, blocks no clean work and does not loop.
  The gap is the point - the other seven are judgement claims no scanner sees -
  and the naming score is read as a floor, since the cases and the guidance
  were written together.
- Renamed from overmind to **rubric**. Four separate projects over 500 stars
  already shared the old name, including a 3,747-star Procfile manager. Project
  state moves from `.overmind/` to `.rubric/`, checkpoints from
  `refs/overmind/` to `refs/rubric/`, delegate worktrees from
  `REPO.overmind-team/` to `REPO.rubric-team/`, and the Claude plugins from
  `overmind*` to `rubric*`. Existing users: `git mv .overmind .rubric` and
  `git update-ref` the ratchet refs, or start a fresh ratchet. `evals/v05_descriptions.json`
  keeps the old name because it is a frozen baseline; routing is unaffected
  (dev 98% top-1, legacy triggers 100%).
- **`vibe_check.py` was a no-op outside this repo.** It pinned its scan target to
  its own install directory, so running it from any project reported
  `0 FAIL, 0 WARN, 0 lines scanned` and exit 0 without reading the staged diff.
  It now takes `--repo` (default: the current directory). Two integration tests
  that passed vacuously under the old behaviour now assert on scan output.
- A leftover `breakpoint()` no longer stalls a runner. `loop.py`, `ratchet.py`
  and `mutate.py` pass `PYTHONBREAKPOINT=0` to the child, so the suite reports
  instead of blocking on pdb until the timeout. Measured: 600s default timeout
  down to 0.1s on the reproduction. The gate still FAILs the leftover.
- Always-loaded descriptions cut 25%, 912 to 683 tokens, while routing improved:
  dev top-1 93% to 98%, top-3 98% to 100%, held-out 73% to 76%, legacy 100%.
- The evals could not run on an Apple Silicon Mac with an x86_64 Python, because
  git's xcrun shim cannot load into an x86 process. `evals/_eval_git.py` carries
  the `arch -arm64` fallback the skill scripts already had. All five now run in CI.
- New eval, `evals/code_quality.py`: three tasks with a visible suite and a
  withheld acceptance suite. 6 of 6 candidates pass their own tests, 3 are wrong,
  10 hidden defects would ship. It also found that **mutation score does not
  predict correctness across implementations and here is anti-correlated** (thin
  83%, solid 62%) - it measures whether a suite is real, not whether code is right.
- New eval, `evals/guidance_coverage.py`: whether the advice given when tests are
  written names the defect classes that actually ship. rubric 6/6 core, 2/4
  extended, 10/10 defects reachable; superpowers 2/6, 1/4, 3/10.
- `build/references/prove-it.md` gains a "Boundaries worth a test" table - nine
  classes, each with the question to ask and the bug it catches - and `Done when`
  requires it. It also states that `loop.py mutate` is not a substitute.

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
