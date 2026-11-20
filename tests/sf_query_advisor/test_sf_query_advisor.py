"""Tests for sf_query_advisor.py: plans, rules (including what must NOT be flagged), Snowflake
evidence files, dbt/Jinja and messy input. The EXPLAIN, operator-stats and history fixtures follow
the formats in Snowflake's documentation; they were not exported from a live account.

python3 tests/sf_query_advisor/test_sf_query_advisor.py   (needs sqlglot; no network)
"""
import csv
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-data/skills/snowflake-query-advisor/scripts/sf_query_advisor.py"
FIX = Path(__file__).resolve().parent / "fixtures"
sys.path.insert(0, str(SCRIPT.parent))
import sf_query_advisor as sfa  # noqa: E402

fails = 0


def check(ok, msg):
    global fails
    if not ok:
        fails += 1
        print("FAIL", msg)


class Args:
    warehouse = None
    generation = 1
    cloud = "aws"
    credit_price = 3.0
    runs_per_day = None


def run_sql(sql, **kw):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "q.sql"
        p.write_text(sql)
        results, _ = sfa.analyze_file(p, Args(), kw.get("explains", []), kw.get("stats", []), kw.get("hist", []), kw.get("tables", {}))
    return results


def rules(sql, **kw):
    return Counter(f["rule"] for r in run_sql(sql, **kw) for f in r["findings"])


# --- what should be flagged
r = rules("select * from db.s.orders where to_date(order_ts) = '2026-03-15'")
check(r["select-star"] == 1 and r["function-on-filter-column"] == 1, f"star + function filter: {r}")
f = [x for x in run_sql("select a from t where to_date(ts) = '2026-03-15'")[0]["findings"] if x["rule"] == "function-on-filter-column"][0]
check(f["rewrite"] == "ts >= '2026-03-15'::DATE AND ts < DATEADD(day, 1, '2026-03-15'::DATE)", f"date rewrite: {f.get('rewrite')}")
for sql, want in [("select a from t where ts::date = '2026-03-15'", "ts >= '2026-03-15'::DATE AND ts < DATEADD(day, 1, '2026-03-15'::DATE)"),
                  ("select a from t where date_trunc('month', ts) = '2026-03-01'", "ts >= '2026-03-01'::DATE AND ts < DATEADD(month, 1, '2026-03-01'::DATE)")]:
    got = [x for x in run_sql(sql)[0]["findings"] if x["rule"] == "function-on-filter-column"][0].get("rewrite")
    check(got == want, f"rewrite for {sql}: {got}")
f = [x for x in run_sql("select a from t where year(d) = 2026")[0]["findings"] if x["rule"] == "function-on-filter-column"][0]
check(f["rewrite"] == "d >= '2026-01-01'::DATE AND d < '2027-01-01'::DATE", f"year rewrite: {f.get('rewrite')}")
check(rules("select a from t, u")["cartesian-join"] == 1, "comma join with no condition is cartesian")
check(rules("select a from t where id not in (select id from u)")["not-in-subquery"] == 1, "NOT IN subquery")
check(rules("select a from t join u on t.a < u.b")["non-equi-join"] == 1, "non-equi join")
check(rules("select a from t join u on t.a = u.a or t.b = u.b")["or-in-join"] == 1, "OR in join")
check(rules("select a from t join u on (t.k = u.k and t.x = 1) or (t.k = u.k and t.y = 2)")["or-in-join"] == 0, "OR sharing a common key is fine")
check(rules("select a from t where name like '%x'")["leading-wildcard"] == 1, "leading wildcard")
check(rules("select a from t union select a from u")["union-distinct"] == 1, "UNION")
check(rules("select a, (select max(b.x) from b where b.k = t.k) from t")["correlated-subquery"] == 1, "correlated subquery")
check(rules("update t set a = 1")["update-all-rows"] == 1, "UPDATE without WHERE")
check(rules("merge into f using s on f.id = s.id when matched then update set f.v = s.v")["merge-full-target-scan"] == 1, "MERGE on keys only")
check(rules("select random() from t")["no-result-reuse"] == 1, "RANDOM blocks reuse")
check(rules("select x from (select a from t order by a) q")["inner-order-by"] == 1, "inner ORDER BY")
check(rules("select a from t where a in (" + ",".join(str(i) for i in range(250)) + ")")["large-in-list"] == 1, "large IN list")

# --- what must NOT be flagged
quiet = {
    "star from a CTE that chose its columns": "with x as (select a, b from t) select * from x",
    "star inside a CTE narrowed outside": "with x as (select * from t) select a from x",
    "EXISTS (SELECT *)": "select a from t where exists (select * from u where u.k = t.k)",
    "comma join with WHERE key": "select t.a from t, u where t.id = u.id",
    "TPC-H unqualified keys": "select l_orderkey from lineitem, orders where l_orderkey = o_orderkey",
    "OR branches that all carry the key": "select a from part, lineitem where (p_partkey = l_partkey and p_size < 5) or (p_partkey = l_partkey and p_size > 9)",
    "LATERAL FLATTEN": "select f.value from t, lateral flatten(input => t.arr) f",
    "TABLE(FLATTEN())": "select f.value from t, table(flatten(input => t.arr)) f",
    "top-level ORDER BY": "select a from t order by a",
    "function on the constant side": "select a from t where ts >= dateadd(day, -7, current_date())",
    "cross join to a one-row aggregate": "select t.a, m.mx from t cross join (select max(a) as mx from t) m",
    "join on two one-row CTEs": "with p as (select count(*) c from a), d as (select count(*) c from b) select * from p join d on p.c <> d.c",
}
for name, sql in quiet.items():
    got = rules(sql)
    noisy = {k: v for k, v in got.items() if k not in ("limit-without-order", "count-distinct")}
    check(not noisy, f"should be quiet ({name}): {noisy}")

# --- plans
res = run_sql((FIX / "orders_report.sql").read_text())[0]
check("TableScan analytics.sales.customers" in res["plan"] and "WithReference recent" in res["plan"], "estimated plan shows scans and CTE refs")
check("filter: TO_DATE(order_ts) = '2026-03-15'" in res["plan"], "WHERE pushed onto the scan")
check("Aggregate group by c.region" in res["plan"] and "Sort" in res["plan"], "aggregate and sort")
res = run_sql("select l_orderkey from lineitem, orders where l_orderkey = o_orderkey")[0]
check("InnerJoin (keys in WHERE)" in res["plan"] and "unqualified" in res["plan"], f"comma join plan: {res['plan']}")

# --- evidence files
plan = sfa.load_explain(FIX / "explain_orders.json")
check(plan["global"]["partitionsTotal"] == 48210 and len(plan["ops"]) == 9, "EXPLAIN JSON loads")
txt = sfa.render_explain(plan)
check("TableScan ANALYTICS.SALES.ORDERS  [partitions 45,800 of 48,000" in txt and txt.splitlines()[0].startswith("Result"), "EXPLAIN renders as a tree")
with tempfile.TemporaryDirectory() as d:
    wrapped = Path(d) / "cell.json"  # a JSON string inside JSON, as a copied cell often is
    wrapped.write_text(json.dumps(json.dumps(json.loads((FIX / "explain_orders.json").read_text()))))
    check(len(sfa.load_explain(wrapped)["ops"]) == 9, "double-encoded EXPLAIN JSON loads")
    tab = Path(d) / "tab.csv"
    tab.write_text("step,id,parentOperators,operation,objects,alias,expressions,partitionsTotal,partitionsAssigned,bytesAssigned\n"
                   "NULL,NULL,NULL,GlobalStats,NULL,NULL,NULL,2,2,1024\n1,0,NULL,Result,NULL,NULL,Z1.ID,NULL,NULL,NULL\n"
                   "1,1,[0],TableScan,TESTDB.DOC.Z1,NULL,ID,2,2,1024\n")
    tp = sfa.load_explain(tab)
    check(tp["global"]["partitionsTotal"] == 2 and tp["ops"][1]["parents"] == [0], "TABULAR export loads")
    cellcsv = Path(d) / "snowsight.csv"  # a one-cell export with whatever header Snowsight gives the column
    with cellcsv.open("w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["SOME HEADER"])
        w.writerow([(FIX / "explain_orders.json").read_text()])
    check(len(sfa.load_explain(cellcsv)["ops"]) == 9, "JSON in a CSV cell loads, whatever the header")
    # statement numbers in file names route plans: a plan for statement 2 must not attach to statement 1
    two = Path(d) / "two.sql"
    two.write_text("select a from t;\n" + (FIX / "orders_report.sql").read_text())
    named = Path(d) / "two_2.explain.json"
    named.write_text((FIX / "explain_orders.json").read_text())
    r2 = subprocess.run([sys.executable, str(SCRIPT), "analyze", str(two), "--explain", str(named), "--json", str(Path(d) / "two.json")],
                        capture_output=True, text=True)
    st = json.loads((Path(d) / "two.json").read_text())[0]["statements"]
    check(st[0]["plan_source"].startswith("estimated") and st[1]["plan_source"].startswith("from EXPLAIN"), f"plan routed by number: {[s['plan_source'][:20] for s in st]}")
    # files under a folder the user names explicitly (dbt's target/compiled) are read
    comp = Path(d) / "target" / "compiled"
    comp.mkdir(parents=True)
    (comp / "m.sql").write_text("select a from t")
    check(sfa.collect([comp]) == [comp / "m.sql"], "target/compiled is read when passed directly")
    check(sfa.collect([Path(d)]) and all("target" not in p.parts for p in sfa.collect([Path(d)])), "target is skipped when scanning a project")

stats = sfa.read_rows(FIX / "operator_stats.csv")
hist = sfa.read_rows(FIX / "history.csv")
tables = sfa.load_tables(FIX / "tables.csv")
full = run_sql((FIX / "orders_report.sql").read_text(), explains=[plan], stats=stats, hist=hist, tables=tables)[0]
fr = Counter(f["rule"] for f in full["findings"])
check(fr["explain-poor-pruning"] >= 1 and fr["remote-spill"] == 1 and fr["exploding-join"] == 1 and fr["late-filter"] == 1 and fr["queued"] == 1,
      f"evidence findings: {fr}")
check(fr["history-poor-pruning"] == 0 and fr["poor-pruning"] == 0, f"pruning reported once, not three times: {fr}")
orders = [f for f in full["findings"] if f["rule"] == "explain-poor-pruning" and "ORDERS" in f["title"]]
check(orders and orders[0]["severity"] == "high", "382 GB scan with poor pruning is high")
cust = [f for f in full["findings"] if f["rule"] == "explain-poor-pruning" and "CUSTOMERS" in f["title"]]
check(cust and cust[0]["severity"] == "low", "a 2 GB dimension read in full is low")
h = full["history"][0]
check(h["size"] == "L" and abs(h["credits"] - 8 * 412 / 3600) < 1e-6, f"Gen1 L credits (the default): {h}")
check(sfa.credits_per_hour("L") == 8 and sfa.credits_per_hour("L", 2, "aws") == 10.8, "Gen1 by default, Gen2 only when asked")
check(sfa.credits_per_hour("XS", 2, "azure") == 1.25 and sfa.credits_per_hour("6XL", 2) is None and sfa.credits_per_hour("Medium", 1) == 4, "rates")
check(full["findings"][0]["severity"] == "high", "findings sorted worst first")

# --- dbt and messy input
res = run_sql((FIX / "dbt_model.sql").read_text())
check(len(res) == 1 and res[0]["parsed"] and "shop.events" in res[0]["plan"], f"dbt model parses with source() resolved: {res[0].get('error')}")
check("2020-01-01" not in res[0]["plan"], "only the first branch of {% if %} is kept")
text, found = sfa.strip_jinja((FIX / "dbt_model.sql").read_text())
check(found and text.count("\n") == (FIX / "dbt_model.sql").read_text().count("\n"), "Jinja stripping keeps line numbers")
res = run_sql((FIX / "messy.sql").read_text())
check(len(res) == 5, f"$$ body not split: {len(res)} statements")
check(res[0]["kind"] == "Create Procedure" and res[0]["plan"] is None, "procedure isn't planned")
check(res[3]["kind"] == "unparsed" and res[3]["error"], "broken statement reported, not fatal")
check(res[4]["findings"] and res[4]["findings"][0]["rule"] == "function-on-filter-column", "cast on a filtered column")
check([x["rule"] for x in res[1]["findings"]] == ["leading-wildcard"], "ILIKE '%x%'")

# --- CLI
r = subprocess.run([sys.executable, str(SCRIPT), "analyze", str(FIX / "orders_report.sql"), "--explain", str(FIX / "explain_orders.json"),
                    "--stats", str(FIX / "operator_stats.csv"), "--history", str(FIX / "history.csv"), "--tables", str(FIX / "tables.csv"),
                    "--fail-on", "high"], capture_output=True, text=True)
check(r.returncode == 1 and "from EXPLAIN: 45,870 of 48,210 partitions" in r.stdout and "Measured run 01b2-demo" in r.stdout, r.stdout[-400:] + r.stderr)
r = subprocess.run([sys.executable, str(SCRIPT), "queries", str(FIX / "orders_report.sql")], capture_output=True, text=True)
r3 = subprocess.run([sys.executable, str(SCRIPT), "queries", str(FIX / "dbt_model.sql")], capture_output=True, text=True)
check("dbt compile" in r3.stdout and "__jinja__" not in r3.stdout, "queries asks for compiled SQL for a dbt model")
check(rules("select seq4() from t")["no-result-reuse"] == 0, "SEQ functions aren't claimed to block reuse")
check(r.returncode == 0 and "EXPLAIN USING JSON\n-- Daily revenue" in r.stdout and "NOT IN (SELECT status" in r.stdout
      and "table_name = 'ORDERS' AND table_schema = 'SALES'" in r.stdout, "queries keeps the user's SQL and lists tables")
with tempfile.TemporaryDirectory() as d:
    out = Path(d) / "r.json"
    r = subprocess.run([sys.executable, str(SCRIPT), "analyze", str(FIX), "--json", str(out), "--md", str(Path(d) / "r.md")], capture_output=True, text=True)
    data = json.loads(out.read_text())
    check(r.returncode == 0 and len(data) == 3 and all("sql" not in s for f in data for s in f["statements"]), "folder run writes JSON without SQL text")

print("OK" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
