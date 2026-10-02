---
name: observe
description: Use when adding a service, endpoint, job or queue consumer with no way to tell if it is healthy, or when defining SLIs, SLOs, error budgets, alerts or runbooks.
---

# observe

Read only the part you need.

| Situation | Read |
| --- | --- |
| Adding a new service, endpoint, job or queue consumer, or when there is no way to tell if something is healthy. Adds the logs, metrics, traces and alerts needed to run it. | `references/observe.md` |
| Defining reliability targets, SLIs, SLOs or error budgets, designing alerts, reducing alert noise, or writing runbooks for a service. | `references/slo.md` |

Order: `references/observe.md` when adding a service, `references/slo.md` when setting targets, alerts or runbooks.
