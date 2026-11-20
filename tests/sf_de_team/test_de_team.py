"""Checks de_team.py: routing, the SQL gate and hook, the researcher/critic/refiner format checks
and a full run folder through verify.

python3 tests/sf_de_team/test_de_team.py   (no dependencies, no network, no Snowflake)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-data/skills/snowflake-de-team/scripts/de_team.py"


def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, input=stdin)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    def route(task, *extra):
        return json.loads(run("route", task, "--json", *extra).stdout)

    # ---- routing
    r = route("why did last night's orders load fail")
    check(r["type"] == "incident" and [s["agent"] for s in r["steps"]] == ["pipeline-failure-triage"],
          "a failed load goes to triage only")
    check(route("the dbt incremental build failed with duplicate keys")["type"] == "incident",
          "incident wins over build when something failed")
    check(route("our snowflake credits doubled")["type"] == "cost", "credits: cost")
    check(route("this query is slow and spills")["type"] == "tune", "slow query: tune")
    check(route("migrate these Oracle PL/SQL packages")["type"] == "migrate", "oracle: migrate")
    r = route("build an incremental dbt model for orders")
    check(r["type"] == "build" and [s["agent"] for s in r["steps"]] ==
          ["sf-researcher", "sf-drafter", "sf-critic", "sf-refiner"], "build: researcher, drafter, critic, refiner")
    models = {s["agent"]: s["model"] for s in r["steps"]}
    check(models["sf-drafter"] == "sonnet" and models["sf-critic"] == "opus", "critic runs on the other model")
    m2 = {s["agent"]: s["model"] for s in route("build a dbt model", "--drafter-model", "opus")["steps"]}
    check(m2["sf-critic"] == "sonnet", "opus drafter gets a sonnet critic")
    r = route("review this dbt model")
    check(r["type"] == "review" and r["parallel"] and
          sorted(s["mode"] for s in r["steps"]) == ["correctness", "performance", "security", "style"],
          "review: four lenses in parallel, beating 'build' on dbt")
    check(route("which tables hold customer emails")["type"] == "research", "data question: research")
    p = run("route", "make it better")
    check(p.returncode == 3 and "Ask" in p.stdout, "unclear request asks instead of guessing (exit 3)")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def gate(sql, *extra):
            f = tmp / "q.sql"
            f.write_text(sql)
            p = run("gate", str(f), "--json", "--dev", "DEV_DE", "--prod", "PROD", *extra)
            return p.returncode, json.loads(p.stdout)["findings"]

        def has(fs, rule, sev=None):
            return any(f["rule"] == rule and (sev is None or f["severity"] == sev) for f in fs)

        # ---- gate
        code, fs = gate("SELECT * FROM PROD.S.T; SHOW TABLES; DESCRIBE TABLE PROD.S.T;\n"
                        "WITH a AS (SELECT 1) SELECT * FROM a; EXPLAIN SELECT 1;")
        check(code == 0 and not fs, "reads pass with no findings")
        code, fs = gate("-- DROP TABLE PROD.S.T;\nSELECT 'DELETE FROM PROD.S.T; x' FROM t; /* TRUNCATE PROD.S.T; */")
        check(code == 0 and not fs, "DML inside comments and strings is ignored")
        code, fs = gate("MERGE INTO PROD.S.T t USING DEV_DE.S.X s ON t.id=s.id WHEN MATCHED THEN DELETE;")
        check(code == 1 and has(fs, "prod-write", "error"), "a MERGE into prod is blocked")
        check(has(gate("INSERT INTO OTHER_DB.S.T VALUES (1);")[1], "prod-write", "error"),
              "a write to a database that isn't dev is blocked")
        check(has(gate("INSERT INTO t VALUES (1);")[1], "unqualified", "error"), "unqualified write is blocked")
        code, fs = gate("USE DATABASE DEV_DE;\nINSERT INTO s.t VALUES (1);")
        check(code == 0 and has(fs, "dev-write", "info"), "USE DATABASE dev makes a two-part name a dev write")
        check(has(gate("USE SCHEMA PROD.S;\nINSERT INTO t VALUES (1);")[1], "prod-write", "error"),
              "USE SCHEMA PROD.S makes it a prod write")
        check(has(gate("DELETE FROM DEV_DE.S.T;")[1], "no-where", "error"), "DELETE without WHERE is blocked even in dev")
        check(not has(gate("DELETE FROM DEV_DE.S.T WHERE d < '2020-01-01';")[1], "no-where"), "DELETE with WHERE is fine")
        check(has(gate("UPDATE DEV_DE.S.T SET x = 1;")[1], "no-where", "error"), "UPDATE without WHERE is blocked")
        code, fs = gate("CREATE OR REPLACE TABLE DEV_DE.S.T AS SELECT 1 a;")
        check(code == 0 and has(fs, "destructive", "warn"), "CREATE OR REPLACE TABLE in dev is a warning")
        check(has(gate("CREATE OR REPLACE TABLE PROD.S.T AS SELECT 1 a;")[1], "destructive", "error"),
              "CREATE OR REPLACE TABLE in prod is an error")
        check(has(gate("DROP TABLE IF EXISTS PROD.S.T;")[1], "destructive", "error"), "DROP in prod is blocked")
        check(has(gate("TRUNCATE TABLE PROD.S.T;")[1], "destructive", "error"), "TRUNCATE in prod is blocked")
        check(has(gate("GRANT SELECT ON TABLE DEV_DE.S.T TO ROLE R;")[1], "grants", "error"), "GRANT needs a person")
        check(has(gate("ALTER WAREHOUSE W SET WAREHOUSE_SIZE='4X-LARGE';")[1], "account-object", "error"),
              "warehouse changes need a person")
        check(has(gate("ALTER ACCOUNT SET X = 1;")[1], "account-object", "error"), "ALTER ACCOUNT needs a person")
        check(has(gate("USE ROLE ACCOUNTADMIN;")[1], "admin-role", "error"), "ACCOUNTADMIN is blocked")
        code, fs = gate("CREATE TEMPORARY TABLE t AS SELECT 1 a;")
        check(code == 0 and has(fs, "temp", "info"), "temporary tables are allowed anywhere")
        code, fs = gate("CREATE DYNAMIC TABLE DEV_DE.I.DT TARGET_LAG='1 hour' WAREHOUSE=W AS SELECT 1 a;\n"
                        "CREATE STREAM DEV_DE.S.ST ON TABLE DEV_DE.S.T;\n"
                        "CREATE TASK DEV_DE.S.TK WAREHOUSE=W SCHEDULE='5 MINUTE' "
                        "WHEN SYSTEM$STREAM_HAS_DATA('DEV_DE.S.ST') AS INSERT INTO DEV_DE.S.X SELECT * FROM DEV_DE.S.ST;")
        check(code == 0 and sum(has([f], "dev-write") for f in fs) == 3, "dynamic table, stream and task in dev pass")
        code, fs = gate("CREATE PROCEDURE DEV_DE.S.P() RETURNS STRING LANGUAGE SQL AS $$\nBEGIN\n"
                        "  DELETE FROM PROD.S.T;\nEND\n$$;\nCALL DEV_DE.S.P();")
        check(has(fs, "body", "warn") and has(fs, "opaque", "warn") and not has(fs, "prod-write"),
              "procedure bodies and CALLs are flagged for a person, not parsed as statements")
        code, fs = gate("SELECT 1;\n\nINSERT INTO PROD.S.T VALUES (1);")
        check([f["line"] for f in fs if f["rule"] == "prod-write"] == [3], "findings carry the right line")
        code, fs = gate("INSERT INTO DEV_DE.S.T VALUES (1);", "--fail-on", "info")
        check(code == 1, "--fail-on info fails on dev writes")
        cfg = tmp / "team.json"
        cfg.write_text(json.dumps({"dev_databases": ["SANDBOX"], "prod_databases": []}))
        f = tmp / "c.sql"
        f.write_text("INSERT INTO SANDBOX.S.T VALUES (1);")
        check(run("gate", str(f), "--config", str(cfg)).returncode == 0, "dev databases come from team.json")

        # ---- hook
        def hook(ev):
            return run("hook", "--dev", "DEV_DE", "--prod", "PROD", stdin=json.dumps(ev))

        p = hook({"tool_name": "Bash", "tool_input": {"command": 'snow sql -c dev -q "DELETE FROM PROD.S.T WHERE id=1"'}})
        check(p.returncode == 2 and "prod-write" in p.stderr, "hook blocks snow sql writing to prod (exit 2)")
        p = hook({"tool_name": "Bash", "tool_input": {"command": "snowsql -q 'SELECT COUNT(*) FROM PROD.S.T'"}})
        check(p.returncode == 0, "hook lets reads through")
        sqlf = tmp / "deploy.sql"
        sqlf.write_text("DROP TABLE PROD.S.T;")
        p = hook({"tool_name": "Bash", "tool_input": {"command": f"snow sql -f {sqlf}"}})
        check(p.returncode == 2, "hook reads snow sql -f files")
        p = hook({"tool_name": "mcp__snowflake__run_snowflake_query", "tool_input": {"statement": "TRUNCATE TABLE PROD.S.T"}})
        check(p.returncode == 2, "hook blocks Snowflake MCP writes")
        check(hook({"tool_name": "Bash", "tool_input": {"command": "rm -rf build && echo DELETE FROM x"}}).returncode == 0,
              "hook ignores commands that aren't Snowflake")
        check(run("hook", stdin="not json").returncode == 0, "hook never blocks on bad input")

        # ---- researcher findings
        def cf(text):
            f = tmp / "f.md"
            f.write_text(text)
            p = run("check-findings", str(f), "--json")
            return p.returncode, json.loads(p.stdout)

        good = ("# Findings\n\n"
                "- ORDERS has 41.2M rows → SELECT COUNT(*) FROM PROD.SALES.ORDERS → [Confidence: High]\n"
                "- ORDER_ID is unique → COUNT(*) = COUNT(DISTINCT ORDER_ID) query → [Confidence: High]\n"
                "- Loaded nightly by Airflow → dags/orders.py:12 → [Confidence: Medium]\n\n"
                "## Unverified\n- whether deletes happen upstream\n")
        code, r = cf(good)
        check(code == 0 and r["findings_count"] == 3, "well-formed findings pass")
        code, r = cf("- ORDER_ID is unique → assumed → [Confidence: High]\n")
        check(code == 1 and any(f["rule"] == "source" for f in r["findings"]), "an 'assumed' source fails")
        code, r = cf("- ORDER_ID is unique → the team said so → [Confidence: High]\n")
        check(code == 0 and any(f["rule"] == "source" and f["severity"] == "warn" for f in r["findings"]),
              "High confidence from a vague source is a warning")
        code, r = cf("- ORDERS is big → SELECT COUNT(*) FROM T\n")
        check(code == 1 and any(f["rule"] == "format" for f in r["findings"]), "a finding with no confidence fails")
        code, r = cf("- 12 failed tasks in the last hour → ACCOUNT_USAGE.TASK_HISTORY → [Confidence: High]\n")
        check(any(f["rule"] == "latency" for f in r["findings"]), "ACCOUNT_USAGE for the last hour is flagged")
        check(cf("Nothing here.\n")[0] == 1, "no findings at all fails")

        # ---- critique
        def cc(text):
            f = tmp / "c.md"
            f.write_text(text)
            p = run("check-critique", str(f), "--json")
            return p.returncode, json.loads(p.stdout)

        critique = ("# Critique\n\n"
                    "- P1 [Critical] `02-draft/fct_orders.sql:14` MERGE key ORDER_LINE_ID isn't unique per findings "
                    "line 4 — re-runs double rows\n"
                    "- P2 [Major] `02-draft/fct_orders.sql:3` no tie-break on late duplicates — nondeterministic rows\n"
                    "- P3 [Minor] `02-draft/fct_orders.sql:1` name doesn't follow FCT_ prefix — inconsistent\n\n"
                    "## Strongest parts\n- the incremental filter prunes on LOADED_AT\n")
        code, r = cc(critique)
        check(code == 0 and r["counts"] == {"Critical": 1, "Major": 1, "Minor": 1}, "a good critique passes")
        code, r = cc(critique.replace("— re-runs double rows", "— use ORDER_ID instead"))
        check(code == 1 and any(f["rule"] == "no-fixes" for f in r["findings"]), "a critic suggesting a fix fails")
        code, r = cc(critique.replace("## Strongest parts\n- the incremental filter prunes on LOADED_AT\n", ""))
        check(code == 1 and any(f["rule"] == "strongest" for f in r["findings"]), "missing strongest parts fails")
        code, r = cc(critique.replace("P2 [Major]", "[Major]"))
        check(code == 1 and any(f["rule"] == "id" for f in r["findings"]), "a problem without an id fails")
        code, r = cc(critique.replace("P2 [Major]", "P1 [Major]"))
        check(code == 1, "duplicate ids fail")
        code, r = cc("# Critique\n\nNo problems found: the model is a straight projection with tests.\n\n"
                     "## Strongest parts\n- tests on the key\n")
        check(code == 0, "'No problems found' with strongest parts passes")
        code, r = cc("## Strongest parts\n- x\n\n- P1 [Major] `a.sql:1` thing — bad\n")
        check(any(f["rule"] == "strongest" and f["severity"] == "warn" for f in r["findings"]),
              "strongest parts before the problems is a warning")

        # ---- refine
        (tmp / "crit.md").write_text(critique)

        def cr(notes):
            (tmp / "n.md").write_text(notes)
            p = run("check-refine", str(tmp / "crit.md"), str(tmp / "n.md"), "--json")
            return p.returncode, json.loads(p.stdout)

        code, r = cr("P1: MERGE on ORDER_ID, LINE_NO (fct_orders.sql:14)\nP2: QUALIFY ROW_NUMBER() tie-break (fct_orders.sql:3)\n")
        check(code == 0 and r["must_fix"] == ["P1", "P2"], "every Critical and Major answered passes; Minor optional")
        code, r = cr("P1: fixed the key\n")
        check(code == 1 and any("P2" in f["msg"] for f in r["findings"]), "an unanswered Major fails")
        code, r = cr("P1: fixed\nP2: skipped\n")
        check(code == 1 and any(f["rule"] == "reason" for f in r["findings"]), "a skip without a reason fails")
        code, r = cr("P1: fixed\nP2: not fixed — findings line 6 shows one row per key upstream, no late duplicates\n")
        check(code == 0, "a skip with evidence passes")

        # ---- kickoff + verify, end to end
        rd = tmp / "runs" / "orders"
        p = run("kickoff", "--task", "build an incremental dbt model for orders", "--out", str(rd),
                "--dev", "DEV_DE", "--prod", "PROD", "--json")
        team = json.loads((rd / "team.json").read_text())
        check(p.returncode == 0 and (rd / "context.md").exists() and team["dev_databases"] == ["DEV_DE"]
              and (rd / "02-draft").is_dir(), "kickoff writes context.md, team.json and the run folder")
        check("DEV_DE" in (rd / "context.md").read_text(), "context names the dev database")

        def verify():
            p = run("verify", str(rd), "--json")
            return p.returncode, json.loads(p.stdout)

        code, v = verify()
        check(code == 1 and "sf-researcher" in v["next"], "verify: researcher first")
        (rd / "01-findings.md").write_text(good)
        code, v = verify()
        check("sf-drafter" in v["next"], "verify: then the drafter")
        (rd / "02-draft" / "fct_orders.sql").write_text("MERGE INTO PROD.SALES.FCT_ORDERS t USING x s ON t.id=s.id "
                                                         "WHEN MATCHED THEN UPDATE SET t.a=s.a;")
        code, v = verify()
        check(code == 1 and "gate" in v["next"], "verify: a prod write in the draft stops the run")
        (rd / "02-draft" / "fct_orders.sql").write_text("MERGE INTO DEV_DE.SALES.FCT_ORDERS t USING x s ON t.id=s.id "
                                                         "WHEN MATCHED THEN UPDATE SET t.a=s.a;")
        code, v = verify()
        check("sf-critic" in v["next"], "verify: then the critic")
        (rd / "03-critique.md").write_text(critique)
        code, v = verify()
        check("sf-refiner" in v["next"], "verify: then the refiner")
        (rd / "04-fix-notes.md").write_text("P1: key fixed\n")
        code, v = verify()
        check(code == 1 and not v["done"], "verify: an unanswered Major keeps the run open")
        (rd / "04-fix-notes.md").write_text("P1: key fixed\nP2: tie-break added\n")
        code, v = verify()
        check(code == 1 and any(s["stage"] == "refined gate" and not s["ok"] for s in v["stages"]),
              "verify: refined SQL must exist")
        (rd / "04-refined" / "fct_orders.sql").write_text((rd / "02-draft" / "fct_orders.sql").read_text())
        code, v = verify()
        check(code == 0 and v["done"] and "person" in v["next"], "verify: done, and a person deploys")

        rr = tmp / "runs" / "rev"
        run("kickoff", "--task", "review this PR's dbt models", "--out", str(rr))
        code, v = (lambda p: (p.returncode, json.loads(p.stdout)))(run("verify", str(rr), "--json"))
        check("sf-critic" in v["next"], "a review run starts with the critics")

    print(f"\n{'All passed' if not failures else f'{len(failures)} failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
