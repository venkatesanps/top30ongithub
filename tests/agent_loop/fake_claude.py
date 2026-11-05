#!/usr/bin/env python3
"""Stands in for `claude -p ... --output-format json` in tests. Behaviour comes from FAKE_MODE;
every prompt is appended to $FAKE_LOG so tests can check what the loop told the agent."""
import json
import os
import sys
from pathlib import Path

prompt = sys.argv[sys.argv.index("-p") + 1]
log = Path(os.environ["FAKE_LOG"])
calls = [l for l in log.read_text().split("\x1e") if l] if log.exists() else []
n = len(calls) + 1
with open(log, "a") as f:
    f.write(prompt + "\x1e")
mode, cost = os.environ.get("FAKE_MODE", "fix2"), float(os.environ.get("FAKE_COST", "0.10"))
out = {"result": "", "total_cost_usd": cost}

if mode in ("fix2", "never", "same"):
    calc = Path("calc.py")
    if mode == "fix2" and n == 1:
        calc.write_text("def add(a, b):\n    return a - b + 1\n")          # still wrong
        Path("other.py").write_text("# drive-by edit outside the scope\n")
        out["result"] = "Changed the formula.\nCAUSE: sign error\nRULE: n/a"
    elif mode == "fix2":
        Path("other.py").unlink(missing_ok=True)
        calc.write_text("def add(a, b):\n    return a + b\n")
        out["result"] = "Fixed.\nCAUSE: add() subtracted instead of adding\nRULE: arithmetic helpers keep a unit test per operator"
    elif mode == "never":
        calc.write_text(f"def add(a, b):\n    return a * b + {n}\n")      # different wrong answer each round
        out["result"] = f"Tried variant {n}.\nCAUSE: unsure\nRULE: none"
    else:  # same: touches nothing, so the failure is identical
        out["result"] = "I think it's fine now.\nCAUSE: none\nRULE: none"
elif mode == "hunt":
    rounds = {1: ["a", "b"], 2: ["b", "c"], 3: ["c"], 4: [], 5: [], 6: ["z"]}
    out["result"] = "Findings:\n" + "\n".join(
        json.dumps({"key": k, "summary": f"issue {k}", "evidence": "line 1"}) for k in rounds.get(n, []))
elif mode == "error":
    print("boom", file=sys.stderr)
    sys.exit(1)
print(json.dumps(out))
