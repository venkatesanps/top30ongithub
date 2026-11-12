"""Walks harness_kit.py through a project's life in a throwaway git repo.

python3 tests/harness_kit/test_harness_kit.py   (needs git; no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-agents/skills/harness-starter/scripts/harness_kit.py"


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp) / "proj"
        d.mkdir()

        def run(*args):
            return subprocess.run([sys.executable, "-I", str(SCRIPT), *args, "--root", str(d)], capture_output=True, text=True, timeout=60)

        def feats():
            return json.loads((d / "feature_list.json").read_text())

        r = run("status")
        check(r.returncode != 0 and "run init first" in r.stderr, "status before init explains what to do")

        seed = Path(tmp) / "seed.json"
        seed.write_text(json.dumps([
            {"category": "load", "description": "Nightly orders load is idempotent", "steps": ["run the load twice", "row count unchanged"], "passes": True},
            {"category": "quality", "description": "fct_orders has no duplicate order_id", "steps": ["dbt test --select fct_orders"]},
        ]))
        r = run("init", "--features", str(seed))
        check(r.returncode == 0 and all((d / f).exists() for f in ("feature_list.json", "claude-progress.txt", "init.sh")), "init creates the three files")
        check([f["id"] for f in feats()] == ["F001", "F002"] and not any(f["passes"] for f in feats()),
              "features get ids and all start failing, even if the seed claimed a pass")
        (d / "init.sh").write_text("#!/bin/sh\necho mine\n")
        r = run("init")
        check("nothing" in r.stdout and "mine" in (d / "init.sh").read_text(), "init never overwrites existing files")

        check(run("guard").returncode == 1, "guard fails until the list is locked")
        r = run("add", "--description", "Late files are quarantined", "--step", "drop a file dated yesterday", "--step", "it lands in quarantine/")
        check(r.returncode == 0 and feats()[-1]["id"] == "F003", "add appends a feature before locking")
        r = run("lock")
        check(r.returncode == 0 and (d / "feature_list.lock").exists() and run("guard").returncode == 0, "lock, then guard passes")

        r = run("next")
        check(json.loads(r.stdout)["id"] == "F001", "next gives the first unfinished feature")
        r = run("mark", "F001", "pass")
        check(r.returncode != 0 and "needs --evidence" in r.stderr, "a pass without evidence is refused")
        r = run("mark", "F001", "pass", "--evidence", "ran load twice; SELECT COUNT(*) = 1204 both times")
        log = (d / "claude-progress.txt").read_text()
        check(r.returncode == 0 and feats()[0]["passes"] and "F001 marked PASS" in log and "1204" in log, "mark pass records the evidence in the progress log")
        check(run("guard").returncode == 0, "changing only 'passes' keeps the guard green")
        r = run("status")
        check("1 of 3 features passing" in r.stdout and "next: F002" in r.stdout and "list: intact" in r.stdout, "status: counts, next, integrity")

        # tampering
        f = feats()
        f[1]["steps"] = ["trust me"]
        (d / "feature_list.json").write_text(json.dumps(f))
        r = run("guard")
        check(r.returncode == 1 and "F002: description, steps or category were edited" in r.stdout, "guard catches a reworded feature")
        r = run("mark", "F002", "pass", "--evidence", "x")
        check(r.returncode != 0 and "tampered" in r.stderr, "mark refuses while the list is tampered")
        f = feats()[:1]
        (d / "feature_list.json").write_text(json.dumps(f))
        out = run("guard").stdout
        check("F002: removed" in out and "F003: removed" in out, "guard catches deleted features")
        f = json.loads(seed.read_text())
        run("init")  # no-op
        # restore, then add without relock
        good = [{"id": "F001", "category": "load", "description": "Nightly orders load is idempotent", "steps": ["run the load twice", "row count unchanged"], "passes": True},
                {"id": "F002", "category": "quality", "description": "fct_orders has no duplicate order_id", "steps": ["dbt test --select fct_orders"], "passes": False},
                {"id": "F003", "category": "functional", "description": "Late files are quarantined", "steps": ["drop a file dated yesterday", "it lands in quarantine/"], "passes": False}]
        (d / "feature_list.json").write_text(json.dumps(good, indent=2))
        check(run("guard").returncode == 0, "restoring the original list satisfies the guard")
        r = run("add", "--description", "New scope", "--step", "s")
        check(r.returncode != 0 and "locked" in r.stderr, "adding scope to a locked list needs --relock")
        r = run("add", "--description", "New scope", "--step", "s", "--relock")
        check(r.returncode == 0 and run("guard").returncode == 0 and len(feats()) == 4, "add --relock adds and re-locks")

        # git base
        for c in (["git", "init", "-q"], ["git", "add", "."], ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "base"]):
            subprocess.run(c, cwd=d, check=True)
        f = feats()
        f[3]["description"] = "Different scope"
        (d / "feature_list.json").write_text(json.dumps(f, indent=2))
        run("lock")  # an agent re-locking to hide an edit
        check(run("guard").returncode == 0 and run("guard", "--base", "HEAD").returncode == 1,
              "re-locking hides an edit from the lock file, but guard --base <git ref> still catches it")

        r = run("log", "Session 3: fixed dedupe macro. Next: F002.")
        check("Session 3" in (d / "claude-progress.txt").read_text() and "Session 3" in run("status").stdout, "log appends; status shows the last entry")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
