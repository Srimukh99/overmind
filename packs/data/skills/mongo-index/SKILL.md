---
name: mongo-index
description: Use when a MongoDB query or aggregation is slow, when explain shows COLLSCAN or an in-memory sort, or when designing indexes for a collection.
---

# mongo-index

## 1. Measure

`db.coll.find(<filter>).sort(<sort>).explain("executionStats")`, or `.explain()` on the aggregate. Look at:

- `totalDocsExamined` vs `nReturned`: far above 1:1 means wasted work.
- A `COLLSCAN` stage on a large collection.
- A bovermindg `SORT` stage (sorting in memory).

## 2. Design the index (Equality, Sort, Range)

Order compound index fields: equality matches first, then sort fields, then range filters. Example: filter `{status: "open", created: {$gt: d}}` sorted by `priority` → index `{status: 1, priority: 1, created: 1}`.

## 3. Sharpen it

- **Covered queries**: project only indexed fields (and exclude `_id` if not in the index) so documents are never fetched.
- **Partial indexes** when queries always target a subset (`{status: "open"}`).
- **TTL indexes** for data that should expire.
- **Aggregations**: put `$match` and `$sort` first so they can use an index; `$lookup` on a large collection needs an index on the foreign field.

## 4. Keep the set healthy

Every index slows writes and uses memory. Use `$indexStats` to find unused indexes and remove them after confirming with the owners. Build new indexes on large production collections during low traffic and watch replication lag.

## Prove it

Report `executionTimeMillis` and `totalDocsExamined` before and after (`ship`).
