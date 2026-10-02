---
name: snow-perf
description: Use when a Snowflake query is slow or expensive, a warehouse costs too much, or you are tuning tables, clustering or warehouse sizing.
---

# snow-perf

## 1. Find what costs most

Query `SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY` (and `WAREHOUSE_METERING_HISTORY` for credits) to rank queries and warehouses by time and cost.

## 2. Read the Query Profile

| You see | Meaning | Try |
| --- | --- | --- |
| Partitions scanned close to total | Poor pruning | Filter on columns the data is naturally ordered by; consider a clustering key on large tables |
| Bytes spilled to local or remote storage | Not enough memory | Reduce data early (filter, project); size the warehouse up for this workload |
| Join output far larger than inputs | Exploding join | Fix join keys or duplicates |
| Most time in one operator | That's the bottleneck | Rewrite that step first |

## 3. Fix options

- Select only needed columns; filter as early as possible.
- Clustering keys only on large tables with measured pruning problems; reclustering costs credits.
- Search optimization for selective point lookups.
- Dynamic tables or materialized views for repeated heavy aggregations.
- Remember the result cache: re-running an identical query can look fast without being faster.

## 4. Warehouse hygiene

Auto-suspend at around 60 seconds, auto-resume on, right-size per workload, multi-cluster for concurrency (not single-query speed), and resource monitors with alerts.

## Prove it

Report elapsed time, bytes scanned and credits before and after (`ship`).
