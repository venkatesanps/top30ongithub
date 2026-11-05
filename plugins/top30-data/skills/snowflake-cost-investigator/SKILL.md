---
name: snowflake-cost-investigator
description: Find where Snowflake credits go and what to change, from read-only ACCOUNT_USAGE views - idle warehouses, warehouses that never suspend, the costliest query patterns, remote spill, full partition scans, queuing, serverless spend and storage held only for time travel. Use when the user asks why Snowflake spend went up, how to cut credits, which warehouse or query costs the most, or for a cost review.
---

# Snowflake cost investigator

One evidence-backed cost report: how much, where, what changed, and the specific change for
each finding, with the credits it's tied to. Read-only: never run ALTER, CREATE, DROP or any
statement that changes the account. Hand the user the fix statements to run themselves.

## 1. Get the data

`scripts/sf_cost.py` holds the queries (all `SELECT`/`WITH`/`SHOW` on
`SNOWFLAKE.ACCOUNT_USAGE`). Pick the route the user's environment allows:

- **Snowflake MCP or CLI already connected** (e.g. kit item 31): write the queries, run each one
  through it, and save each result as `<section>.csv` in the same folder:
  `python3 "${CLAUDE_PLUGIN_ROOT}/skills/snowflake-cost-investigator/scripts/sf_cost.py" queries --days 30 --out ./sf-cost`
- **Python connector with a named connection** in `~/.snowflake/connections.toml`:
  `python3 .../sf_cost.py run --connection <name> --days 30 --out ./sf-cost`
- **Nothing connected:** run `queries`, give the user the `.sql` files to run in Snowsight, and
  ask them to download each result as CSV into the folder.

Never ask for a password, key or token in chat. The role needs `IMPORTED PRIVILEGES` on the
`SNOWFLAKE` database (or the `USAGE_VIEWER` / `GOVERNANCE_VIEWER` database roles). ACCOUNT_USAGE
lags by up to a few hours, so say "as of" in the report.

Use the path inside this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set.

## 2. Analyze

```bash
python3 .../sf_cost.py analyze --in ./sf-cost --credit-price <USD per credit>
```

Ask for their contract credit price; if they don't know it, use the default ($3.00) and say so.
It writes `report.md` and `findings.json`. A missing CSV is listed under "Not checked".

## 3. Write the answer

Start from `report.md`, then add judgement the script can't make:

1. **Headline:** total credits and dollars, the trend, and the one change worth doing first.
2. **Findings, most important first.** For each: what, the credits involved, the exact
   statement or change, and the risk. Keep the script's distinction: idle credits are
   *recoverable*; a query pattern's credits are what it *cost*, not what a fix saves.
3. **Before recommending a change, check the trade-off:**
   - Lower `AUTO_SUSPEND` loses the warehouse cache: fine for ETL, may slow BI dashboards.
     For BI, 60-300s is usually the sweet spot.
   - Upsizing a spilling query can cost less overall when it finishes more than twice as fast.
     Suggest a measured test (same query, two sizes) rather than asserting it.
   - Multi-cluster settings need Enterprise edition.
   - TRANSIENT tables have no fail-safe: only for data a pipeline can rebuild.
4. **For the top query pattern**, ask for or fetch its full text and query profile, and give
   a concrete rewrite (earlier filter, fewer columns, pre-aggregation, incremental load) if one
   is visible.
5. **Measure:** suggest re-running the same window a week after changes and comparing.

Sample query text in the report has literals replaced by `?`. Don't paste full query text,
user names or literal values into anything that leaves the user's machine.
