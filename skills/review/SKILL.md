---
name: review
description: Use when a task or feature is finished and needs an independent review of the diff before merging, when review comments arrive and need judging on merit, or when code touches login, sessions, permissions, secrets, uploads, webhooks or personal data and needs a security review.
---

# review

Read only the part you need.

| Situation | Read |
| --- | --- |
| Code touches login, sessions, permissions, secrets, file uploads, user input parsing, outbound calls, webhooks or personal data. Reviews the change for security flaws before it ships. | `references/threat-check.md` |
| A task or feature is finished and before merging or opening a PR. Gets an independent review of the diff against the requirements and ranks findings by severity. | `references/second-look.md` |
| You receive code review comments or suggestions, from a person or an agent, before changing any code. Judges each point on its merits instead of agreeing by reflex. | `references/weigh-in.md` |

Order: `references/threat-check.md` while writing security-sensitive code, `references/second-look.md` when the change is finished, `references/weigh-in.md` when comments come back.
