#!/usr/bin/env python3
"""Lint Agent Skills (SKILL.md folders) for the habits that make them hold up in real runs.

    python3 scripts/skill_lint.py plugins/                 # report every skill under a folder
    python3 scripts/skill_lint.py path/to/my-skill --json  # one skill, machine-readable
    python3 scripts/skill_lint.py plugins/ --baseline scripts/skill_lint_baseline.json   # CI: fail on new findings only
    python3 scripts/skill_lint.py plugins/ --write-baseline scripts/skill_lint_baseline.json

The checks follow Uber's description of the linter behind its internal skills marketplace
("How Uber Evals 1 Million Agent Skill Invocations a Month", November 23, 2026,
https://www.uber.com/us/en/blog/optimizing-ubers-agent-skills/). The post describes the rules, not an implementation;
these are heuristics written to match it:

  numbered-steps      the procedure is written as numbered steps
  step-verifies       each step says how to check its result (soft verification is fine)
  step-command        each step gives a concrete command, in `code` or a fenced block
  error-recovery      a table of failures and their fixes
  retry-only-fix      a fix that only says "try again" doesn't count
  body-length         the body stays under 500 lines (it loads in full whenever the skill runs)
  description-length  the description stays under 1,024 characters (it is always loaded)
  frontmatter         name and description are present
  mcp-config          no .mcp.json in the skill folder or its plugin root: Uber blocks these because
                      installed MCP tool definitions preload into every session (100+ tools cost
                      50,000-70,000 tokens); call tools from scripts instead

Steps are "## 1. Title" style headings, or top-level numbered list items (lists under headings
such as Rules, Don'ts or Notes are not steps). Code fences are ignored when looking for headings,
lists and tables, but code inside a step counts as its command.

A skill that isn't a procedure can opt out of checks with a comment anywhere in SKILL.md:
    <!-- skill-lint: disable=step-command,error-recovery  reason: reference card, no commands -->
`disable` with no list turns off every check. Python standard library only.
"""
import argparse
import json
import re
import sys
from pathlib import Path

CHECKS = ("numbered-steps", "step-verifies", "step-command", "error-recovery", "retry-only-fix",
          "body-length", "description-length", "frontmatter", "mcp-config")
STEP_HEADING = re.compile(r"^(#{2,4})\s+(?:step\s+)?(\d+)[.:)]?\s+\S", re.I)
HEADING = re.compile(r"^(#{1,6})\s+(.*)")
LIST_ITEM = re.compile(r"^ ?(\d+)[.)]\s+\S")
NOT_STEPS = re.compile(r"\b(rules?|don'?ts?|principles?|notes?|tips?|why|corrections?|references?|sources?|"
                       r"what (?:it|the \w+) (?:checks|finds|does)|examples?|key terms|glossary|faq|limits?)\b", re.I)
ERROR_HEADING = re.compile(r"\b(errors?|failures?|fail(?:s|ing)?|troubleshoot\w*|recover\w*|goes wrong|"
                           r"breaks?|problems?|common issues|fixing)\b", re.I)
ERROR_TABLE_HEAD = re.compile(r"\b(error|failure|fails|symptom|problem|when|if|what happens)\b", re.I)
FIX_TABLE_HEAD = re.compile(r"\b(fix|recovery|resolution|what to do|do|action|then|remedy|response)\b", re.I)
VERIFY = re.compile(
    r"\b(check(?:s|ed)?|verif\w*|confirm\w*|expect\w*|assert\w*|ensure|make sure|validat\w*|compare\w*|"
    r"test(?:s|ed)?|pass(?:es|ed)?|fail(?:s|ed|ure)?|until|exit(?:s)?\s*(?:code\s*)?0|exit 0|"
    r"should (?:print|return|show|list|say|be|exit|pass|match|contain)|look for|success\w*|"
    r"if (?:it|this|that|the \w+) (?:errors?|returns?|is empty|shows?))\b", re.I)
RETRY_ONLY = re.compile(r"^(?:just |simply )?(?:try again|retry|re-?run(?: it)?|run (?:it )?again)(?: later)?$", re.I)
DISABLE = re.compile(r"<!--\s*skill-lint:\s*disable(?:\s*=\s*([\w,\- ]+?))?(?:\s+reason:.*?)?\s*-->", re.I | re.S)


def split_frontmatter(text):
    m = re.match(r"---\n(.*?)\n---\n?", text, re.S)
    if not m:
        return {}, text, 0
    fm, block = {}, m.group(1)
    for key in ("name", "description"):
        km = re.search(rf"^{key}:\s*(.*(?:\n[ \t]+.*)*)", block, re.M)
        if km:
            fm[key] = re.sub(r"\s+", " ", km.group(1)).strip().strip("\"'>| ")
    return fm, text[m.end():], text[:m.end()].count("\n")


def mark_fences(lines):
    """True for lines inside (or delimiting) a fenced code block."""
    out, fence = [], None
    for ln in lines:
        s = ln.lstrip()
        m = re.match(r"(`{3,}|~{3,})", s)
        if fence is None and m:
            fence = m.group(1)[0] * len(m.group(1))
            out.append(True)
        elif fence is not None:
            out.append(True)
            if s.startswith(fence) and s.strip() == fence[0] * len(s.strip()):
                fence = None
        else:
            out.append(False)
    return out


def headings(lines, fenced):
    hs = []
    for i, ln in enumerate(lines):
        if fenced[i]:
            continue
        m = HEADING.match(ln)
        if m:
            hs.append((i, len(m.group(1)), m.group(2).strip()))
    return hs


def heading_above(hs, i):
    best = None
    for j, lvl, title in hs:
        if j < i:
            best = (j, lvl, title)
    return best


def find_steps(lines, fenced, hs):
    """List of (start, end, title) for each step; end is exclusive."""
    steps = []
    for k, (i, lvl, title) in enumerate(hs):
        if STEP_HEADING.match(lines[i]):
            end = next((j for j, l2, _ in hs[k + 1:] if l2 <= lvl), len(lines))
            steps.append((i, end, title))
    if steps:
        return steps
    i = 0
    while i < len(lines):
        if fenced[i] or not LIST_ITEM.match(lines[i]):
            i += 1
            continue
        above = heading_above(hs, i)
        if above and NOT_STEPS.search(above[2]):
            i += 1
            continue
        start = i
        i += 1
        while i < len(lines):  # the item runs until the next top-level item, heading or unindented text
            ln = lines[i]
            if not fenced[i] and (LIST_ITEM.match(ln) or HEADING.match(ln)):
                break
            if not fenced[i] and ln.strip() and not ln.startswith((" ", "\t")) and not lines[i - 1].strip() \
                    and not (i + 1 < len(lines) and lines[i + 1].startswith((" ", "\t"))):
                break
            i += 1
        steps.append((start, i, re.sub(r"^ ?\d+[.)]\s+", "", lines[start]).strip()))
    return steps


def table_rows(lines, fenced, start, end):
    """Markdown tables in lines[start:end] as lists of rows of cells (header first, separator dropped)."""
    tables, cur = [], []
    for i in range(start, end):
        ln = lines[i].strip()
        if not fenced[i] and ln.startswith("|") and ln.count("|") >= 2:
            cells = [c.strip() for c in ln.strip("|").split("|")]
            if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                cur.append(cells)
        else:
            if cur:
                tables.append(cur)
            cur = []
    if cur:
        tables.append(cur)
    return tables


def error_tables(lines, fenced, hs):
    found = []
    for k, (i, lvl, title) in enumerate(hs):
        if ERROR_HEADING.search(title):
            end = next((j for j, l2, _ in hs[k + 1:] if l2 <= lvl), len(lines))
            found += [t for t in table_rows(lines, fenced, i + 1, end) if len(t) >= 3]
    for t in table_rows(lines, fenced, 0, len(lines)):
        head = " ".join(t[0])
        if len(t) >= 3 and ERROR_TABLE_HEAD.search(head) and FIX_TABLE_HEAD.search(head) and t not in found:
            found.append(t)
    return found


def plain(cell):
    return re.sub(r"[`*_.!]", "", cell).strip().lower()


def lint_text(text, rel="SKILL.md"):
    fm, body, offset = split_frontmatter(text)
    disabled = set()
    for m in DISABLE.finditer(body):
        names = {x.strip().lower() for x in (m.group(1) or "").split(",") if x.strip()}
        disabled |= names or set(CHECKS)
    lines = body.split("\n")
    fenced = mark_fences(lines)
    hs = headings(lines, fenced)
    findings = []

    def add(check, line, msg):
        if check not in disabled:
            findings.append({"skill": rel, "check": check, "line": line + offset + 1 if line is not None else None,
                             "message": msg})

    if not fm.get("name") or not fm.get("description"):
        add("frontmatter", None, "frontmatter needs both name and description")
    if len(fm.get("description", "")) > 1024:
        add("description-length", None, f"description is {len(fm['description'])} characters; keep it under 1,024 "
                                         "(it is loaded in every session)")
    if len(lines) > 500:
        add("body-length", None, f"body is {len(lines)} lines; keep it under 500 and move detail into references/")

    steps = find_steps(lines, fenced, hs)
    if not steps:
        add("numbered-steps", None, "no numbered steps: write the procedure as '1. ...' items or '## 1. ...' headings")
    for s, e, title in steps:
        chunk = "\n".join(lines[s:e])
        name = title[:60]
        if not VERIFY.search(chunk):
            add("step-verifies", s, f"step '{name}' doesn't say how to check its result")
        if "`" not in chunk:
            add("step-command", s, f"step '{name}' gives no concrete command (`code` or a fenced block)")

    tables = error_tables(lines, fenced, hs)
    if not tables:
        add("error-recovery", None, "no failure-and-fix table (e.g. '## When it fails' with | Failure | Fix |)")
    for t in tables:
        for row in t[1:]:
            if row and RETRY_ONLY.match(plain(row[-1])):
                add("retry-only-fix", None, f"fix for '{row[0][:50]}' only says '{row[-1]}': say what to change first")
    return findings


def mcp_findings(path, rel_dir, text):
    """A .mcp.json next to the skill, or at the root of the plugin that ships it."""
    m = re.search(r"<!--\s*skill-lint:\s*disable(?:=([\w,\- ]+))?", text)
    if m and (not m.group(1) or "mcp-config" in [x.strip() for x in re.split(r"[ ,]+", m.group(1))]):
        return []
    out, seen = [], set()
    d = path.resolve().parent
    candidates = [d / ".mcp.json"]
    for anc in d.parents:
        if (anc / ".claude-plugin" / "plugin.json").is_file():
            candidates.append(anc / ".mcp.json")
            break
    for c in candidates:
        if c.is_file() and c not in seen:
            seen.add(c)
            where = "the skill folder" if c.parent == d else f"its plugin root ({c.parent.name})"
            out.append({"skill": rel_dir, "check": "mcp-config", "line": 0,
                        "message": f".mcp.json in {where} installs MCP servers whose tool definitions load into "
                                   "every session; call the tool from a script instead, or document why it's needed"})
    return out


def find_skills(paths):
    out = []
    for p in paths:
        p = Path(p)
        if p.is_file() and p.name == "SKILL.md":
            out.append(p)
        elif (p / "SKILL.md").is_file():
            out.append(p / "SKILL.md")
        elif p.is_dir():
            out += sorted(x for x in p.rglob("SKILL.md") if "node_modules" not in x.parts and ".git" not in x.parts)
    return out


def rel(p):
    try:
        return p.resolve().relative_to(Path.cwd().resolve()).parent.as_posix()
    except ValueError:
        return p.resolve().parent.as_posix()


def counts(findings):
    c = {}
    for f in findings:
        key = f"{f['skill']}::{f['check']}"
        c[key] = c.get(key, 0) + 1
    return dict(sorted(c.items()))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", help="skill folders, SKILL.md files, or folders to search")
    ap.add_argument("--json", action="store_true", help="print findings as JSON")
    ap.add_argument("--baseline", help="JSON of accepted findings (skill::check -> count); fail only on new ones")
    ap.add_argument("--write-baseline", help="write the current findings as the baseline and exit 0")
    a = ap.parse_args(argv)

    skills = find_skills(a.paths)
    if not skills:
        sys.exit("no SKILL.md found")
    findings = []
    for p in skills:
        text = p.read_text(encoding="utf-8", errors="replace")
        findings += lint_text(text, rel(p))
        findings += mcp_findings(p, rel(p), text)
    now = counts(findings)
    if a.write_baseline:
        Path(a.write_baseline).write_text(json.dumps(now, indent=1) + "\n")
        print(f"baseline: {len(skills)} skills, {len(findings)} findings written to {a.write_baseline}")
        return 0
    base = json.loads(Path(a.baseline).read_text()) if a.baseline else None
    new = {k: v - (base or {}).get(k, 0) for k, v in now.items() if v > (base or {}).get(k, 0)} if base is not None else now
    fixed = {k: v for k, v in (base or {}).items() if now.get(k, 0) < v}

    if a.json:
        print(json.dumps({"skills": len(skills), "findings": findings, "new": new, "fixed": fixed}, indent=1))
    else:
        by_skill = {}
        for f in findings:
            by_skill.setdefault(f["skill"], []).append(f)
        clean = len(skills) - len(by_skill)
        for skill, fs in by_skill.items():
            print(f"\n{skill}")
            for f in fs:
                where = f":{f['line']}" if f["line"] else ""
                print(f"  [{f['check']}]{where} {f['message']}")
        per_check = {c: sum(1 for f in findings if f["check"] == c) for c in CHECKS}
        print(f"\n{len(skills)} skills, {clean} with no findings, {len(findings)} findings: "
              + ", ".join(f"{c} {n}" for c, n in per_check.items() if n))
        if base is not None:
            print(f"against the baseline: {sum(new.values())} new, {sum(fixed.values())} fixed"
                  + ("" if not fixed else " (run --write-baseline to lock in the fixes)"))
            for k, v in new.items():
                print(f"  NEW {k} (+{v})")
    if base is not None:
        return 1 if new else 0
    return 1 if findings else 0


if __name__ == "__main__":
    sys.exit(main())
