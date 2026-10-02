# preflight

Answer every line before deploying. Anything you can't answer is a blocker.

- [ ] CI green on the exact commit being shipped (`references/receipts.md`)
- [ ] `vibe-check`, `iac-check` and `deps-check` clean
- [ ] Migrations backwards compatible with the currently running code (`pg-migrate`)
- [ ] New behaviour behind a feature flag where practical, default off
- [ ] Config and secrets exist in the target environment
- [ ] Rollback written down: the exact command or steps, and how long it takes
- [ ] Data changes that can't be rolled back are called out, with a backup taken
- [ ] Dashboards and alerts ready for the change (`observe`)
- [ ] Success signals defined: which metrics, what thresholds, how long to watch
- [ ] Timing: not during peak traffic or a freeze; owner available to watch
- [ ] Regulated systems: change ticket, approver other than the author (`reg-audit`)

Then continue with `ship`.
