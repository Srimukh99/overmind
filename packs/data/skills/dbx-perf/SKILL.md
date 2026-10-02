---
name: dbx-perf
description: Use when a Databricks or Spark job is slow, fails with out-of-memory or executor loss, costs too much, or when tuning Delta tables.
---

# dbx-perf

## 1. Find the slow part

Open the Spark UI (or the query profile for SQL warehouses). Sort stages by duration. In the slowest stage compare max task time with the median.

| You see | Meaning | Try |
| --- | --- | --- |
| Max task far above median | Data skew | Adaptive query execution skew handling; salt the hot key; filter nulls before joining |
| Spill to disk | Partitions too big for memory | More shuffle partitions or let AQE coalesce; bigger nodes for this job |
| Huge shuffle read/write | Wide joins or aggregations | Broadcast the small side; pre-aggregate; filter earlier |
| Many tiny tasks or files | Small-file problem | `OPTIMIZE`; predictive optimization; tune write sizes |
| Python UDF stages slow | Row-by-row Python | Use built-in functions, or pandas (vectorized) UDFs |

## 2. Delta tables

- Liquid clustering on the columns most queries filter by, instead of hand-picked partitions.
- If you do partition, keep partitions large (around 1 GB or more); never partition by high-cardinality columns.
- Enable predictive optimization or schedule `OPTIMIZE` and `VACUUM`.

## 3. Code smells

`collect()` or `toPandas()` on large data, loops issuing one Spark action per row, `count()` used only for logging, caching data that is read once.

## 4. Cost

Check `system.billing.usage` for DBUs by job. Right-size clusters, use autoscaling and job clusters (or serverless) instead of always-on all-purpose clusters.

## Prove it

Report runtime and DBUs before and after (`ship`).
