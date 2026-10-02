# receipts

Every claim needs proof you produced just now.

| Claim | Proof |
| --- | --- |
| Tests pass | Test command output from this session showing 0 failures |
| Bug fixed | The original repro now behaves correctly |
| It builds | Build command output |
| Deployed | Health check or smoke test against the target |
| Faster / cheaper | Before and after numbers from the same measurement |
| Lint / types clean | Linter and type-checker output |

## Rules

- Run it now. Earlier runs don't count after code changed.
- Read the output; don't assume from the exit code alone.
- Partially done means saying "partially done" and listing what's left.
- If you can't run it, say "unverified" and why.

## Format

`Verified: <claim> — <command> → <key output line>`
