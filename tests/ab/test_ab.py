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
if "--restricted" in a:  # the judge
    prompt = a[a.index("-p") + 1]
    open(os.environ["FAKE_LOG"], "a").write(json.dumps({"cwd": os.getcwd(), "judge": True, "on": on, "args": a,
                                                        "files": os.listdir(".")}) + "\n")
    if os.environ.get("FAKE_JUDGE_BAD"):
        print(json.dumps({"type": "result", "result": "I cannot decide.", "total_cost_usd": 0.01})); sys.exit(0)
    ra = prompt.split("<response_a>")[1].split("</response_a>")[0]
    rb = prompt.split("<response_b>")[1].split("</response_b>")[0]
    ga, gb = "made OUT.md" in ra, "made OUT.md" in rb
    w = "tie" if ga == gb else ("A" if ga else "B")
    print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.01,
                      "result": "Verdict: " + json.dumps({"winner": w, "reason": "x"})}))
    sys.exit(0)
open(os.environ["FAKE_LOG"], "a").write(json.dumps({"cwd": os.getcwd(), "on": on, "args": a}) + "\n")
if on:
    open("OUT.md", "w").write("done\n")
print(json.dumps({"type": "result", "is_error": False, "total_cost_usd": 0.10 if on else 0.20,
                  "result": "made OUT.md" if on else "could not finish",
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
        check(all("--restricted" not in c["args"] for c in calls), "no judge calls without --judge")

        def ab(*extra, e=None):
            log.write_text("")
            o = tmp / "judge.json"
            r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/ab.py"), "--plugin", "demo@market",
                                "--prompt", "make OUT.md", "--repo", str(repo), "--check", "test -s OUT.md",
                                "--out", str(o), "--judge", "--judge-files", "OUT.md,../../etc/passwd", *extra],
                               env=e or env, capture_output=True, text=True, timeout=120)
            return r, [json.loads(x) for x in log.read_text().splitlines()], (json.loads(o.read_text()) if o.exists() else None)

        p3, calls3, res3 = ab("--runs", "6", "--noise-runs", "5", "--seed", "7")
        check(p3.returncode == 0, f"judge run exits 0 ({p3.stderr[-300:]})")
        judges = [c for c in calls3 if c.get("judge")]
        check(len(judges) == 11, f"6 on-vs-off + 5 noise judge calls ({len(judges)})")
        check(sum(1 for c in calls3 if not c.get("judge")) == 22, "12 arm runs + 10 noise runs")
        check(all(c["on"] is False for c in judges), "judge runs with the plugin off")
        check(all("--tools" in c["args"] and c["args"][c["args"].index("--tools") + 1] == "" and "--strict-mcp-config" in c["args"]
                  for c in judges), "judge has no tools and no MCP servers")
        check(all(c["files"] == [] for c in judges), "judge runs in an empty folder")
        jp = judges[0]["args"][judges[0]["args"].index("-p") + 1]
        check("--- file OUT.md ---" in jp and "done" in jp and "root:" not in jp, "judge sees --judge-files, nothing outside the copy")
        check("demo@market" not in jp and " on" not in jp.split("<task>")[0][-50:], "the prompt doesn't name the plugin or arm")
        j = res3["judge"]
        check(j["main"]["wins"] == 6 and j["main"]["losses"] == 0, f"on wins every comparison: {j['main']}")
        check(j["noise"]["ties"] == 5, f"identical runs tie: {j['noise']}")
        check(all("output" not in r and "files" not in r for r in res3["runs"]), "outputs not saved without --keep-outputs")
        sides = {c["x_was"] for c in j["comparisons"]}
        check(sides == {"A", "B"}, "the A/B order is shuffled and recorded")
        check(abs(j["main"]["ci"][0] - 0.61) < 0.01, f"Wilson lower bound for 6/6 is ~61%: {j['main']['ci']}")
        check("plugin preferred, beyond the noise band" in p3.stdout and "Noise band: ±0 points around 50%." in p3.stdout, f"verdict: {p3.stdout[-600:]}")
        check("| on vs off | 6 | 6 | 0 | 0 | 0 | 100% | 61–100% |" in p3.stdout, "judge table row")
        check("judge cost $0.110" in p3.stdout, "judge cost printed")
        _, _, again = ab("--runs", "6", "--noise-runs", "5", "--seed", "7")
        check([c["x_was"] for c in again["judge"]["comparisons"]] == [c["x_was"] for c in j["comparisons"]], "same seed, same order")

        p7, _, res7 = ab("--runs", "6", "--noise-runs", "3", "--keep-outputs")
        check("plugin preferred, but no noise band" in p7.stdout and "too few to use" in p7.stdout, f"3 noise pairs is no band: {p7.stdout[-400:]}")
        check(res7["runs"][0]["output"] in ("made OUT.md", "could not finish"), "--keep-outputs saves outputs")
        p8, _, _ = ab("--runs", "6")
        check("plugin preferred, but no noise band" in p8.stdout, "no --noise-runs: no band claimed")
        p4, _, res4 = ab("--runs", "2")
        check("too few comparisons to tell" in p4.stdout, "fewer than 5 comparisons: too few to tell")
        check(res4["judge"]["noise"] is None, "no noise band without --noise-runs")
        p5, _, res5 = ab("--runs", "6", e=dict(env, FAKE_JUDGE_BAD="1"))
        check(res5["judge"]["main"]["unparsed"] == 6 and res5["judge"]["main"]["n"] == 0, "unparseable verdicts counted apart from ties")
        check("too few comparisons" in p5.stdout, "all-unparseable is not a verdict")
        p6 = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/ab.py"), "--plugin", "demo@market", "--prompt", "x",
                             "--repo", str(repo), "--noise-runs", "2"], env=env, capture_output=True, text=True)
        check(p6.returncode != 0 and "needs --judge" in p6.stderr, "--noise-runs without --judge is refused")
    print(f"\n{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
