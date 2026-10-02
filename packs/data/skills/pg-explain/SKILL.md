---
name: pg-explain
description: Use when a Postgres query is slow, an endpoint is slow because of SQL, or you are adding a query against a large table. Reads the plan and fixes the cause with measured before and after timings.
---

# pg-explain

## 1. Find the query

Use `pg_stat_statements` ordered by `total_exec_time` to find the top offenders, or take the query from the slow log or trace.

## 2. Get the real plan

`EXPLAIN (ANALYZE, BUFFERS) <query>;` on production-like data. `ANALYZE` executes the query, so wrap writes in `BEGIN; ... ROLLBACK;`.

## 3. Read it

| You see | Likely cause | Try |
| --- | --- | --- |
| Estimated rows far from actual (10x+) | Stale or missing statistics | `ANALYZE <table>`; extended statistics for correlated columns |
| Seq Scan on a big table with a selective filter | Missing or unusable index | Index on the filter columns; avoid functions on the column or add an expression index |
| Nested Loop with a large outer side | Bad estimate or missing join index | Fix stats; index the join key |
| Sort or Hash with `external merge` / disk | Not enough memory or no index for order | Index matching `ORDER BY`; raise `work_mem` for that query only |
| High `shared read` buffers | Data not cached, too much scanned | Narrow the query; covering index (`INCLUDE`) |

## 4. Choose the index type

B-tree for equality and ranges; GIN for JSONB, arrays and full-text; GiST for geometry and ranges; BRIN for huge append-only tables ordered by time. Partial indexes when queries always filter the same subset.

## 5. Prove it

Change one thing, re-run `EXPLAIN ANALYZE`, and report before and after execution time (`ship`). New indexes on live tables go through `pg-migrate`. Check that you're not duplicating an existing index; each one slows writes.
