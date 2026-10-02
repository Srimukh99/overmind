---
name: crd-check
description: Use when writing or changing Kubernetes CustomResourceDefinitions, custom resources, operators or controllers, or before upgrading a cluster. Validates CRD structure, custom resources against their schema, and removed or deprecated Kubernetes APIs.
---

# crd-check

## Do

1. Run `python3 <this skill folder>/scripts/crd_check.py <manifest dirs> --target <cluster version>` (for example `--target 1.30`). Needs PyYAML.
2. For Helm charts, render first with `helm template` and scan the output.
3. Fix every **FAIL**; review every **WARN**.

## What it checks

| Check | Why it matters |
| --- | --- |
| `metadata.name` is `<plural>.<group>`, kind and scope set | The API server rejects the CRD otherwise |
| Exactly one storage version, at least one served | Objects can't be stored or read otherwise |
| Every version has an `openAPIV3Schema` | Required in `apiextensions.k8s.io/v1` |
| Root-level preserve-unknown-fields | Means no validation at all |
| Status field without a status subresource | Controllers and users overwrite each other |
| Multiple versions, different schemas, no conversion | Stored objects break when clients switch versions |
| Custom resources use a defined, served version | Applies fail or use a deprecated version |
| Custom resource fields vs schema | Missing required fields, wrong types, bad enums, and unknown fields that Kubernetes silently drops (usually typos) |
| Removed APIs (for example `batch/v1beta1` CronJob, `policy/v1beta1`) | Manifests fail on upgrade |

## Controller design rules

- Reconcile toward the desired state; never assume the previous step succeeded.
- Use `status.conditions` with `observedGeneration`.
- Use finalizers for external cleanup, and remove them reliably.
- Make reconciles idempotent and safe to run concurrently.
