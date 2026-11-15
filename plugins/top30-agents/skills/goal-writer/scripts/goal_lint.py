#!/usr/bin/env python3
"""Check a Claude Code /goal condition before you start it, and suggest a stronger one.

  goal_lint.py "all tests pass"                     lint a condition
  goal_lint.py --file goal.txt [--json]             lint one from a file
  goal_lint.py --recipes [name]                     ready-made conditions for data work
  goal_lint.py "..." --fail-on error                exit 1 on errors (for scripts and CI)

Why: /goal hands each turn to an evaluator model that reads only the conversation. It doesn't run
commands or open files, so a condition is only as good as the proof Claude puts in the transcript.
A strong condition has one measurable end state, a stated check that a program can fail, the
constraints that must hold on the way, and a bound. Standard library only.
"""
import argparse
import json
import re
import sys

MAX_CHARS = 4000  # the documented limit for a /goal condition
SEV = {"error": 0, "warn": 1, "info": 2}

CHECK_TOOLS = (r"pytest|unittest|tox|nox|npm (?:run )?test|pnpm test|yarn test|vitest|jest|go test|cargo test|mvn |gradle|"
               r"ruff|mypy|pyright|eslint|tsc|sqlfluff|dbt (?:build|test|run|compile)|terraform (?:validate|plan)|"
               r"tflint|pre-commit|shellcheck|actionlint|ora2sf|registry_kit|graph_check|kit\.py|git status|git diff|wc -l|grep|"
               r"make (?:test|check|lint|build|all|ci)|"
               r"snow sql|snowsql|curl|exit code|exits? (?:0|zero|non-?zero)|returns? 0")
CHECK = re.compile(rf"`[^`]+`|\b({CHECK_TOOLS})\b", re.I)
MEASURE = re.compile(r"\b(\d+|zero|no|none|every|all|each|empty|0)\b|exits? 0|is clean|passes|pass\b|green|match(es)?\b|under \d|below \d|at most|at least", re.I)
VAGUE = re.compile(r"\b(good|better|nice|(?<!is )(?<!are )clean(er)?|proper(ly)?|robust|optimi[sz]ed|fast(er)?|perfect|polished|production[- ]ready|"
                   r"high[- ]quality|reasonable|improved?|looks? (right|good|fine))\b", re.I)
BOUND = re.compile(r"\b(stop|give up|halt|end)\b[^.;]{0,40}\b(after|at)\b[^.;]{0,20}\b\d+\s*(turns?|rounds?|attempts?|minutes?|mins?|hours?|h\b|m\b)|"
                   r"\bwithin \d+\s*(turns?|minutes?|hours?)|\bat most \d+\s*(turns?|rounds?)", re.I)
CONSTRAINT = re.compile(r"\b(without|do not|don't|never|no other|no changes? to|read-only|only (?:change|touch|edit|modify)|"
                        r"only [\w ,/]{0,30} (?:may|can) change|must not|instead of|leave .{0,30} (?:unchanged|alone)|"
                        r"keep .{0,30} (?:unchanged|passing|as is))\b", re.I)
INVISIBLE = re.compile(r"\b(in the (?:browser|ui|dashboard)|visually|looks? (?:right|correct)|users? (?:are|can|will)|"
                       r"customers?|in production|stakeholders?|on staging)\b", re.I)
RISKY = re.compile(r"\b(deploy(?:ed|s)?|release|publish|push (?:to )?(?:main|master|prod)|force[- ]push|drop (?:table|schema|database)|"
                   r"truncate|delete from|merge into \w*prod|production (?:table|data|database)|backfill|send (?:email|message)s?|"
                   r"migrat(?:e|ion) (?:of |the )?prod)\w*", re.I)
IMPLIED = re.compile(r"\btests?\b[^.;]{0,40}\bpass|\bbuild[^.;]{0,20}\b(passes|succeeds)|\blint\b", re.I)
SELF_JUDGED = re.compile(r"\b(confident|you think|you believe|you're sure|seems done|feel(?:s)? done)\b", re.I)

RECIPES = {
    "pytest": ("Python tests",
               "Every test in tests/ passes: `pytest -q` exits 0 and its summary line is shown. Do not delete, skip or xfail "
               "existing tests or weaken their assertions. Or stop after 20 turns and report what still fails."),
    "dbt": ("dbt models",
            "`dbt build --select state:modified+` exits 0 with no test failures or warnings-as-errors shown in its summary. "
            "Do not change seeds, sources.yml freshness thresholds or existing tests to get there. Or stop after 25 turns."),
    "sqlfluff": ("SQL lint",
                 "`sqlfluff lint models/ --dialect snowflake` reports 0 violations. Only formatting and style may change: "
                 "no change to selected columns, joins, filters or results. Or stop after 15 turns."),
    "ora2sf": ("Oracle to Snowflake translation",
               "`python3 ora2sf.py legacy/sql --out ora2sf-out --fail-on error` exits 0 and the report's error count is 0. "
               "Fix the SQL, never the converter or its rules. Or stop after 20 turns and list the remaining errors."),
    "reconcile": ("Row-count reconciliation",
                  "For every table in recon/tables.txt, the source and target row counts and the SUM of the amount column printed by "
                  "`python3 recon.py --all` match exactly, and the script exits 0. Read-only: no DML or DDL on either system. "
                  "Or stop after 15 turns."),
    "types": ("Type checking",
              "`mypy src/` reports 'Success: no issues found'. Do not add `# type: ignore`, `Any` casts or exclude paths "
              "to get there. Or stop after 20 turns."),
    "file-size": ("Split a large file",
                  "src/pipeline.py is split into modules under src/pipeline/, `wc -l src/pipeline/*.py` shows every file under 300 "
                  "lines, and `pytest -q` still exits 0. Public function names and signatures don't change. Or stop after 30 turns."),
    "backlog": ("Work through a queue",
                "`gh issue list --label agent-ready --state open` returns no issues; each closed issue has a linked PR whose CI "
                "passed. Do not close issues that need a product decision: comment on them and move on. Or stop after 40 turns."),
}


def lint(cond):
    c = " ".join(cond.split())
    fs = []

    def add(sev, rule, msg):
        fs.append({"severity": sev, "rule": rule, "message": msg})

    if not c:
        add("error", "empty", "The condition is empty.")
        return fs
    if len(cond) > MAX_CHARS:
        add("error", "too-long", f"{len(cond)} characters: /goal accepts at most {MAX_CHARS}. Move background into a file and point to it.")
    has_check = bool(CHECK.search(c))
    if not has_check and IMPLIED.search(c):
        add("warn", "no-check", "The check is implied, not stated. Name the exact command so its output lands in the transcript, "
            "e.g. '`pytest -q tests/auth` exits 0'.")
    elif not has_check:
        add("error", "no-check", "No stated check. The evaluator reads only the conversation, so name the command whose output proves it, "
            "e.g. '`pytest -q` exits 0'.")
    if not MEASURE.search(c):
        add("error", "not-measurable", "No measurable end state (a count, 'all', 'zero', 'exits 0', 'passes').")
    v = sorted({m.group(0).lower() for m in VAGUE.finditer(c)})
    if v:
        add("warn", "vague", f"Vague words ({', '.join(v)}): the evaluator can't measure them. Replace each with a number or a check.")
    if SELF_JUDGED.search(c):
        add("error", "self-judged", "Asks for the model's own judgement ('confident', 'seems done'). That's the one signal a goal can't trust.")
    if INVISIBLE.search(c) and not has_check:
        add("warn", "invisible", "Depends on something outside the transcript (a UI, users, production). Turn it into a command whose output shows it.")
    elif INVISIBLE.search(c):
        add("info", "invisible", "Mentions something outside the transcript; make sure the check's output actually shows it.")
    if not BOUND.search(c):
        add("warn", "no-bound", "No bound. Add 'or stop after 20 turns' (and say what to report), so a stuck goal ends on its own.")
    if not CONSTRAINT.search(c):
        add("info", "no-constraint", "No constraints. Say what must not change on the way, e.g. 'do not delete or skip tests'.")
    ands = len(re.findall(r"\band\b|;", c))
    if ands >= 5:
        add("warn", "compound", f"{ands} joined requirements: one end state is easier to judge. Split into separate goals, or a checklist file and one check over it.")
    r = sorted({m.group(0).lower() for m in RISKY.finditer(c)})
    if r:
        add("warn", "irreversible", f"Mentions {', '.join(r)}. Goal turns can run unattended: keep irreversible steps out of the goal "
            "and do them yourself after it's achieved.")
    fs.sort(key=lambda f: SEV[f["severity"]])
    return fs


def score(fs):
    s = 100 - sum({"error": 30, "warn": 12, "info": 4}[f["severity"]] for f in fs)
    return max(0, s)


def suggest(cond, fs):
    rules = {f["rule"] for f in fs}
    if not rules & {"no-check", "not-measurable", "vague", "no-bound", "no-constraint", "self-judged"}:
        return None
    end = re.sub(r"\s+", " ", cond.strip().rstrip("."))
    parts = [end if "not-measurable" not in rules and "vague" not in rules else
             f"<one measurable end state for: {end}>"]
    if "no-check" in rules:
        parts.append("proven by `<command>` exiting 0, with its summary shown in the transcript")
    out = ", ".join(parts) + "."
    if "no-constraint" in rules:
        out += " Do not <what must not change, e.g. delete or skip tests>."
    if "no-bound" in rules:
        out += " Or stop after 20 turns and report what's left."
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("condition", nargs="?")
    ap.add_argument("--file")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--recipes", nargs="?", const="", metavar="NAME")
    ap.add_argument("--fail-on", choices=["error", "warn"])
    a = ap.parse_args(argv)
    if a.recipes is not None:
        if a.recipes:
            if a.recipes not in RECIPES:
                sys.exit(f"no recipe {a.recipes!r}; have: {', '.join(RECIPES)}")
            print(f"/goal {RECIPES[a.recipes][1]}")
            return
        for k, (title, body) in RECIPES.items():
            print(f"{k:10} {title}\n           /goal {body}\n")
        return
    cond = open(a.file).read() if a.file else a.condition
    if cond is None:
        ap.error("give a condition, --file, or --recipes")
    fs = lint(cond)
    sc, sug = score(fs), suggest(cond, fs)
    if a.json:
        print(json.dumps({"score": sc, "findings": fs, "suggestion": sug}, indent=1))
    else:
        print(f"goal_lint: score {sc}/100")
        for f in fs:
            print(f"  [{f['severity']}] {f['rule']}: {f['message']}")
        if sug:
            print(f"\nStronger shape:\n  /goal {sug}")
        if not fs:
            print("  Ready to run. For a check a program enforces (not a model's reading of the transcript), see goal_gate.py.")
    if a.fail_on and any(SEV[f["severity"]] <= SEV[a.fail_on] for f in fs):
        sys.exit(1)


if __name__ == "__main__":
    main()
