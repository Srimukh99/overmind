---
name: debug
description: Use when there is a bug, failing test, crash, flaky behaviour or wrong output, an unexpected null or bad data far from its origin, a failing service that needs its logs, or a pasted log or stack trace. Fetches logs (CloudWatch, Cloud Logging, Loki), points to the source line, and finds the cause before any fix.
---

# debug

Evidence first, then cause, then fix. Read only the part you need.

| Situation | Read |
| --- | --- |
| The user pastes or points to a log, stack trace, error output, CloudWatch or kubectl logs. Finds the error, the exact source line in this repo, and whether it runs on Lambda, ECS, EKS or elsewhere, before you read any code. | `references/log-trace.md` |
| You need logs for a service and do not already have them - resolves the service to its runtime and log backend (CloudWatch, Cloud Logging, Azure Monitor, Loki, Datadog, Splunk and others), runs one read-only query, and returns a summary instead of raw logs. | `references/log-fetch.md` |
| There is a bug, failing test, crash, flaky behaviour, performance regression, or output that doesn't match expectations, before proposing any fix. | `references/hunt.md` |
| An error shows up far from where it starts, such as bad data deep in a call stack, an unexpected null from upstream, or a wrong number in a report. Follows the value back to its origin. | `references/trace-back.md` |

Order: get the evidence first (`references/log-trace.md` for a pasted log, `references/log-fetch.md` when you have none), then `references/hunt.md` to find the cause before any fix. Use `references/trace-back.md` when the symptom is far from the cause. Never run `kubectl logs`; query the log backend.

Scripts: `scripts/log_trace.py`, `scripts/log_fetch.py`, `scripts/service_map.py`, `scripts/backends.py`, `scripts/okf.py` (exports the service map as an Open Knowledge Format bundle).
