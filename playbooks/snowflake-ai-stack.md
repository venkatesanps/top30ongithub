# Playbook: Snowflake's AI products, fact-checked (checked November 2026)

Prompted by a widely shared infographic, "Stop using Snowflake like a data warehouse. Start using
it like a full Data + AI system". It covers five products: Workspaces, CoCo, Pipeline Builder,
Cortex Agents and CoWork.

**Verdict:** accurate. All five exist and do what the infographic says. It leaves out three
things a team needs before rolling them out: two products were renamed, who gets access by
default, and how each one is billed. The headline is marketing. None of these replaces the
warehouse; they all run on it, so warehouse sizing and query tuning still apply to every query an
agent writes.

## The five products

| Product | What it is | Notes the infographic doesn't have | Where it fits with what you run now |
|---|---|---|---|
| **Workspaces** | File-based editor in Snowsight for SQL, Python files and notebooks, with Git | GA September 2025. Notebooks in Workspaces went GA in February 2026 and run on Snowpark Container Services compute pools, which are billed separately from warehouses | Replaces Worksheets. Point it at the same Git repo as your dbt project |
| **CoCo** | Snowflake's coding agent, formerly **Cortex Code**. Runs in a desktop app, a CLI, and inside Snowsight | Billed by tokens. Daily per-user credit limits are **unlimited until you set them**. Snowflake's benchmark claim (72.1% on dbt Labs' ADE-Bench, against 65.1% for Claude Code and Codex) comes from its own internal testing | A data-aware alternative to Claude Code for Snowflake work. Same review rule: run its SQL through `snowflake-query-advisor` |
| **Pipeline Builder** | Visual designer in Workspaces for SQL, Python and notebook pipelines | Each pipeline is a **DCM project**: files plus a `manifest.yml`, deployed as tasks and task graphs, with one project object per target (DEV, PROD) | Overlaps with dbt plus Airflow. Choose one owner per object. Two tools deploying the same table will fight |
| **Cortex Agents** | Managed agents: an agent is a schema-level object bundling a model, tools and instructions | Tools include Cortex Analyst (SQL from semantic views), Cortex Search, code execution, custom tools, **web search and MCP connectors** | Snowflake runs the loop that [examples/first-agent](../examples/first-agent/) writes by hand |
| **CoWork** | The business-user app, formerly **Snowflake Intelligence** | Inherits row access and column masking policies; can email recurring reports; has user skills and a mobile app | What you point business users at instead of a dashboard backlog. The answers are only as good as the semantic views behind them |

## Before you turn it on at work

**1. Access: tighten the defaults.**
- `SNOWFLAKE.CORTEX_USER` is granted to `PUBLIC` by default, so every user has it. Revoke it from
  `PUBLIC` and grant it to the roles that should have it.
- For CoCo, `SNOWFLAKE.COPILOT_USER` is required. `SNOWFLAKE.CORTEX_AGENT_USER` is the
  least-privilege option: it covers CoCo's agent features without the rest of Cortex.
- A **Restricted Session Scope** makes a CoCo chat read-only or limits it to chosen roles. Use it
  for anything near production.

```sql
REVOKE DATABASE ROLE SNOWFLAKE.CORTEX_USER FROM ROLE PUBLIC;
GRANT DATABASE ROLE SNOWFLAKE.CORTEX_AGENT_USER TO ROLE DE_ENGINEER;   -- least privilege for CoCo agents
GRANT DATABASE ROLE SNOWFLAKE.COPILOT_USER     TO ROLE DE_ENGINEER;
```

**2. Cost: set limits before the pilot, not after the bill.**
- CoCo is billed by tokens, with a separate daily limit for each surface: CLI, Desktop and
  Snowsight. The default is unlimited.
- A Cortex Agents request pays for four things: orchestration tokens, Cortex Analyst tokens,
  Cortex Search (by index size and how long it's kept), and warehouse time for custom tools.

```sql
ALTER ACCOUNT SET CORTEX_CODE_CLI_DAILY_EST_CREDIT_LIMIT_PER_USER = 20;
ALTER ACCOUNT SET CORTEX_CODE_DESKTOP_DAILY_EST_CREDIT_LIMIT_PER_USER = 20;
ALTER ACCOUNT SET CORTEX_CODE_SNOWSIGHT_DAILY_EST_CREDIT_LIMIT_PER_USER = 20;

-- Who spent what on CoCo, by surface, in the last 30 days
SELECT interface, user_name, SUM(token_credits) AS credits
FROM SNOWFLAKE.ACCOUNT_USAGE.SNOWFLAKE_COCO_USAGE_HISTORY
WHERE usage_time >= DATEADD('day', -30, CURRENT_TIMESTAMP())
GROUP BY 1, 2 ORDER BY credits DESC;
```

Warehouse time spent on SQL that an agent runs shows up in query history as usual, so
`snowflake-cost-investigator` and `snowflake-query-advisor --attribution` cover it.

**3. Data leaving the account.** Most agent tools run inside Snowflake. **Web search and MCP
connectors send requests over the public internet.** Leave them off until your firm approves
each one. The same applies to CoCo Desktop and CLI on a laptop: check what local files and
terminals they may reach.

## A sensible order to try them

1. **Workspaces** with your existing Git repo. It's an editor; nothing new runs.
2. **CoCo in Snowsight** for a few engineers, with a read-only session scope, credit limits set,
   and usage checked weekly with the query above.
3. **One semantic view and one Cortex Agent** over a mart you already trust, tested with 20
   questions that have known answers, like the
   [first-agent eval](../examples/first-agent/evals.json).
4. **CoWork** for one business team, on that agent only.
5. **Pipeline Builder**, only for pipelines that aren't already in dbt or Airflow.

## Sources (checked 2026-11-21)

- CoCo (formerly Cortex Code), its surfaces and benchmark claim: <https://www.snowflake.com/en/product/snowflake-coco/>, <https://snowflake.com/en/blog/snowflake-coco-ai-coding-agent-modern-data-stack/>
- CoCo access roles and Restricted Session Scope: <https://docs.snowflake.com/en/user-guide/cortex-code/cortex-code-snowsight>
- CoCo billing and daily limits: <https://docs.snowflake.com/user-guide/cortex-code/cortex-code>, <https://docs.snowflake.com/en/user-guide/cortex-code/credit-usage-limit>
- CoCo usage view: <https://docs.snowflake.com/en/sql-reference/account-usage/snowflake_coco_usage_history>
- CoWork (formerly Snowflake Intelligence): <https://docs.snowflake.com/en/user-guide/snowflake-cortex/snowflake-cowork>, <https://www.snowflake.com/en/blog/snowflake-cowork-personal-work-agent/>
- Cortex Agents, tools and costs: <https://docs.snowflake.com/en/user-guide/snowflake-cortex/cortex-agents>
- Pipeline Builder and DCM projects: <https://docs.snowflake.com/user-guide/pipeline-builder/pipeline-builder-overview>, <https://docs.snowflake.com/en/user-guide/dcm-projects/dcm-projects-overview>
- Workspaces GA: <https://docs.snowflake.com/release-notes/2025/other/2025-09-11-workspaces-ga>; Notebooks in Workspaces GA: <https://docs.snowflake.com/release-notes/2026/other/2026-02-05-notebooks-in-workspaces>
