# How a Snowflake query runs: checked facts

Checked against Snowflake documentation on 2026-11-19. Both the advisor skill and the animated
explainer (`guide/snowflake-query-execution/`) are written from this list; change it here first.
Where sources disagreed or only blogs said it, the wording is hedged and marked.

## Cloud services (no warehouse)

- Authentication, access control, parsing, optimization and compilation run in cloud services.
- `EXPLAIN` compiles a statement without executing it, so it needs no running warehouse. Its
  `partitionsAssigned` is what is left after **compile-time** pruning, an upper bound: runtime
  optimizations (for example join filters) can prune further. The plan is logical; the actual
  execution order can differ.
  https://docs.snowflake.com/en/sql-reference/sql/explain
- Compiling (including `EXPLAIN`) uses cloud services credits, like other metadata operations.
- Cloud services credits are billed only for the part above 10% of that day's warehouse credits,
  computed daily in UTC. Serverless features don't count toward the 10%.
  https://docs.snowflake.com/en/user-guide/cost-understanding-compute

## Result cache (persisted query results)

- A result is kept 24 hours; each reuse resets the 24 hours, up to 31 days from first run.
- Reuse needs: the same query text (case and aliases count), no functions that change per run
  (UUID_STRING, RANDOM, RANDSTR), no external functions, no hybrid tables, unchanged data and
  micro-partitions, the result not purged, privileges on every table (SHOW: same role), unchanged
  result-affecting settings, `USE_CACHED_RESULT` on (the default).
- Meeting every condition does not guarantee reuse.
- The docs page doesn't mention CURRENT_DATE or UDFs; don't claim either way.
  https://docs.snowflake.com/en/user-guide/querying-persisted-results

## Metadata

- Snowflake keeps per-micro-partition metadata (value ranges per column, distinct counts, row
  counts). Pruning uses it.
  https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions
- Some queries are answered from metadata alone without a warehouse; Query Profile shows a
  metadata-based result. `SELECT COUNT(*) FROM t` is the documented-style example. Hedged: which
  MIN/MAX queries qualify is not pinned down in the docs; say "simple aggregates such as COUNT(*)".

## Micro-partitions and pruning

- Each micro-partition holds 50-500 MB of uncompressed data, stored compressed and columnar, so
  a query reads only the columns it references.
- Pruning skips partitions whose value ranges can't match the filter. How much it skips depends
  on how the data is ordered (clustering): micro-partitions are not monthly buckets.
- Clustering depth (SYSTEM$CLUSTERING_INFORMATION / SYSTEM$CLUSTERING_DEPTH): lower is better.
  https://docs.snowflake.com/en/user-guide/tables-clustering-micropartitions

## Virtual warehouse

- Billed per second while running, with a 60-second minimum each time it starts; nothing while
  suspended. Resizing up bills a minute for the added resources.
  https://docs.snowflake.com/en/user-guide/warehouses-overview
- The warehouse cache (local SSD) is dropped when the warehouse suspends, so the first queries
  after a resume read from remote storage.
  https://docs.snowflake.com/en/user-guide/performance-query-warehouse-cache
- Gen1 standard credits/hour: XS 1, S 2, M 4, L 8, XL 16, 2XL 32, 3XL 64, 4XL 128, 5XL 256, 6XL 512.
- Gen2 standard credits/hour: 1.35x Gen1 on AWS and GCP, 1.25x on Azure (XS 1.35 / 1.25 ... 4XL
  172.8 / 160). Gen2 isn't offered at 5XL or 6XL.
  https://www.snowflake.com/legal-files/CreditConsumptionTable.pdf
  https://docs.snowflake.com/user-guide/warehouses-gen2
- Gen2 is the default generation for new standard warehouses where available (behavior change
  2026_03, BCR-2250). Existing warehouses keep their generation. Set it with `GENERATION = '2'`;
  `RESOURCE_CONSTRAINT = STANDARD_GEN_2` errors after bundle 2026_02 (BCR-2225).
  https://docs.snowflake.com/en/release-notes/bcr-bundles/2026_03/bcr-2250
- Multi-cluster warehouses (Enterprise edition and up) add clusters for concurrency, not speed.
- Query Acceleration Service leases extra compute for eligible scans (large scans with a selective
  filter or aggregation; large INSERT/COPY). Not eligible: too few partitions, unselective filters,
  very high-cardinality GROUP BY, nondeterministic functions. Hedged: docs say it is on by default
  for new Gen2 and multi-cluster warehouses; another doc snippet says single-cluster stays off.
  Tell users to check `SHOW WAREHOUSES` (`enable_query_acceleration`). Scale factor caps its
  spend (8 when enabled explicitly).
  https://docs.snowflake.com/en/user-guide/query-acceleration-service

## Execution

- The warehouse splits the plan across its nodes and runs scans, joins, aggregations and sorts in
  parallel. When memory runs out an operator spills to local storage, then to remote storage;
  remote spill is the slow, expensive case.
- `GET_QUERY_OPERATOR_STATS(query_id)` returns one row per operator with `OPERATOR_STATISTICS`
  (input_rows, output_rows, pruning.partitions_scanned / partitions_total,
  spilling.bytes_spilled_local_storage / bytes_spilled_remote_storage, io, network) and
  `EXECUTION_TIME_BREAKDOWN.overall_percentage`. Needs OPERATE or MONITOR on the warehouse.
  Joins with output_rows > input_rows can mean an exploding join.
  https://docs.snowflake.com/en/sql-reference/functions/get_query_operator_stats

## Cost per query (checked 2026-11-19)

- `SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY.CREDITS_ATTRIBUTED_COMPUTE` is the warehouse
  credits attributed to one query, including resizing and multi-cluster scaling. Queries that run
  at the same time share the cost by weighted resource use.
- It leaves out warehouse idle time, cloud services, storage, data transfer, serverless features
  and AI tokens, and omits queries of about 100 ms or less. Adaptive warehouses aren't in it.
- Query Acceleration credits are a separate column (`CREDITS_USED_QUERY_ACCELERATION`); the
  query's total is the two added. Child queries (a stored procedure's statements) carry the
  caller in `ROOT_QUERY_ID`.
- Access needs the USAGE_VIEWER or GOVERNANCE_VIEWER database role; rows can lag by up to about
  eight hours; retention is 365 days.
- `QUERY_PARAMETERIZED_HASH` is the same for queries that differ only in literal values in
  simple comparisons, so it groups every run of a query shape.

- Comparing a text column with a number makes Snowflake convert the text to a number (when one
  input is numeric, the result is numeric), and a value that can't convert, such as `'xyz'`,
  makes the statement fail. https://docs.snowflake.com/en/sql-reference/data-type-conversion

Sources: <https://docs.snowflake.com/en/sql-reference/account-usage/query_attribution_history>,
<https://docs.snowflake.com/en/user-guide/query-hash>.

## What the explainer adds to the community infographic (Abhisek Sahu)

The original is a good one-page summary; some of what follows it simplified on purpose.

1. Pruning by micro-partition min/max ranges (50-500 MB units) rather than monthly buckets, so the
   role of clustering shows.
2. Two pruning passes: compile time in cloud services (EXPLAIN shows it without a warehouse) and
   runtime in the warehouse.
3. Metadata-only answers (COUNT(*) and similar) that skip the warehouse.
4. The full result-reuse conditions: privileges, per-run functions, external functions, hybrid
   tables, settings; and that reuse is never guaranteed.
5. Gen2 rates (1.35x on AWS and GCP, 1.25x on Azure), the Gen2 default for new warehouses, and no
   Gen2 at 5XL/6XL.
6. Cloud services billing above 10% of daily warehouse credits.
7. Warehouse resume (start-up, 60-second minimum) and queueing.
8. Query Acceleration Service and its scale-factor cap.
