---
name: iac-check
description: Use when writing or reviewing Terraform, CloudFormation, Kubernetes manifests, Helm output or Dockerfiles, or when asked if infrastructure is secure.
---

# iac-check

## Do

1. Run `python3 <this skill folder>/scripts/iac_check.py <paths>` (default: current directory). It prints only findings, each with a fix.
2. For Helm charts, render first: `helm template <chart> > /tmp/rendered.yaml`, then scan that file.
3. Fix every **FAIL** before merge. For each **WARN**, fix it or record why it's intended (for example a public web load balancer).
4. A deliberate exception gets a comment `iac-check: ignore` in that resource, plus the reason in the PR.

## What it calls out

| Area | Examples |
| --- | --- |
| Public exposure | Public S3 ACLs, disabled public access block, `publicly_accessible` databases, public EKS API, SSH/RDP/database ports open to `0.0.0.0/0`, internet-facing LoadBalancer Services, unauthenticated Lambda URLs |
| Identity | `Action: "*"`, service-wide wildcards, long-lived IAM user keys, `cluster-admin` bindings |
| Data protection | Unencrypted RDS/EBS, no deletion protection, CloudTrail validation off |
| Workloads | Privileged containers, host namespaces, hostPath, root user, `:latest` or untagged images, no limits, no readiness probe |
| Secrets | Hard-coded secrets in Terraform, Secrets committed as manifests, secrets in Dockerfile `ENV`/`ARG` |

## Design rules beyond the scanner

- Databases, caches and queues live in private subnets only.
- Admin access through SSM Session Manager, a bastion with SSO, or a VPN; never open admin ports.
- One role per workload (IRSA, ECS task roles, Lambda execution roles), scoped to its own resources.
- Regulated data stores also follow `reg-phi` or `reg-pci`.

Add `python3 <this skill folder>/scripts/iac_check.py` to `.overmind/checks` so `vibe-check` runs it on every commit.
