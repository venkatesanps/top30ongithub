---
name: oracle-to-snowflake
description: Translate Oracle SQL and PL/SQL to Snowflake and flag every construct that won't run or will silently return different results (ROWNUM, '' vs NULL, NUMBER scale, SYSDATE timezone, date arithmetic, db links, packages, triggers, row-by-row loops). Use when migrating Oracle queries, views, packages or procedures to Snowflake, or reviewing a translation someone already did.
---

# Oracle → Snowflake

Translate what can be translated deterministically, flag what a translator can't know, and
rewrite procedural code set-based. Never claim a translation is equivalent until it has been
proven on data.

## 1. Run the converter first

`scripts/ora2sf.py` uses SQLGlot (`pip install sqlglot`) plus a rule scan. It only reads the
files you name and only writes under `--out`.

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/oracle-to-snowflake/scripts/ora2sf.py" <files-or-folders> --out ./ora2sf-out
```

(Use the script's path inside this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set.) It accepts
`.sql .pks .pkb .prc .fnc .trg .vw .pls .plb`. PL/SQL blocks must end with a `/` line, as in
SQL*Plus scripts; if a file has none, the whole rest of the file is treated as one block.

Then read `./ora2sf-out/report.md` and `findings.json`. `converted/<file>.sql` has the
translated SQL with `-- [ora2sf]` notes above each statement that needs a decision; PL/SQL is
kept as a comment for you to rewrite.

Add `--fail-on error` in CI to block merges that still contain constructs Snowflake can't run.

## 2. Fix errors, decide warnings

Work through `report.md` by rule, most severe first. The ones that bite silently:

| Rule | Why it matters | Usual fix |
|---|---|---|
| `empty-string-null` | Oracle stores `''` as NULL. `WHERE x = ''` matches nothing in Oracle, rows in Snowflake. | Decide the intent; often `NULLIF(x, '') IS NULL`. |
| `number-no-scale` | `NUMBER` becomes `NUMBER(38,0)` and drops decimals. | Declare the scale from the data (`MAX(scale)` profiling). |
| `sysdate-timezone` | Server local time vs UTC. | `CONVERT_TIMEZONE('America/Chicago', CURRENT_TIMESTAMP())` or the team's standard zone. |
| `date-integer-math` | `d - 1` works on DATE, errors on TIMESTAMP; `+ 1/24` means an hour. | `DATEADD(day, -1, d)`, `DATEADD(hour, 1, d)`. |
| `date-has-time` | Oracle DATE has a time part. | `TIMESTAMP_NTZ` if any row has a non-midnight time. |
| `rownum` | No ROWNUM. | `LIMIT`, `QUALIFY ROW_NUMBER() OVER (...) = 1`. |
| `outer-join-plus` | Works with restrictions; unreadable. | ANSI `LEFT JOIN ... ON`. |
| `db-link` | No cross-database links to Oracle. | Land the table first (replication, Snowpipe, or the migration load). |

Show each change as before/after with one line of reasoning. Don't change business logic while
translating; list anything that looks like a bug in the original under "Questions for the owner".

## 3. Rewrite PL/SQL, don't port it

For each `plsql-rewrite` finding:

1. Summarize what the block does in plain English: inputs, tables read, tables written, rules.
2. Replace loops (`BULK COLLECT`, `FORALL`, cursor `FOR` loops) with one `INSERT ... SELECT`,
   `UPDATE ... FROM` or `MERGE` where order doesn't matter. Say why each loop could go.
3. Only what must stay procedural becomes a Snowflake Scripting procedure
   (`CREATE OR REPLACE PROCEDURE ... LANGUAGE SQL AS $$ ... $$`). Map:
   - `RAISE_APPLICATION_ERROR` → declared `EXCEPTION (-20001, '...')` and `RAISE`
   - `NO_DATA_FOUND` / `TOO_MANY_ROWS` → check `SQLROWCOUNT` or the row count explicitly
   - `%TYPE` / `%ROWTYPE` → explicit types
   - `DBMS_OUTPUT` → return a value, or log to a table
   - packages → one procedure per public routine, in a schema named after the package
   - triggers → a stream + task, or logic moved into the load
   - `PRAGMA AUTONOMOUS_TRANSACTION` → write the audit row after the main work, or from a task
4. Watch transaction boundaries: DDL commits implicitly in Snowflake.

## 4. Prove it

For every migrated object, write the comparison queries to run on both systems against the same
input snapshot: row counts, `SUM`/`COUNT DISTINCT` checksums per key column, and a sample
diff (`EXCEPT` both ways on a few thousand rows). Report "equivalent" only when those match.

## Output

Give the user, in this order: the effort summary from `report.md`; the decisions they need to
make (warnings that need intent); the translated SQL; the PL/SQL rewrites; the proof queries.
