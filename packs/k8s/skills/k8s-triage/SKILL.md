---
name: k8s-triage
description: Use when a Kubernetes pod, deployment or service misbehaves, including CrashLoopBackOff, ImagePullBackOff, Pending pods, OOMKilled, failing probes, 502 or 503 errors, or a stuck rollout on EKS, AKS, GKE or any cluster.
---

# k8s-triage

Start broad and cheap: run the `drift` skill's script with `-n <ns> --no-tf`. It lists every unhealthy rollout and pod in one summary. Then go to the matching row.

| Symptom | Look at | Usual causes |
| --- | --- | --- |
| CrashLoopBackOff | `kubectl logs <pod> --previous` piped into `log-trace`; `describe pod` exit code | App error on start, missing config or secret, failing liveness probe |
| OOMKilled / exit 137 | `describe pod` Last State; memory usage vs limit | Limit too low, memory leak, JVM or Node heap not sized to the container |
| ImagePullBackOff | `describe pod` events | Wrong tag, private registry auth, node can't reach the registry |
| Pending | `describe pod` events (FailedScheduling) | Requests bigger than any node, node selector or taint mismatch, PVC not bound |
| Running but not Ready | Readiness probe config; app health endpoint | Probe path or port wrong, dependency down, slow start without a startup probe |
| 502/503 from ingress | `kubectl get endpoints <svc>`; Service selector vs pod labels | No ready endpoints, wrong targetPort, label mismatch |
| Rollout stuck | `kubectl rollout status`; ReplicaSet events | New pods failing (see rows above), quota, PodDisruptionBudget brubricg |
| CreateContainerConfigError | `describe pod` | Referenced ConfigMap or Secret key missing |

## Rules

- Read-only commands first (`get`, `describe`, `logs`, `events`). Ask before `delete`, `rollout undo`, `scale` or `edit` on shared clusters.
- Fix the manifest in git, not the live object (`drift`).
- Pipe logs through `log-trace` instead of reading them raw.
