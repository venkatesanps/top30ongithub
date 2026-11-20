#!/usr/bin/env python3
"""Set up a data engineering repo for Claude Code, for any warehouse.

  de_setup.py detect [DIR] [--json]       what stack this repo uses (warehouse, dbt, orchestrator, commands)
  de_setup.py init   [DIR] [--warehouse W] [--dry-run] [--force]
                                          write CLAUDE.md, read-only MCP config, deny rules, project skills
  de_setup.py check  [DIR] [--json]       secrets in profiles/MCP, .env not ignored, prod rules, model docs/tests
  de_setup.py path                        a learning order for Claude Code in data engineering

Standard library only. Never connects to a database, never reads ~/.dbt or ~/.snowflake.
init never overwrites a file without --force; JSON files are merged, not replaced.
"""
import argparse
import json
import re
import sys
from pathlib import Path

WAREHOUSES = ["snowflake", "bigquery", "databricks", "postgres", "redshift", "duckdb"]
SKIP = {".git", "node_modules", ".venv", "venv", "target", "dbt_packages", "logs", "__pycache__", ".tox"}

# what in a repo points at a warehouse: (regex, file glob kind)
DEP_HINTS = {
    "snowflake": r"snowflake-connector-python|snowflake-snowpark|dbt-snowflake|snowflake-sqlalchemy|apache-airflow-providers-snowflake",
    "bigquery": r"google-cloud-bigquery|dbt-bigquery|pandas-gbq|apache-airflow-providers-google",
    "databricks": r"databricks-sql-connector|databricks-sdk|dbt-databricks|databricks-connect|pyspark",
    "postgres": r"psycopg2?|psycopg\[|asyncpg|dbt-postgres|apache-airflow-providers-postgres",
    "redshift": r"redshift-connector|dbt-redshift|apache-airflow-providers-amazon",
    "duckdb": r"\bduckdb\b|dbt-duckdb",
}
SQL_HINTS = {  # dialect fingerprints in .sql files; weak, so they only count when nothing stronger is found
    "snowflake": r"\bqualify\b|\bflatten\s*\(|\bvariant\b|\biff\s*\(|::(variant|number|varchar)",
    "bigquery": r"`[\w-]+\.[\w-]+\.[\w-]+`|\bsafe_cast\b|\bunnest\s*\(|\bstruct<|\bdate_trunc\([^,]+,\s*(day|month|week)\)",
    "databricks": r"\bdelta\.`|\busing delta\b|\boptimize\s+\w+\s+zorder|\bcatalog\.\w+\.\w+",
    "postgres": r"\bserial\b|\bjsonb\b|::(int|text|jsonb)\b|\bilike\b",
}

MCP = {
    "snowflake": {"command": "uvx", "args": ["snowflake-labs-mcp", "--service-config-file", ".claude/snowflake-mcp.yaml",
                                             "--connection-name", "claude_readonly"]},
    "bigquery": {"command": "toolbox", "args": ["--prebuilt", "bigquery", "--stdio"],
                 "env": {"BIGQUERY_PROJECT": "${BIGQUERY_PROJECT}"}},
    "databricks": {"type": "http", "url": "${DATABRICKS_HOST}/api/2.0/mcp/sql",
                   "headers": {"Authorization": "Bearer ${DATABRICKS_TOKEN}"}},
    "postgres": {"command": "toolbox", "args": ["--prebuilt", "postgres", "--stdio"],
                 "env": {"POSTGRES_HOST": "${POSTGRES_HOST}", "POSTGRES_PORT": "${POSTGRES_PORT:-5432}",
                         "POSTGRES_DATABASE": "${POSTGRES_DATABASE}", "POSTGRES_USER": "${POSTGRES_USER}",
                         "POSTGRES_PASSWORD": "${POSTGRES_PASSWORD}"}},
    "redshift": {"command": "toolbox", "args": ["--prebuilt", "postgres", "--stdio"],
                 "env": {"POSTGRES_HOST": "${REDSHIFT_HOST}", "POSTGRES_PORT": "${REDSHIFT_PORT:-5439}",
                         "POSTGRES_DATABASE": "${REDSHIFT_DATABASE}", "POSTGRES_USER": "${REDSHIFT_USER}",
                         "POSTGRES_PASSWORD": "${REDSHIFT_PASSWORD}"}},
    "duckdb": {"command": "toolbox", "args": ["--prebuilt", "duckdb", "--stdio"],
               "env": {"DUCKDB_DATABASE": "${DUCKDB_DATABASE:-dev.duckdb}"}},
}
DBT_MCP = {"command": "uvx", "args": ["dbt-mcp"],
           "env": {"DBT_PROJECT_DIR": "${DBT_PROJECT_DIR:-.}", "DBT_PATH": "${DBT_PATH:-dbt}", "DISABLE_DBT_CLI": "false"}}
ENV_VARS = {
    "snowflake": ["# Snowflake: the MCP server reads the [claude_readonly] connection from ~/.snowflake/connections.toml"],
    "bigquery": ["BIGQUERY_PROJECT=", "# auth: gcloud auth application-default login (as a read-only principal)"],
    "databricks": ["DATABRICKS_HOST=https://<workspace>.cloud.databricks.com", "DATABRICKS_TOKEN="],
    "postgres": ["POSTGRES_HOST=", "POSTGRES_PORT=5432", "POSTGRES_DATABASE=", "POSTGRES_USER=", "POSTGRES_PASSWORD="],
    "redshift": ["REDSHIFT_HOST=", "REDSHIFT_PORT=5439", "REDSHIFT_DATABASE=", "REDSHIFT_USER=", "REDSHIFT_PASSWORD="],
    "duckdb": ["DUCKDB_DATABASE=dev.duckdb"],
}
SNOWFLAKE_MCP_YAML = """# Read-only service config for Snowflake-Labs/mcp (snowflake-labs-mcp).
# Key names follow the server's example config; check them against the version you install.
other_services:
  object_manager: False      # no CREATE/DROP through the agent
  query_manager: True        # run SQL, limited by the permissions below
  semantic_manager: False
sql_statement_permissions:
  - Select: True
  - Describe: True
  - Show: True
  - Use: True
  - Command: False
  - Insert: False
  - Update: False
  - Delete: False
  - Merge: False
  - Create: False
  - Drop: False
  - Alter: False
  - TruncateTable: False
  - Unknown: False
"""
DENY = ["Read(./.env)", "Read(./.env.*)", "Read(~/.dbt/profiles.yml)", "Read(~/.snowflake/**)", "Read(~/.databrickscfg)",
        "Read(~/.config/gcloud/**)",
        "Bash(dbt run --target prod:*)", "Bash(dbt build --target prod:*)", "Bash(dbt run -t prod:*)",
        "Bash(dbt build -t prod:*)", "Bash(dbt seed --target prod:*)", "Bash(dbt snapshot --target prod:*)",
        "Bash(databricks bundle deploy -t prod:*)", "Bash(databricks bundle run -t prod:*)",
        "Bash(bq rm:*)", "Bash(git push --force:*)"]
ASK = ["Bash(dbt run:*)", "Bash(dbt seed:*)", "Bash(dbt snapshot:*)", "Bash(airflow dags trigger:*)",
       "Bash(databricks bundle deploy:*)", "Bash(bq query:*)", "Bash(snow sql:*)", "Bash(psql:*)"]


def files(root, *globs):
    for g in globs:
        for p in root.rglob(g):
            if not any(part in SKIP for part in p.relative_to(root).parts[:-1]) and p.is_file():
                yield p


def read(p, limit=400_000):
    try:
        return p.read_text(errors="replace")[:limit]
    except OSError:
        return ""


def detect(root):
    d = {"warehouses": [], "evidence": {}, "dbt": None, "orchestrator": None, "bundle": False, "pytest": False,
         "sqlfluff": False, "name": root.resolve().name}

    def hit(w, why):
        if w not in d["warehouses"]:
            d["warehouses"].append(w)
        d["evidence"].setdefault(w, []).append(why)

    dbt = next(iter(sorted(files(root, "dbt_project.yml"), key=lambda p: len(p.parts))), None)
    if dbt:
        txt = read(dbt)
        m = re.search(r"^name:\s*['\"]?([\w-]+)", txt, re.M)
        prof = re.search(r"^profile:\s*['\"]?([\w-]+)", txt, re.M)
        mp = re.search(r"^model-paths:\s*\[\s*['\"]?([\w/-]+)", txt, re.M)
        d["dbt"] = {"dir": str(dbt.parent.relative_to(root)) or ".", "name": m.group(1) if m else None,
                    "profile": prof.group(1) if prof else None, "model_dir": mp.group(1) if mp else "models"}
        for p in files(root, "profiles.yml"):
            for t in re.findall(r"^\s*type:\s*['\"]?(\w+)", read(p), re.M):
                if t in WAREHOUSES:
                    hit(t, f"{p.relative_to(root)}: type {t}")
    for p in files(root, "requirements*.txt", "pyproject.toml", "Pipfile", "setup.cfg", "environment.yml", "packages.yml"):
        txt = read(p).lower()
        for w, rx in DEP_HINTS.items():
            if re.search(rx, txt):
                hit(w, f"{p.relative_to(root)} depends on it")
    if any(files(root, "databricks.yml")):
        d["bundle"] = True
        hit("databricks", "databricks.yml (asset bundle)")
    for p in files(root, "*.py"):
        txt = read(p, 60_000)
        if re.search(r"^\s*(from|import) airflow\b", txt, re.M):
            d["orchestrator"] = "airflow"
            break
        if re.search(r"^\s*(from|import) dagster\b", txt, re.M):
            d["orchestrator"] = "dagster"
            break
        if re.search(r"^\s*(from|import) prefect\b", txt, re.M):
            d["orchestrator"] = "prefect"
            break
    if not d["warehouses"]:
        score = {}
        for p in list(files(root, "*.sql"))[:300]:
            txt = read(p, 50_000).lower()
            for w, rx in SQL_HINTS.items():
                score[w] = score.get(w, 0) + len(re.findall(rx, txt))
        best = max(score.items(), key=lambda kv: kv[1], default=(None, 0))
        if best[1] >= 2:
            hit(best[0], f"SQL dialect hints in .sql files ({best[1]})")
    d["pytest"] = (root / "tests").is_dir() or "pytest" in read(root / "pyproject.toml").lower()
    d["sqlfluff"] = (root / ".sqlfluff").exists() or "sqlfluff" in read(root / "pyproject.toml").lower()
    return d


def commands(d, w):
    cmd = []
    if d["dbt"]:
        sel = "" if d["dbt"]["dir"] == "." else f" --project-dir {d['dbt']['dir']}"
        cmd += [f"- Build one model and its tests: `dbt build --select <model>{sel}`",
                f"- Build a model and everything downstream: `dbt build --select <model>+{sel}`",
                f"- Compile only (see the SQL, run nothing): `dbt compile --select <model>{sel}`",
                f"- Test: `dbt test --select <model>{sel}`"]
    if d["sqlfluff"]:
        cmd.append(f"- Lint SQL: `sqlfluff lint <path> --dialect {'sparksql' if w == 'databricks' else w or 'ansi'}`")
    if d["orchestrator"] == "airflow":
        cmd += ["- Parse DAGs: `python -c \"from airflow.models import DagBag; print(DagBag(include_examples=False).import_errors)\"`",
                "- Run one DAG locally without the scheduler: `airflow dags test <dag_id> <yyyy-mm-dd>`"]
    if d["orchestrator"] == "dagster":
        cmd.append("- Check definitions load: `dagster definitions validate`")
    if d["bundle"]:
        cmd += ["- Validate the bundle: `databricks bundle validate -t dev`",
                "- Run a job in dev: `databricks bundle run <job> -t dev`"]
    if d["pytest"]:
        cmd.append("- Python tests: `pytest -q`")
    if not cmd:
        cmd.append("- Test: <the command that proves a change works - fill this in>")
    return cmd


def claude_md(d, w):
    wh = ", ".join(d["warehouses"]) or "unknown - fill in"
    parts = [f"# {d['name']} - data project", "",
             f"Warehouse: {wh}." + (f" Transform: dbt (`{d['dbt']['dir']}`, profile `{d['dbt']['profile']}`)." if d["dbt"] else "")
             + (f" Orchestrator: {d['orchestrator']}." if d["orchestrator"] else "")
             + (" Deploys with Databricks asset bundles." if d["bundle"] else ""), "",
             "## Commands", *commands(d, w), "",
             "## Environments",
             "- Work against dev only (dbt target `dev`, bundle target `dev`). Never use a prod target; a person deploys.",
             "- The database MCP connection uses a read-only role. Ask before any DDL or DML, even in dev.",
             "- Query with a LIMIT, or count first, before pulling rows into the conversation.", ""]
    if d["dbt"]:
        md = d["dbt"]["model_dir"]
        parts += ["## dbt conventions (edit to match this repo)",
                  f"- Layers: `{md}/staging` (`stg_<source>__<table>`, one per source table, rename and cast only) ->",
                  f"  `{md}/intermediate` (`int_`) -> `{md}/marts` (`fct_`, `dim_`).",
                  "- Reference with `ref()` and `source()`; no hard-coded database or schema names.",
                  "- Every model has an entry in a .yml with a description and `unique` + `not_null` on its key.",
                  "- Incremental models state `unique_key` and how late-arriving rows are handled.", ""]
    parts += ["## Before saying done",
              "- The build/test command above passes for the changed models and their children.",
              "- For a changed model, compare row counts and key uniqueness before and after (via MCP, in dev) and report them.",
              "- New columns are documented in the model's .yml." if d["dbt"] else "- The pipeline ran end to end in dev.", "",
              "## Project skills",
              "- `/de-new-model`, `/de-debug-run`, `/de-document` in `.claude/skills/`."]
    return "\n".join(parts) + "\n"


SKILLS = {
    "de-new-model": """---
name: de-new-model
description: Add a new model or table to this data project - find the sources, write staging then the mart, add yml docs and key tests, build it in dev and report row counts. Use when asked to add a model, table, mart, fact or dimension.
---

1. Find the source tables (MCP: list and describe them; `LIMIT 20` samples). Write down the grain:
   one row per what?
2. If the source has no staging model, add one: rename, cast, nothing else.
3. Write the model with `ref()`/`source()` only. State the grain in a comment at the top.
4. Add it to a .yml: description, column descriptions, `unique` + `not_null` on the key,
   `relationships` to the dimensions it joins.
5. Run the build command from CLAUDE.md for the model and its children. Fix until it passes.
6. In dev, query: total rows, distinct keys (must equal rows), null rate of each join key.
   Report the numbers, not "looks good".
""",
    "de-debug-run": """---
name: de-debug-run
description: Find why a pipeline, DAG, job or dbt run failed - first real error, what changed, root cause, smallest safe fix, whether a re-run is safe. Use when a run failed, a test failed, or data looks wrong.
---

1. Get the first error, not the last: dbt `target/run_results.json` and `logs/dbt.log`, the
   Airflow task log, the Databricks job run output. Quote it.
2. What changed: `git log -p --since=<last good run> -- <paths>`, upstream source freshness,
   schema changes on the source table (MCP: describe it now vs. what the model expects).
3. Reproduce in dev with the smallest command (one model, one task).
4. Fix the cause, not the symptom. Don't widen a test, cast away an error or add
   `on_schema_change: ignore` without saying so.
5. Say whether re-running is safe (idempotent? incremental with a unique_key? appends?) and
   which test would have caught it - then add that test.
""",
    "de-document": """---
name: de-document
description: Write or update dbt yml documentation for models - descriptions from the SQL and real column profiles, tests for keys and accepted values. Use when asked to document models, add descriptions, or when models have no yml entry.
---

1. Read the model SQL and say what one row is.
2. Profile the columns in dev via MCP (count, distinct, nulls, min/max, top 5 values) with one
   aggregate query - no row dumps.
3. Write the yml: model description (grain, source, refresh), every column described in words
   a business user understands, `unique`/`not_null` on the key, `accepted_values` where the
   profile shows a small fixed set, `relationships` for foreign keys.
4. Don't invent meaning. If a column's purpose isn't clear from SQL and data, write
   `TODO: confirm with owner` instead.
5. Run `dbt test --select <model>` and report what passed.
""",
}


def merge_json(path, update, dry, out):
    cur = {}
    if path.exists():
        try:
            cur = json.loads(path.read_text() or "{}")
        except json.JSONDecodeError:
            out.append(f"skip  {path.name}: not valid JSON, fix it by hand")
            return
    new = update(json.loads(json.dumps(cur)))
    if new == cur:
        out.append(f"same  {path}")
        return
    out.append(f"{'merge' if cur else 'write'} {path}")
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(new, indent=2) + "\n")


def write(path, text, dry, force, out, root):
    rel = path.relative_to(root)
    if path.exists() and not force:
        out.append(f"keep  {rel} (exists; --force to replace)")
        return False
    out.append(f"write {rel}")
    if not dry:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return True


def init(root, warehouse, dry, force):
    d = detect(root)
    whs = [warehouse] if warehouse else d["warehouses"]
    if warehouse and warehouse not in d["warehouses"]:
        d["warehouses"].insert(0, warehouse)
    w = whs[0] if whs else None
    out = []
    cm = root / "CLAUDE.md"
    if not write(cm, claude_md(d, w), dry, force, out, root):
        write(root / "CLAUDE.de.md", claude_md(d, w), dry, True, out, root)
        out.append("      -> CLAUDE.de.md is a suggestion; copy what you want into CLAUDE.md")

    def mcp(cur):
        servers = cur.setdefault("mcpServers", {})
        for x in whs:
            servers.setdefault(x, MCP[x])
        if d["dbt"]:
            servers.setdefault("dbt", DBT_MCP)
        return cur
    if whs or d["dbt"]:
        merge_json(root / ".mcp.json", mcp, dry, out)
    if "snowflake" in whs:
        write(root / ".claude" / "snowflake-mcp.yaml", SNOWFLAKE_MCP_YAML, dry, force, out, root)

    def settings(cur):
        perm = cur.setdefault("permissions", {})
        for key, rules in (("deny", DENY), ("ask", ASK)):
            lst = perm.setdefault(key, [])
            lst += [r for r in rules if r not in lst]
        return cur
    merge_json(root / ".claude" / "settings.json", settings, dry, out)
    for name, body in SKILLS.items():
        write(root / ".claude" / "skills" / name / "SKILL.md", body, dry, force, out, root)
    env = ["# Names only. Put values in your shell or a direnv .envrc - Claude Code expands ${VAR} in .mcp.json",
           "# from the environment it starts in, not from this file."]
    for x in whs:
        env += ENV_VARS[x]
    if d["dbt"]:
        env += ["DBT_PROJECT_DIR=" + d["dbt"]["dir"], "DBT_PATH=dbt"]
    write(root / ".env.example", "\n".join(env) + "\n", dry, force, out, root)
    gi = root / ".gitignore"
    have = read(gi).splitlines()
    add = [x for x in (".env", ".env.*", "!.env.example", ".claude/settings.local.json") if x not in have]
    if add:
        out.append(f"{'append' if have else 'write'} .gitignore: {' '.join(add)}")
        if not dry:
            gi.write_text("\n".join(have + add) + "\n")
    todo = ["Create a read-only role or service account for the MCP connection (SELECT on dev/analytics schemas only).",
            "Pin the MCP server versions in .mcp.json (pkg@1.2.3) once they work.",
            "Edit the conventions in CLAUDE.md to match how this repo really does it, then cut what's not true."]
    if "snowflake" in whs:
        todo.insert(0, "Add a [claude_readonly] connection to ~/.snowflake/connections.toml (key-pair auth, read-only role).")
    if "databricks" in whs:
        todo.insert(0, "Check the Databricks managed MCP URL for your workspace (SQL is /api/2.0/mcp/sql) and use an OAuth or "
                       "short-lived token for a principal with read-only grants.")
    if any(x in whs for x in ("bigquery", "postgres", "redshift", "duckdb")):
        todo.insert(0, "Install Google's MCP Toolbox for Databases (`toolbox` binary) - it serves the prebuilt "
                       "bigquery/postgres/duckdb tools in .mcp.json.")
    if not whs:
        todo.insert(0, "No warehouse found: rerun with --warehouse snowflake|bigquery|databricks|postgres|redshift|duckdb.")
    return d, out, todo


def check(root):
    fs = []

    def add(sev, msg, f=""):
        fs.append({"severity": sev, "file": f, "msg": msg})

    d = detect(root)
    for p in files(root, "profiles.yml"):
        for i, line in enumerate(read(p).splitlines(), 1):
            m = re.match(r"\s*(password|token|private_key|private_key_passphrase|keyfile_json|client_secret)\s*:\s*(.+)", line)
            if m and "env_var(" not in m.group(2) and m.group(2).strip() not in ('""', "''", "~", "null"):
                add("error", f"literal {m.group(1)} in a committed profiles.yml: use \"{{{{ env_var('X') }}}}\"",
                    f"{p.relative_to(root)}:{i}")
    mcp = root / ".mcp.json"
    servers = {}
    if mcp.exists():
        try:
            servers = json.loads(read(mcp) or "{}").get("mcpServers", {})
        except (json.JSONDecodeError, AttributeError):
            add("error", "not valid JSON", ".mcp.json")
        for name, s in servers.items():
            for k, v in list((s.get("env") or {}).items()) + list((s.get("headers") or {}).items()):
                if re.search(r"key|token|secret|password|authorization", k, re.I) and v and "${" not in str(v):
                    add("error", f"server '{name}' has a literal {k}; use ${{VAR}}", ".mcp.json")
    for w in d["warehouses"]:
        if not any(w in n.lower() or w in json.dumps(s).lower() for n, s in servers.items()):
            add("info", f"{w} found ({d['evidence'][w][0]}) but no MCP server for it: Claude can't look at the data. "
                "`init` adds a read-only one")
    ign = read(root / ".gitignore").splitlines()
    if (root / ".env").exists() and not any(x.strip() in (".env", ".env*", ".env.*", "*.env") for x in ign):
        add("error", ".env exists and isn't in .gitignore", ".env")
    cm = next((root / n for n in ("CLAUDE.md", "AGENTS.md") if (root / n).exists()), None)
    if not cm:
        add("warn", "no CLAUDE.md: Claude doesn't know the warehouse, the commands or that prod is off limits")
    else:
        low = read(cm).lower()
        if d["warehouses"] and not any(w in low for w in d["warehouses"]):
            add("warn", "CLAUDE.md doesn't name the warehouse (so the SQL dialect is a guess)", cm.name)
        if d["dbt"] and "dbt build" not in low and "dbt test" not in low:
            add("warn", "CLAUDE.md doesn't say how to build or test a model", cm.name)
        if "prod" not in low:
            add("warn", "CLAUDE.md doesn't say prod is off limits", cm.name)
    st = read(root / ".claude" / "settings.json")
    if "prod" not in st:
        add("warn", "no permission rule blocks prod targets (e.g. deny Bash(dbt run --target prod:*))",
            ".claude/settings.json")
    if d["dbt"]:
        mdir = root / d["dbt"]["dir"] / d["dbt"]["model_dir"]
        models = {p.stem for p in mdir.rglob("*.sql")} if mdir.is_dir() else set()
        ymltxt = "\n".join(read(p) for p in (mdir.rglob("*.yml") if mdir.is_dir() else []))
        documented = set(re.findall(r"^\s*-\s*name:\s*['\"]?(\w+)", ymltxt, re.M))
        undoc = sorted(models - documented)
        if undoc:
            add("info", f"{len(undoc)} of {len(models)} models have no yml entry: {', '.join(undoc[:8])}"
                + (" ..." if len(undoc) > 8 else "") + " - /de-document", d["dbt"]["model_dir"])
        if models and not re.search(r"\b(unique|not_null|dbt_utils\.unique_combination_of_columns)\b", ymltxt):
            add("warn", "no unique/not_null tests on any model: a broken join can double rows without anything failing",
                d["dbt"]["model_dir"])
        if not d["sqlfluff"]:
            add("info", "no .sqlfluff: a SQL linter gives Claude a fast check besides dbt build")
    return d, fs


PATH = """Learning order for Claude Code in data engineering
(after AiswaryaVenkit's list of ten videos; titles from the post - the videos weren't watched here)

1. Basics and project context  - videos 1 "Claude Code: 5 Essentials", 2 "The AI Workflow", 7 "Structure an AI Project"
   do:  de_setup.py init      -> CLAUDE.md with commands, dev-only rule, conventions
        /agent-setup-audit (top30-agents) to check the result
2. Teach it your conventions    - video 3 "Teaching Claude Code the Art of Data Engineering"
   do:  edit CLAUDE.md conventions; .claude/skills/de-new-model, de-debug-run, de-document
3. Let it see the data          - videos 8 "Claude Desktop + BigQuery", 9 "Connect Claude AI to a Database",
                                  10 "Claude Code and MCP Server"
   do:  read-only role + the .mcp.json init wrote; then the warehouse-explorer agent maps the schemas
4. Build pipelines              - videos 5 "Build an End-to-End Data Pipeline", 6 "From Claude to Pipelines"
   do:  /de-new-model; snowflake-de-team for researcher -> drafter -> critic -> refiner
5. Your platform                - video 4 "Databricks Vibe Coding" (Databricks), or for Snowflake:
                                  snowflake-query-advisor, snowflake-cost-investigator, oracle-to-snowflake
6. When it breaks               - /de-debug-run, pipeline-failure-triage agent, session-doctor (top30-agents)
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for c in ("detect", "init", "check"):
        p = sub.add_parser(c)
        p.add_argument("dir", nargs="?", default=".")
        p.add_argument("--json", action="store_true")
        if c == "init":
            p.add_argument("--warehouse", choices=WAREHOUSES)
            p.add_argument("--dry-run", action="store_true")
            p.add_argument("--force", action="store_true")
    sub.add_parser("path")
    a = ap.parse_args()
    if a.cmd == "path":
        print(PATH)
        return 0
    root = Path(a.dir)
    if not root.is_dir():
        print(f"not a folder: {root}", file=sys.stderr)
        return 2
    if a.cmd == "detect":
        d = detect(root)
        if a.json:
            print(json.dumps(d, indent=2))
        else:
            print(f"warehouse:    {', '.join(d['warehouses']) or 'none found'}")
            for w, ev in d["evidence"].items():
                print(f"  {w}: {'; '.join(ev[:3])}")
            print(f"dbt:          {d['dbt']['dir'] + ' (profile ' + str(d['dbt']['profile']) + ')' if d['dbt'] else 'no'}")
            print(f"orchestrator: {d['orchestrator'] or 'none found'}")
            print(f"bundle:       {'yes' if d['bundle'] else 'no'}   pytest: {'yes' if d['pytest'] else 'no'}"
                  f"   sqlfluff: {'yes' if d['sqlfluff'] else 'no'}")
            print("commands:\n  " + "\n  ".join(commands(d, (d["warehouses"] or [None])[0])))
        return 0
    if a.cmd == "init":
        d, out, todo = init(root, a.warehouse, a.dry_run, a.force)
        if a.json:
            print(json.dumps({"detected": d, "actions": out, "todo": todo}, indent=2))
        else:
            print(("DRY RUN - nothing written\n" if a.dry_run else "") + "\n".join(out))
            print("\nStill for you to do:\n" + "\n".join(f"  - {t}" for t in todo))
        return 0
    d, fs = check(root)
    if a.json:
        print(json.dumps({"detected": d, "findings": fs}, indent=2))
    else:
        for f in sorted(fs, key=lambda f: ["error", "warn", "info"].index(f["severity"])):
            print(f"{f['severity'].upper():5} {f['file'] + ': ' if f['file'] else ''}{f['msg']}")
        print(f"\n{sum(f['severity'] == 'error' for f in fs)} error(s), {sum(f['severity'] == 'warn' for f in fs)} warning(s)")
    return 1 if any(f["severity"] == "error" for f in fs) else 0


if __name__ == "__main__":
    sys.exit(main())
