"""Runs sf_cost.py on invented ACCOUNT_USAGE exports and checks the findings and safety rules.

python3 tests/sf_cost/test_sf_cost.py   (no dependencies, no network, no Snowflake account)
"""
import csv
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
from datetime import date, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-data/skills/snowflake-cost-investigator/scripts/sf_cost.py"
TB = 1024 ** 4
END = date(2026, 11, 3)


def write(folder, name, cols, rows):
    with open(folder / f"{name}.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([c.upper() for c in cols])  # Snowflake exports upper-case headers
        w.writerows(rows)


def fixture(folder):
    days = [END - timedelta(days=i) for i in range(13, -1, -1)]
    wm = []
    for d in days:
        late = d > END - timedelta(days=7)
        wm.append(["ETL_WH", d, 30, 29, 1, 27])                      # busy, little idle
        wm.append(["BI_WH", d, 15 if late else 10, 15 if late else 10, 0, 4])  # mostly idle
        wm.append(["DEV_WH", d, 2, 2, 0, 1])
    write(folder, "warehouse_metering", ["warehouse_name", "day", "credits_used", "credits_compute",
                                         "credits_cloud", "credits_attributed"], wm)
    sm = []
    for d in days:
        late = d > END - timedelta(days=7)
        sm.append(["WAREHOUSE_METERING", d, 47 if late else 42])
        sm.append(["AUTO_CLUSTERING", d, 12 if late else 8])
    write(folder, "service_metering", ["service_type", "day", "credits_billed"], sm)
    write(folder, "warehouse_load", ["warehouse_name", "queries", "queued_queries", "queued_seconds",
                                     "remote_spill_queries", "median_seconds"],
          [["ETL_WH", 5000, 20, 300, 40, 12], ["BI_WH", 2000, 300, 9000, 0, 2], ["DEV_WH", 50, 0, 0, 0, 1]])
    write(folder, "query_patterns", ["query_parameterized_hash", "warehouse_name", "runs", "credits", "avg_seconds",
                                     "remote_spill_bytes", "local_spill_bytes", "partitions_scanned", "partitions_total",
                                     "sample_text"],
          [["h1", "ETL_WH", 14, 120, 900, 50 * 1024 ** 3, 10, 100, 1000,
            "INSERT INTO fact SELECT * FROM big JOIN huge ON big.k = huge.k WHERE email = 'jane.doe@corp.com'"],
           ["h2", "ETL_WH", 140, 90, 120, 0, 0, 95000, 100000,
            "SELECT * FROM positions WHERE account_no = 4111111111111111"],
           ["h3", "BI_WH", 2000, 30, 2, 0, 0, 10, 20, "SELECT count(*) FROM dash_tile WHERE region = 'TX'"]])
    write(folder, "table_storage", ["table_catalog", "table_schema", "table_name", "is_transient", "active_bytes",
                                    "time_travel_bytes", "failsafe_bytes", "retained_for_clone_bytes"],
          [["RAW", "STG", "STG_TRADES", "NO", int(0.05 * TB), int(0.2 * TB), int(0.3 * TB), 0],
           ["MART", "CORE", "DIM_ACCOUNT", "NO", int(2 * TB), int(0.1 * TB), int(0.1 * TB), 0]])
    write(folder, "warehouses", ["name", "state", "size", "auto_suspend", "auto_resume"],
          [["ETL_WH", "STARTED", "Large", 60, "true"], ["BI_WH", "STARTED", "Medium", 600, "true"],
           ["DEV_WH", "SUSPENDED", "X-Small", "", "true"]])


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=60)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        q = tmp / "q"
        r = run("queries", "--days", "14", "--out", q)
        sqls = {p.stem: p.read_text() for p in q.glob("*.sql")}
        check(r.returncode == 0 and len(sqls) == 6, f"queries writes 6 files ({sorted(sqls)})")
        check(all(re.match(r"\s*(SELECT|WITH|SHOW)\b", s, re.I) for s in sqls.values()), "every query is SELECT/WITH/SHOW")
        check(not any(re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|GRANT)\b", s, re.I) for s in sqls.values()),
              "no write or DDL keywords in any query")
        check("-14," in sqls["warehouse_metering"] and "{days}" not in "".join(sqls.values()), "window substituted")

        d = tmp / "d"
        d.mkdir()
        fixture(d)
        r = run("analyze", "--in", d, "--credit-price", "2.5")
        check(r.returncode == 0, f"analyze exits 0 ({r.stderr.strip()[:200]})")
        rep = (d / "report.md").read_text()
        fs = json.loads((d / "findings.json").read_text())
        rules = [f["rule"] for f in fs]

        check("763.0 credits ($1,908)" in rep, "total credits and dollars from service metering")
        check("up 18%" in rep, "week-over-week change reported")
        check(fs and fs[0]["rule"] == "never-suspends" and "DEV_WH SET AUTO_SUSPEND = 60" in fs[0]["do"],
              "warehouse that never suspends is the first finding, with the fix")
        idle = [f for f in fs if f["rule"] == "idle-warehouse"]
        check(len(idle) == 1 and idle[0]["warehouse"] == "BI_WH" and "now 600s" in idle[0]["do"],
              "idle BI_WH flagged with its current auto-suspend")
        check(abs(idle[0]["credits"] - 119) < 0.01 if idle else False, "idle credits = compute minus attributed")
        check(not any(f["rule"] == "idle-warehouse" and f["warehouse"] == "ETL_WH" for f in fs), "busy warehouse not called idle")
        check(any(f["rule"] == "queuing" and f["warehouse"] == "BI_WH" for f in fs), "queuing flagged on BI_WH")
        check(any(f["rule"] == "remote-spill" for f in fs), "remote spill flagged")
        check(any(f["rule"] == "full-scan" and "95%" in f["what"] for f in fs), "full partition scan flagged")
        check(any(f["rule"] == "frequent" for f in fs), "very frequent pattern flagged")
        check(any(f["rule"] == "serverless-share" and "AUTO_CLUSTERING" in f["what"] for f in fs), "serverless share flagged")
        rs = [f for f in fs if f["rule"] == "recovery-storage"]
        check(len(rs) == 1 and "STG_TRADES" in rs[0]["what"], "only the staging table is a TRANSIENT candidate")
        check(rules.index("never-suspends") < rules.index("idle-warehouse") < rules.index("queuing"), "findings ordered by severity")
        check("jane.doe" not in rep and "4111111111111111" not in rep and "'?'" in rep, "literals hidden in sample SQL")
        check("Not checked" not in rep, "nothing reported missing when all CSVs exist")

        (d / "table_storage.csv").unlink()
        run("analyze", "--in", d)
        check("`table_storage.csv` not found" in (d / "report.md").read_text(), "missing section listed under Not checked")

        e = tmp / "empty"
        e.mkdir()
        r = run("analyze", "--in", e)
        check(r.returncode != 0 and "queries" in r.stderr, "clear message when there is nothing to analyze")

        if importlib.util.find_spec("snowflake") is None:
            r = run("run", "--connection", "x", "--out", tmp / "r")
            check(r.returncode != 0 and "snowflake-connector-python" in r.stderr, "run explains the missing connector")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
