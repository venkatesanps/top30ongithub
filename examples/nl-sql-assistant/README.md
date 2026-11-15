# Natural-language SQL assistant (Claude + SQLite or Snowflake, read-only)

Ask a database a question in plain English. Claude writes one SQL query through tool calling,
three independent locks make sure it can only read, the rows come back as a table, and Claude
explains them without ever seeing personal values.

It's the "weekend project" from the LLM-projects post (Python, Streamlit, SQLite, an LLM API),
built the way Superpowers (item **5**) works: brainstorm, design, plan, tests first. The design
and plan are in [PLAN.md](PLAN.md).

```bash
pip install sqlglot anthropic streamlit          # + snowflake-connector-python for Snowflake
export ANTHROPIC_API_KEY=...

cd examples/nl-sql-assistant
python3 cli.py --sqlite sample/shop.db "Show top 5 products by revenue"   # creates the sample DB on first run
streamlit run app.py                                                      # the web version
```

```text
SQL (1 attempt):
  SELECT p.product_name, SUM(s.amount) AS revenue FROM sales AS s JOIN products AS p
  ON p.product_id = s.product_id GROUP BY p.product_name ORDER BY revenue DESC LIMIT 5
```

## Snowflake

```bash
python3 cli.py --snowflake my_conn --role ANALYST_RO --database ANALYTICS --sf-schema MART \
  "Revenue by month for 2026, highest first"
```

The connection comes from `~/.snowflake/connections.toml`. A role is required, and admin roles
(`ACCOUNTADMIN`, `SYSADMIN`, `SECURITYADMIN`, `ORGADMIN`, `USERADMIN`) are refused. Give the
role reads only:

```sql
CREATE ROLE IF NOT EXISTS ANALYST_RO;
GRANT USAGE ON WAREHOUSE REPORTING_WH TO ROLE ANALYST_RO;
GRANT USAGE ON DATABASE ANALYTICS TO ROLE ANALYST_RO;
GRANT USAGE ON SCHEMA ANALYTICS.MART TO ROLE ANALYST_RO;
GRANT SELECT ON ALL TABLES IN SCHEMA ANALYTICS.MART TO ROLE ANALYST_RO;
GRANT SELECT ON FUTURE TABLES IN SCHEMA ANALYTICS.MART TO ROLE ANALYST_RO;
```

At work, run Claude through Amazon Bedrock so traffic stays in your AWS account:
`--provider bedrock --model <your Bedrock Claude model id>`. Point it at a dev or masked copy
first, never production, and check with your firm before using it on work data.

## What it sends to the model

| Sent | Never sent |
|---|---|
| Your question | Values from columns flagged sensitive (name, email, phone, SSN, address, birth date, card or account number, salary, IP...) |
| Table and column names and types (`--schema` prints exactly this) | Personal data found inside other values (emails, phone numbers, SSNs, card numbers are masked) |
| Errors from a refused or failed query, for a retry | Rows at all with `--explain facts`, or anything after the SQL with `--explain none` |
| For the explanation: computed totals and up to 20 rows, masked | |

Flags come from column names; adjust them with `--sensitive TABLE.COLUMN` and
`--not-sensitive TABLE.COLUMN`. You still see the real rows locally. A local audit log
(`~/.nl-sql-assistant/audit.jsonl`) keeps each question, SQL, row count and outcome, never rows.

## The three read-only locks

The post's safety check, `sql.strip().upper().startswith("SELECT")`, lets
`SELECT 1; DROP TABLE sales` through and blocks a perfectly good `WITH ... SELECT`. Here, any
one of these locks stops a write on its own:

| Lock | Where | What it does |
|---|---|---|
| Parser guard | `nlsql/guard.py` | sqlglot parses the SQL. One statement only; every node must be a read (no DML, DDL, CALL, COPY, PUT, GRANT, USE, SET, PRAGMA, ATTACH, anywhere, including CTEs); no side-effect functions (`SYSTEM$...`, `load_extension`, `writefile`); only tables in the schema; a row limit added or capped. |
| Read-only session | `nlsql/db.py` | SQLite: opened `mode=ro`, `PRAGMA query_only=ON`, and an authorizer that denies anything but reads, plus a query timeout. Snowflake: named non-admin role, statement timeout, query tag. |
| Least privilege | Snowflake grants above | The role can't write even if the first two were bypassed. |

When the guard or the database refuses a query, the reason goes back to Claude for up to two
corrected attempts.

## Your own SQL

`--sql "SELECT ..."` (or "Run your own SQL" in the app) runs a query you wrote through the same
guard and read-only session, with no model call.

## Tests

`python3 tests/nl_sql/test_nl_sql.py`: 80 checks, no network or API key (a fake Claude client).
They cover 30+ refused statements, writes blocked by the database even with the guard bypassed,
schema flags, masking, self-correction, the audit log, and that no personal value reaches the
model.
