# NL→SQL assistant: design and plan

Built with the Superpowers flow (item **5**): brainstorm → design → plan → test first → verify.
This file is the design and plan, kept with the code so the reasoning stays reviewable.

## Brainstorm: decisions taken

| Question | Decision | Why |
|---|---|---|
| Which model writes the SQL? | Claude API (approved), or Claude on Amazon Bedrock with `--provider bedrock` | Best SQL. Bedrock keeps traffic in your AWS account at work. |
| What goes to the model? | The question, table and column names and types. **Never row values from sensitive columns.** | Owner's rule: nothing outside without approval, no PII outside. Schema + questions were approved. |
| Which databases? | SQLite (sample shop) and Snowflake through a read-only role | The weekend MVP from the post, plus the warehouse the team actually uses. |
| How is "read-only" enforced? | Three locks, any one of which is enough on its own | `startswith("SELECT")` (the post's check) passes `SELECT 1; DROP TABLE x` and misses `WITH x AS (...) DELETE`. |
| Explanation of results | Computed facts + a masked sample of up to 20 rows; `--explain none` sends nothing | The post's "explain the result" step is where row data would leak. |

## The three read-only locks

1. **Parser guard** (`guard.py`, sqlglot): exactly one statement; every node in the tree must be a
   read (no INSERT/UPDATE/DELETE/MERGE/CREATE/DROP/ALTER/GRANT/COPY/PUT/CALL/PRAGMA/ATTACH/SET/USE,
   anywhere, including CTEs and subqueries); no side-effect functions (`SYSTEM$...`,
   `load_extension`, `writefile`, `readfile`, `fts3_tokenizer`); tables must exist in the schema it
   was given; a row LIMIT is added or capped.
2. **Database session**: SQLite opened `mode=ro` with `PRAGMA query_only=ON` and an authorizer
   that denies anything but reads. Snowflake runs under a role you name; the runner refuses roles
   called `ACCOUNTADMIN`, `SYSADMIN`, `SECURITYADMIN`, `ORGADMIN`, sets a statement timeout and a
   query tag.
3. **Least privilege**: the Snowflake role should have only `USAGE` + `SELECT` (see README).

## Sensitive columns

`schema.py` flags columns whose names look personal (email, phone, ssn, tax id, name, address,
birth/dob, card, account number, ip, passport, license...). Flags are shown to the model so it
can avoid selecting them unless asked, and their values are masked (`[masked]`) in anything sent
back to the model. You can add or remove columns with `--sensitive` / `--not-sensitive`.

## Tasks (each test-first)

1. `guard.validate(sql, dialect, tables)` → `Verdict(ok, sql, problems)`. Tests: 30+ attack strings.
2. `db.SQLiteRunner` (read-only URI, query_only, authorizer) and `db.SnowflakeRunner`
   (connections.toml name, role check, timeout, tag, fetchmany cap). Tests: writes fail even if
   the guard is bypassed; a fake Snowflake connection records the session statements.
3. `schema.describe(runner)` → compact text + sensitive set. Tests: sample DB, flags.
4. `llm.ClaudeSQL` with tool calling (`run_sql` tool, forced), cached schema block, and
   `explain()`. Tests: a fake client checks the request never holds a sensitive value.
5. `assistant.ask()` → generate → validate → run → explain, with up to 2 self-corrections fed back
   from the guard or the database, and a local JSONL audit log (question, SQL, row count; no rows).
6. `cli.py` and `app.py` (Streamlit): show the SQL before and after the guard, the table, the
   explanation and every warning.
7. Verify: unit tests in CI with no network; one live run against the sample DB by hand.
