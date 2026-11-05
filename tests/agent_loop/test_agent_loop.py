"""Drives agent_loop.py with a fake agent (fake_claude.py) in throwaway git repos.

python3 tests/agent_loop/test_agent_loop.py   (needs git; no network, no Claude account)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-agents/skills/agent-loop/scripts/agent_loop.py"
FAKE = HERE / "fake_claude.py"
CHECK = f"{sys.executable} -c \"import calc; assert calc.add(2, 2) == 4, calc.add(2, 2)\""


def repo(tmp, name, broken=True):
    d = Path(tmp) / name
    d.mkdir()
    (d / "calc.py").write_text("def add(a, b):\n    return a - b\n" if broken else "def add(a, b):\n    return a + b\n")
    for c in (["git", "init", "-q"], ["git", "add", "."],
              ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "init"]):
        subprocess.run(c, cwd=d, check=True)
    return d


def run(d, mode, *args, cost="0.10"):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", CLAUDE_BIN=str(FAKE), FAKE_MODE=mode, FAKE_LOG=str(d.parent / f"{d.name}.fake_log"), FAKE_COST=cost)
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=d, env=env, capture_output=True, text=True, timeout=120)


def prompts(d):
    p = d.parent / f"{d.name}.fake_log"
    return [x for x in p.read_text().split("\x1e") if x] if p.exists() else []


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        base = ["repair", "--task", "Make add() correct", "--check", CHECK, "--scope", "calc.py"]

        d = repo(tmp, "green", broken=False)
        r = run(d, "fix2", *base)
        check(r.returncode == 0 and "already passes" in r.stdout and not prompts(d), "passing check: no agent call, no spend")

        d = repo(tmp, "fix")
        r = run(d, "fix2", *base, "--rules", "RULES.md", "--max-rounds", "3")
        ps = prompts(d)
        check(r.returncode == 0 and "PASS after 2 round(s)" in r.stdout, f"repaired in round 2 ({r.stdout.strip()[-120:]})")
        check(len(ps) == 2, "exactly two agent calls")
        check("change only calc.py" in ps[0] and "AssertionError" in ps[0], "prompt carries the scope line and the failing evidence")
        check("outside the scope: other.py" in ps[1], "round 2 is told about its out-of-scope edit")
        check("Already tried" in ps[1] and "sign error" in ps[1], "round 2 remembers what round 1 tried")
        rules = (d / "RULES.md").read_text() if (d / "RULES.md").exists() else ""
        check("unit test per operator" in rules, "the cause of a hard-won fix is written down as a rule")
        r2 = run(d, "fix2", *base, "--rules", "RULES.md")
        check("already passes" in r2.stdout, "re-run after success does nothing")

        d = repo(tmp, "never")
        (d / "RULES.md").write_text("# Rules\n\n- adapters keep keyword arguments exactly\n")
        r = run(d, "never", *base, "--rules", "RULES.md", "--max-rounds", "3")
        ps = prompts(d)
        check(r.returncode == 3 and len(ps) == 3, "round limit reached -> escalate (exit 3) after 3 calls")
        check("keyword arguments" in ps[0], "standing rules are read into every prompt")
        esc = list(d.glob(".agent-loop/*/ESCALATION.md"))
        check(esc and "the plan is probably wrong" in esc[0].read_text(), "escalation note written for a person")

        d = repo(tmp, "same")
        r = run(d, "same", *base, "--max-rounds", "5")
        check(r.returncode == 3 and len(prompts(d)) == 2 and "no progress" in r.stdout,
              "same failure twice -> escalate early, not after 5 rounds")

        d = repo(tmp, "budget")
        r = run(d, "never", *base, "--max-rounds", "5", "--budget-usd", "1.5", cost="1.00")
        check(r.returncode == 4 and len(prompts(d)) == 2 and "budget" in r.stdout, "budget cap stops the loop (exit 4)")

        d = repo(tmp, "error")
        r = run(d, "error", *base)
        check(r.returncode == 4 and len(prompts(d)) == 2, "agent failure: one retry, then stop")

        # hunt
        d = repo(tmp, "hunt")
        verify = f"{sys.executable} -c \"import json,sys; sys.exit(1 if json.load(sys.stdin)['key'] == 'b' else 0)\""
        r = run(d, "hunt", "hunt", "--task", "find flaky tests", "--verify", verify, "--max-rounds", "6")
        ps = prompts(d)
        rows = [json.loads(x) for f in d.glob(".agent-loop/hunt-*/findings.jsonl") for x in f.read_text().splitlines()]
        check(r.returncode == 0 and len(ps) == 4, f"rounds 3 and 4 find nothing new -> stop after 4 calls (got {len(ps)})")
        check(sorted(x["key"] for x in rows) == ["a", "b", "c"], "each finding recorded once")
        check({x["key"]: x["status"] for x in rows}.get("b") == "rejected", "verify command rejects b")
        check("- b (rejected)" in ps[1], "rejected findings stay in memory so they aren't rediscovered")
        check(not any(x["key"] == "z" for x in rows), "later rounds never run")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
