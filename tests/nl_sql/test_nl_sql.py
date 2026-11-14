"""Tests for examples/nl-sql-assistant (guard, read-only runners, schema, masking, assistant, CLI).

python3 tests/nl_sql/test_nl_sql.py   (needs sqlglot; no network, no API key, no Snowflake)
"""
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
APP = ROOT / "examples/nl-sql-assistant"
sys.path.insert(0, str(APP))

from nlsql import guard, db, schema, assistant  # noqa: E402
from nlsql.llm import ClaudeSQL, mask_rows  # noqa: E402
sys.path.insert(0, str(APP / "sample"))
import make_sample  # noqa: E402

TABLES = {"sales", "products", "customers"}


class FakeMessages:
    """Stands in for anthropic.Anthropic().messages: returns queued tool calls / texts, records requests."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []

    def create(self, **kw):
        self.requests.append(kw)
        r = self.replies.pop(0)
        if isinstance(r, str) and not r.startswith("TEXT:"):
            block = type("B", (), {"type": "tool_use", "name": "run_sql", "input": {"sql": r, "intent": "x"}})()
        else:
            block = type("B", (), {"type": "text", "text": r[5:]})()
        usage = type("U", (), {"input_tokens": 10, "output_tokens": 5, "cache_read_input_tokens": 0})()
        return type("M", (), {"content": [block], "usage": usage, "stop_reason": "tool_use"})()


class FakeClient:
    def __init__(self, replies):
        self.messages = FakeMessages(replies)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    # ---------- guard: allowed ----------
    ok_sql = [
        "SELECT product_name, SUM(amount) AS revenue FROM sales GROUP BY product_name ORDER BY revenue DESC LIMIT 5",
        "select * from products",
        "WITH t AS (SELECT customer_id, SUM(amount) a FROM sales GROUP BY 1) SELECT * FROM t ORDER BY a DESC",
        "SELECT p.category, COUNT(*) FROM sales s JOIN products p ON p.product_id = s.product_id GROUP BY 1",
        "SELECT 1 UNION ALL SELECT 2",
        "SELECT * FROM sales WHERE amount > (SELECT AVG(amount) FROM sales)",
        "  -- top products\nSELECT product_id FROM sales;",
    ]
    for s in ok_sql:
        v = guard.validate(s, "sqlite", TABLES)
        check(v.ok, f"allows: {s[:60]!r} {v.problems}")

    # ---------- guard: refused ----------
    bad_sql = {
        "SELECT 1; DROP TABLE sales": "one statement",
        "DROP TABLE sales": "not a read",
        "DELETE FROM sales": "not a read",
        "UPDATE sales SET amount = 0": "not a read",
        "INSERT INTO sales VALUES (1)": "not a read",
        "WITH x AS (SELECT 1) DELETE FROM sales": "not a read",
        "CREATE TABLE t AS SELECT * FROM sales": "not a read",
        "ALTER TABLE sales ADD COLUMN x INT": "not a read",
        "PRAGMA writable_schema = 1": "not a read",
        "ATTACH DATABASE '/tmp/x.db' AS x": "not a read",
        "SELECT load_extension('/tmp/evil.so')": "side effect",
        "SELECT writefile('/tmp/x', 'y')": "side effect",
        "SELECT * FROM secret_table": "unknown table",
        "SELECT * FROM main.sqlite_master": "unknown table",
        "": "empty",
        "SELEC * FROM sales": "parse",
        "show me the money": "not a read",
        "VACUUM": "not a read",
        "REPLACE INTO sales VALUES (1)": "not a read",
    }
    for s, why in bad_sql.items():
        v = guard.validate(s, "sqlite", TABLES)
        check(not v.ok and any(why in p for p in v.problems), f"refuses ({why}): {s[:50]!r} {v.problems}")

    sf_bad = {
        "SELECT SYSTEM$CANCEL_ALL_QUERIES(1)": "side effect",
        "CALL my_proc()": "not a read",
        "COPY INTO @stage FROM sales": "not a read",
        "GRANT SELECT ON sales TO ROLE public": "not a read",
        "USE ROLE ACCOUNTADMIN": "not a read",
        "MERGE INTO sales s USING products p ON s.product_id = p.product_id WHEN MATCHED THEN DELETE": "not a read",
        "PUT file:///tmp/x @~": "not a read",
        "SELECT * FROM sales; SELECT 2": "one statement",
    }
    for s, why in sf_bad.items():
        v = guard.validate(s, "snowflake", TABLES)
        check(not v.ok and any(why in p for p in v.problems), f"snowflake refuses ({why}): {s[:50]!r} {v.problems}")
    v = guard.validate("SELECT * FROM ANALYTICS.MART.SALES", "snowflake", {"analytics.mart.sales"})
    check(v.ok, f"snowflake: fully qualified known table allowed {v.problems}")
    v = guard.validate("SELECT * FROM sales", "snowflake", {"analytics.mart.sales"})
    check(v.ok, f"snowflake: bare name matches a qualified known table {v.problems}")

    # ---------- guard: limits ----------
    v = guard.validate("SELECT * FROM sales", "sqlite", TABLES, max_rows=100)
    check(v.ok and "LIMIT 100" in v.sql.upper(), "adds LIMIT when missing")
    v = guard.validate("SELECT * FROM sales LIMIT 50000", "sqlite", TABLES, max_rows=100)
    check(v.ok and "LIMIT 100" in v.sql.upper() and v.warnings, "caps a large LIMIT and says so")
    v = guard.validate("SELECT * FROM sales LIMIT 5", "sqlite", TABLES, max_rows=100)
    check(v.ok and "LIMIT 5" in v.sql.upper(), "keeps a small LIMIT")
    v = guard.validate("SELECT COUNT(*) FROM sales", "sqlite", TABLES, max_rows=100)
    check(v.ok, "aggregate query ok")

    # ---------- sample DB + SQLite runner ----------
    tmp = Path(tempfile.mkdtemp())
    dbp = tmp / "shop.db"
    make_sample.build(dbp)
    r = db.SQLiteRunner(dbp)
    cols, rows = r.run("SELECT COUNT(*) FROM sales")
    check(rows[0][0] > 100, f"sample DB has sales ({rows[0][0]})")
    for attack in ("DELETE FROM sales", "DROP TABLE sales", "INSERT INTO products VALUES (999,'x','y',1.0)",
                   "PRAGMA query_only = OFF", "ATTACH DATABASE ':memory:' AS m", "CREATE TABLE z(a)"):
        try:
            r.run(attack)
            check(False, f"runner blocks even without the guard: {attack}")
        except db.ReadOnlyError:
            check(True, f"runner blocks even without the guard: {attack}")
    cols, rows = r.run("SELECT COUNT(*) FROM sales")
    check(rows[0][0] > 100, "data intact after attacks")
    cols, rows = r.run("SELECT * FROM sales", max_rows=7)
    check(len(rows) == 7, "runner caps rows fetched")
    check(not os.access(dbp, os.W_OK) or sqlite3.connect(dbp).execute("PRAGMA integrity_check").fetchone()[0] == "ok", "file untouched")

    # ---------- Snowflake runner with a fake connection ----------
    class FakeCur:
        def __init__(self, log):
            self.log, self.description = log, None

        def execute(self, sql, *a):
            self.log.append(sql)
            if sql.startswith("SELECT"):
                self.description = [("REVENUE",), ("PRODUCT",)]

        def fetchmany(self, n):
            return [(1.0, "a")] * min(n, 3)

        def close(self):
            pass

    class FakeConn:
        def __init__(self):
            self.log = []

        def cursor(self):
            return FakeCur(self.log)

    fc = FakeConn()
    sr = db.SnowflakeRunner(conn=fc, role="ANALYST_RO", timeout=30)
    cols, rows = sr.run("SELECT 1", max_rows=2)
    joined = "\n".join(fc.log)
    check("USE ROLE ANALYST_RO" in joined and "STATEMENT_TIMEOUT_IN_SECONDS = 30" in joined and "QUERY_TAG" in joined,
          "snowflake session: role, timeout, query tag set")
    check(cols == ["REVENUE", "PRODUCT"] and len(rows) == 2, "snowflake rows capped")
    for role in ("ACCOUNTADMIN", "sysadmin", "SecurityAdmin", "ORGADMIN"):
        try:
            db.SnowflakeRunner(conn=FakeConn(), role=role)
            check(False, f"refuses admin role {role}")
        except db.ReadOnlyError:
            check(True, f"refuses admin role {role}")
    try:
        db.SnowflakeRunner(conn=FakeConn(), role="")
        check(False, "requires a named role")
    except db.ReadOnlyError:
        check(True, "requires a named role")

    # ---------- schema ----------
    sch = schema.describe_sqlite(r)
    check(set(sch.tables) == TABLES, f"schema lists tables {sorted(sch.tables)}")
    check({"customers.email", "customers.phone", "customers.full_name"} <= sch.sensitive, f"flags personal columns {sorted(sch.sensitive)}")
    check("products.product_name" not in sch.sensitive and "sales.amount" not in sch.sensitive, "doesn't flag ordinary columns")
    txt = sch.text()
    check("customers(" in txt and "email TEXT [sensitive]" in txt and "@" not in txt, "schema text has names and types, no values")
    sch2 = schema.describe_sqlite(r, extra_sensitive={"sales.amount"}, not_sensitive={"customers.full_name"})
    check("sales.amount" in sch2.sensitive and "customers.full_name" not in sch2.sensitive, "overrides add and remove flags")

    # ---------- masking ----------
    m = mask_rows(["full_name", "email", "revenue"], [("Jane Doe", "jane@x.com", 10.0)], {"full_name", "email"})
    check(m == [["[masked]", "[masked]", 10.0]], "masks sensitive columns by name")
    m = mask_rows(["note"], [("call 214-555-0182 or jane.doe@gmail.com",)], set())
    check("214-555-0182" not in str(m) and "jane.doe@gmail.com" not in str(m), "masks personal data found in values too")

    # ---------- assistant with a fake Claude ----------
    good = "SELECT p.product_name, SUM(s.amount) AS revenue FROM sales s JOIN products p ON p.product_id = s.product_id GROUP BY 1 ORDER BY 2 DESC LIMIT 5"
    fake = FakeClient([good, "TEXT:Widgets lead revenue."])
    a = assistant.Assistant(runner=r, schema=sch, llm=ClaudeSQL(client=fake, model="m"), audit_path=tmp / "audit.jsonl")
    res = a.ask("Show top 5 products by revenue")
    check(res.ok and len(res.rows) == 5 and res.columns == ["product_name", "revenue"], f"answers the post's example {res.problems}")
    check(res.explanation == "Widgets lead revenue.", "explanation returned")
    req0 = fake.messages.requests[0]
    check(req0["tool_choice"] == {"type": "tool", "name": "run_sql"} and req0["tools"][0]["name"] == "run_sql", "uses forced tool calling")
    sys_blocks = req0["system"]
    check(any(b.get("cache_control") for b in sys_blocks if isinstance(b, dict)), "schema block is prompt-cached")

    # never send personal values
    fake = FakeClient(["SELECT full_name, email, phone FROM customers LIMIT 3", "TEXT:Three customers."])
    a = assistant.Assistant(runner=r, schema=sch, llm=ClaudeSQL(client=fake, model="m"), audit_path=tmp / "audit.jsonl")
    res = a.ask("list three customers with contact details")
    sent = json.dumps(fake.messages.requests, default=str)
    real = r.run("SELECT full_name, email, phone FROM customers LIMIT 3")[1]
    check(res.ok and res.rows == [list(x) for x in real], "user still sees the real rows locally")
    check(all(str(v) not in sent for row in real for v in row), "no personal value reached the model")
    check(any("sensitive" in w for w in res.warnings), "warns that sensitive columns were selected")

    # explain none: nothing about rows goes out
    fake = FakeClient([good])
    a = assistant.Assistant(runner=r, schema=sch, llm=ClaudeSQL(client=fake, model="m"), explain="none", audit_path=tmp / "audit.jsonl")
    res = a.ask("top 5 products by revenue")
    check(res.ok and len(fake.messages.requests) == 1 and res.explanation.startswith("5 rows"), "explain=none: one call, local summary only")

    # self-correction: guard refusal, then a DB error, then good
    fake = FakeClient(["DELETE FROM sales", "SELECT nope FROM sales", good, "TEXT:ok"])
    a = assistant.Assistant(runner=r, schema=sch, llm=ClaudeSQL(client=fake, model="m"), audit_path=tmp / "audit.jsonl")
    res = a.ask("top products")
    second = json.dumps(fake.messages.requests[1]["messages"])
    third = json.dumps(fake.messages.requests[2]["messages"])
    check(res.ok and res.attempts == 3, f"recovers after a refused and a failing query ({res.attempts})")
    check("not a read" in second and "no such column" in third, "feeds the guard and database errors back")
    fake = FakeClient(["DROP TABLE sales"] * 3)
    a = assistant.Assistant(runner=r, schema=sch, llm=ClaudeSQL(client=fake, model="m"), audit_path=tmp / "audit.jsonl")
    res = a.ask("drop everything")
    check(not res.ok and res.attempts == 3 and r.run("SELECT COUNT(*) FROM sales")[1][0][0] > 100, "gives up after 3 tries, data intact")

    audit = [json.loads(x) for x in (tmp / "audit.jsonl").read_text().splitlines()]
    check(audit and all(set(e) >= {"ts", "question", "sql", "ok", "rows"} for e in audit), "audit log written")
    check("jane" not in (tmp / "audit.jsonl").read_text().lower() and all(isinstance(e["rows"], int) for e in audit), "audit log holds counts, not rows")

    # ---------- CLI (no model: --sql) ----------
    cli = APP / "cli.py"
    p = subprocess.run([sys.executable, str(cli), "--sqlite", str(dbp), "--sql", "SELECT category, COUNT(*) n FROM products GROUP BY 1", "--json"],
                       capture_output=True, text=True, timeout=60)
    out = json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}
    check(p.returncode == 0 and out.get("ok") and out.get("columns") == ["category", "n"], f"cli runs your own SQL through the guard {p.stderr[-200:]}")
    p = subprocess.run([sys.executable, str(cli), "--sqlite", str(dbp), "--sql", "DELETE FROM sales"], capture_output=True, text=True, timeout=60)
    check(p.returncode != 0 and "not a read" in (p.stdout + p.stderr), "cli refuses a write")
    p = subprocess.run([sys.executable, str(cli), "--sqlite", str(dbp), "--schema"], capture_output=True, text=True, timeout=60)
    check(p.returncode == 0 and "sales(" in p.stdout and "[sensitive]" in p.stdout, "cli prints the schema it would send")

    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
