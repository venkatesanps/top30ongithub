"""Package selected skills as Claude.ai-uploadable zips (one skill folder per zip).
Validates SKILL.md frontmatter (name + description) and reports sizes.
Usage: python3 -I pack_claude_ai.py <repos_dir> <out_dir>
"""
import os, sys, re, shutil, zipfile, json

R, OUT = sys.argv[1], sys.argv[2]
EXCLUDE_DIRS = {".git", "node_modules", "__pycache__", "tests", "test", "evals", ".github", ".pytest_cache"}

SETS = [
    ("01-karpathy", "andrej-karpathy-skills/skills", ["karpathy-guidelines"]),
    ("02-mattpocock", "mattpocock-skills/skills", ["productivity/grill-me", "engineering/tdd", "engineering/to-spec",
        "engineering/diagnosing-bugs", "engineering/code-review", "engineering/domain-modeling", "productivity/handoff", "productivity/teach"]),
    ("04-agent-skills", "agent-skills/skills", ["spec-driven-development", "planning-and-task-breakdown", "code-review-and-quality",
        "debugging-and-error-recovery", "security-and-hardening", "api-and-interface-design", "documentation-and-adrs", "idea-refine", "interview-me"]),
    ("05-superpowers", "superpowers/skills", ["brainstorming", "writing-plans", "executing-plans", "systematic-debugging",
        "test-driven-development", "verification-before-completion", "requesting-code-review", "receiving-code-review"]),
    ("06-ponytail", "ponytail/skills", ["ponytail", "ponytail-review"]),
    ("17-caveman", "caveman/skills", ["caveman"]),
    ("19-taste", "taste-skill/skills", ["taste-skill"]),
    ("20-archify", "archify", ["archify"]),
    ("21-diagram-design", "diagram-design/skills", ["diagram-design"]),
    ("22-impeccable", "impeccable/plugin/skills", ["impeccable"]),
    ("23-ui-ux-pro-max", "ui-ux-pro-max-skill/.claude/skills", ["ui-ux-pro-max"]),
    ("25-marketing", "marketingskills/skills", None),  # all
    ("28-humanizer", "humanizer", ["."]),
    ("30-i-have-adhd", "i-have-adhd/skills", ["i-have-adhd"]),
]

def frontmatter(p):
    t = open(p, encoding="utf-8", errors="replace").read()
    m = re.match(r"^---\s*\n(.*?)\n---", t, re.S)
    if not m: return None, None
    fm = m.group(1)
    name = re.search(r"^name:\s*(.+)$", fm, re.M)
    desc = re.search(r"^description:\s*(.*)$", fm, re.M)
    return (name.group(1).strip().strip("'\"") if name else None), (desc is not None)

report, names = [], {}
shutil.rmtree(OUT, ignore_errors=True)
for folder, base, skills in SETS:
    basep = os.path.join(R, base)
    if skills is None:
        skills = sorted(d for d in os.listdir(basep) if os.path.isfile(os.path.join(basep, d, "SKILL.md")))
    os.makedirs(os.path.join(OUT, folder), exist_ok=True)
    for s in skills:
        src = os.path.normpath(os.path.join(basep, s))
        sk = os.path.join(src, "SKILL.md")
        name, has_desc = frontmatter(sk)
        if not name or not has_desc:
            report.append((folder, s, "SKIP: bad frontmatter", 0)); continue
        if name in names:
            report.append((folder, s, f"SKIP: duplicate name '{name}' (kept {names[name]})", 0)); continue
        names[name] = folder
        zpath = os.path.join(OUT, folder, f"{name}.zip")
        with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
            for root, dirs, files in os.walk(src, followlinks=True):
                dirs[:] = [d for d in dirs if d not in EXCLUDE_DIRS]
                for f in files:
                    if src.endswith("humanizer") and not (root == src and f == "SKILL.md"):
                        continue  # repo root: ship only the skill file
                    full = os.path.join(root, f)
                    arc = os.path.join(name, os.path.relpath(full, src))
                    z.write(full, arc)
        report.append((folder, s, "ok", os.path.getsize(zpath)))

ok = [r for r in report if r[2] == "ok"]
print(f"{len(ok)} zips built")
for r in report:
    if r[2] != "ok": print("  ", r)
big = sorted(ok, key=lambda r: -r[3])[:6]
print("largest:", [(r[1], round(r[3]/1e6, 1)) for r in big])
json.dump([{"folder": f, "skill": s, "status": st, "bytes": b} for f, s, st, b in report], open(os.path.join(OUT, "_manifest.json"), "w"), indent=1)
