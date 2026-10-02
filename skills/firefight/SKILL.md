---
name: firefight
description: Use when production is down or degraded, an alert fires, users report an outage, or an incident needs a postmortem.
---

# firefight

## 1. Triage (first 5 minutes)

- **Impact**: who is affected, how many, and since when.
- **Severity**: SEV1 (outage or data at risk), SEV2 (major degradation), SEV3 (minor or workaround exists).
- Name an incident lead and open one channel. Post an update at least every 30 minutes for SEV1 and SEV2.

## 2. Mitigate before you debug

Ask: what changed? Check recent deploys, config, flags and infrastructure (`drift --history`). The fastest fixes are roll back (`ship`), disable a flag, scale up, fail over, or shed load. Restore service first, find the root cause after.

## 3. Find the cause

Feed logs to `log-trace` for the error, source line and runtime. On Kubernetes, use `k8s-triage`. Then `debug`. Keep a timeline as you go: time, what was seen, what was done.

## 4. Resolve

Confirm recovery with metrics against baseline (`ship`), and keep watching for 30 minutes before closing.

## 5. Postmortem (blameless), within 5 business days

Summary, impact (users, duration, data, money), timeline, root cause and contributing factors, what went well, what went poorly, and action items, each with an owner and a due date. Focus on systems and process, not people. Regulated incidents may have notification duties (for example HIPAA breach rules); involve compliance early.
