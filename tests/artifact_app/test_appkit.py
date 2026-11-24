"""Checks the artifact-app skill: planner, linter, budget, examples, references.

python3 tests/artifact_app/test_appkit.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SK = ROOT / "plugins/top30-ui/skills/artifact-app"
AK = SK / "scripts/appkit.py"

GOOD_HEAD = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Order Board</title>
<style>:root{--bg:#fff;--ink:#111}@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--bg:#000}}
:root[data-theme="dark"]{--bg:#000}body{background:var(--bg);color:var(--ink)}</style></head><body>
"""


def run(*args):
    return subprocess.run([sys.executable, str(AK), *map(str, args)], capture_output=True, text=True)


def lint_str(html):
    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False) as fh:
        fh.write(html)
    r = run("lint", fh.name, "--json")
    Path(fh.name).unlink()
    d = json.loads(r.stdout)
    return r.returncode, {f["rule"] for f in d["findings"]}


def page(body):
    return GOOD_HEAD + body + "\n</body></html>"


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # plan
    p = json.loads(run("plan", "menu bar app that reminds me when replies are due, using my gmail", "--json").stdout)
    caps = {c["capability"] for c in p["capabilities"]}
    check(p["tier"] == "app-permissions", f"tier: {p['tier']}")
    check({"notifications", "menu-bar-or-tray", "connectors"} <= caps, f"caps: {caps}")
    p = json.loads(run("plan", "rename the files in my downloads folder", "--json").stdout)
    check(p["tier"] == "full-access" and any("drag-and-drop" in a for a in p["advice"]), f"full access: {p}")
    p = json.loads(run("plan", "a pomodoro timer", "--json").stdout)
    check(p["tier"] == "app-permissions" and {c["capability"] for c in p["capabilities"]} == {"always-on-top"}, f"timer: {p}")
    p = json.loads(run("plan", "a static price sheet", "--json").stdout)
    check(p["tier"] == "default" and not p["capabilities"], f"static: {p}")

    # budget
    b = json.loads(run("budget", "--every-min", "5", "--claude-calls", "2", "--json").stdout)
    check(b["claude_calls_per_day"] == 240 and b["verdict"].startswith("heavy"), f"budget heavy: {b}")
    b = json.loads(run("budget", "--every-min", "30", "--json").stdout)
    check(b["claude_calls_per_day"] == 20 and b["verdict"] == "light", f"budget light: {b}")

    # shipped examples
    r = run("lint", SK / "examples/chargeback-clock.html", "--strict")
    check(r.returncode == 0, f"good example lints clean under --strict: {r.stdout}")
    rc, rules = lint_str((SK / "examples/bad-app.html").read_text())
    check(rc == 1, "bad example exits 1")
    for rule in ("A01", "A02", "A03", "A04", "A05", "A06", "A07", "A08", "A09", "A10", "A11", "A12",
                 "A13", "A14", "A15", "A16", "A17", "A19"):
        check(rule in rules, f"bad example should raise {rule}: {sorted(rules)}")

    # unit cases
    rc, rules = lint_str(page("<p>hi</p>"))
    check(rc == 0 and rules == {"A20"}, f"minimal good page: {rules}")
    _, rules = lint_str(page("") .replace("<title>Order Board</title>", ""))
    check("A01" in rules, "missing title")
    _, rules = lint_str(page('<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script><p>x</p>'))
    check("A06" not in rules and "A07" not in rules, f"pinned jsdelivr ok: {rules}")
    _, rules = lint_str(page('<script src="https://cdnjs.cloudflare.com/ajax/libs/d3/7.9.0/d3.min.js"></script>'))
    check("A07" not in rules, f"pinned cdnjs ok: {rules}")
    _, rules = lint_str(page('<script src="https://unpkg.com/react@18/umd/react.production.min.js"></script>'))
    check("A07" in rules, "major-only version is not pinned")
    _, rules = lint_str(page('<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter">'))
    check("A08" not in rules, "google fonts ok")
    _, rules = lint_str(page("<script>try { localStorage.setItem('a','b'); } catch (e) {}</script>"))
    check("A09" not in rules, f"storage in try ok: {rules}")
    _, rules = lint_str(page("<script>try { x(); } catch (e) {} localStorage.setItem('a','b');</script>"))
    check("A09" in rules, "storage after a closed try block is flagged")
    _, rules = lint_str(page("<script>if (window.claude) { window.claude.foo(); }</script>"))
    check("A10" not in rules, f"guarded runtime ok: {rules}")
    _, rules = lint_str(page("<script>window.claude?.foo();</script>"))
    check("A10" not in rules, "optional chaining ok")
    _, rules = lint_str(page("<script>async function r(){try{await fetch('/x')}catch(e){}} setInterval(r, 5*60*1000); addEventListener('offline',()=>{})</script>"))
    check("A14" not in rules and "A15" not in rules and "A15b" not in rules, f"slow poll with catch ok: {rules}")
    _, rules = lint_str(page("<script>async function r(){try{await fetch('/x')}catch(e){}} setInterval(r, 2000)</script>"))
    check("A14" in rules, "fast poll flagged")
    _, rules = lint_str(page("<script>el.textContent = data;</script>"))
    check("A13" not in rules, "textContent ok")

    # files
    for f in ("SKILL.md", "references/permissions.md", "references/patterns.md", "references/lint-rules.md",
              "references/checklist.md", "examples/chargeback-clock.html", "examples/bad-app.html"):
        check((SK / f).exists(), f"missing {f}")
    skill = (SK / "SKILL.md").read_text()
    check(skill.startswith("---\nname: artifact-app\n"), "frontmatter")
    for ref in ("permissions.md", "patterns.md", "lint-rules.md", "checklist.md"):
        check(f"references/{ref}" in skill, f"SKILL.md links {ref}")
    rules_doc = (SK / "references/lint-rules.md").read_text()
    for n in range(1, 21):
        check(f"A{n:02d}" in rules_doc, f"lint-rules.md documents A{n:02d}")
    agent = (ROOT / "plugins/top30-ui/agents/app-permission-reviewer.md").read_text()
    check("tools: Read, Glob, Grep, Bash" in agent and "appkit.py lint" in agent, "reviewer agent")
    check((ROOT / "plugins/top30-ui/claude-ai/artifact-app.zip").exists(), "claude-ai zip")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("artifact-app: all checks passed")


if __name__ == "__main__":
    main()
