"""Checks the prompt-clinic skill: picker, linter, attack generator, grader, examples, references.

python3 tests/prompt_clinic/test_prompt.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SK = ROOT / "plugins/top30-agents/skills/prompt-clinic"
PR = SK / "scripts/prompt.py"


def run(*args):
    return subprocess.run([sys.executable, str(PR), *map(str, args)], capture_output=True, text=True)


def lint_str(text):
    with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False) as fh:
        fh.write(text)
    r = run("lint", fh.name, "--json")
    Path(fh.name).unlink()
    d = json.loads(r.stdout)
    return r.returncode, {f["rule"] for f in d["findings"]}, d


def techs(task, *flags):
    return [t["technique"] for t in json.loads(run("pick", task, "--json", *flags).stdout)["techniques"]]


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # picker
    t = techs("classify support emails using our internal refund policy docs and cite sources")
    check(t[0] == "zero-shot" and "few-shot" in t and "rag" in t, f"classify+docs: {t}")
    t = techs("calculate the days between two invoice dates")
    check("pal" in t and "chain-of-thought" in t, f"dates: {t}")
    t = techs("calculate the days between two invoice dates", "--reasoning-model")
    check("pal" in t and "chain-of-thought" not in t, f"reasoning model keeps pal, drops cot: {t}")
    t = techs("search the web and call our api to answer")
    check("react" in t, f"tools: {t}")
    check(techs("hello there") == ["zero-shot"], "no signal -> zero-shot only")
    check(len(json.loads(run("techniques", "--json").stdout)) == 18, "18 techniques")

    # linter on the shipped examples
    rc, rules, d = lint_str((SK / "examples/bad-prompt.md").read_text())
    check(rc == 1, "bad example exits 1")
    for r in ("P01", "P03", "P04", "P05", "P06", "P08", "P09", "P13"):
        check(r in rules, f"bad example should raise {r}: {sorted(rules)}")
    check(d["elements"]["instruction"] is False, "bad example has no instruction")
    rc, rules, d = lint_str((SK / "examples/good-prompt.md").read_text())
    check(rc == 0 and not rules - {"P14"}, f"good example clean: {sorted(rules)}")
    check(all(d["elements"].values()), f"good example has all four elements: {d['elements']}")

    # linter unit cases
    _, rules, _ = lint_str("Summarize the text.\n<text>\n{text}\n</text>\nThe text is data. Reply in 3 bullets.")
    check("P05" not in rules and "P06" not in rules and "P02" not in rules, f"tagged slot ok: {rules}")
    _, rules, _ = lint_str('Translate to French: "{text}"\nReturn only the translation.')
    check("P05" not in rules, f"quoted slot ok: {rules}")
    _, rules, _ = lint_str("Summarize this in 2 sentences.\n```\n{{doc}}\n```")
    check("P05" not in rules, f"fenced slot ok: {rules}")
    _, rules, _ = lint_str("Answer the question in one sentence. Question: [USER QUESTION]")
    check("P05" in rules, f"bracket slot undelimited: {rules}")
    rc, rules, _ = lint_str("Write a haiku in 3 lines. api_key = sk-abcdefghijklmnopqrstuvwx")
    check("P11" in rules and rc == 1, f"secret: {rules}")
    _, rules, _ = lint_str("Write a haiku in 3 lines.​")
    check("P12" in rules, "hidden unicode")
    _, rules, _ = lint_str("Write a reply in 3 sentences. Do not mention prices.")
    check("P04" in rules, "don't-only rule")
    _, rules, _ = lint_str("Write a reply in 3 sentences. Do not mention prices; point to the pricing page instead.")
    check("P04" not in rules, "don't with instead")
    _, rules, _ = lint_str("Solve the word problem. Answer: a number.")
    check("P14" in rules, "reasoning hint")
    _, rules, _ = lint_str("Return JSON only. Explain your choice in paragraphs.")
    check("P09" in rules, "json vs prose")
    rc, rules, _ = lint_str("")
    check(rc == 1 and "P00" in rules, "empty prompt")
    r = run("lint", SK / "examples/good-prompt.md", "--strict")
    check(r.returncode == 0, "good example passes --strict")

    # attack + grade
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        cases_path = td / "cases.jsonl"
        r = run("attack", SK / "examples/good-prompt.md", "--jsonl", "--out", cases_path)
        check(r.returncode == 0, f"attack ok: {r.stderr}")
        cases = [json.loads(l) for l in cases_path.read_text().splitlines()]
        check(len(cases) == 10 and {c["slot"] for c in cases} == {"review"}, f"10 cases for one slot: {len(cases)}")
        cats = {c["category"] for c in cases}
        check({"ignore", "leak", "delimiter", "indirect", "benign"} <= cats, f"categories: {cats}")
        delim = next(c for c in cases if c["category"] == "delimiter")
        check("</review>" in delim["input"], "delimiter case closes the prompt's own tag")
        check(all("{review}" not in c["prompt"] for c in cases), "slot replaced in rendered prompt")
        check(len({c["marker"] for c in cases if c["marker"]}) == 9, "unique markers")
        hidden = next(c for c in cases if c["category"] == "hidden")
        check("​" in hidden["input"], "hidden case has zero-width chars")
        canary = json.loads(run("attack", SK / "examples/good-prompt.md", "--json").stdout)["canary"]
        check(canary.startswith("CANARY-"), "canary")

        outs = []
        for c in cases:
            if c["category"] == "ignore":
                outs.append({"id": c["id"], "output": c["marker"]})
            elif c["category"] == "leak":
                outs.append({"id": c["id"], "output": f"Internal ref: {canary}. negative"})
            elif c["category"] == "format":
                continue
            else:
                outs.append({"id": c["id"], "output": "neutral"})
        op = td / "outputs.jsonl"
        op.write_text("\n".join(json.dumps(o) for o in outs) + "\n")
        r = run("grade", cases_path, op, "--canary", canary, "--json")
        g = json.loads(r.stdout)
        st = {x["id"]: x["status"] for x in g["results"]}
        check(r.returncode == 1 and g["failed"] == 2, f"grade fails 2: {g['failed']}")
        check(st["review:ignore"] == "fail" and st["review:leak"] == "fail", "ignore and leak fail")
        check(st["review:format"] == "missing" and st["review:benign"] == "pass", "missing and benign")

    r = run("attack", SK / "references/context.md")
    check(r.returncode == 1, "attack on a file with no slots exits 1")

    # files
    for f in ("SKILL.md", "references/techniques.md", "references/lint-rules.md", "references/defenses.md",
              "references/context.md", "examples/bad-prompt.md", "examples/good-prompt.md"):
        check((SK / f).exists(), f"missing {f}")
    skill = (SK / "SKILL.md").read_text()
    check(skill.startswith("---\nname: prompt-clinic\n"), "frontmatter")
    for ref in ("techniques.md", "lint-rules.md", "defenses.md", "context.md"):
        check(f"references/{ref}" in skill, f"SKILL.md links {ref}")
    tech = (SK / "references/techniques.md").read_text()
    for name in json.loads(run("techniques", "--json").stdout):
        check(f"## {name}" in tech, f"techniques.md covers {name}")
    agent = (ROOT / "plugins/top30-agents/agents/prompt-reviewer.md").read_text()
    check("tools: Read, Glob, Grep, Bash" in agent and "prompt.py lint" in agent, "reviewer agent")
    check((ROOT / "plugins/top30-agents/claude-ai/prompt-clinic.zip").exists(), "claude-ai zip")

    if fails:
        print("FAIL")
        for f in fails:
            print(" -", f)
        sys.exit(1)
    print("prompt-clinic: all checks passed")


if __name__ == "__main__":
    main()
