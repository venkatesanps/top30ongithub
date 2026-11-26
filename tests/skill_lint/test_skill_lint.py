"""Tests for scripts/skill_lint.py: each check fires on the problem it names and stays quiet on the
usual false positives (lists inside code fences, numbered rules lists, specific retries).

python3 tests/skill_lint/test_skill_lint.py   (no dependencies)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import skill_lint as sl  # noqa: E402

fails = []


def check(cond, msg):
    print(("PASS " if cond else "FAIL ") + msg)
    if not cond:
        fails.append(msg)


def ids(text):
    return sorted(f["check"] for f in sl.lint_text(text))


GOOD = """---
name: good-skill
description: Does one job well. Use when testing the linter.
---
# Good skill

## Steps

1. Install the tool: `pip install demo`. Check that `demo --version` prints 1.x.
2. Run it on the folder:
   ```bash
   demo run ./data
   ```
   Expect `0 errors`; if it reports errors, read them before going on.

## Rules

1. Never run it on production.
2. Keep the output.

## When it fails

| Failure | Fix |
|---|---|
| `demo: command not found` | Activate the virtualenv, then run step 1 again |
| Timeout on large folders | Retry with `--workers 4` after clearing the cache |
"""
check(ids(GOOD) == [], f"a well-formed skill has no findings: {ids(GOOD)}")

no_steps = GOOD.replace("1. Install", "Install").replace("2. Run", "Run")
check("numbered-steps" in ids(no_steps), "no numbered steps is flagged")

no_verify = GOOD.replace(" Check that `demo --version` prints 1.x.", "")
check(ids(no_verify) == ["step-verifies"], f"a step with no way to check its result is flagged: {ids(no_verify)}")

no_cmd = GOOD.replace("Install the tool: `pip install demo`. Check that `demo --version` prints 1.x.",
                      "Install the tool and check it works.")
check(ids(no_cmd) == ["step-command"], f"a step with no concrete command is flagged: {ids(no_cmd)}")

no_table = GOOD.split("## When it fails")[0]
check(ids(no_table) == ["error-recovery"], f"a missing failure table is flagged: {ids(no_table)}")

retry = GOOD.replace("Activate the virtualenv, then run step 1 again", "Try again.")
check(ids(retry) == ["retry-only-fix"], f"'Try again.' alone is flagged: {ids(retry)}")
for fix in ("retry", "Just retry", "re-run it", "`run again`"):
    check("retry-only-fix" in ids(GOOD.replace("Activate the virtualenv, then run step 1 again", fix)),
          f"bare '{fix}' is flagged")
check("retry-only-fix" not in ids(GOOD), "'Retry with --workers 4 after clearing the cache' passes")

fenced = GOOD.replace("## Steps", "## Steps\n\n```text\n1. this is inside a fence\n2. so is this\n## not a heading\n| a | b |\n```\n")
check(ids(fenced) == [], f"numbered lines, headings and tables inside fences are ignored: {ids(fenced)}")

rules_only = GOOD.replace("## Steps", "## Don'ts").replace("1. Install the tool", "Install the tool").replace(
    "2. Run it", "Run it")
check("numbered-steps" in ids(rules_only) and "step-command" not in ids(rules_only),
      "a numbered Rules list isn't mistaken for steps")

heading_steps = """---
name: h
description: d
---
## 1. Set up
Run `make setup` and confirm it exits 0.

### Detail under step one
More text.

## 2. Ship
Run `make ship`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| make fails | Install GNU make 4+ |
| ship hangs | Check the VPN, then rerun `make ship` |
"""
found = sl.lint_text(heading_steps)
check([f["check"] for f in found] == ["step-verifies"] and "Ship" in found[0]["message"],
      f"'## N. Title' headings are steps, sub-headings stay inside their step: {found}")
check(found[0]["line"] == 11, f"line numbers count the frontmatter: {found[0]['line']}")

anywhere = no_table + "\n## Reference\n\n| Error | What to do |\n|---|---|\n| 401 | Refresh the token with `demo login` |\n| 429 | Wait 60 s; lower `--rate` |\n"
check(ids(anywhere) == [], f"a failure/fix table under any heading counts: {ids(anywhere)}")
one_row = no_table + "\n## Errors\n\n| Error | Fix |\n|---|---|\n| 401 | Log in |\n"
check(ids(one_row) == ["error-recovery"], "a failure table needs at least two rows")

check(ids("# no frontmatter\n1. `a` check it\n") .count("frontmatter") == 1, "missing frontmatter is flagged")
long_desc = GOOD.replace("Does one job well.", "x" * 1100)
check("description-length" in ids(long_desc), "a description over 1,024 characters is flagged")
long_body = GOOD + "\n" * 520
check("body-length" in ids(long_body), "a body over 500 lines is flagged")

opt = no_table + "\n<!-- skill-lint: disable=error-recovery reason: a reference card -->\n"
check(ids(opt) == [], "a disable comment turns off the named check")
opt_all = no_steps.split("## When it fails")[0] + "<!-- skill-lint: disable -->"
check(ids(opt_all) == [], "a bare disable comment turns off every check")

# CLI, baseline and JSON
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    (d / "a").mkdir()
    (d / "b").mkdir()
    (d / "a" / "SKILL.md").write_text(GOOD)
    (d / "b" / "SKILL.md").write_text(no_table)
    run = lambda *x: subprocess.run([sys.executable, "-I", str(ROOT / "scripts/skill_lint.py"), *map(str, x)],
                                    capture_output=True, text=True, cwd=d)
    r = run(".")
    check(r.returncode == 1 and "2 skills, 1 with no findings, 1 findings" in r.stdout, f"report and exit 1: {r.stdout}")
    r = run(".", "--write-baseline", "base.json")
    check(r.returncode == 0 and json.loads((d / "base.json").read_text()) == {"b::error-recovery": 1}, "baseline written")
    r = run(".", "--baseline", "base.json")
    check(r.returncode == 0 and "0 new, 0 fixed" in r.stdout, f"known findings pass against the baseline: {r.stdout[-200:]}")
    (d / "a" / "SKILL.md").write_text(no_verify)
    r = run(".", "--baseline", "base.json")
    check(r.returncode == 1 and "NEW a::step-verifies (+1)" in r.stdout, f"a new finding fails: {r.stdout[-200:]}")
    (d / "a" / "SKILL.md").write_text(GOOD)
    (d / "b" / "SKILL.md").write_text(GOOD)
    r = run(".", "--baseline", "base.json")
    check(r.returncode == 0 and "1 fixed" in r.stdout, "fixes are reported, not failed")
    r = run("a", "--json")
    check(r.returncode == 0 and json.loads(r.stdout)["findings"] == [], "--json on a clean skill")

# mcp-config: a .mcp.json in the skill folder or at the plugin root is flagged
with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    sk = d / "plug" / "skills" / "s"
    sk.mkdir(parents=True)
    (sk / "SKILL.md").write_text(GOOD)
    (d / "plug" / ".claude-plugin").mkdir()
    (d / "plug" / ".claude-plugin" / "plugin.json").write_text("{}")
    check(sl.mcp_findings(sk / "SKILL.md", "s", GOOD) == [], "no .mcp.json, no mcp-config finding")
    (d / "plug" / ".mcp.json").write_text("{}")
    f = sl.mcp_findings(sk / "SKILL.md", "s", GOOD)
    check([x["check"] for x in f] == ["mcp-config"] and "plugin root" in f[0]["message"], "a plugin-root .mcp.json is flagged")
    (sk / ".mcp.json").write_text("{}")
    check(len(sl.mcp_findings(sk / "SKILL.md", "s", GOOD)) == 2, "a skill-folder .mcp.json is flagged too")
    opted = GOOD + "\n<!-- skill-lint: disable=mcp-config reason: the server is the product -->\n"
    check(sl.mcp_findings(sk / "SKILL.md", "s", opted) == [], "disable=mcp-config opts out")
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/skill_lint.py"), str(sk)], capture_output=True, text=True)
    check(r.returncode == 1 and "[mcp-config]" in r.stdout, f"the CLI reports mcp-config: {r.stdout[-200:]}")

# the repo's own baseline matches the skills as they are
r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts/skill_lint.py"), "plugins/",
                    "--baseline", "scripts/skill_lint_baseline.json"], capture_output=True, text=True, cwd=ROOT)
check(r.returncode == 0, f"top30's skills have no findings beyond the baseline: {r.stdout[-400:]}")
pc = ROOT / "plugins/top30-agents/skills/papercut"
if pc.exists():
    check(sl.lint_text((pc / "SKILL.md").read_text()) == [], "the papercut skill passes the linter with no findings")

print("OK" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
