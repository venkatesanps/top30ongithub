# How a Snowflake query runs

An animated, phone-friendly explainer of what happens between pressing Run and getting rows back:
cloud services, the result cache, metadata-only answers, warehouse resume and queueing,
micro-partition pruning, parallel execution and spilling, and what each step costs.

- Open `index.html` in a browser (one self-contained page). Pick a scenario: first run, the same
  query again, `COUNT(*)`, a warm warehouse. Each one takes a different route through the map.
- Published with the field guide at
  https://venkatesanps.github.io/top30ongithub/snowflake-query-execution/ (after the next daily refresh).
- `?static` shows the finished picture with no controls (used for `infographic.png`); the page
  respects reduced motion.

![The flow map playing three scenarios](flow.gif)

[Full infographic (PNG)](infographic.png)

## What changed from the community infographic

A rework of a community infographic by Abhisek Sahu, checked against Snowflake's documentation
on 19 Nov 2026. The checked facts and their sources are in
[`plugins/top30-data/skills/snowflake-query-advisor/references/execution-facts.md`](../../plugins/top30-data/skills/snowflake-query-advisor/references/execution-facts.md).

1. **Pruning.** The original draws it as monthly buckets. Micro-partitions are 50-500 MB units,
   skipped by their per-column min/max ranges, so how well pruning works depends on clustering.
2. **Two pruning passes.** Compile-time pruning happens in cloud services: `EXPLAIN` shows it
   without a warehouse. Runtime pruning, such as join filters, happens again in the warehouse.
3. **Metadata-only answers.** Missing from the original. `SELECT COUNT(*)` and similar queries
   skip the warehouse.
4. **Result cache conditions.** The original keeps only "same text, unchanged data". Reuse also
   needs privileges on every table, no per-run functions (RANDOM, UUID_STRING), no external
   functions and no hybrid tables. Even then, reuse isn't guaranteed.
5. **Gen2 pricing.** The original lists only Gen1. Gen2 is the default for new warehouses and
   costs 1.35x (AWS, GCP) or 1.25x (Azure) per hour. It isn't offered at 5XL or 6XL.
6. **Cloud services billing.** Missing from the original. It's billed only above 10% of each
   day's warehouse credits.
7. **Resume and queueing.** Missing from the original. A suspended warehouse adds start-up time
   and a 60-second minimum; a busy one makes the query wait.
8. **Query Acceleration Service.** Missing from the original, along with its scale-factor cost cap.
9. **The pruning example.** Its text was garbled (`order_date =^ prime 2026-3-15`).

To review a query of your own, use the `snowflake-query-advisor` skill in the `top30-data` plugin.
