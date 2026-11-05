#!/usr/bin/env python3
"""Find where Snowflake credits go and what to change, from read-only ACCOUNT_USAGE views.

Three steps; use the ones that fit how you're allowed to reach Snowflake:

  python3 sf_cost.py queries --days 30 --out ./sf-cost        # write the SQL, run it anywhere
  python3 sf_cost.py run --connection my_conn --days 30 --out ./sf-cost   # or run it here
  python3 sf_cost.py analyze --in ./sf-cost --credit-price 3.00            # report from the CSVs

`queries` writes one <section>.sql per section. Run each (Snowsight, SnowSQL, `snow sql`,
the Snowflake MCP server) and save the result as <section>.csv in the same folder.
`run` does that for you with snowflake-connector-python and a named connection from
~/.snowflake/connections.toml; credentials never pass through this script's arguments.
`analyze` reads the CSVs and writes report.md and findings.json. It needs no connection.

Every statement is a SELECT or SHOW. Needs a role with IMPORTED PRIVILEGES on the SNOWFLAKE
database (or the USAGE_VIEWER / GOVERNANCE_VIEWER database roles).
"""
import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

AU = "snowflake.account_usage"
SECTIONS = {
    "warehouse_metering": f"""
SELECT warehouse_name, TO_DATE(start_time) AS day,
       SUM(credits_used) AS credits_used,
       SUM(credits_used_compute) AS credits_compute,
       SUM(credits_used_cloud_services) AS credits_cloud,
       SUM(credits_attributed_compute_queries) AS credits_attributed
FROM {AU}.warehouse_metering_history
WHERE start_time >= DATEADD(day, -{{days}}, CURRENT_TIMESTAMP())
GROUP BY 1, 2
ORDER BY 1, 2""",
    "service_metering": f"""
SELECT service_type, usage_date AS day, SUM(credits_billed) AS credits_billed
FROM {AU}.metering_daily_history
WHERE usage_date >= DATEADD(day, -{{days}}, CURRENT_DATE())
GROUP BY 1, 2
ORDER BY 1, 2""",
    "warehouse_load": f"""
SELECT warehouse_name, COUNT(*) AS queries,
       SUM(IFF(queued_overload_time > 0, 1, 0)) AS queued_queries,
       SUM(queued_overload_time) / 1000 AS queued_seconds,
       SUM(IFF(bytes_spilled_to_remote_storage > 0, 1, 0)) AS remote_spill_queries,
       MEDIAN(total_elapsed_time) / 1000 AS median_seconds
FROM {AU}.query_history
WHERE start_time >= DATEADD(day, -{{days}}, CURRENT_TIMESTAMP()) AND warehouse_name IS NOT NULL
GROUP BY 1
ORDER BY 2 DESC""",
    "query_patterns": f"""
WITH attr AS (
  SELECT query_parameterized_hash, warehouse_name, COUNT(*) AS runs,
         SUM(credits_attributed_compute) AS credits
  FROM {AU}.query_attribution_history
  WHERE start_time >= DATEADD(day, -{{days}}, CURRENT_TIMESTAMP())
  GROUP BY 1, 2
), qh AS (
  SELECT query_parameterized_hash, warehouse_name,
         ANY_VALUE(LEFT(query_text, 400)) AS sample_text,
         AVG(total_elapsed_time) / 1000 AS avg_seconds,
         SUM(bytes_spilled_to_remote_storage) AS remote_spill_bytes,
         SUM(bytes_spilled_to_local_storage) AS local_spill_bytes,
         SUM(partitions_scanned) AS partitions_scanned,
         SUM(partitions_total) AS partitions_total
  FROM {AU}.query_history
  WHERE start_time >= DATEADD(day, -{{days}}, CURRENT_TIMESTAMP()) AND warehouse_name IS NOT NULL
  GROUP BY 1, 2
)
SELECT a.query_parameterized_hash, a.warehouse_name, a.runs, a.credits, q.avg_seconds,
       q.remote_spill_bytes, q.local_spill_bytes, q.partitions_scanned, q.partitions_total, q.sample_text
FROM attr a LEFT JOIN qh q USING (query_parameterized_hash, warehouse_name)
ORDER BY a.credits DESC NULLS LAST
LIMIT 50""",
    "table_storage": f"""
SELECT table_catalog, table_schema, table_name, is_transient,
       active_bytes, time_travel_bytes, failsafe_bytes, retained_for_clone_bytes
FROM {AU}.table_storage_metrics
WHERE deleted = FALSE AND (time_travel_bytes + failsafe_bytes) > 0
ORDER BY time_travel_bytes + failsafe_bytes DESC
LIMIT 50""",
    "warehouses": "SHOW WAREHOUSES",
}
READ_ONLY = re.compile(r"^\s*(SELECT|WITH|SHOW)\b", re.I)
TB = 1024 ** 4


# ---------- queries / run ----------
def render(days):
    return {k: v.strip().replace("{days}", str(int(days))) + "\n" for k, v in SECTIONS.items()}


def cmd_queries(a):
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for name, sql in render(a.days).items():
        (out / f"{name}.sql").write_text(sql)
    print(f"wrote {len(SECTIONS)} queries to {out}/. Save each result as <name>.csv next to it, then run analyze.")


def cmd_run(a):
    try:
        import snowflake.connector
    except ImportError:
        sys.exit("run needs snowflake-connector-python (pip install snowflake-connector-python), "
                 "or use `queries` and run the SQL yourself.")
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    con = snowflake.connector.connect(connection_name=a.connection, session_parameters={"QUERY_TAG": "sf_cost.py"})
    try:
        cur = con.cursor()
        for name, sql in render(a.days).items():
            assert READ_ONLY.match(sql), f"{name} is not read-only"
            (out / f"{name}.sql").write_text(sql)
            try:
                cur.execute(sql)
            except Exception as e:  # keep going: one missing grant shouldn't stop the rest
                print(f"  {name}: skipped ({str(e).splitlines()[0][:160]})")
                continue
            cols = [d[0].lower() for d in cur.description]
            with open(out / f"{name}.csv", "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(cur.fetchall())
            print(f"  {name}: ok")
    finally:
        con.close()


# ---------- analyze ----------
def num(v):
    try:
        return float(v) if v not in (None, "", "NULL") else 0.0
    except ValueError:
        return 0.0


def load(folder, name):
    p = Path(folder) / f"{name}.csv"
    if not p.exists():
        return None
    with open(p, newline="", encoding="utf-8-sig") as f:
        return [{k.strip().strip('"').lower(): v for k, v in row.items()} for row in csv.DictReader(f)]


def mask_sql(text):
    """Hide literals in sample query text: they can hold customer data."""
    t = re.sub(r"'(?:[^']|'')*'", "'?'", text or "")
    t = re.sub(r"\b\d{4,}\b", "?", t)
    return " ".join(t.split())[:160]


def day(v):
    return datetime.strptime(str(v)[:10], "%Y-%m-%d").date()


def analyze(folder, credit_price, storage_price):
    wm, sm, wl = load(folder, "warehouse_metering"), load(folder, "service_metering"), load(folder, "warehouse_load")
    qp, ts, wh = load(folder, "query_patterns"), load(folder, "table_storage"), load(folder, "warehouses")
    missing = [n for n, v in [("warehouse_metering", wm), ("service_metering", sm), ("warehouse_load", wl),
                              ("query_patterns", qp), ("table_storage", ts), ("warehouses", wh)] if v is None]
    if wm is None and sm is None:
        sys.exit(f"no warehouse_metering.csv or service_metering.csv in {folder}: run `queries` or `run` first")
    usd = lambda c: f"${c * credit_price:,.0f}"  # noqa: E731
    findings, md = [], []

    # totals and trend
    daily = defaultdict(float)
    if sm:
        for r in sm:
            daily[day(r["day"])] += num(r["credits_billed"])
    else:
        for r in wm:
            daily[day(r["day"])] += num(r["credits_used"])
    total = sum(daily.values())
    last = max(daily) if daily else date.today()
    wk = sum(v for d, v in daily.items() if d > last - timedelta(days=7))
    prev = sum(v for d, v in daily.items() if last - timedelta(days=14) < d <= last - timedelta(days=7))
    days = len(daily) or 1
    md += ["# Snowflake cost report", "",
           f"**{total:,.1f} credits ({usd(total)})** over {days} day(s) ending {last}, at ${credit_price:.2f}/credit "
           "(an assumption: use your contract rate).", ""]
    if prev:
        ch = (wk - prev) / prev * 100
        md.append(f"Last 7 days: {wk:,.1f} credits, {'up' if ch >= 0 else 'down'} {abs(ch):.0f}% on the 7 days before.")
        if ch > 25:
            findings.append({"severity": "warn", "rule": "spend-rising", "credits": wk - prev,
                             "what": f"Spend up {ch:.0f}% week over week.",
                             "do": "Compare the top query patterns and warehouses below with last week's; look for new jobs or a resized warehouse."})
        md.append("")

    if sm:
        by_svc = defaultdict(float)
        for r in sm:
            by_svc[r["service_type"]] += num(r["credits_billed"])
        md += ["## By service", "", "| Service | Credits | Share |", "|---|---|---|"]
        for s, c in sorted(by_svc.items(), key=lambda kv: -kv[1]):
            md.append(f"| {s} | {c:,.1f} | {c / total * 100 if total else 0:.0f}% |")
            if s != "WAREHOUSE_METERING" and total and c / total > 0.10:
                findings.append({"severity": "info", "rule": "serverless-share", "credits": c,
                                 "what": f"{s} is {c / total * 100:.0f}% of spend.",
                                 "do": "Check the matching history view (e.g. AUTOMATIC_CLUSTERING_HISTORY, SERVERLESS_TASK_HISTORY) for the objects behind it."})
        md.append("")

    # warehouses
    whs = defaultdict(lambda: defaultdict(float))
    for r in wm or []:
        w = whs[r["warehouse_name"]]
        for k in ("credits_used", "credits_compute", "credits_attributed"):
            w[k] += num(r.get(k))
    cfg = {r.get("name", "").upper(): r for r in wh or []}
    load_by = {r["warehouse_name"].upper(): r for r in wl or []}
    if whs:
        md += ["## Warehouses", "",
               "| Warehouse | Size | Auto-suspend | Credits | Idle credits | Idle % | Queued queries | Remote-spill queries |",
               "|---|---|---|---|---|---|---|---|"]
        for name, w in sorted(whs.items(), key=lambda kv: -kv[1]["credits_used"]):
            c, idle = cfg.get(name.upper(), {}), max(0.0, w["credits_compute"] - w["credits_attributed"])
            idle_pct = idle / w["credits_compute"] * 100 if w["credits_compute"] else 0
            ld = load_by.get(name.upper(), {})
            susp = c.get("auto_suspend", "")
            shown = (susp if susp not in ("", "0", "null", "NULL", "None") else "never") if c else "?"
            md.append(f"| {name} | {c.get('size', '?')} | {shown} | {w['credits_used']:,.1f} | {idle:,.1f} | "
                      f"{idle_pct:.0f}% | {int(num(ld.get('queued_queries')))} | {int(num(ld.get('remote_spill_queries')))} |")
            if c and susp in ("", "0", "null", "NULL", "None"):
                findings.append({"severity": "error", "rule": "never-suspends", "credits": idle or w["credits_compute"], "recoverable": True,
                                 "warehouse": name, "what": f"{name} never auto-suspends.",
                                 "do": f"ALTER WAREHOUSE {name} SET AUTO_SUSPEND = 60;"})
            elif idle_pct >= 30 and total and idle / total >= 0.01:
                s = int(num(susp)) if susp else 0
                fix = f"ALTER WAREHOUSE {name} SET AUTO_SUSPEND = 60; (now {s}s)" if s > 60 else \
                    "Auto-suspend is already short: consolidate into a busier warehouse, or batch the jobs that keep waking it."
                findings.append({"severity": "warn", "rule": "idle-warehouse", "credits": idle, "recoverable": True, "warehouse": name,
                                 "what": f"{name}: {idle:,.1f} credits ({idle_pct:.0f}%) billed while no query was running.",
                                 "do": fix})
            q, n = num(ld.get("queued_queries")), num(ld.get("queries"))
            if n and q / n >= 0.05:
                findings.append({"severity": "info", "rule": "queuing", "credits": 0, "warehouse": name,
                                 "what": f"{name}: {q / n * 100:.0f}% of queries waited in a queue ({num(ld.get('queued_seconds')):,.0f}s total).",
                                 "do": "Latency, not cost: raise MAX_CLUSTER_COUNT (Enterprise edition) or split the workloads that collide."})
        md.append("")
        md.append("Idle credits = compute billed minus compute attributed to queries: the most you could save by suspending sooner.")
        md.append("")

    # query patterns
    if qp:
        qtotal = sum(num(r["credits"]) for r in qp)
        md += ["## Most expensive query patterns", "",
               "| # | Warehouse | Runs | Credits | Avg s | Remote spill | Scanned partitions | Sample (literals hidden) |",
               "|---|---|---|---|---|---|---|---|"]
        for i, r in enumerate(qp[:10], 1):
            pt, ps = num(r.get("partitions_total")), num(r.get("partitions_scanned"))
            scan = f"{ps / pt * 100:.0f}% of {int(pt):,}" if pt else "n/a"
            spill = f"{num(r.get('remote_spill_bytes')) / 1024 ** 3:,.1f} GB" if num(r.get("remote_spill_bytes")) else "-"
            md.append(f"| {i} | {r['warehouse_name']} | {int(num(r['runs'])):,} | {num(r['credits']):,.2f} | "
                      f"{num(r.get('avg_seconds')):,.1f} | {spill} | {scan} | `{mask_sql(r.get('sample_text')).replace('|', '/')}` |")
        md.append("")
        for i, r in enumerate(qp[:20], 1):
            c, pt, ps = num(r["credits"]), num(r.get("partitions_total")), num(r.get("partitions_scanned"))
            if num(r.get("remote_spill_bytes")) > 0:
                findings.append({"severity": "warn", "rule": "remote-spill", "credits": c, "warehouse": r["warehouse_name"],
                                 "what": f"Pattern #{i} spills to remote storage ({num(r['remote_spill_bytes']) / 1024 ** 3:,.1f} GB).",
                                 "do": "Filter and project earlier, split the big join or window, or run it on one size larger and compare cost."})
            if pt >= 1000 and ps / pt >= 0.8 and qtotal and c / qtotal >= 0.02:
                findings.append({"severity": "warn", "rule": "full-scan", "credits": c, "warehouse": r["warehouse_name"],
                                 "what": f"Pattern #{i} reads {ps / pt * 100:.0f}% of {int(pt):,} partitions.",
                                 "do": "Add a filter on the column the table is ordered or clustered by; for a very large hot table, consider a clustering key."})
            if num(r["runs"]) >= 24 * days and qtotal and c / qtotal >= 0.05:
                findings.append({"severity": "info", "rule": "frequent", "credits": c, "warehouse": r["warehouse_name"],
                                 "what": f"Pattern #{i} runs {num(r['runs']) / days:,.0f} times a day.",
                                 "do": "Check whether it needs to be that fresh: a less frequent schedule, a result cache, a materialized view or a dynamic table."})

    # storage
    if ts:
        rows = []
        for r in ts:
            act, tt, fs = num(r["active_bytes"]), num(r["time_travel_bytes"]), num(r["failsafe_bytes"])
            if tt + fs >= 0.1 * TB and (tt + fs) > act:
                full = f"{r['table_catalog']}.{r['table_schema']}.{r['table_name']}"
                rows.append((tt + fs, full, act, str(r.get("is_transient", "")).upper()))
        if rows:
            md += ["## Storage held only for recovery", "", "| Table | Active TB | Time travel + fail-safe TB | Transient |",
                   "|---|---|---|---|"]
            for extra, full, act, tr in sorted(rows, reverse=True)[:10]:
                md.append(f"| {full} | {act / TB:,.2f} | {extra / TB:,.2f} | {tr} |")
                findings.append({"severity": "info", "rule": "recovery-storage", "credits": 0, "usd_month": extra / TB * storage_price,
                                 "what": f"{full} keeps {extra / TB:,.2f} TB of history, more than its live data.",
                                 "do": "If it's rebuilt by a pipeline (staging, scratch), recreate it as TRANSIENT or lower DATA_RETENTION_TIME_IN_DAYS."})
            md.append("")

    # findings
    order = {"error": 0, "warn": 1, "info": 2}
    findings.sort(key=lambda f: (order[f["severity"]], -f.get("credits", 0)))
    md += ["## What to change, most important first", ""]
    if not findings:
        md.append("Nothing stood out. Re-run with a longer window, or check the patterns table for jobs that shouldn't exist.")
    for i, f in enumerate(findings, 1):
        money = (f" Up to {f['credits']:,.1f} credits ({usd(f['credits'])}) recoverable over the window." if f.get("recoverable")
                 else f" It cost {f['credits']:,.1f} credits ({usd(f['credits'])}) over the window.") if f.get("credits") else \
            (f" About ${f['usd_month']:,.0f}/month at ${storage_price}/TB." if f.get("usd_month") else "")
        md += [f"{i}. **[{f['severity']}] {f['what']}**{money}", f"   {f['do']}"]
    md += ["", "\"Recoverable\" is an upper bound from the billing views; \"it cost\" is what that item spent, not what a fix saves. "
           "Re-run this after each change to measure the real saving."]
    if missing:
        md += ["", "## Not checked", "", *[f"- `{m}.csv` not found (missing grant, or not run)." for m in missing]]
    return "\n".join(md) + "\n", findings


def cmd_analyze(a):
    rep, fs = analyze(a.inp, a.credit_price, a.storage_price)
    out = Path(a.inp)
    (out / "report.md").write_text(rep)
    (out / "findings.json").write_text(json.dumps(fs, indent=1) + "\n")
    print(f"sf_cost: {len(fs)} finding(s) -> {out}/report.md")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    q = sub.add_parser("queries")
    q.add_argument("--days", type=int, default=30)
    q.add_argument("--out", default="./sf-cost")
    r = sub.add_parser("run")
    r.add_argument("--connection", required=True, help="name in ~/.snowflake/connections.toml")
    r.add_argument("--days", type=int, default=30)
    r.add_argument("--out", default="./sf-cost")
    z = sub.add_parser("analyze")
    z.add_argument("--in", dest="inp", default="./sf-cost")
    z.add_argument("--credit-price", type=float, default=3.0, help="USD per credit (default 3.00)")
    z.add_argument("--storage-price", type=float, default=23.0, help="USD per TB-month (default 23)")
    a = ap.parse_args(argv)
    {"queries": cmd_queries, "run": cmd_run, "analyze": cmd_analyze}[a.cmd](a)


if __name__ == "__main__":
    main()
