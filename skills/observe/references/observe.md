# observe

## Every new service or endpoint gets

1. **Structured logs** (JSON) with timestamp, level, service, request or trace ID, and outcome. No secrets or regulated data (`reg-phi`, `reg-pci`).
2. **RED metrics**: request rate, error rate, duration (as a histogram, so you get p95 and p99).
3. **Resource saturation**: CPU, memory, connection pool, queue depth or lag.
4. **Traces** with OpenTelemetry, propagating context across HTTP and queue boundaries.
5. **Health endpoints**: liveness (the process is alive) kept separate from readiness (it can serve traffic).
6. **Alerts** on symptoms users feel (error rate, latency, SLO burn rate), not on every cause. Each alert links to a runbook (`references/slo.md`).
7. **A dashboard**: the RED metrics, saturation and recent deploys on one screen.

## Rules

- Watch label cardinality: never use user IDs, emails or request IDs as metric labels.
- Log levels mean something: ERROR is for things a human must act on.
- Sample traces by rate, but always keep errors and slow requests.
