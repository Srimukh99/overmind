# threat-check

## Ask first

- Who can call this, and how do we know who they are?
- What can they reach that they shouldn't?
- What happens with hostile input, at volume?
- What leaks if this log, error or response is seen by the wrong person?

## Checklist

| Area | Must be true |
| --- | --- |
| Authentication | Every entry point checks identity; tokens expire and are validated server-side |
| Authorization | Checked per object (does this user own record 123?), not only per route |
| Input | Validated against an allowlist; parameterized queries only; size limits on bodies and uploads |
| Output | Encoded for its context (HTML, SQL, shell); errors don't expose stack traces or internals |
| Secrets | From env or a secret manager; never in code, logs, URLs or client bundles |
| Outbound calls | URL allowlist or SSRF guard; timeouts; TLS verified |
| Webhooks | Signature verified; replay window enforced |
| Abuse | Rate limits on login, signup, password reset and expensive endpoints |
| Crypto | Vetted libraries only; no home-made crypto; passwords hashed with argon2id or bcrypt |
| Dependencies | Pinned and scanned; no unmaintained packages for security-critical work |
| Logging | Security events logged (login, permission change, export) without secrets or regulated data |

## Output

Findings as **Blocker**, **Should fix** or **Nit**, with `file:line`, the attack in one sentence, and the fix. Regulated data also needs the matching `reg-*` skill.
