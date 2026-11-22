"""Offline tests for examples/first-agent: the loop, the tools, the read-only locks, the row cap,
is_error, the step limit and the eval runner, driven by a scripted fake client. No API calls.

python3 tests/first_agent/test_first_agent.py
"""
import contextlib
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as NS

ROOT = Path(__file__).resolve().parent.parent.parent
EX = ROOT / "examples/first-agent"
sys.path.insert(0, str(EX))
import agent  # noqa: E402

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def text(t):
    return NS(type="text", text=t)


def tool(name, args, i):
    return NS(type="tool_use", name=name, input=args, id=f"tu_{i}")


class FakeClient:
    """Replays scripted replies and records every request."""
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []
        self.messages = self

    def create(self, **kw):
        self.calls.append(json.loads(json.dumps(kw, default=lambda o: vars(o))))
        content = self.replies.pop(0) if self.replies else [tool("list_schema", {}, 99)]
        stop = "tool_use" if any(b.type == "tool_use" for b in content) else "end_turn"
        return NS(content=content, stop_reason=stop)


tmp = Path(tempfile.mkdtemp())
dbp = tmp / "sales.db"
check(agent.make_sample(str(dbp)) == 288, "sample database has 288 rows")
db = agent.connect(str(dbp))

# read-only, twice over
for stmt in ("DELETE FROM sales", "CREATE TABLE x (a INT)", "UPDATE sales SET amount = 0"):
    out, err = agent.call_tool(db, "run_sql", {"query": stmt})
    check(err and "readonly" in out.lower().replace(" ", ""), f"write refused: {stmt} -> {out}")
check(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0] == 288, "nothing was written")
qo = sqlite3.connect(str(dbp))
qo.execute("PRAGMA query_only = ON")
try:
    qo.execute("DELETE FROM sales")
    check(False, "PRAGMA query_only blocks writes on its own")
except sqlite3.Error:
    check(True, "PRAGMA query_only blocks writes on its own")

# schema tool
schema, err = agent.call_tool(db, "list_schema", {})
check(not err and schema.startswith("sales(sale_id INTEGER") and "amount REAL" in schema, f"schema: {schema}")

# row cap is told to the model
out, err = agent.call_tool(db, "run_sql", {"query": "SELECT * FROM sales"})
data = json.loads(out.split("\nCUT OFF")[0])
check(not err and len(data["rows"]) == agent.MAX_ROWS and "CUT OFF" in out, "more than 50 rows: 50 shown and the cut is stated")
out, err = agent.call_tool(db, "run_sql", {"query": "SELECT region, SUM(amount) FROM sales GROUP BY 1"})
check(not err and "CUT OFF" not in out and len(json.loads(out)["rows"]) == 4, "small result: no cut-off note")

# errors are flagged
out, err = agent.call_tool(db, "run_sql", {"query": "SELECT nope FROM sales"})
check(err and "no such column" in out, f"bad SQL comes back with is_error: {out}")
check(agent.call_tool(db, "drop_table", {}) == ("Unknown tool: drop_table", True), "unknown tool is an error")
check(agent.call_tool(db, "run_sql", {})[1], "missing argument is an error, not a crash")

# the loop: schema -> bad query -> fixed query -> answer
fake = FakeClient([
    [tool("list_schema", {}, 1)],
    [text("Querying."), tool("run_sql", {"query": "SELECT regon FROM sales"}, 2)],
    [tool("run_sql", {"query": "SELECT region, SUM(amount) s FROM sales WHERE sale_date LIKE '2025%' GROUP BY 1 ORDER BY s DESC LIMIT 1"}, 3)],
    [text("West had the highest 2025 sales: 14,994.\nSQL: SELECT ...")],
])
logged = []
ans = agent.ask(fake, db, "Which region had the highest sales in 2025?", log=logged.append)
check(ans.startswith("West had the highest"), f"answer returned: {ans}")
check(len(fake.calls) == 4 and all(c["system"] == agent.SYSTEM and c["model"] == agent.MODEL for c in fake.calls),
      "every call carries the system prompt and model")
third = fake.calls[2]["messages"][-1]["content"][0]
check(third["type"] == "tool_result" and third["tool_use_id"] == "tu_2" and third["is_error"] is True and "no such column" in third["content"],
      f"the failed query went back with is_error: {third}")
fourth = fake.calls[3]["messages"][-1]["content"][0]
check(fourth["is_error"] is False and "West" in fourth["content"] and "14994" in fourth["content"], f"the fixed query's rows went back: {fourth}")
check(len(logged) == 3 and logged[1].startswith("[run_sql]") and "ERROR" in logged[1], "every tool call is logged")

# parallel tool calls in one turn both get results
fake = FakeClient([[tool("run_sql", {"query": "SELECT 1"}, 1), tool("run_sql", {"query": "SELECT 2"}, 2)], [text("done")]])
agent.ask(fake, db, "x", log=lambda *_: None)
ids = [r["tool_use_id"] for r in fake.calls[1]["messages"][-1]["content"]]
check(ids == ["tu_1", "tu_2"], f"two tool calls in one turn, two results: {ids}")

# step limit says so
fake = FakeClient([])
ans = agent.ask(fake, db, "loop forever", log=lambda *_: None)
check(len(fake.calls) == agent.MAX_STEPS and "step limit was reached" in ans, f"step limit: {len(fake.calls)} calls, {ans}")

# evals: the shipped cases' expectations hold on the sample data, and the runner scores them
cases = json.loads((EX / "evals.json").read_text())
check(len(cases) == 5, "five eval cases")
truth = {
    cases[0]["question"]: "West had the highest sales in 2025 (14,994).",
    cases[1]["question"]: "Total 2025 sales were 40,176.",
    cases[2]["question"]: "There are 288 rows.",
    cases[3]["question"]: "East grew the most, by 15.8%.",
    cases[4]["question"]: "Gizmo sold the most in 2024.",
}
import re  # noqa: E402
check(all(re.search(c["expect"], truth[c["question"]], re.I) for c in cases), "each expectation matches a correct answer")
check(not re.search(cases[0]["expect"], "East had the highest sales in 2025.", re.I), "a wrong answer fails")
west = db.execute("SELECT region FROM sales WHERE sale_date LIKE '2025%' GROUP BY 1 ORDER BY SUM(amount) DESC LIMIT 1").fetchone()[0]
tot = db.execute("SELECT SUM(amount) FROM sales WHERE sale_date LIKE '2025%'").fetchone()[0]
check(west == "West" and tot == 40176, "the expected answers are what the sample data says")


class AnswerClient(FakeClient):
    def __init__(self, answers):
        super().__init__([])
        self.answers = list(answers)

    def create(self, **kw):
        self.calls.append(kw)
        return NS(content=[text(self.answers.pop(0))], stop_reason="end_turn")


buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    res = agent.run_evals(AnswerClient([truth[c["question"]] for c in cases[:4]] + ["Widget"]), db, EX / "evals.json")
check(res == (4, 5) and "4/5 passed" in buf.getvalue(), f"eval runner scores 4/5: {res}")

# CLI without a question is an error; --make-sample needs no API key
with contextlib.redirect_stdout(io.StringIO()):
    check(agent.main(["--make-sample", str(tmp / "b.db")]) == 0 and (tmp / "b.db").exists(), "--make-sample works offline")
try:
    with contextlib.redirect_stderr(io.StringIO()):
        agent.main([])
    check(False, "no question is a usage error")
except SystemExit as e:
    check(e.code == 2, "no question is a usage error")

print("OK" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
