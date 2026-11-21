"""Checks the think-through skill: router, template, ledger linter, examples, references.

python3 tests/think_through/test_think.py   (no dependencies, no network)
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SK = ROOT / "plugins/top30-agents/skills/think-through"
TH = SK / "scripts/think.py"


def run(*args):
    return subprocess.run([sys.executable, str(TH), *map(str, args)], capture_output=True, text=True)


def route(p):
    return json.loads(run("route", p, "--json").stdout)


def lint(path):
    r = run("lint", path, "--json")
    return r.returncode, json.loads(r.stdout)["findings"]


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # router
    r = route("the nightly job fails with a timeout since tuesday, why?")
    check(r["modes"][:1] == ["diagnose"] and "check" in r["modes"], f"bug route: {r}")
    r = route("should we port it to rust?")
    check({"frame", "weigh", "commit"} <= set(r["modes"]) and r["depth"] == "deep", f"decision route: {r}")
    r = route("suggest some concepts for the landing page, it must stand out but look professional")
    check("widen" in r["modes"] and "taste" in r["modes"], f"design+taste route: {r}")
    r = route("obviously we just need an index, right? and what is the latest snowflake pricing")
    check("pushback" in r["modes"] and "fresh" in r["modes"], f"premise+fresh route: {r}")
    for p in ("what is the capital of France", "rename foo to bar", "fix the typo"):
        check(route(p)["depth"] == "skip", f"should skip: {p}")
    r = route("review this migration plan for the payments table")
    check("check" in r["modes"] and r["depth"] == "deep", f"review+stakes route: {r}")
    for p in ("should we use kafka", "design a cache", "why does login fail"):
        rr = route(p)
        order = ["frame", "diagnose", "widen", "fresh", "check", "weigh", "taste", "pushback", "commit", "integrate"]
        check([m for m in order if m in rr["modes"]] == rr["modes"], f"modes out of order: {rr}")

    # modes and references line up
    listed = [l.split()[0] for l in run("modes").stdout.splitlines()]
    check(len(listed) == 10, f"modes: {listed}")
    for m in listed:
        check((SK / "references" / f"{m}.md").exists(), f"reference missing for {m}")
    skill = (SK / "SKILL.md").read_text()
    check(skill.startswith("---\nname: think-through\n"), "SKILL.md frontmatter")
    for m in listed:
        check(f"references/{m}.md" in skill, f"SKILL.md doesn't link {m}")
    check("s0md3v/overthink" in skill, "credit missing")

    # template
    r = run("template", "frame,widen,weigh,commit", "--prompt", "x")
    check(r.returncode == 0 and r.stdout.count("carry:") == 4 and "## [ ] widen" in r.stdout, "template")
    check(run("template", "frame,nope").returncode == 2, "template should reject unknown modes")

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        (t / "empty.md").write_text(run("template", "frame,widen,diagnose,check,fresh,weigh,commit,pushback").stdout)
        code, fs = lint(t / "empty.md")
        msgs = " ".join(f["msg"] for f in fs)
        check(code == 1, "an unfilled template must not pass")
        for needle in ("2+ structurally", "competing causes", "no claim tagged", "nothing checked",
                       "no choice", "verdict"):
            check(needle in msgs, f"empty template: '{needle}' finding missing")

        (t / "hedge.md").write_text("## Orient\ngoal: g\nlikely failure if answered fast: f\n\n"
                                    "## [x] commit\n- choice: both, it depends\n- tradeoff: t\n"
                                    "- would change if: w\ncarry: c\n")
        code, fs = lint(t / "hedge.md")
        check(code == 0 and any("hedges" in f["msg"] for f in fs), f"hedge warning: {fs}")

        (t / "rule.md").write_text("## Orient\ngoal: g\nlikely failure if answered fast: f\n\n"
                                   "## [x] commit\n- choice: X if writes > 1k/s, else Y\n- tradeoff: t\n"
                                   "- would change if: w\ncarry: c\n")
        code, fs = lint(t / "rule.md")
        check(code == 0 and not fs, f"a rule-based choice is not a hedge: {fs}")

        (t / "bare.md").write_text("## [x] check\n- claim: a [verified]\ncarry: c\n")
        code, fs = lint(t / "bare.md")
        check(any("no method" in f["msg"] for f in fs), f"bare [verified] should warn: {fs}")

        (t / "nofresh.md").write_text("## [x] fresh\n- no time-sensitive facts\ncarry: c\n")
        code, fs = lint(t / "nofresh.md")
        check(code == 0, f"'no time-sensitive facts' is a valid fresh result: {fs}")

        (t / "none.md").write_text("just prose, no sections\n")
        check(lint(t / "none.md")[0] == 1, "no sections should be an error")
    check(run("lint", "/nonexistent/ledger.md").returncode == 2, "missing file should exit 2")

    # shipped examples
    code, fs = lint(SK / "examples/good-ledger.md")
    check(code == 0 and not [f for f in fs if f["severity"] != "info"], f"good example should be clean: {fs}")
    code, fs = lint(SK / "examples/bad-ledger.md")
    check(code == 1 and sum(f["severity"] == "error" for f in fs) >= 3, f"bad example should fail: {fs}")

    # auditor agent
    ag = (ROOT / "plugins/top30-agents/agents/think-auditor.md").read_text()
    fm = ag.split("---")[1]
    check(re.search(r"^name: think-auditor$", fm, re.M) and re.search(r"^tools: Read, Glob, Grep, Bash$", fm, re.M),
          "auditor frontmatter")
    for w in ("Write", "Edit"):
        check(w not in fm, f"auditor must be read-only: {w}")
    check("think.py lint" in ag and "sycophancy" in ag and "stale" in ag, "auditor body")

    if fails:
        print(f"FAIL ({len(fails)})")
        for f in fails:
            print(" -", f)
        return 1
    print("ok - think-through: router, template, linter, examples, references, auditor")
    return 0


if __name__ == "__main__":
    sys.exit(main())
