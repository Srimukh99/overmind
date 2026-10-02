# log-fetch

Get the logs yourself instead of asking the user to paste them.

Never shell out to `kubectl logs`. Kubernetes logs live in whatever backend the
cluster ships to - CloudWatch on EKS, Cloud Logging on GKE, Azure Monitor on AKS,
or an aggregator like Loki or Datadog that holds everything regardless of compute.
Resolve the backend, then query it.

## Flow

1. **Map the services** (once per repo):
   `python3 skills/debug/scripts/service_map.py .`
   Scans Terraform, CloudFormation, Kubernetes manifests and Compose files.
   Writes `.overmind/services.json`: name, runtime, cloud, log group or selector,
   IaC file and line, source path.

2. **Fetch**:
   `python3 skills/debug/scripts/log_fetch.py notification-service --since 2h`
   Resolves the name, picks the backend, runs one read-only query, pipes the
   result through `log-trace` and prints the summary.

3. **Read the summary, not the logs.** The error, its category, the runtime, the
   source frame to start at, and the next step. Raw output stays out of context.

## Log shippers decide the destination

Managed clusters (EKS, GKE, AKS) usually run a shipper: Fluent Bit, Fluentd,
Vector, Promtail, Alloy or the CloudWatch agent. The shipper's config, not the
cloud, says where pod logs land. `service_map.py` finds it, reads its output
or sink blocks, and records `shipper`, `ships_to` and any log group in
`.overmind/services.json`. That record is the debugging map: resolve it once,
reuse it on every later incident. Shipper evidence beats every other signal.

Cluster shippers cover pods only. ECS uses FireLens per task definition;
serverless runtimes write to their cloud's own log service.

If a query on a mapped backend comes back empty, say so and name the shipper
config to check. Empty usually means nothing is shipping, not nothing failed.

## Picking a backend

Confidence comes from three signals: a provider block or agent config in the
repo, an authenticated CLI on the machine, and relevant environment variables.
A vendor-neutral aggregator outranks a cloud-native backend at equal confidence,
because when a shop runs Datadog or Splunk it usually holds every service.
A native backend is skipped when the service runs on a different cloud.

Force one with `--backend loki`. See what was detected with `--backends`.

## Backends

Cloud-native: AWS CloudWatch Logs, GCP Cloud Logging, Azure Monitor Log Analytics
(KQL), Oracle Cloud Logging, IBM Cloud Logs, Alibaba Cloud SLS, DigitalOcean App
Platform, Scaleway Cockpit, OVH Logs Data Platform.

Vendor-neutral: Grafana Loki, Datadog, Splunk, Elasticsearch/OpenSearch,
New Relic, Honeycomb, OpenTelemetry collector (reports its destination).

## Flags

`--since 2h` lookback. `--limit 200` max lines. `--grep "text"` pushes a filter
into the backend query rather than fetching everything and filtering locally.
`--dry-run` prints the command without running it. `--raw` prints logs instead of
a summary. `--list` shows mapped services. `--refresh` rebuilds the map.

## Rules

- Read-only. Query, never mutate. No scaling, no restarting, no deleting.
- One query per investigation. Narrow with `--grep` and `--since` before widening.
- If a query needs credentials from the environment, the script prints the exact
  command rather than guessing at secrets. Hand it to the user.
- When no backend is usable, report the runtime, the IaC file and line, and what
  was missing. Do not fall back to exploring the repo at random.
- Stale map: if a service is missing, run `--refresh` once. Do not rebuild per call.

## When it does not apply

Logs already in hand - pipe them to `log-trace` instead. Local development -
read the terminal. A cluster with no log shipping configured - say so plainly.

## Share the map (Open Knowledge Format)

`python3 skills/debug/scripts/service_map.py . --okf` also writes the map to `docs/okf/` as an
OKF bundle (Google Cloud's open format for knowledge agents read): one file per service,
cluster and log shipper, an `index.md` in each folder and a `log.md` history. Commit it so
every agent and teammate sees the same map. Re-running rewrites only generated files;
hand-written runbooks in the same folder are kept. Check a bundle with
`python3 skills/debug/scripts/okf.py check docs/okf`. The bundle names your services and log
groups, so think before committing it to a public repo.
