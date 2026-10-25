# Playbook: lead data engineer (Snowflake, Oracle, Informatica, AWS)

Goal: faster migrations and safer pipelines, with checks the whole team runs the same way.

## Pick by task

| Task | Use | Notes |
|---|---|---|
| Oracle SQL → Snowflake SQL | **41** SQLGlot + Claude | SQLGlot gives an exact, repeatable translation of SQL; Claude handles PL/SQL packages and procedures and explains the diffs. |
| Whole-warehouse Oracle/Teradata → Snowflake | **31** Snowflake AI Kit (Cortex Code `/migrate`), Snowflake SnowConvert AI | Snowflake's own tools. Its docs mark Oracle code extraction as "planned", so check the current status. |
| Informatica PowerCenter → Snowflake/dbt | SnowConvert AI (free, from Snowflake), Cortex Code `/migrate` | Both document Informatica-to-dbt or Snowflake Scripting conversion. |
| Informatica cloud catalog lookups | **43** Informatica for Claude (IDMC) | Only for Informatica's cloud (CDGC). |
| Build and test dbt models | **32** dbt Agent Skills, **33** dbt MCP | Unit tests, semantic layer, job failure triage. |
| Debug Airflow DAGs | **34** Astronomer agents | Works with open-source Airflow 2.x/3.x. |
| Glue / EMR / Athena / CloudWatch / cost | **38** Agent Toolkit for AWS, **39** AWS MCP servers | Read-only role first. |
| Query Oracle from Claude | **40** Oracle SQLcl MCP | `sql -mcp` on a saved, read-only connection. |
| SQL style on every PR | **42** SQLFluff | `sqlfluff lint --dialect snowflake` in CI. |
| Data quality and freshness | **36** Elementary, **37** Great Expectations | Elementary if you're on dbt; GX otherwise. |
| Snowflake spend by team/model | **35** dbt-snowflake-monitoring | Feeds a cost dashboard managers will actually read. |

## A migration loop that holds up in review

1. **Inventory.** "List every object PKG_X reads and writes, with the statement that does it."
2. **Translate SQL deterministically** with SQLGlot, then have Claude review the output against the
   original for semantics SQLGlot can't know (empty string vs NULL, date arithmetic, sequence
   behaviour, implicit commits).
3. **Rewrite, don't translate, procedural logic.** Row-by-row PL/SQL loops usually become set-based
   `MERGE` statements. Ask Claude for the set-based version and the reason each loop disappears.
4. **Prove equivalence.** Generate row-count, checksum and sample-diff queries for both systems
   and run them on the same input snapshot.
5. **Watch for concurrency traps.** Patterns that rely on Oracle row-level locks (many threads
   updating one status table) serialize on Snowflake. Prefer append-only status rows or one
   writer.
6. **Lock it in.** dbt tests + SQLFluff + Elementary on every PR.

## Prompts that work

- "Here is the Oracle package spec and body. Draw the data flow from source tables to the final
  insert, then list the business rules in plain English."
- "Translate with SQLGlot, then show me every place where the Snowflake result could differ."
- "Write dbt unit tests that would have caught the bug in this incident."
- "Why did last night's DAG run take 40 minutes longer? Compare task durations with the previous
  7 runs."

## Legacy reporting (Actuate / BIRT)

There is no public AI tooling for Actuate e.Report Designer. BIRT (eclipse-birt/birt) is the
open-source line that Actuate came from, but it doesn't read Actuate Basic or .ROD files. The
practical route is a skill of your own that reads the exported `.bas` source with the Oracle
packages behind each report. If your firm allows sharing it, it would fit in this repo next to
the dbt and Airflow skills.

## Share with the team

- Commit a `CLAUDE.md` in each repo with your conventions (naming, MERGE patterns, test
  expectations), so everyone's assistant follows the same rules.
- Keep shared skills in the repo's `.claude/skills/` so they're reviewed like code.
