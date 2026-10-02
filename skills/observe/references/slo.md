# slo

## Define

1. **SLI**: a ratio of good events to all events that users would recognise, for example the share of requests under 300 ms that return non-5xx.
2. **SLO**: the target over a window, for example 99.9% over 30 days. Pick from what users need and what history supports, not 100%.
3. **Error budget**: 1 − SLO. At 99.9% over 30 days that is about 43 minutes of failure. When the budget is spent, reliability work comes before features.

## Alert on burn rate

Use multi-window burn-rate alerts instead of raw thresholds:

| Severity | Budget burned | Long window | Short window |
| --- | --- | --- | --- |
| Page | 2% | 1 hour | 5 minutes |
| Page | 5% | 6 hours | 30 minutes |
| Ticket | 10% | 3 days | 6 hours |

Both windows must be over the threshold. This catches fast outages quickly and slow leaks without paging at night.

## Runbooks

Every paging alert links to a runbook: what it means, how to check impact, the first three actions, how to roll back, and who to escalate to. An alert nobody acts on gets fixed or deleted.
