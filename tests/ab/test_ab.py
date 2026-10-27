"""Runs scripts/ab.py against a fake `claude` and checks it: arms toggle the plugin, the repo is
never modified, checks are counted, results are summarised.

python3 tests/ab/test_ab.py   (no dependencies, no network, no Claude account)
"""
import json
import os
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
FAKE = r'''#!/usr/bin/env python3
import json, os, sys
a = sys.argv[1:]
if a[:2] == ["plugin", "list"]:
    print("  > demo@market\n    Status: enabled"); sys.exit(0)
s = json.loads(a[a.index("--settings") + 1])
on = s["enabledPlugins"]["demo@market"]
open(os.environ["FAKE_LOG"], "a").write(json.dumps({"cwd": os.getcwd(), "on": on, "args": a}) + "\n")
if on:
    open("OUT.md", "w").write("done\n")
print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.10 if on else 0.20,
                  "num_turns": 3, "duration_ms": 1000,
                  "usage": {"input_tokens": 100, "output_tokens": 50 if on else 80,
                            "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 0}}))
'''


def main():
    fails = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        fake = tmp / "claude"
        fake.write_text(FAKE)
        fake.chmod(fake.stat().st_mode | stat.S_IEXEC)
        repo = tmp / "repo"
        repo.mkdir()
        (repo / "README.md").write_text("sandbox\n")
        log = tmp / "log.jsonl"
        env = dict(os.environ, CLAUDE_BIN=str(fake), FAKE_LOG=str(log))
        out = tmp / "res.json"
        p = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/ab.py"), "--plugin", "demo@market",
                            "--prompt", "make OUT.md", "--repo", str(repo), "--runs", "2",
                            "--check", "test -s OUT.md", "--out", str(out)],
                           env=env, capture_output=True, text=True, timeout=120)
        check(p.returncode == 0, f"exits 0 ({p.stderr[-200:]})")
        calls = [json.loads(x) for x in log.read_text().splitlines()]
        check(len(calls) == 4 and sum(c["on"] for c in calls) == 2, "2 runs per arm, plugin toggled via --settings")
        check([c["on"] for c in calls] == [False, True, True, False], "arm order alternates between runs")
        check(len({c["cwd"] for c in calls}) == 4 and all(str(repo) != c["cwd"] for c in calls), "each run in its own copy")
        check(sorted(x.name for x in repo.iterdir()) == ["README.md"], "original repo untouched")
        check("| off | 2/2 | 0/2 | $0.200 |" in p.stdout and "| on | 2/2 | 2/2 | $0.100 |" in p.stdout, "table: checks and cost per arm")
        check("-50%" in p.stdout and "cheaper with the plugin" in p.stdout, "cost change and verdict")
        check(len(json.loads(out.read_text())["runs"]) == 4, "per-run JSON saved")
        p2 = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/ab.py"), "--plugin", "missing@x",
                             "--prompt", "x", "--repo", str(repo)], env=env, capture_output=True, text=True)
        check(p2.returncode != 0 and "not installed" in p2.stderr, "refuses a plugin that isn't installed")
    print(f"\n{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
