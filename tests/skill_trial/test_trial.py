"""Walks trial.py through two invented trials against the real catalog.json.

python3 tests/skill_trial/test_trial.py   (no dependencies, no network; uses a temp state file)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-coach/skills/skill-trial/scripts/trial.py"
CATALOG = json.loads((ROOT / "catalog.json").read_text())


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "trials.json"

        def run(*args, at="2026-11-04T09:00:00+00:00"):
            env = {k: v for k, v in os.environ.items() if not k.startswith(("SKILL_TRIAL", "TOP30"))}
            env.update(SKILL_TRIAL_STATE=str(state), SKILL_TRIAL_NOW=at)
            return subprocess.run([sys.executable, "-I", str(SCRIPT), *args], capture_output=True, text=True,
                                  timeout=30, env=env, cwd=tmp)

        r = run("status")
        check(r.returncode == 0 and "No active trial" in r.stdout, "status with no state")
        r = run("log", "--saved", "5")
        check(r.returncode != 0 and "No active trial" in r.stderr, "log refuses without a trial")

        sqlglot = next(i for i in CATALOG["items"] if i["name"] == "SQLGlot")
        r = run("start", str(sqlglot["n"]), "--goal", "translate Oracle views")
        check(r.returncode == 0 and "SQLGlot" in r.stdout and f"./install.sh {sqlglot['n']}" in r.stdout,
              "start by kit number resolves name and install command from catalog.json")
        r = run("start", "humanizer")
        check(r.returncode != 0 and "Already trying SQLGlot" in r.stderr, "one trial at a time")

        for m in ("20", "15", "-5"):
            run("log", "--saved", m, "--note", "real task")
        r = run("status", at="2026-11-06T09:00:00+00:00")
        check("3 use(s), +30 min" in r.stdout and "5 day(s) left" in r.stdout, f"status totals uses and days left ({r.stdout.strip()})")
        r = run("review")
        check(r.returncode != 0 and "--now" in r.stderr, "review waits for the trial to end")
        r = run("review", at="2026-11-12T09:00:00+00:00")
        check(r.returncode == 0 and r.stdout.startswith("KEEP SQLGlot"), "3 uses and time saved -> keep")

        r = run("start", "humanizer", at="2026-11-12T10:00:00+00:00")
        run("log", "--saved", "4")
        r = run("review", at="2026-11-20T10:00:00+00:00")
        check(r.stdout.startswith("EXTEND humanizer"), "1 use -> extend one more week")
        r = run("review", at="2026-11-28T10:00:00+00:00")
        check(r.stdout.startswith("DROP humanizer") and "disable" in r.stdout, "still too few uses after extension -> drop")

        r = run("start", "copy-editing", at="2026-11-28T11:00:00+00:00")
        run("log", "--saved", "-10")
        run("log", "--saved", "-5")
        run("log", "--saved", "2")
        r = run("review", "--now", at="2026-11-29T11:00:00+00:00")
        check(r.stdout.startswith("DROP copy-editing"), "uses that cost time overall -> drop")

        r = run("start", str(sqlglot["n"]), at="2026-11-30T11:00:00+00:00")
        check(r.returncode != 0 and "already kept" in r.stderr, "won't restart a kept skill")

        r = run("suggest", "--role", "data", "--catalog", str(ROOT / "catalog.json"))
        rows = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("#")]
        data_rows = {CATALOG["rows"][k] for k in ("6", "7", "1")}
        check(r.returncode == 0 and len(rows) == 3, "suggest gives three")
        check(all(any(n in ln for n in data_rows) for ln in rows), "suggestions come from the data rows")
        check("SQLGlot" not in r.stdout, "suggest skips skills already tried")
        check(rows and CATALOG["rows"]["6"] in rows[0], "most relevant row first")

        h = json.loads(state.read_text())
        check([x["verdict"] for x in h["history"]] == ["keep", "drop", "drop"] and h["active"] is None, "history recorded")
        r = run("history")
        check(r.stdout.count("\n") == 3 and "keep" in r.stdout, "history lists every finished trial")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
