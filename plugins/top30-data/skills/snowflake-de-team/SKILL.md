---
name: snowflake-de-team
description: Run a small AI team for Snowflake data engineering - a read-only researcher, a drafter, an independent critic on a different model, and a refiner - routed by task type (pipeline failure, cost, slow query, Oracle migration, new dbt model / stream / task / dynamic table / MERGE load, SQL review, data questions). Files are the handoff, a deterministic gate blocks prod writes, GRANTs and DELETE without WHERE (also as a PreToolUse hook on snow sql and Snowflake MCP calls), and checkers fail the run when findings lack sources, the critic suggests fixes, or a Critical/Major problem goes unanswered. Use when the user wants an agent or team to build, review, tune or migrate Snowflake pipelines, or asks for an "AI team" for data engineering.
---

# Snowflake data-engineering team

Adapted from Rahul's "How To Build Your First AI Team in 2026" (X, 2026): four roles
(researcher, drafter, critic, refiner), a router that picks who works on what, critique from
the opposite model, and one shared context every agent reads. Built here with Claude Code
subagents and files instead of a hosted platform, and specialised for Snowflake.

```bash
T="python3 ${CLAUDE_PLUGIN_ROOT}/skills/snowflake-de-team/scripts/de_team.py"   # or this folder's scripts/
```

The team: `sf-researcher` (read-only, sonnet), `sf-drafter` (files only, sonnet), `sf-critic`
(read-only, **opus**: the other model), `sf-refiner` (sonnet), plus this plugin's
`pipeline-failure-triage` agent and the `snowflake-cost-investigator`,
`snowflake-query-advisor` and `oracle-to-snowflake` skills they call. If the user runs the
drafter on opus, set the critic to sonnet in its frontmatter: the point is a different model.

## 1. Route

`$T route "<the user's request>"` prints the task type, the agents in order with their models,
and what done looks like. Exit 3 means unclear: ask the question it prints, don't guess.

| Type | Steps |
|---|---|
| incident | `pipeline-failure-triage` only. Know why before changing anything. |
| cost | researcher (via `sf_cost.py`) → critic → refiner |
| tune | researcher (via `sf_query_advisor.py`) → drafter → critic → refiner |
| migrate | researcher → drafter (via `ora2sf.py`) → critic → refiner |
| build | researcher → drafter → critic → refiner |
| review | four critics in parallel: security, correctness, performance, style |
| research | researcher only |

## 2. Kick off

```bash
$T kickoff --task "<request>" --out runs/<short-name> --dev DEV_DE --prod PROD --prod RAW
```

It writes `context.md` (the shared context: environment, conventions, constraints), `team.json`
(route plus dev/prod databases, read by the gate) and the run folder. Fill in `context.md` with
the user: connection name, role, research warehouse, naming conventions. Never put a password,
key or token in it or in chat.

## 3. Run the steps

Call each agent with the run folder path, one at a time (review: all four critics in one
message, each with its lens, each writing `03-critique-<lens>.md`, then merge them into
`03-critique.md`). Each agent writes its file; after each step run `$T verify runs/<name>`. It
checks the files so no agent's word is taken for it:

| Step | File | Check |
|---|---|---|
| researcher | `01-findings.md` | every line is `Finding → Source → [Confidence: High/Medium/Low]`; no "assumed" or empty sources; High needs a query, view or file; ACCOUNT_USAGE cited for the last hour is flagged (it lags) |
| drafter | `02-draft/*.sql`, `DEPLOY.md` | `gate`: no writes outside dev databases, no unqualified targets, no GRANT/REVOKE, no warehouse/role/user/account changes, no ACCOUNTADMIN, no DELETE/UPDATE without WHERE, DROP/TRUNCATE/CREATE OR REPLACE TABLE only in dev; `$$` bodies and CALLs flagged for a person |
| critic | `03-critique.md` | every problem `P<n> [Critical/Major/Minor]` with a location; no fix language; "Strongest parts" last |
| refiner | `04-refined/`, `04-fix-notes.md` | every Critical and Major id has a one-line note; "not fixed" needs a reason; refined SQL passes the gate |

`verify` prints the next step and exits 0 only when every check passes. Loop a step at most
twice; if it still fails, show the user the check output rather than looping. The checkers
also run alone: `gate`, `check-findings`, `check-critique`, `check-refine` (all take `--json`
and `--fail-on`).

## 4. Hand over

Nothing the team writes runs in prod. Show the user `04-refined/DEPLOY.md`, the fix notes and
any gate errors that need a person (GRANTs, prod deploys). They deploy.

## Guard the session (optional, recommended)

The same gate as a PreToolUse hook blocks `snow sql` / `snowsql` commands and Snowflake MCP
tool calls that would write outside dev, in any session. In `.claude/settings.json`:

```json
{"hooks": {"PreToolUse": [{"matcher": "Bash|mcp__.*[Ss]nowflake.*",
  "hooks": [{"type": "command",
    "command": "python3 \"$CLAUDE_PROJECT_DIR\"/path/to/de_team.py hook --dev DEV_DE --prod PROD"}]}]}}
```

Exit 2 blocks the call and tells Claude why. It is a backstop, not the boundary: give the
team's Snowflake role read-only grants on prod so a pattern the gate misses still can't write.

## Corrections to the post

| Post | Here |
|---|---|
| Critic works in the same shared workspace | A critic that read the drafter's reasoning shares its blind spots. Ours has its own context, reads only the files, and runs on the other model. |
| "Only report what you can verify" (a prompt) | Prompts don't enforce it. `check-findings` fails sourceless or "assumed" findings, and the role is read-only in Snowflake. |
| Router "picks the right agent" | Ours is code with an "unclear: ask" route, and incidents always go to triage first. |
| Refiner "fixes every Critical and Major" | `check-refine` proves it by id, and a skipped fix needs a reason. |
| Shared context lives in a hosted workspace | `context.md` in the run folder, versioned with the code, with no secrets. No paid platform needed. |
| Code review: security, logic, performance, style agents | Same four lenses for SQL, run in parallel, merged by keeping the highest rating per line. |
| Agents act on your data | Read-only role for research, writes only to dev databases, a person deploys. ACCOUNT_USAGE is 45 min to 3 h behind; INFORMATION_SCHEMA table functions cover only the last 7 days or so. |

The short prompts the main session sends, and a kickoff prompt to paste into a fresh session:
`references/prompts.md`.
