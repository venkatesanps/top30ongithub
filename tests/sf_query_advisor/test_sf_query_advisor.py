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
        results, _ = sfa.analyze_file(p, Args(), kw.get("explains", []), kw.get("stats", []), kw.get("hist", []), kw.get("tables", {}),
                                      kw.get("columns"), kw.get("attribution"), kw.get("cfg"))
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

# --- 0.3.0: credits Snowflake attributed to the query
att = sfa.load_attribution([FIX / "attribution.csv", FIX / "pattern.csv"])
check(len(att[0]) == 1 and len(att[1]) == 1, f"attribution rows split into runs and patterns: {att}")
full2 = run_sql((FIX / "orders_report.sql").read_text(), hist=hist, attribution=att)[0]
a2, p2 = full2.get("attributed") or {}, full2.get("pattern") or {}
check(abs(a2.get("total", 0) - 0.3105) < 1e-9 and (a2.get("hash") or "").startswith("9f3c"), f"attributed credits: {a2}")
check(p2.get("runs") == 720 and abs(p2["credits"] - 221.4) < 1e-9 and 29 < p2["days"] < 30.5 and abs(p2["per_day"] * p2["days"] - 221.4) < 1e-6,
      f"pattern summary: {p2}")
md2 = sfa.report_md([("q.sql", [full2], False)], Args(), {"explain": False, "stats": False, "history": True, "tables": False, "attribution": True})
check("Credits Snowflake attributed to this run: 0.3105" in md2 and "Rate × run time would have said 0.9156" in md2
      and "Estimate: a warehouse shared" not in md2 and "720 runs" in md2 and "snowflake-cost-investigator" in md2, md2[-900:])
kids = [{"QUERY_ID": "P1", "CREDITS_ATTRIBUTED_COMPUTE": "0.1", "QUERY_PARAMETERIZED_HASH": "h1"},
        {"QUERY_ID": "C1", "PARENT_QUERY_ID": "P1", "ROOT_QUERY_ID": "P1", "CREDITS_ATTRIBUTED_COMPUTE": "0.2", "CREDITS_USED_QUERY_ACCELERATION": "0.05"}]
k = sfa.attributed_credits("P1", kids)
check(k and abs(k["total"] - 0.35) < 1e-9 and k["rows"] == 2 and abs(k["qas"] - 0.05) < 1e-9 and k["hash"] == "h1", f"child queries add up: {k}")
check(sfa.attributed_credits(None, kids)["rows"] == 2 and sfa.attributed_credits("X", kids) is None, "one root without an id; unknown id is None")
two = [{"QUERY_ID": "A", "QUERY_PARAMETERIZED_HASH": "h", "CREDITS_ATTRIBUTED_COMPUTE": "1", "START_TIME": "2026-11-01 00:00:00"},
       {"QUERY_ID": "B", "QUERY_PARAMETERIZED_HASH": "h", "CREDITS_ATTRIBUTED_COMPUTE": "3", "START_TIME": "2026-11-05 00:00:00"}]
ps = sfa.pattern_summary([], two, "h")
check(ps and ps["runs"] == 2 and ps["credits"] == 4 and ps["days"] == 4 and ps["per_day"] == 1, f"pattern from per-run rows: {ps}")
check(sfa.pattern_summary([], two[:1], "h") is None, "one run is not a pattern")
joined = [dict(sfa.read_rows(FIX / "history.csv")[0], CREDITS_ATTRIBUTED_COMPUTE="0.2")]
check(len(sfa.load_attribution([], joined)[0]) == 1, "history rows that carry attributed credits count")

# --- 0.3.0: schema-aware checks
COLS = sfa.load_columns(FIX / "columns.csv")
check(list(COLS["orders"][0]["cols"])[:3] == ["order_id", "customer_id", "order_ts"] and COLS["customers"][0]["cols"]["customer_id"][1] == "TEXT",
      "columns load in ordinal order with types")
s3 = run_sql((FIX / "orders_report.sql").read_text(), columns=COLS)[0]
fof = [f for f in s3["findings"] if f["rule"] == "function-on-filter-column"][0]
check(fof["rewrite_status"].startswith("type checked: order_ts is TIMESTAMP_NTZ") and fof["confidence"] == "high" and "assumes" not in fof["fix"],
      f"date rewrite checked against the type: {fof}")
jm = [f for f in s3["findings"] if f["rule"] == "join-type-mismatch"]
check(len(jm) == 1 and "NUMBER" in jm[0]["title"] and "TEXT" in jm[0]["title"] and jm[0]["severity"] == "medium",
      f"NUMBER = TEXT join found through the CTE's SELECT *: {jm}")
txt = [f for f in run_sql("select amount from analytics.sales.orders where to_date(order_date_txt) = '2026-03-15'", columns=COLS)[0]["findings"]
       if f["rule"] == "function-on-filter-column"][0]
check("rewrite" not in txt and txt["rewrite_status"] == "no rewrite: the column is text" and "YYYY-MM-DD" in txt["fix"], f"text date: {txt}")
tz = {"t": [{"key": ("", ""), "name": "T", "cols": {"ts": ("TS", "TIMESTAMP_TZ")}}]}
tzf = [f for f in run_sql("select a from t where to_date(ts) = '2026-03-15'", columns=tz)[0]["findings"] if f["rule"] == "function-on-filter-column"][0]
check("time zone" in tzf["rewrite_status"] and tzf.get("rewrite"), f"TIMESTAMP_TZ caveat: {tzf}")
nf = [f for f in run_sql("select a from other_t where to_date(ts) = '2026-03-15'", columns=COLS)[0]["findings"] if f["rule"] == "function-on-filter-column"][0]
check(nf["rewrite_status"].startswith("unchecked: the column's type isn't"), f"unknown type stays unchecked: {nf}")
nf = [f for f in run_sql("select a from t where to_date(ts) = '2026-03-15'")[0]["findings"] if f["rule"] == "function-on-filter-column"][0]
check(nf["rewrite_status"].startswith("unchecked") and nf["confidence"] == "medium", f"no schema: unchecked, medium: {nf}")
r = rules("select o.amount from analytics.sales.orders o where o.region = 5 and o.order_id = '5' and o.region = 'EU' and o.order_ts > '2026-01-01'",
          columns=COLS)
check(r["implicit-cast-filter"] == 1, f"only TEXT = number is an implicit cast: {r}")
check(rules("select o.amount from analytics.sales.orders o where o.region in (1, 2)", columns=COLS)["implicit-cast-filter"] == 1, "IN list too")
r = rules("select o.amount, o.bogus, c.status from analytics.sales.orders o join analytics.sales.customers c on o.region = c.region", columns=COLS)
check(r["unknown-column"] == 1 and r["join-type-mismatch"] == 0, f"unknown column; TEXT = TEXT join is fine: {r}")
check(rules("with x as (select order_id as k from analytics.sales.orders) select x.k, x.nope from x", columns=COLS)["unknown-column"] == 0,
      "CTE columns aren't checked against tables")
check(rules("select 1 from analytics.sales.orders o join analytics.ref.blocked_status b on o.order_ts = b.status", columns=COLS)["join-type-mismatch"] == 1,
      "timestamp = text join is flagged")
dt = {"a": [{"key": ("", ""), "name": "A", "cols": {"d": ("D", "DATE")}}], "b": [{"key": ("", ""), "name": "B", "cols": {"t": ("T", "TIMESTAMP_LTZ")}}]}
check(rules("select 1 from a join b on a.d = b.t", columns=dt)["join-type-mismatch"] == 0, "DATE = TIMESTAMP is comparable")
star = [f for f in run_sql("select * from analytics.sales.orders", columns=COLS)[0]["findings"] if f["rule"] == "select-star"][0]
check(star["rewrite"] == "SELECT ORDER_ID, CUSTOMER_ID, ORDER_TS, AMOUNT, REGION, ORDER_DATE_TXT" and "6 columns" in star["why"]
      and star["confidence"] == "high", f"SELECT * expanded: {star}")
star = [f for f in run_sql("select * from analytics.sales.orders o join analytics.sales.customers c on o.region = c.region", columns=COLS)[0]["findings"]
        if f["rule"] == "select-star"][0]
check(star["rewrite"].startswith("SELECT o.ORDER_ID,") and "c.STATUS" in star["rewrite"] and "9 columns" in star["why"], f"two tables: {star['rewrite']}")
star = [f for f in run_sql("select c.* from analytics.sales.orders o join analytics.sales.customers c on o.region = c.region", columns=COLS)[0]["findings"]
        if f["rule"] == "select-star"][0]
check(star["rewrite"] == "SELECT c.CUSTOMER_ID, c.REGION, c.STATUS", f"t.* expands only t: {star.get('rewrite')}")
check("rewrite" not in [f for f in run_sql("select * from analytics.sales.orders o join unknown_t u on o.region = u.region", columns=COLS)[0]["findings"]
                        if f["rule"] == "select-star"][0], "no partial column list when a table isn't exported")
amb = {"a": [{"key": ("", ""), "name": "A", "cols": {"k": ("K", "NUMBER")}}], "b": [{"key": ("", ""), "name": "B", "cols": {"k": ("K", "TEXT")}}]}
check(rules("select 1 from a join b on a.k = b.k where k = 5", columns=amb)["implicit-cast-filter"] == 0, "ambiguous unqualified column isn't guessed")
check(sfa.type_family("NUMBER(38,0)") == "number" and sfa.type_family("VARCHAR(16777216)") == "text" and sfa.type_family("TIMESTAMP_NTZ(9)") == "timestamp"
      and sfa.type_family("TIME") == "time" and sfa.type_family("GEOGRAPHY") == "other", "type families")

# --- 0.3.0: confidence
c = {f["rule"]: f["confidence"] for f in run_sql("select * from t where name like '%x' and to_date(ts) = '2026-01-01'")[0]["findings"]}
check(c.get("leading-wildcard") == "high" and c.get("function-on-filter-column") == "medium", f"confidence by rule: {c}")
check(all(f["confidence"] == "high" for f in full["findings"] if f["rule"] in sfa.MEASURED_RULES), "measured findings are high confidence")
res = run_sql((FIX / "messy.sql").read_text())
check(all(f["confidence"] == "low" for f in res[3]["findings"]), "text-level checks on unparsed SQL are low confidence")
with tempfile.TemporaryDirectory() as d:
    p = Path(d) / "m.sql"
    p.write_text("select * from {{ ref('orders') }} where name like '%x'")
    rs, j = sfa.analyze_file(p, Args(), [], [], [], {})
    check(j and {f["confidence"] for f in rs[0]["findings"]} == {"medium"}, f"dbt templates step down a level: {[f['confidence'] for f in rs[0]['findings']]}")

# --- 0.3.0: turning rules off
sup = run_sql("select * from t -- sf-advisor: disable=select-star\nwhere name like '%x'")[0]
check([f["rule"] for f in sup["findings"]] == ["leading-wildcard"] and sup["suppressed"] == ["select-star"], f"disable on the line: {sup['suppressed']}")
sup = run_sql("-- sf-advisor: disable-next-line=select-star,leading-wildcard because it's a lookup\nselect * from t where name like '%x'")[0]
check(not sup["findings"] and sorted(sup["suppressed"]) == ["leading-wildcard", "select-star"], f"disable-next-line with a reason: {sup['suppressed']}")
sup = run_sql("/* sf-advisor: disable-file=leading-wildcard */\nselect a from t\nwhere name like '%x'")[0]
check(not sup["findings"], "disable-file in a block comment")
sup = run_sql("{# sf-advisor: disable #}select * from t where name like '%x'")[0]
check(not sup["findings"] and len(sup["suppressed"]) == 2, "bare disable in a Jinja comment turns off every rule on the line")
sup = run_sql("select * from t where name like '%x'", cfg={"disable": {"select-star"}, "severity": {"leading-wildcard": "high"}})[0]
check([(f["rule"], f["severity"]) for f in sup["findings"]] == [("leading-wildcard", "high")], f"config disable and severity: {sup['findings']}")
h1 = run_sql("select 1 from t where x not in (select y from u)", hist=hist)[0]
check(h1["findings"], "statement-level findings exist")
h2 = run_sql("-- sf-advisor: disable=queued\nselect 1\nfrom t where x not in (select y from u)", hist=hist)[0]
check("queued" in h2["suppressed"], "a directive inside the statement turns off its line-less findings")

# --- statement-level findings sit on the first code line, so directives above them work
u = run_sql("-- full reload\nUPDATE t SET a = 1;")[0]
check([(f["rule"], f["line"]) for f in u["findings"]] == [("update-all-rows", 2)] and u["code_line"] == 2, f"anchored to the UPDATE: {u['findings']}")
check(not run_sql("-- sf-advisor: disable-next-line=update-all-rows\nUPDATE t SET a = 1;")[0]["findings"], "disable-next-line above an UPDATE")
check(not run_sql("-- full reload\nUPDATE t SET a = 1;  -- sf-advisor: disable=update-all-rows")[0]["findings"], "disable on the UPDATE's line")
check(not run_sql("/* reload\n   every night */\n\nDELETE FROM t; -- sf-advisor: disable")[0]["findings"], "block comments before the statement")
check(sfa.first_code_line("\n-- a\n/* b */ select 1", 10) == 12 and sfa.first_code_line("-- only a comment", 3) == 3, "first code line")
# --- a table name in two schemas with different columns isn't guessed
with tempfile.TemporaryDirectory() as d:
    cp = Path(d) / "cols.csv"
    cp.write_text("TABLE_SCHEMA,TABLE_NAME,COLUMN_NAME,DATA_TYPE\nSALES,ORDERS,ID,NUMBER\nSALES,ORDERS,REGION,TEXT\n"
                  "ARCHIVE,ORDERS,ID,TEXT\nARCHIVE,ORDERS,OLD_COL,TEXT\nA,DIM,K,NUMBER\nB,DIM,K,NUMBER\n")
    two_schemas = sfa.load_columns(cp)
r = rules("select o.region from orders o where o.id = 5 and o.bogus = 1", columns=two_schemas)
check(r["implicit-cast-filter"] == 0 and r["unknown-column"] == 0, f"ambiguous ORDERS: no guessed findings: {r}")
r = rules("select o.bogus from sales.orders o where o.region = 5", columns=two_schemas)
check(r["implicit-cast-filter"] == 1 and r["unknown-column"] == 1, f"schema-qualified ORDERS resolves: {r}")
check(rules("select d.nope from dim d", columns=two_schemas)["unknown-column"] == 1, "identical copies in two schemas still resolve")

# --- 0.3.0: config, changed-only, SARIF, brief
def run_cli(*args, cwd=None):
    return subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True, cwd=cwd)
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "legacy").mkdir()
    (d / "a.sql").write_text((FIX / "orders_report.sql").read_text())
    (d / "legacy" / "b.sql").write_text("select * from big_t")
    (d / ".sf-advisor.toml").write_text('[sf-advisor]\ndisable = ["count-distinct"]\nexclude = ["legacy/*"]\nfail_on = "high"\ngeneration = 2\n'
                                        '[sf-advisor.severity]\nnot-in-subquery = "high"\n')
    r = run_cli("analyze", d, "--json", d / "o.json", "--md", d / "o.md")
    data = json.loads((d / "o.json").read_text())
    rs = [x["rule"] for f in data for s in f["statements"] for x in s["findings"]]
    sev = {x["rule"]: x["severity"] for f in data for s in f["statements"] for x in s["findings"]}
    check(r.returncode == 1 and len(data) == 1 and "count-distinct" not in rs and sev.get("not-in-subquery") == "high",
          f"config: exclude, disable, severity, fail_on: rc={r.returncode} {rs} {r.stderr}")
    r = run_cli("analyze", d, "--json", d / "o.json", "--md", d / "o.md", "--no-config")
    check(r.returncode == 0 and len(json.loads((d / "o.json").read_text())) == 2, f"--no-config ignores it: {r.returncode}")
    r = run_cli("analyze", d, "--generation", "1", "--fail-on", "info", "--md", d / "o.md", "--history", FIX / "history.csv", "--no-config")
    (d / "bad.json").write_text('{"disabel": ["x"]}')
    r = run_cli("analyze", d / "a.sql", "--config", d / "bad.json")
    check(r.returncode != 0 and "unknown setting" in r.stderr, f"unknown config keys are an error: {r.stderr}")
    g = lambda *x: subprocess.run(["git", "-c", "user.email=t@example.com", "-c", "user.name=t", *x], cwd=d, capture_output=True, text=True, check=True)
    g("init", "-q")
    g("add", "-A")
    g("commit", "-qm", "base")
    r = run_cli("analyze", ".", "--changed-only", "--sarif", "empty.sarif", "--no-config", cwd=d)
    empty = json.loads((d / "empty.sarif").read_text())
    check(r.returncode == 0 and "no changed .sql files" in r.stdout and empty["runs"][0]["results"] == [], f"nothing changed: {r.stdout}{r.stderr}")
    (d / "c.sql").write_text("select a from t\nwhere name like '%x'\n")
    (d / "a.sql").write_text((d / "a.sql").read_text() + "\n-- edited\n")
    r = run_cli("analyze", ".", "--changed-only", "HEAD", "--brief", "--sarif", "out.sarif", "--no-config", cwd=d)
    lines = r.stdout.strip().splitlines()
    check(r.returncode == 0 and any(x.startswith("c.sql:2: [low] leading-wildcard:") for x in lines) and any(x.startswith("a.sql:") for x in lines)
          and not any("legacy" in x for x in lines) and lines[-1].startswith("2 file(s)"), f"changed-only + brief: {r.stdout}{r.stderr}")
    (d / "sub").mkdir()
    (d / "sub" / "e.sql").write_text("select a from t where name like '%x'\n")
    r2 = run_cli("analyze", ".", "--changed-only", "--brief", "--no-config", cwd=d / "sub")
    check(r2.returncode == 0 and r2.stdout.startswith("e.sql:1:") or "e.sql:1:" in r2.stdout, f"untracked files found from a subfolder: {r2.stdout}{r2.stderr}")
    (d / "sub" / "e.sql").unlink()
    (d / "sub").rmdir()
    sar = json.loads((d / "out.sarif").read_text())
    run0 = sar["runs"][0]
    ids = {x["id"] for x in run0["tool"]["driver"]["rules"]}
    check(sar["version"] == "2.1.0" and run0["tool"]["driver"]["version"] == sfa.VERSION and run0["results"]
          and all(x["ruleId"] in ids and x["level"] in ("error", "warning", "note") for x in run0["results"])
          and all(loc["physicalLocation"]["region"]["startLine"] >= 1 and not loc["physicalLocation"]["artifactLocation"]["uri"].startswith("/")
                  for x in run0["results"] for loc in x["locations"])
          and {x["locations"][0]["physicalLocation"]["artifactLocation"]["uri"] for x in run0["results"]} == {"a.sql", "c.sql"},
          f"SARIF shape: {json.dumps(sar)[:600]}")
    lw = [x for x in run0["results"] if x["ruleId"] == "leading-wildcard"][0]
    check(lw["locations"][0]["physicalLocation"]["region"]["startLine"] == 2 and lw["properties"]["confidence"] == "high"
          and len(lw["partialFingerprints"]["sfQueryAdvisor/v1"]) == 40, f"SARIF result: {lw}")
    (d / "c.sql").write_text("\n\nselect a from t\nwhere name like '%x'\n")
    run_cli("analyze", "c.sql", "--sarif", "moved.sarif", "--no-config", cwd=d)
    moved = [x for x in json.loads((d / "moved.sarif").read_text())["runs"][0]["results"] if x["ruleId"] == "leading-wildcard"][0]
    check(moved["partialFingerprints"] == lw["partialFingerprints"], "fingerprints survive lines moving")
r = run_cli("queries", FIX / "orders_report.sql")
check("QUERY_ATTRIBUTION_HISTORY" in r.stdout and "INFORMATION_SCHEMA.COLUMNS" in r.stdout and "root_query_id = '<query_id>'" in r.stdout
      and "query_parameterized_hash" in r.stdout, "queries prints the attribution and column exports")
r = run_cli("analyze", FIX / "orders_report.sql", "--columns", FIX / "columns.csv", "--history", FIX / "history.csv",
            "--attribution", FIX / "attribution.csv", "--attribution", FIX / "pattern.csv", "--no-config")
check(r.returncode == 0 and "column types, attributed credits" in r.stdout and "type checked" in r.stdout and "720 runs" in r.stdout, r.stdout[:300] + r.stderr)

print("OK" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
