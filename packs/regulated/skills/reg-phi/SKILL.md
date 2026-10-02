---
name: reg-phi
description: Use when code, data, logs, tests or prompts may touch health information such as patient records, claims, diagnoses, prescriptions, lab results or member IDs, or when working on any HIPAA-covered system.
---

# reg-phi

Engineering guardrails for protected health information (PHI). This is not legal advice; your privacy and compliance officers decide policy.

## Treat as PHI

Health information linked to any identifier: names, addresses smaller than a state, dates (except year) tied to a person, phone, fax, email, SSN, medical record number, health plan or member ID, account numbers, licence numbers, vehicle and device IDs, URLs, IP addresses, biometrics, full-face photos, and any other unique code. These are the 18 HIPAA Safe Harbor identifiers.

## Rules

1. **Minimum necessary**: read, return and store only the fields the feature needs.
2. **Never in**: logs, URLs or query strings, error messages, analytics events, crash reports, cache keys, or LLM prompts (unless the provider is covered by a signed BAA and the use is approved).
3. **Encrypt** in transit (TLS 1.2+) and at rest; keys in a managed KMS with rotation.
4. **Access**: role-based, least privilege, every read and write of PHI audit-logged (`reg-audit`). Break-glass access is logged and reviewed.
5. **Test data** is synthetic only (for example Synthea-generated records). Never copy production PHI to dev, test or a laptop.
6. **De-identification** uses Safe Harbor (remove all 18 identifiers) or Expert Determination. Hashing an identifier alone is not de-identification.
7. **Retention and deletion** follow written policy; deletion covers backups and replicas on schedule.
8. **Third parties** (SaaS, cloud services, AI APIs) receive PHI only under a BAA.

## Review checklist

- [ ] New fields justified under minimum necessary
- [ ] No PHI in logs, URLs, errors, analytics or prompts (grep the diff)
- [ ] Encryption at rest and in transit confirmed
- [ ] PHI access emits audit events
- [ ] Fixtures and seeds are synthetic
- [ ] Every vendor touching the data has a BAA

Run `vibe-check` too; it catches SSNs and secrets but cannot recognise every kind of PHI.
