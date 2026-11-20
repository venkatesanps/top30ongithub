---
name: de-project-setup
description: Set up a data engineering repo so Claude Code works well in it, for Snowflake, BigQuery, Databricks, Postgres, Redshift or DuckDB - detects the warehouse, dbt, Airflow/Dagster and Databricks bundles, then writes a short CLAUDE.md with the real build and test commands and a dev-only rule, a read-only database MCP config (plus dbt MCP), permission rules that block prod targets and secrets, and three project skills (new model, debug a run, document models). check finds literal secrets in profiles.yml or .mcp.json, an unignored .env, missing prod rules and models with no docs or key tests. Use when the user starts using Claude Code on a data project, wants to connect Claude to their warehouse or database, asks how to structure a data repo for AI, or asks where to start learning Claude for data engineering.
---

# Data engineering project setup

From Aiswarya Venkit's "10 practical videos to learn how to use Claude for Data Engineering"
(X, 2026). The post's advice - start with Claude Code basics, project context and workflow,
then the tutorials for your stack - is what this skill does to a repo. The videos weren't
watched here (the post links through lnkd.in); the skill is built from the topics the titles
name: project structure, teaching Claude your conventions, MCP to a database, pipelines.

```bash
S=${CLAUDE_PLUGIN_ROOT}/skills/de-project-setup/scripts/de_setup.py
python3 $S detect .             # what it found and the commands it would write
python3 $S init . --dry-run     # what it would write
python3 $S init .               # write it (never overwrites; merges JSON)
python3 $S check .              # exit 1 on secrets; warnings for missing rules and docs
python3 $S path                 # the learning order, mapped to the post's videos
```

Standard library only. It never connects to a database and never reads `~/.dbt`,
`~/.snowflake` or other credentials.

## What `init` writes

| File | What's in it |
|---|---|
| `CLAUDE.md` | Warehouse, dbt project and profile, orchestrator; the real commands (`dbt build --select <model>+`, `airflow dags test`, `databricks bundle validate -t dev`, `pytest`, `sqlfluff`); dev only, never a prod target; read-only MCP; LIMIT before pulling rows; dbt layer and naming conventions to edit; what "done" means (build passes, row counts and key uniqueness before/after). Under 100 lines, no generic advice. If a CLAUDE.md exists it's kept and the suggestion goes to `CLAUDE.de.md`. |
| `.mcp.json` | One read-only server per warehouse found, plus `dbt-mcp` when there's a dbt project. Existing servers are kept. Every secret is a `${VAR}`. |
| `.claude/snowflake-mcp.yaml` | For Snowflake: SELECT/DESCRIBE/SHOW only; insert, update, delete, merge, create, drop, alter off; no object manager. |
| `.claude/settings.json` | Deny: `.env`, `~/.dbt/profiles.yml`, `~/.snowflake`, `~/.databrickscfg`, gcloud credentials, `dbt run/build/seed/snapshot --target prod`, `databricks bundle deploy/run -t prod`, `bq rm`, force push. Ask: `dbt run`, `dbt seed`, `airflow dags trigger`, `bundle deploy`, `bq query`, `snow sql`, `psql`. Merged into existing rules. |
| `.claude/skills/de-new-model` | Sources, grain, staging then mart, yml with key tests, build in dev, report row and key counts. |
| `.claude/skills/de-debug-run` | First real error, what changed, reproduce small, fix the cause, is a re-run safe, the test that would have caught it. |
| `.claude/skills/de-document` | Profile columns with one aggregate query, write yml descriptions and tests, `TODO: confirm with owner` instead of guessing. |
| `.env.example`, `.gitignore` | Variable names only; `.env` ignored. |

### The MCP servers

| Warehouse | Server in `.mcp.json` | You provide |
|---|---|---|
| Snowflake | `uvx snowflake-labs-mcp` (Snowflake-Labs/mcp) with the read-only service config | A `[claude_readonly]` connection in `~/.snowflake/connections.toml`, key-pair auth, a role with SELECT only |
| BigQuery | `toolbox --prebuilt bigquery --stdio` (Google's MCP Toolbox for Databases) | `BIGQUERY_PROJECT`, `gcloud auth application-default login` as a read-only principal |
| Databricks | Managed MCP over http: `${DATABRICKS_HOST}/api/2.0/mcp/sql` | `DATABRICKS_HOST`, a token for a principal with read-only grants (OAuth or short-lived) |
| Postgres / Redshift | `toolbox --prebuilt postgres --stdio` | `POSTGRES_*` / `REDSHIFT_*` for a read-only user |
| DuckDB | `toolbox --prebuilt duckdb --stdio` | `DUCKDB_DATABASE` |
| dbt | `uvx dbt-mcp` (dbt Labs) | `DBT_PROJECT_DIR`, `DBT_PATH` |

The server flags and URLs are as published when this was written; check each server's README
for the version you install, then pin it (`pkg@1.2.3`) - `agent-setup-audit` warns on
unpinned `uvx`. Claude Code expands `${VAR}` from the environment it starts in, not from
`.env`, so export the values in your shell or a direnv `.envrc`.

**The read-only part is the role, not the config.** MCP tool lists and permission rules help,
but the database user Claude connects as should only be able to read. Prefix permission rules
are easy to sidestep (`dbt --target prod run` reorders flags); for Snowflake, the
`snowflake-de-team` hook also blocks prod writes by parsing the SQL.

## What `check` finds

| Severity | Finding |
|---|---|
| error | Literal `password`/`token`/`private_key`/`keyfile_json` in a committed `profiles.yml` (use `{{ env_var('X') }}`) |
| error | Literal key, token, password or Authorization header in `.mcp.json` |
| error | `.env` present and not in `.gitignore` |
| warn | No CLAUDE.md; it doesn't name the warehouse (dialect becomes a guess), how to build/test a model, or that prod is off limits |
| warn | No permission rule mentioning prod |
| warn | No `unique`/`not_null` test on any dbt model |
| info | Warehouse found but no MCP server for it; models with no yml entry (by name); no `.sqlfluff` |

## Learning order (`path`)

1. Basics and project context - the post's videos 1, 2 and 7: run `init`, then
   `agent-setup-audit` (top30-agents) on the result.
2. Teach it your conventions - video 3: edit the CLAUDE.md conventions and the three skills.
3. Let it see the data - videos 8, 9 and 10: read-only role, `.mcp.json`, then the
   `warehouse-explorer` agent writes a data map.
4. Build pipelines - videos 5 and 6: `/de-new-model`; `snowflake-de-team` for a
   researcher, drafter, critic and refiner.
5. Your platform - video 4 for Databricks; for Snowflake `snowflake-query-advisor`,
   `snowflake-cost-investigator`, `oracle-to-snowflake`.
6. When it breaks - `/de-debug-run`, the `pipeline-failure-triage` agent, `session-doctor`.

## Notes on the post

| The post | What's accurate |
|---|---|
| Claude can "explore databases" and "connect tools through MCP" | Yes, with an MCP server - and it explores whatever the connecting user can reach. Give it a read-only role on dev or analytics schemas, not your admin login. |
| "Claude Desktop + BigQuery" | Claude Desktop and Claude Code use the same MCP servers; Desktop reads `claude_desktop_config.json`, Code reads `.mcp.json` (project) or `claude mcp add`. The server block is the same. |
| Start with videos 1, 2 and 7 | Agreed: a CLAUDE.md with the real commands and a dev-only rule does more than any one tutorial. |

## Tests

`python3 tests/de_setup/test_de_setup.py` builds dbt + Snowflake + Airflow, BigQuery,
Databricks bundle, Postgres-by-dialect and empty repos in temp folders, checks detection,
`init` (dry run, merge, never overwrite, no duplicate rules on a second run), `check`, and
that `agent-setup-audit` finds no errors in what `init` wrote.
