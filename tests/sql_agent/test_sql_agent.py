"""Offline tests for examples/sql-review-agent: the sqlglot rules, the read-only guard and the
lint tool's path check. No model calls, no network.

python3 tests/sql_agent/test_sql_agent.py   (needs: pip install sqlglot claude-agent-sdk)
"""
import asyncio
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
AGENT = ROOT / "examples/sql-review-agent"
sys.path.insert(0, str(AGENT))
from checks import check_sql  # noqa: E402

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def rules(sql):
    return sorted({f["rule"] for f in check_sql(sql)})


sample = (AGENT / "sample/daily_refiner.sql").read_text()
found = {(f["line"], f["rule"]) for f in check_sql(sample)}
check({(2, "select-star"), (2, "join-no-on"), (2, "fn-on-filter-column"), (2, "not-in-subquery"),
       (8, "order-in-subquery"), (8, "union-distinct"), (17, "no-where")} <= found, "sample: all seeded problems found with lines")
check(check_sql((AGENT / "sample/clean_model.sql").read_text()) == [], "clean model: no findings")
check(rules((AGENT / "sample/broken.sql").read_text()) == ["parse"], "broken SQL: parse error, no crash")
check(rules("update t set a = 1") == ["no-where"], "UPDATE without WHERE")
check(rules("select a from t where name = upper('x')") == [], "function on the literal side is fine")
check(rules("select a from t, lateral flatten(input => t.v) f") == [], "LATERAL FLATTEN is not a missing join condition")
check(rules("select a from t cross join u") == [], "explicit CROSS JOIN is intentional")

try:
    import agent  # noqa: E402
except ImportError as e:
    print(f"SKIP agent tests ({e})")
else:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp).resolve()
        (root / "a.sql").write_text("delete from t;")
        (root / "notes.txt").write_text("x")
        guard = agent.make_guard(root)
        run = lambda name, ti: asyncio.run(guard({"tool_name": name, "tool_input": ti}, "id", None))
        denied = lambda r: r.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
        check(denied(run("Write", {"file_path": "x.sql", "content": "x"})), "guard denies Write")
        check(denied(run("Bash", {"command": "ls"})), "guard denies Bash")
        check(denied(run("Read", {"file_path": "/etc/passwd"})), "guard denies reads outside the folder")
        check(denied(run("Read", {"file_path": "../../etc/passwd"})), "guard denies ../ escapes")
        check(run("Read", {"file_path": "a.sql"}) == {}, "guard allows reading inside the folder")
        check(run("Glob", {"pattern": "**/*.sql"}) == {}, "guard allows Glob")
        lint = agent.make_lint_tool(root).handler
        ok = asyncio.run(lint({"path": "a.sql"}))
        check(json.loads(ok["content"][0]["text"])["findings"][0]["rule"] == "no-where", "lint tool returns findings")
        check(asyncio.run(lint({"path": "../x.sql"})).get("is_error") is True, "lint tool refuses paths outside the folder")
        check(asyncio.run(lint({"path": "notes.txt"})).get("is_error") is True, "lint tool refuses non-.sql files")

print(f"\n{len(fails)} failure(s)")
sys.exit(1 if fails else 0)
