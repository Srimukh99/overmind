---
name: reg-audit
description: Use when building or changing a regulated system in finance, healthcare or government that must show who did what, when and why, or when the work involves SOX, HIPAA audit controls, SOC 2 or change control.
---

# reg-audit

This is not legal advice; retention periods and controls come from your compliance team.

## Audit event

Every security- or compliance-relevant action emits one event:

| Field | Notes |
| --- | --- |
| `actor` | User or service identity, never a shared account |
| `action` | Verb from a fixed list (read, create, update, delete, export, grant, login) |
| `resource` | Type and ID, never the sensitive contents |
| `before` / `after` | Changed fields, or a hash when values are regulated |
| `timestamp` | UTC, from a synchronized clock |
| `request_id` | Correlates with traces and logs |
| `source` | IP or service, user agent |
| `reason` | Ticket or justification for privileged actions |

## Storage

1. Append-only and tamper-evident: write-once storage (object lock) or a hash chain.
2. Separate permissions: application admins cannot edit or delete audit records.
3. No secrets, raw PHI or card numbers in events; reference IDs instead.
4. Retention follows written policy (6–7 years is common in finance and healthcare; confirm yours).
5. Searchable for investigations and exportable for auditors.

## Change control

- Every production change links to a ticket and is approved by someone other than the author (segregation of duties).
- Deploys record who, what version, when, and the approval.
- Emergency changes are allowed but reviewed after the fact.

## Tests

Assert that each sensitive action emits exactly one correct audit event, and that audit writes failing makes the action fail rather than proceed silently.
