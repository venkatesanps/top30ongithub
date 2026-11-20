"""Checks pattern_kit.py: pick prefers the smallest pattern that fits, every scaffold passes its
own audit, and each pattern's way of breaking plus the ten production rules are caught.

python3 tests/pattern_kit/test_pattern_kit.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-agents/skills/agent-pattern-picker/scripts/pattern_kit.py"
ALL = ["single", "sequential", "parallel", "loop", "review", "refine", "coordinator", "hierarchical",
       "swarm", "react", "hitl", "plan-execute", "reflexion", "custom-logic", "event-driven"]


def run(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], capture_output=True, text=True)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    def pick(*flags):
        return json.loads(run("pick", "--json", *flags).stdout)

    r = pick("--predictable")
    check(r["verdict"] == "no-agent", "a predictable task gets no agent")
    r = pick("--predictable", "--tool-choice")
    check(r["verdict"] == "agent", "predictable but needs tool choice is still an agent")
    check(pick("--tool-choice")["primary"] == "single", "tool choice alone: single agent")
    r = pick("--tool-choice", "--path-unknown")
    check(r["primary"] == "react" and "single" not in r["also"], "unknown path: ReAct, no simpler 'also'")
    check(pick("--approve-plan")["primary"] == "plan-execute", "plan to approve: plan-and-execute")
    check(pick("--approve-plan", "--fast-changing")["primary"] == "react", "plan goes stale: ReAct instead")
    check(pick("--route")["primary"] == "coordinator", "different request kinds: coordinator")
    check(pick("--quality")["primary"] == "review", "quality without a metric: review and critique")
    check(pick("--quality", "--measurable")["primary"] == "refine", "measurable quality: iterative refinement")
    check(pick("--repeat")["primary"] == "loop", "retry until a check: loop")
    check(pick("--self-correct")["primary"] == "reflexion", "informative failures: reflexion")
    check(pick("--stages")["primary"] == "sequential", "fixed stages: sequential")
    check(pick("--independent")["primary"] == "parallel", "independent subtasks: parallel")
    check(pick("--broad", "--independent")["primary"] == "parallel", "broad but independent: smallest is parallel")
    check(pick("--broad")["primary"] == "hierarchical", "broad problem: hierarchical")
    check(pick("--no-right-answer")["primary"] == "swarm", "no right answer: swarm")
    check(pick("--event")["primary"] == "event-driven", "events: event-driven")
    r = pick("--tool-choice", "--risk")
    check(r["primary"] == "single" and [w[0] for w in r["wrap"]] == ["custom-logic", "hitl"],
          "risk wraps the pattern in custom logic and a human step")
    check(pick()["primary"] == "single", "no flags: the simplest pattern")
    out = run("pick", "--route").stdout
    check("In Claude Code:" in out and "Breaks when" in out, "text pick says how to build it and how it breaks")

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)

        def audit(design, *extra):
            p = tmp / "d.json"
            p.write_text(json.dumps(design))
            r = run("audit", str(p), "--json", *extra)
            return r.returncode, json.loads(r.stdout)["findings"]

        def has(findings, rule, text="", sev=None):
            return any(f["rule"].startswith(rule) and text in f["msg"] and (sev is None or f["severity"] == sev)
                       for f in findings)

        for p in ALL:
            d = json.loads(run("scaffold", p).stdout)
            code, fs = audit(d, "--fail-on", "warn")
            check(code == 0 and d["pattern"] == p, f"scaffold '{p}' passes its own audit")

        # the ten rules
        code, fs = audit({"pattern": "single", "system_prompt_words": 3000,
                          "tools": [{"name": "t", "description": "does stuff"}] + [
                              {"name": f"t{i}", "description": "x" * 50} for i in range(9)]})
        check(code == 1, "a bare design fails")
        check(has(fs, "rule 7", "3000 words"), "long system prompt flagged")
        check(has(fs, "single agent", "10 tools"), "too many tools for one agent")
        check(has(fs, "rule 2", "'t'"), "short tool description flagged")
        check(has(fs, "rule 3", sev="error"), "missing budget is an error")
        check(has(fs, "rule 4", sev="error"), "missing trace is an error")
        check(has(fs, "rule 6"), "missing failure evals flagged")
        sp = tmp / "prompt.txt"
        sp.write_text("Help users. But don't refund when the order is older than 30 days.")
        code, fs = audit({"pattern": "single", "system_prompt_file": str(sp)})
        check(has(fs, "rule 7", "two jobs"), "'but don't X when Y' in the prompt flagged")

        base = json.loads(run("scaffold", "single").stdout)
        d = dict(base, tools=[{"name": "issue_refund", "description": "Refunds an order to the original card, in full."}])
        code, fs = audit(d)
        check(has(fs, "rule 5", "sounds irreversible") and has(fs, "rule 5", "gate 'none'", "error"),
              "unmarked refund tool is caught and needs a gate")
        d["tools"][0].update(irreversible=True, gate="model")
        check(has(audit(d)[1], "rule 5", "gate 'model'", "error"), "a model is not a gate for money")
        d["tools"][0]["gate"] = "human"
        check(not has(audit(d)[1], "rule 5"), "a human gate passes")

        # each pattern's way of breaking
        def broken(p, **kw):
            d = json.loads(run("scaffold", p).stdout)
            for k, v in kw.items():
                if v is None:
                    d.pop(k, None)
                else:
                    d[k] = v
            return audit(d)[1]

        check(has(broken("loop", exit={}), "loop", "max_rounds", "error") and has(broken("loop", exit={}), "loop", "exit check"),
              "loop without a cap or check")
        check(has(broken("react", budget={"max_usd": 1}), "react", "max_steps", "error"), "ReAct without a step cap")
        check(has(broken("review", critic={"model": "opus", "context": "shared"}), "review", "own"), "critic sharing context")
        check(has(broken("review", critic={"model": "opus", "context": "own"}), "review", "blind spots"),
              "same model, no rubric: same blind spots")
        check(has(broken("refine", score={"by": "same-model", "threshold": 0.8}), "refine", "scores itself", "error"),
              "self-scored refinement is an error")
        fs = broken("parallel", stages=[{"name": "a", "out": ["x"]}, {"name": "b", "in": ["x"], "out": ["y"]}])
        check(has(fs, "parallel", "needs x", "error"), "a dependent branch isn't parallel")
        fs = broken("sequential", stages=[{"name": "a", "out": ["x"]}, {"name": "b", "in": ["z"]}])
        check(has(fs, "sequential", "doesn't produce"), "sequential stage missing its input")
        check(has(broken("coordinator", fallback_route=None), "coordinator", "fallback", "error"), "coordinator with no fallback")
        check(has(broken("coordinator", routes=["only"]), "coordinator", "fewer than two"), "a one-route coordinator")
        check(has(broken("hierarchical", subgoals=[{"name": "a"}, {"name": "b", "depends_on": ["a"]}]),
                  "hierarchical", "needs a"), "dependent subgoals")
        check(has(broken("swarm", rounds=None), "swarm", "round limit", "error"), "swarm with no round limit")
        fs = broken("hitl", human={"when": "big refunds"})
        check(all(has(fs, "hitl", k) for k in ("reviewer", "timeout", "on_timeout", "durable")), "HITL as a pause button")
        fs = broken("plan-execute", plan={"reviewed": False})
        check(has(fs, "plan-execute", "isn't reviewed") and has(fs, "plan-execute", "stale"), "unreviewed, stale plan")
        check(has(broken("reflexion", memory={}), "reflexion", "lessons file", "error"), "reflexion with no lessons file")
        check(has(broken("custom-logic", rules_in_code=[]), "custom-logic", "never decide", "error"), "custom logic with no rules")
        fs = broken("event-driven", trigger={"event": "x"})
        check(has(fs, "event-driven", "condition", "error") and has(fs, "event-driven", "dedupe")
              and has(fs, "event-driven", "rate limit"), "vague event trigger")
        check(has(broken("swarm", roles=["a"], tools=[]), "swarm", "three roles"), "two-person swarm")

        code, fs = audit({"patterns": ["react", "hitl"], "budget": {"max_usd": 1}})
        check(has(fs, "react") and has(fs, "hitl"), "combined patterns get both sets of checks")
        code, fs = audit({"pattern": "magic"})
        check(has(fs, "pattern", "unknown", "error"), "unknown pattern")
        (tmp / "bad.json").write_text("{")
        check(run("audit", str(tmp / "bad.json")).returncode == 2, "unreadable design is exit 2")

    out = run("list").stdout
    check(all(p in out for p in ALL) and out.count("Claude Code:") == 15, "list covers all 15 with a Claude Code build")

    print(f"\n{'All passed' if not failures else f'{len(failures)} failed'}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
