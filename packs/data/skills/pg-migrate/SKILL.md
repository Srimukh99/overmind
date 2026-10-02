---
name: pg-migrate
description: Use when changing a Postgres schema on a database that serves live traffic, including adding or dropping columns, indexes, constraints, types or tables, or renaming anything.
---

# pg-migrate

## Always

- Set `SET lock_timeout = '5s';` and a `statement_timeout` at the top of each migration so a blocked lock fails fast instead of freezing traffic.
- Test timing on a production-sized copy.
- Every migration is reversible, or documented as forward-only with a recovery plan.

## Safe patterns

| Change | Do this |
| --- | --- |
| Add index | `CREATE INDEX CONCURRENTLY` (outside a transaction); check it is `VALID` afterwards |
| Add column | Nullable, or with a constant default (fast on PG 11+); no volatile defaults |
| Backfill | In batches of a few thousand rows with pauses, not one huge `UPDATE` |
| Add NOT NULL | Add `CHECK (col IS NOT NULL) NOT VALID`, then `VALIDATE CONSTRAINT`, then `SET NOT NULL` (PG 12+ skips the scan) |
| Add foreign key | `ADD CONSTRAINT ... NOT VALID`, then `VALIDATE CONSTRAINT` separately |
| Rename column or table | Expand and contract: add new, dual-write, backfill, switch reads, stop writing old, drop old |
| Drop column | Remove all code use, deploy, then drop in a later migration |
| Change column type | New column plus backfill plus swap, unless the change is binary-compatible |

## Order of deploys

Schema changes that old code can live with go first; code that depends on them goes second; cleanup goes last.

## Regulated systems

Schema changes are production changes: ticket, second approver and deploy record (`reg-audit`).
