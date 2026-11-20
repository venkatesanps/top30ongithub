"""Walks decisions.py through invented decisions: log, due, review, stats, and bad input.

python3 tests/sparring/test_decisions.py   (no dependencies, no network; uses a temp state file)
"""
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-sparring/skills/sparring-partner/scripts/decisions.py"


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        state = Path(tmp) / "decisions.json"

        def run(*args, at="2026-11-01T09:00:00+00:00"):
            env = {k: v for k, v in os.environ.items() if not k.startswith("SPARRING")}
            env.update(SPARRING_STATE=str(state), SPARRING_NOW=at)
            return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True, env=env)

        r = run("stats")
        check(r.returncode == 0 and "0 logged" in r.stdout, "stats on an empty log")

        r = run("add", "Move nightly loads from Airflow to Snowflake tasks", "--chose", "migrate in Q1",
                "--confidence", "80", "--risk", "connector not ready", "--risk", "team lacks task experience",
                "--risk", "cost rises", "--kill", "two missed loads in a month", "--review-in", "30")
        check(r.returncode == 0 and "Logged #1" in r.stdout and "review on 2026-12-01" in r.stdout, "add with risks")

        r = run("add", "Hire a contractor for the dashboard", "--chose", "yes", "--confidence", "60",
                "--review-in", "10")
        check(r.returncode == 0 and "can't count" in r.stdout, "add without risks warns")

        r = run("add", "x", "--confidence", "30")
        check(r.returncode != 0 and "50 (coin flip)" in r.stderr, "confidence below 50 rejected")

        r = run("due", at="2026-11-05T09:00:00+00:00")
        check("Nothing due" in r.stdout, "nothing due before review dates")

        r = run("due", at="2026-12-03T09:00:00+00:00")
        check("2 decision(s) due" in r.stdout and "late" in r.stdout, "both due later, with lateness")

        r = run("review", "1", "--outcome", "bad", "--happened", "1", "--note", "vendor slipped")
        check(r.returncode == 0 and "(predicted)" in r.stdout, "review with a predicted risk")

        r = run("review", "1", "--outcome", "good")
        check(r.returncode != 0 and "already reviewed" in r.stderr, "second review needs --force")

        r = run("review", "2", "--outcome", "mixed", "--happened", "4")
        check(r.returncode != 0 and "out of range" in r.stderr, "risk number out of range rejected")

        r = run("review", "#2", "--outcome", "mixed", "--happened", "scope doubled")
        check(r.returncode == 0 and "pre-mortem missed" in r.stdout, "review with an unpredicted failure")

        r = run("stats", "--json")
        s = json.loads(r.stdout)
        # Brier: (0.8-0)^2=0.64, (0.6-0.5)^2=0.01 -> 0.325
        check(s["reviewed"] == 2 and s["brier"] == 0.325, f"brier score computed ({s.get('brier')})")
        check(s["went_wrong"] == 2 and s["predicted"] == 1, "pre-mortem hit rate counted")
        bands = {b["band"]: b for b in s["bands"]}
        check(bands["80-89"]["actual"] == 0 and bands["60-69"]["actual"] == 50, "calibration bands")

        r = run("stats")
        check("over-confident" in r.stdout and "Fewer than 5" in r.stdout, "readable stats with caveat")

        r = run("list", "--open")
        check("No open decisions" in r.stdout, "list --open after reviews")

        r = run("show", "99")
        check(r.returncode != 0, "unknown id rejected")

        state.write_text("{not json")
        r = run("list")
        check(r.returncode != 0 and "not valid JSON" in r.stderr, "corrupt state reported, not overwritten")
        check(state.read_text() == "{not json", "corrupt state left untouched")

    print(f"\n{'All passed' if not failures else f'{len(failures)} failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
