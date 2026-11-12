"""The first-ai-team example must pass the kit's own graph checker with no warnings.

python3 tests/first_team/test_first_team.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SPEC = ROOT / "plugins/top30-agents/skills/first-ai-team/templates/content-team.json"
CHECK = ROOT / "plugins/top30-agents/skills/agent-graph-designer/scripts/graph_check.py"


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run([sys.executable, "-I", str(CHECK), "check", str(SPEC), "--out", tmp, "--fail-on", "warn"],
                           capture_output=True, text=True, timeout=60)
        check(r.returncode == 0, f"example team passes graph_check at --fail-on warn ({r.stdout.strip()})")
        st = json.loads((Path(tmp) / "findings.json").read_text())["stats"]
        check(st["waves"][2] == ["packager", "producer"], "packaging runs in parallel with rendering")
    spec = json.loads(SPEC.read_text())
    n = spec["nodes"]
    check(3 <= len(n) <= 5, "3 to 5 agents")
    check([k for k, v in n.items() if v["gate"] == "human"] == ["publish"] and n["publish"]["undo"] == "irreversible",
          "exactly one human gate, on the irreversible step")
    check(n["producer"]["kind"] == "code" and n["publish"]["kind"] == "code", "rendering and uploading are code, not a model")
    skill = (SPEC.parent.parent / "SKILL.md").read_text()
    check("START HERE FIRST" in skill and "Never ask for passwords" in skill, "skill keeps the approval rules and the first-step ending")
    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
