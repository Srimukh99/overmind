# ship

Run `references/preflight.md` first.

## Roll out gradually

| Platform | Gradual option |
| --- | --- |
| Kubernetes | Rolling update with `maxUnavailable: 0`, or a canary (Argo Rollouts, Flagger) |
| ECS | Rolling deployment with the circuit breaker and rollback enabled, or CodeDeploy blue/green |
| Lambda | Alias with weighted traffic shift (canary or linear) |
| Feature flags | Internal users, then 1%, 10%, 50%, 100% |

## Watch

At each step, compare with the pre-deploy baseline for at least 10 minutes: error rate, p95/p99 latency, saturation (CPU, memory, connections), and the business metric the change affects. Use `drift` to confirm the new version is actually what's running.

## Roll back

Roll back immediately, without debating, when error rate or latency crosses the agreed threshold, or something unexplained happens. Rollback first, debug after (`debug`).

- Kubernetes: `kubectl rollout undo deploy/<name>`, or revert the GitOps commit.
- ECS: redeploy the previous task definition revision.
- Lambda: point the alias back at the previous version.

## Done when

100% rolled out, signals within baseline for the watch window, and the result posted with `references/receipts.md`. Always ask before running a production deploy or rollback command.
