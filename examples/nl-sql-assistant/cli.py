#!/usr/bin/env python3
"""Ask a database a question in plain English; get read-only SQL, the rows and an explanation.

  python3 cli.py --sqlite sample/shop.db "Show top 5 products by revenue"
  python3 cli.py --snowflake my_conn --role ANALYST_RO --database ANALYTICS --sf-schema MART "Revenue by month this year"
  python3 cli.py --sqlite sample/shop.db --schema          # print exactly what schema text is sent
  python3 cli.py --sqlite sample/shop.db --sql "SELECT ..." # guard + run your own SQL, no model call

Model: Claude through the Anthropic API (ANTHROPIC_API_KEY), or --provider bedrock (AWS credentials,
pass the Bedrock model id with --model). What is sent: the question and table/column names and
types; for the explanation, computed facts plus up to 20 rows with personal values masked
(--explain facts sends no rows, --explain none makes no second call).
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from nlsql import db, schema  # noqa: E402
from nlsql.assistant import Assistant  # noqa: E402


def build(a):
    if a.sqlite:
        p = Path(a.sqlite).expanduser()
        if not p.exists() and p.name == "shop.db":
            sys.path.insert(0, str(HERE / "sample"))
            import make_sample
            make_sample.build(p)
        runner = db.SQLiteRunner(p, timeout=a.timeout)
        sch = schema.describe_sqlite(runner, a.sensitive, a.not_sensitive)
    else:
        if not (a.role and a.database and a.sf_schema):
            sys.exit("--snowflake needs --role (read-only), --database and --sf-schema")
        runner = db.SnowflakeRunner(connection_name=a.snowflake, role=a.role, warehouse=a.warehouse, timeout=a.timeout)
        sch = schema.describe_snowflake(runner, a.database, a.sf_schema, a.sensitive, a.not_sensitive)
    return runner, sch


def show(res, as_json):
    if as_json:
        print(json.dumps({k: getattr(res, k) for k in ("ok", "question", "sql", "intent", "columns", "rows", "explanation",
                                                       "warnings", "problems", "attempts")}, default=str, indent=2))
        return
    print(f"SQL ({res.attempts} attempt{'s' if res.attempts != 1 else ''}):\n  " + (res.sql or "-").replace("\n", "\n  "))
    for w in res.warnings:
        print(f"note: {w}")
    if not res.ok:
        print("refused or failed: " + "; ".join(res.problems), file=sys.stderr)
        return
    widths = [max(len(str(c)), *(len(str(r[i])) for r in res.rows[:50])) if res.rows else len(str(c)) for i, c in enumerate(res.columns)]
    print("\n" + "  ".join(str(c).ljust(w) for c, w in zip(res.columns, widths)))
    print("  ".join("-" * w for w in widths))
    for r in res.rows[:50]:
        print("  ".join(str(v).ljust(w) for v, w in zip(r, widths)))
    if len(res.rows) > 50:
        print(f"... {len(res.rows) - 50} more rows (use --json for all)")
    print("\n" + res.explanation)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--sqlite", help="path to a SQLite file (sample/shop.db is created if missing)")
    src.add_argument("--snowflake", metavar="CONNECTION", help="connection name in ~/.snowflake/connections.toml")
    ap.add_argument("question", nargs="?")
    ap.add_argument("--role", help="Snowflake read-only role (required; admin roles are refused)")
    ap.add_argument("--database")
    ap.add_argument("--sf-schema")
    ap.add_argument("--warehouse")
    ap.add_argument("--sql", help="run your own SQL through the guard (no model call)")
    ap.add_argument("--schema", action="store_true", help="print the schema text that would be sent, then stop")
    ap.add_argument("--explain", choices=["sample", "facts", "none"], default="sample")
    ap.add_argument("--provider", choices=["anthropic", "bedrock"], default="anthropic")
    ap.add_argument("--model", default=None)
    ap.add_argument("--max-rows", type=int, default=1000)
    ap.add_argument("--timeout", type=int, default=60)
    ap.add_argument("--sensitive", action="append", default=[], metavar="TABLE.COLUMN")
    ap.add_argument("--not-sensitive", action="append", default=[], metavar="TABLE.COLUMN")
    ap.add_argument("--audit", default="~/.nl-sql-assistant/audit.jsonl")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    try:
        runner, sch = build(a)
    except (db.ReadOnlyError, FileNotFoundError, ValueError) as e:
        sys.exit(f"error: {e}")
    if a.schema:
        print(sch.text())
        return 0
    if a.sql:
        res = Assistant(runner, sch, llm=None, max_rows=a.max_rows, audit_path=a.audit).run_sql(a.sql)
    else:
        if not a.question:
            ap.error("ask a question, or use --sql / --schema")
        from nlsql.llm import ClaudeSQL, DEFAULT_MODEL
        llm = ClaudeSQL(model=a.model or DEFAULT_MODEL, provider=a.provider)
        res = Assistant(runner, sch, llm, explain=a.explain, max_rows=a.max_rows, audit_path=a.audit).ask(a.question)
    show(res, a.json)
    return 0 if res.ok else 2


if __name__ == "__main__":
    sys.exit(main())
