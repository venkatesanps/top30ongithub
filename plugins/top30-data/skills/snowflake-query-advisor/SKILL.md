---
name: snowflake-query-advisor
description: Review a Snowflake query or .sql file (dbt models included) like an explain plan - an operator tree showing scans, pruning, joins, aggregates and sorts - and recommend specific rewrites and settings that make it faster and cheaper (less scanning, no spills, fewer credits). Reads EXPLAIN output, GET_QUERY_OPERATOR_STATS, QUERY_HISTORY, QUERY_ATTRIBUTION_HISTORY and INFORMATION_SCHEMA.COLUMNS exports when the user has them, and runs as a pre-commit hook or CI check with SARIF output. Use when someone asks why a Snowflake query is slow or expensive, to tune or review SQL, to read an explain plan or query profile, or to size a warehouse for a query.
---

# Snowflake query advisor

Turns SQL into a plan someone can read, then into a short list of changes, each with the reason,
the rewrite and what it costs to adopt. Read-only: it reads files and never connects to
Snowflake or runs the statement.

`scripts/sf_query_advisor.py` needs `sqlglot` (`pip install sqlglot`). Use the path inside this
skill folder if `CLAUDE_PLUGIN_ROOT` isn't set:

```bash
Q="python3 ${CLAUDE_PLUGIN_ROOT}/skills/snowflake-query-advisor/scripts/sf_query_advisor.py"
```

## 1. Analyze the SQL

Save pasted SQL to a file first. Then:

```bash
$Q analyze query.sql                 # one file, several statements, or a folder (dbt models too)
$Q analyze models/ --md review.md --json review.json
```

You get, per statement, an **estimated** plan tree (Snowflake operator names: TableScan with
the columns and filters pushed onto it, joins, Aggregate, WindowFunction, Sort, Result) and
findings ranked high to low. It handles multi-statement files, `$$` procedure bodies,
`?`/`:1` binds and dbt/Jinja (`ref()`/`source()` become table names, the first branch of each
`{% if %}` is kept). A statement that doesn't parse is reported and gets text-level checks.

## 2. Get real evidence when the user can

The estimate becomes a measurement with Snowflake's own numbers. Print the statements to run:

```bash
$Q queries query.sql > for_snowflake.sql
```

It lists, using the user's own SQL text:

- `EXPLAIN USING JSON <statement>`: compiles without running and needs no warehouse. It gives the
  real plan and `partitionsAssigned` of `partitionsTotal` after compile-time pruning.
- `INFORMATION_SCHEMA.TABLES` (rows, bytes, clustering keys) and `INFORMATION_SCHEMA.COLUMNS`
  (column types) queries for the tables it reads.
- After one real run: `GET_QUERY_OPERATOR_STATS('<query_id>')` (rows in and out, spill, pruning,
  time per operator), the `QUERY_HISTORY` row (time, size, queueing, cache %, spill), and two
  `QUERY_ATTRIBUTION_HISTORY` queries: the credits Snowflake attributed to this run, and every run
  of the same query shape over 30 days (same `query_parameterized_hash`).

Pick the route the user's setup allows, the same way as `snowflake-cost-investigator`:

- **Snowflake MCP or CLI connected:** ask before running anything. EXPLAIN and the metadata
  queries are read-only, but the user should approve them. Never run the statement being
  reviewed, and never run DML.
- **Nothing connected:** give them `for_snowflake.sql` to run in Snowsight, and ask them to
  download each result as JSON or CSV.

Never ask for a password, key or token. Then re-run with whatever they bring back:

```bash
$Q analyze query.sql --explain query_1.explain.json --tables tables.csv --columns columns.csv \
   --stats stats.csv --history history.csv --attribution attribution.csv --attribution pattern.csv \
   --warehouse L --credit-price 3.00
```

EXPLAIN accepts the JSON, a JSON string pasted from a cell, or a CSV of `EXPLAIN USING TABULAR`.

- **Cost.** With `--attribution` the report uses the credits Snowflake attributed to the run
  (compute plus Query Acceleration, child queries included) and totals every run of the query
  shape, so a fix can be priced per day. That figure leaves out idle time and cloud services; the
  view needs USAGE_VIEWER or GOVERNANCE_VIEWER and lags by hours. Without it, history gives an
  estimate (rate × execution time): say it's an estimate. Rates are Gen1 unless the user says the
  warehouse is Gen2; then add `--generation 2 --cloud aws|azure|gcp`. Ask for their credit price;
  if they don't know, use $3.00 and say so. For a whole warehouse, use `snowflake-cost-investigator`.
- **Types.** With `--columns` it checks join keys and filters for type mismatches, flags columns a
  table doesn't have, checks each date rewrite against the column's real type (and drops it for a
  text column), and turns `SELECT *` into the table's column list.

## 3. Write the answer

1. **The plan** from the report, with one sentence on where the work is (the biggest scan, the
   heaviest operator).
2. **The top three changes** in order of payoff, each with:
   - what to change
   - why, in terms of the plan
   - the rewritten SQL (use the script's `Rewrite:` lines and finish the rest by hand). Repeat
     the rewrite's status: "type checked" means the column types fit, not that results are
     proven equal; "unchecked" means test it on real data first
   - how to check it
   Show the full rewritten query when changes interact.
3. **Compute and cost:** sizing only from evidence (EXPLAIN bytes, spill, measured time). Upsizing
   doubles the rate per second, so it saves money only when the query runs more than twice as fast:
   propose a timed test on two sizes, not a verdict. Queueing calls for multi-cluster or a separate
   warehouse, not a bigger one.
4. **What wasn't checked**, for example "estimated plan only; no EXPLAIN yet". Each finding has a
   confidence: high (measured, or certain from the SQL), medium (the cost depends on data the SQL
   doesn't show), low (unparsed SQL); one level lower inside dbt templates. Lead with high ones.

## 4. Run it on every change

For a repo of SQL or dbt models, `references/ci.md` sets up a pre-commit hook, a GitHub Actions
check with SARIF for code scanning, a project config (`.sf-advisor.toml`) and comments that turn a
rule off where it's intended (`-- sf-advisor: disable=select-star`). The `examples/` folder has
files to copy. Before suggesting SARIF upload, note that it sends findings, with SQL snippets, to
GitHub: only for repos whose SQL is already there.

## Judgement the script can't make

- **Rewrites before features.** A prunable filter, fewer columns, a fixed join or an earlier
  aggregate costs nothing to run. Each feature below has a running cost; name it whenever you
  suggest one:
  - Clustering keys: automatic clustering credits and storage churn. Only for large tables queried
    far more than they change, filtered on the same columns.
  - Search optimization: Enterprise edition, serverless credits and storage. For selective point
    lookups and substring search.
  - Materialized views: Enterprise edition, refresh credits.
  - Query Acceleration: credits up to its scale factor, for large scans with selective filters.
- **Keep the meaning.** The NOT IN to NOT EXISTS rewrite changes results when the subquery has
  NULLs. That is usually a fix, but say so. A range rewrite of `TO_DATE(ts) = d` must keep the
  same day boundaries.
- **The result cache** needs identical text and unchanged data, and is never guaranteed. Don't
  promise savings from it.
- **Gen2 vs Gen1:** Gen2 costs 1.35x per hour on AWS and GCP, 1.25x on Azure. It's the default for
  new warehouses and doesn't exist at 5XL/6XL. Faster runtimes can offset the rate, but only
  measurement shows it.
- **The plan is logical.** Snowflake can reorder joins and prune further at run time. When the
  estimate and EXPLAIN disagree, EXPLAIN wins, and operator stats beat both.

`references/execution-facts.md` has the checked facts (caches, pruning, billing, Gen2, QAS) with
sources. The animated explainer at `guide/snowflake-query-execution/` draws the same facts.
Reference runs: TPC-H (22) and TPC-DS (99) queries parse completely. Two public Fivetran dbt
packages: 123 of 139 statements parse. The fixtures follow Snowflake's documented formats and
were not exported from a live account.
