"""Tests for goal_lint.py and the goal_gate.py Stop hook (simulated hook input, throwaway folders).

python3 tests/goal_tools/test_goal_tools.py   (no dependencies, no network, no Claude account)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
LINT = ROOT / "plugins/top30-agents/skills/goal-writer/scripts/goal_lint.py"
GATE = ROOT / "plugins/top30-agents/hooks/goal_gate.py"


def lint(cond, *extra):
    r = subprocess.run([sys.executable, "-I", str(LINT), cond, "--json", *extra], capture_output=True, text=True, timeout=30)
    return r, json.loads(r.stdout) if r.stdout.strip().startswith("{") else {}


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    # ---------- goal_lint ----------
    r, d = lint("make the pipeline better and production ready")
    rules = {f["rule"] for f in d["findings"]}
    check({"no-check", "not-measurable", "vague", "no-bound"} <= rules and d["score"] < 30, "vague goal: no check, not measurable, vague, unbounded")
    check("make" not in str([f for f in d["findings"] if f["rule"] == "no-check"]) and d["suggestion"].startswith("<one measurable end state"),
          "'make the' isn't mistaken for a make target; suggestion asks for an end state")
    r, d = lint("all tests in test/auth pass and the lint step is clean")
    sev = {f["rule"]: f["severity"] for f in d["findings"]}
    check(sev.get("no-check") == "warn" and "vague" not in sev, "docs example: implied check is a warning; 'is clean' isn't vague")
    r, d = lint("`pytest -q` exits 0. Do not delete or skip tests. Or stop after 20 turns.")
    check(d["score"] == 100 and d["suggestion"] is None, "a stated check, constraint and bound scores 100")
    r, d = lint("keep going until you're confident the refactor is done")
    check(any(f["rule"] == "self-judged" and f["severity"] == "error" for f in d["findings"]), "self-judged completion is an error")
    r, d = lint("`dbt build` exits 0, then deploy to production and backfill fct_orders. Or stop after 10 turns. Do not edit tests.")
    check(any(f["rule"] == "irreversible" for f in d["findings"]), "deploy/backfill inside a goal flagged as irreversible")
    r, d = lint("x " * 2100)
    check(any(f["rule"] == "too-long" for f in d["findings"]), "over 4,000 characters is an error")
    r, _ = lint("make it nicer", "--fail-on", "error")
    check(r.returncode == 1, "--fail-on error exits 1")
    rec = subprocess.run([sys.executable, "-I", str(LINT), "--recipes"], capture_output=True, text=True).stdout
    names = [ln.split()[0] for ln in rec.splitlines() if ln and not ln.startswith(" ")]
    check(len(names) >= 6 and "dbt" in names and "reconcile" in names, "recipes listed")
    for n in names:
        body = subprocess.run([sys.executable, "-I", str(LINT), "--recipes", n], capture_output=True, text=True).stdout.strip()
        _, d = lint(body.removeprefix("/goal "))
        check(d["score"] == 100, f"recipe {n} passes its own linter")

    # ---------- goal_gate ----------
    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        proj = tmp / "proj"
        (proj / "sub").mkdir(parents=True)
        flag = proj / "fixed"
        env = dict(os.environ, GOAL_GATE_HOME=str(tmp / "gatehome"))
        env.pop("CLAUDE_PROJECT_DIR", None)

        def cli(*args, cwd=proj):
            return subprocess.run([sys.executable, "-I", str(GATE), *args], capture_output=True, text=True, timeout=60, cwd=cwd, env=env)

        def stop(session="s1", cwd=None, **extra):
            payload = {"hook_event_name": "Stop", "session_id": session, "cwd": str(cwd or proj), "stop_hook_active": False, **extra}
            r = subprocess.run([sys.executable, "-I", str(GATE), "hook"], input=json.dumps(payload), capture_output=True,
                               text=True, timeout=60, env=env)
            return r, (json.loads(r.stdout) if r.stdout.strip() else {})

        r, out = stop()
        check(r.returncode == 0 and out == {}, "not switched on: the hook says nothing and never blocks")

        # check: fails with a changing message until a file exists
        chk = f"{sys.executable} -c \"import pathlib,sys,random; p=pathlib.Path('fixed'); print('FAIL', random.random()) if not p.exists() else None; sys.exit(0 if p.exists() else 1)\""
        r = cli("on", "--check", chk, "--max-rounds", "3")
        check(r.returncode == 0 and "goal gate ON" in r.stdout, "on: saves the gate")
        check(not list(proj.rglob("*.json")), "nothing is written inside the repo (a clone can't plant a gate)")
        r, out = stop(cwd=proj / "sub")
        check(out.get("decision") == "block" and "round 1 of 3" in out.get("reason", "") and "FAIL" in out["reason"],
              "failing check blocks the stop, with the failing output (found from a subfolder)")
        check("Don't weaken, skip or delete checks" in out["reason"], "block reason tells Claude not to weaken the check")
        r, out = stop()
        check(out.get("decision") == "block" and "round 2 of 3" in out["reason"], "second stop: round 2")
        st = cli("status").stdout
        check("ON" in st and "round 2" in st, "status shows the session's round")
        r, out = stop(session="s2")
        check("round 1 of 3" in out.get("reason", ""), "rounds are counted per session")
        flag.write_text("ok")
        r, out = stop()
        check("decision" not in out and "passed" in out.get("systemMessage", ""), "passing check lets Claude stop and says so")
        r, out = stop()
        check("passed" in out.get("systemMessage", ""), "and the session's round count was reset")

        # limit reached
        flag.unlink()
        cli("on", "--check", chk, "--max-rounds", "2")
        outs = [stop(session="lim")[1] for _ in range(3)]
        check([o.get("decision") for o in outs] == ["block", "block", None] and "after 2 rounds" in outs[2].get("systemMessage", ""),
              "after max rounds the gate lets Claude stop and tells the person why")

        # same failure three times in a row
        cli("on", "--check", f"{sys.executable} -c \"import sys; print('same error'); sys.exit(1)\"", "--max-rounds", "9")
        outs = [stop(session="same")[1] for _ in range(3)]
        check([o.get("decision") for o in outs] == ["block", "block", None] and "same failure" in outs[2].get("systemMessage", ""),
              "identical failure three times: stop early instead of burning rounds")

        # --once turns itself off
        flag.write_text("ok")
        cli("on", "--check", chk, "--once")
        r, out = stop()
        check("turned off" in out.get("systemMessage", "") and "OFF" in cli("status").stdout, "--once: off after the first pass")
        r, out = stop()
        check(out == {}, "and stays quiet afterwards")

        # timeout, bad input, off
        cli("on", "--check", f"{sys.executable} -c \"import time; time.sleep(5)\"", "--timeout", "1")
        r, out = stop(session="slow")
        check(out.get("decision") == "block" and "timed out" in out["reason"], "a check that times out counts as a failure")
        r = subprocess.run([sys.executable, "-I", str(GATE), "hook"], input="not json", capture_output=True, text=True, env=env)
        check(r.returncode == 0 and r.stdout.strip() == "", "unreadable hook input: never blocks")
        r, out = stop(hook_event_name="SubagentStop")
        check(out == {}, "only acts on Stop, not on subagent stops")
        cli("off")
        r, out = stop(session="slow")
        check(out == {} and "OFF" in cli("status").stdout, "off: the gate goes quiet")

    hooks = json.loads((ROOT / "plugins/top30-agents/hooks/hooks.json").read_text())
    cmd = hooks["hooks"]["Stop"][0]["hooks"][0]
    check(cmd["type"] == "command" and "${CLAUDE_PLUGIN_ROOT}/hooks/goal_gate.py" in cmd["command"] and cmd["command"].endswith(" hook"),
          "plugin registers the gate as a command Stop hook")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
