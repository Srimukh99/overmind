---
name: drift
description: Use when asked whether what is running matches what is in git, after a deploy, when a rollout seems stuck, or when someone changed infrastructure by hand. Compares desired state with current state and tracks drift over time.
---

# drift

Desired state is git: Terraform, manifests, Helm values, GitOps apps. Current state is what is live. This skill finds the gap and records it.

## Do

1. Run `python3 <this skill folder>/scripts/drift_check.py` with any of `--k8s-dir deploy/`, `-n <namespace>`, `--tf-dir infra/`. It is read-only: it runs `terraform plan`, `kubectl diff` and `kubectl get` only, and skips tools that aren't installed.
2. Read the summary:
   - **terraform**: resources to create, update, replace or destroy, and changes made outside Terraform.
   - **manifests**: resources whose live spec differs from the files.
   - **rollouts**: desired vs updated vs ready replicas, stuck rollouts, and specs the controller hasn't observed yet.
   - **pods**: crash loops, image pull errors, OOM kills, unschedulable pods.
   - **gitops / helm**: Argo CD apps not synced or healthy, Flux not ready, failed Helm releases.
3. Every run is appended to `.overmind/state.jsonl` (commit SHA, what drifted). Run `--history` to see when drift first appeared.

## Correcting drift

1. Decide which side is right. If the live change was an emergency fix, put it in git first.
2. Correct through the normal path: a PR, then `terraform apply` or a GitOps sync. Never hand-edit live resources to "fix" drift.
3. Re-run drift and show it in sync (`ship`).
4. For regulated systems, log the correction as a change (`reg-audit`).

Never run `apply`, `sync`, `delete` or `rollout undo` without the user's explicit go-ahead.
