"""Checks de_setup.py: stack detection, init (writes, merges, never overwrites), check, and that
what init writes passes agent-setup-audit with no errors.

python3 tests/de_setup/test_de_setup.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-data/skills/de-project-setup/scripts/de_setup.py"
AUDIT = ROOT / "plugins/top30-agents/skills/agent-setup-audit/scripts/setup_audit.py"


def run(*args, script=SCRIPT):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)


def mk(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        # ---- dbt + Snowflake + Airflow
        sf = tmp / "sf"
        mk(sf, {
            "dbt_project.yml": "name: 'shop'\nprofile: 'shop'\nmodel-paths: ['models']\n",
            "profiles.yml": "shop:\n  target: dev\n  outputs:\n    dev:\n      type: snowflake\n      password: hunter2\n",
            "requirements.txt": "dbt-snowflake==1.8.0\napache-airflow==2.9.0\n",
            "dags/daily.py": "from airflow import DAG\n",
            "models/staging/stg_shop__orders.sql": "select * from {{ source('shop','orders') }}\n",
            "models/marts/fct_orders.sql": "select * from {{ ref('stg_shop__orders') }}\n",
            "models/staging/_shop__models.yml": "models:\n  - name: stg_shop__orders\n",
            ".env": "SNOWFLAKE_PASSWORD=x\n",
        })
        d = json.loads(run("detect", sf, "--json").stdout)
        check(d["warehouses"] == ["snowflake"], "detect: snowflake from profiles.yml and requirements")
        check(d["dbt"]["name"] == "shop" and d["dbt"]["profile"] == "shop", "detect: dbt project name and profile")
        check(d["orchestrator"] == "airflow", "detect: airflow from a DAG import")

        p = run("check", sf, "--json")
        fs = json.loads(p.stdout)["findings"]
        msgs = " | ".join(f["msg"] for f in fs)
        check(p.returncode == 1, "check fails on a repo with secrets")
        check(any("literal password" in f["msg"] and f["file"] == "profiles.yml:6" for f in fs), "check: literal password in profiles.yml, by line")
        check(".env exists and isn't in .gitignore" in msgs, "check: .env not ignored")
        check("no MCP server" in msgs and "no CLAUDE.md" in msgs, "check: no MCP, no CLAUDE.md")
        check("1 of 2 models have no yml entry: fct_orders" in msgs, "check: undocumented model named")
        check("no unique/not_null tests" in msgs, "check: no key tests")

        p = run("init", sf, "--dry-run")
        check(p.returncode == 0 and "DRY RUN" in p.stdout and not (sf / "CLAUDE.md").exists(), "init --dry-run writes nothing")
        p = run("init", sf)
        check(p.returncode == 0, "init runs")
        cm = (sf / "CLAUDE.md").read_text()
        check("Warehouse: snowflake" in cm and "dbt build --select <model>" in cm and "airflow dags test" in cm,
              "CLAUDE.md: warehouse, dbt and airflow commands")
        check("Never use a prod target" in cm and len(cm.splitlines()) < 100, "CLAUDE.md: dev-only rule, under 100 lines")
        mcp = json.loads((sf / ".mcp.json").read_text())["mcpServers"]
        check(set(mcp) == {"snowflake", "dbt"} and "claude_readonly" in mcp["snowflake"]["args"], "MCP: snowflake (read-only connection) + dbt")
        yaml = (sf / ".claude/snowflake-mcp.yaml").read_text()
        check("Select: True" in yaml and "Drop: False" in yaml and "object_manager: False" in yaml, "Snowflake MCP config is read-only")
        st = json.loads((sf / ".claude/settings.json").read_text())["permissions"]
        check("Bash(dbt run --target prod:*)" in st["deny"] and "Read(./.env)" in st["deny"] and "Bash(dbt run:*)" in st["ask"],
              "settings: prod targets and .env denied, dbt run asks")
        for s in ("de-new-model", "de-debug-run", "de-document"):
            check((sf / f".claude/skills/{s}/SKILL.md").read_text().startswith(f"---\nname: {s}\n"), f"skill {s} written")
        gi = (sf / ".gitignore").read_text()
        check(".env" in gi.splitlines() and "!.env.example" in gi, ".gitignore gets .env")
        check("connections.toml" in p.stdout, "todo says where the Snowflake connection goes")

        # idempotent: second run keeps everything
        before = {q: q.read_text() for q in sf.rglob("*") if q.is_file()}
        p = run("init", sf)
        after = {q: q.read_text() for q in sf.rglob("*") if q.is_file() and q.name != "CLAUDE.de.md"}
        check(all(before.get(k) == v for k, v in after.items()), "second init changes no existing file")
        check("keep  CLAUDE.md" in p.stdout and (sf / "CLAUDE.de.md").exists(), "existing CLAUDE.md kept, suggestion written beside it")

        # after init and fixing the profile, check is clean of errors; audit agrees
        (sf / "profiles.yml").write_text("shop:\n  outputs:\n    dev:\n      type: snowflake\n      password: \"{{ env_var('SF_PW') }}\"\n")
        p = run("check", sf, "--json")
        fs = json.loads(p.stdout)["findings"]
        left = [f["msg"][:24] for f in fs if f["severity"] != "info"]
        check(p.returncode == 0 and left == ["no unique/not_null tests"],
              "check after init: only the repo's own missing key tests remain" + ("" if left == ["no unique/not_null tests"] else f" {left}"))
        a = json.loads(run("audit", sf, "--json", script=AUDIT).stdout)["findings"]
        errs = [f for f in a if f["severity"] == "error"]
        check(not errs, "agent-setup-audit finds no errors in what init wrote" + ("" if not errs else f" {errs}"))
        check(not any(f["check"] == "generic" for f in a), "generated CLAUDE.md has no generic advice")

        # merge into an existing .mcp.json and settings.json
        mg = tmp / "merge"
        mk(mg, {"dbt_project.yml": "name: x\nprofile: x\n", "requirements.txt": "dbt-bigquery\n",
                ".mcp.json": json.dumps({"mcpServers": {"github": {"command": "gh-mcp"}}}),
                ".claude/settings.json": json.dumps({"permissions": {"deny": ["Read(./secrets/**)"]}, "model": "sonnet"})})
        run("init", mg)
        mcp = json.loads((mg / ".mcp.json").read_text())["mcpServers"]
        check(set(mcp) == {"github", "bigquery", "dbt"}, "MCP merge keeps existing servers")
        check(mcp["bigquery"]["args"] == ["--prebuilt", "bigquery", "--stdio"], "BigQuery via MCP Toolbox prebuilt")
        st = json.loads((mg / ".claude/settings.json").read_text())
        check(st["model"] == "sonnet" and st["permissions"]["deny"][0] == "Read(./secrets/**)", "settings merge keeps existing keys")
        check(st["permissions"]["deny"].count("Read(./.env)") == 1, "no duplicate rules")
        run("init", mg)
        check(json.loads((mg / ".claude/settings.json").read_text())["permissions"]["deny"].count("Read(./.env)") == 1,
              "no duplicates on a second run")

        # ---- Databricks bundle
        db = tmp / "db"
        mk(db, {"databricks.yml": "bundle:\n  name: etl\n", "src/job.py": "from pyspark.sql import SparkSession\n"})
        d = json.loads(run("detect", db, "--json").stdout)
        check(d["warehouses"] == ["databricks"] and d["bundle"], "detect: databricks bundle")
        run("init", db)
        m = json.loads((db / ".mcp.json").read_text())["mcpServers"]["databricks"]
        check(m["url"] == "${DATABRICKS_HOST}/api/2.0/mcp/sql" and "${DATABRICKS_TOKEN}" in m["headers"]["Authorization"],
              "Databricks managed MCP with env-var token")
        cm = (db / "CLAUDE.md").read_text()
        check("databricks bundle validate -t dev" in cm and "dbt" not in cm.split("## Commands")[1].split("##")[0],
              "bundle commands, no dbt commands without dbt")

        # ---- SQL dialect fallback, postgres env, --warehouse override, literal MCP secret
        pg = tmp / "pg"
        mk(pg, {"sql/a.sql": "select data::jsonb from t where name ilike 'x%'\n", "sql/b.sql": "create table t (id serial)\n"})
        check(json.loads(run("detect", pg, "--json").stdout)["warehouses"] == ["postgres"], "detect: postgres from SQL dialect hints")
        run("init", pg)
        m = json.loads((pg / ".mcp.json").read_text())["mcpServers"]["postgres"]
        check(all(v.startswith("${") for v in m["env"].values()), "postgres MCP uses only ${VAR}s")
        check("POSTGRES_PASSWORD=" in (pg / ".env.example").read_text(), ".env.example lists the variable names")
        m["env"]["POSTGRES_PASSWORD"] = "s3cret"
        (pg / ".mcp.json").write_text(json.dumps({"mcpServers": {"postgres": m}}))
        check(any("literal POSTGRES_PASSWORD" in f["msg"] for f in json.loads(run("check", pg, "--json").stdout)["findings"]),
              "check: literal password in .mcp.json")
        none = tmp / "none"
        none.mkdir()
        p = run("init", none, "--dry-run")
        check("No warehouse found" in p.stdout, "init with nothing detected says to pass --warehouse")
        run("init", none, "--warehouse", "duckdb")
        check("duckdb" in json.loads((none / ".mcp.json").read_text())["mcpServers"], "--warehouse adds that server")

        check("Structure an AI Project" in run("path").stdout, "path prints the learning order")
        check(run("detect", tmp / "missing").returncode == 2, "missing folder is exit 2")

    print(f"\n{'All passed' if not failures else f'{len(failures)} failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
