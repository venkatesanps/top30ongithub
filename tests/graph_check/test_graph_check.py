"""Runs graph_check.py on its own template (should be clean) and on a pipeline with every mistake planted.

python3 tests/graph_check/test_graph_check.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-agents/skills/agent-graph-designer/scripts/graph_check.py"


def run(*args):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=60)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        r = run("init")
        check(r.returncode == 0, "init prints a template")
        (tmp / "tpl.json").write_text(r.stdout)
        r = run("check", tmp / "tpl.json", "--out", tmp / "t", "--fail-on", "warn")
        check(r.returncode == 0, f"the template passes its own check at --fail-on warn ({r.stdout.strip()})")
        rep = (tmp / "t" / "report.md").read_text()
        check("**27 min**" in rep and "**17 min**" in rep, "three independent steps: 27 min in a line, 17 as a graph")
        check("1. pricing, repo_scan, research" in rep, "independent steps share the first wave")
        check("Recurring and hard to undo" in rep, "who-draws-the-graph advice follows runs + worst undo")
        check((tmp / "t" / "graph.mmd").read_text().startswith("flowchart LR"), "Mermaid diagram written")

        r = run("check", HERE / "bad_pipeline.json", "--out", tmp / "b")
        data = json.loads((tmp / "b" / "findings.json").read_text())
        fs, st = data["findings"], data["stats"]

        def has(rule, where=None, sev=None):
            return any(f["rule"] == rule and (where is None or f["where"] == where) and (sev is None or f["severity"] == sev)
                       for f in fs)

        check(r.returncode == 0, "without --fail-on, findings don't fail the run")
        check(has("arrow-carries-nothing", "extract -> fx", "error"), "arrow with no variable is an error")
        check(st["waves"][0] == ["extract", "fx"], "and fx runs in the first wave once that arrow is gone")
        check(st["serial_minutes"] == 48 and st["critical_minutes"] == 37, "48 min in a line, 37 as a graph")
        check(has("model-doing-code", "dedupe"), "dedupe/sort on a model flagged as code's job")
        check(has("no-real-check", "dedupe", "error") and has("no-real-check", "load", "error"),
              "'looks good' and 'no errors' are not checks")
        check(has("weak-check", "review_a", "warn"), "reviewer-agent approval is a weak check")
        check(not has("no-real-check", "extract") and not has("weak-check", "fix"), "row counts and dbt tests are strong checks")
        check(has("unbounded-cycle", sev="error"), "fix <-> review loop without max_rounds is an error")
        check(has("open-irreversible", "load", "error") and has("confidence-gate", "load"),
              "production MERGE gated on confidence: closed lane error + confidence warning")
        check(has("contract", "load", "error") and has("input-without-source", "load", "error"),
              "missing fails_as and an input nobody produces")
        check(has("arrow-not-read", "fix -> review_a"), "arrow carrying something the target never reads")
        check(sum(1 for f in fs if f["rule"] == "shared-context") == 1, "shared-context reported once for the reviewer pair")
        check(has("repair-without-limit", "fix"), "repair with no round limit")
        r = run("check", HERE / "bad_pipeline.json", "--out", tmp / "b2", "--fail-on", "error")
        check(r.returncode == 1, "--fail-on error fails the bad pipeline")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
