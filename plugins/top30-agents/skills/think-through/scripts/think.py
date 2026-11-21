#!/usr/bin/env python3
"""Helpers for the think-through skill: pick thinking modes for a prompt, print a ledger
skeleton, and lint a finished ledger so "I thought it through" is checkable.

  think.py route "the user's prompt" [--json]     # suggested depth and mode chain
  think.py template frame,widen,weigh,commit      # ledger skeleton for a chain
  think.py lint LEDGER.md [--json]                 # did the thinking actually happen?
  think.py modes                                   # the ten modes, one line each

Standard library only. Routing is keyword heuristics: a starting point the agent may
override, saying why.
"""
import argparse
import json
import re
import sys
from pathlib import Path

MODES = {
    "frame": "Name the real goal, the unit of analysis, hard vs assumed constraints; change the frame if it hides the answer.",
    "widen": "Generate structurally different options (invert, subtract, change scale, actor, time, medium) before judging any.",
    "diagnose": "Turn symptoms into competing causes; find the cheapest check that tells them apart.",
    "check": "Verify the claims the answer rests on with tests, sources, numbers or tools; label what stays unverified.",
    "fresh": "Find facts that may have changed since training (versions, prices, people, APIs, laws) and look them up.",
    "weigh": "Pick criteria for this goal, weight them, score options with evidence; a critical fail can't be outvoted.",
    "commit": "Choose one option, state the main tradeoff and what would change the choice; or name the cheap test first.",
    "taste": "Fix a point of view and the job the form must do, then judge or shape concrete choices against it.",
    "pushback": "Test whether you're agreeing because the user said so: steelman the case against their premise.",
    "integrate": "Merge the modes' results into one through-line, keeping the tension or exception that matters.",
}
ORDER = ["frame", "diagnose", "widen", "fresh", "check", "weigh", "taste", "pushback", "commit", "integrate"]

RULES = [
    # (name, regex, modes)
    ("bug", r"\b(bug|error|fail(s|ing|ed)?|broken|crash\w*|regress\w*|flaky|why (does|is|did)|not working|stack ?trace|exception|slow(er)?|timeout)\b",
     ["diagnose", "check"]),
    ("decision", r"\b(should (we|i)|vs\.?|versus|which (one|is better)|choose|pick|worth it|port (it )?to|migrate|adopt|or not|trade-?offs?)\b",
     ["frame", "weigh", "commit"]),
    ("design", r"\b(design|architect\w*|concepts?|ideas?|brainstorm|name (for|it)|naming|propose|come up with|make .* (simpler|better|more secure))\b",
     ["frame", "widen", "weigh", "integrate"]),
    ("review", r"\b(review|critique|audit|assess|evaluate|feedback on|what('s| is) wrong with|poke holes)\b",
     ["frame", "weigh", "check"]),
    ("aesthetic", r"\b(landing|logo|look(s)? (good|nice|professional)|visual|ui|ux|tone|voice|copy|typography|colou?rs?|brand|feel|aesthetic|stand out)\b",
     ["taste"]),
    ("plan", r"\b(plan|roadmap|what (should|do) we do next|next steps?|priorit\w*|strategy)\b",
     ["frame", "weigh", "commit"]),
    ("fresh", r"\b(latest|current(ly)?|newest|today|this (year|month|week)|recent(ly)?|now|still|pric(e|es|ing)|version|release|20[2-3]\d|deprecated)\b",
     ["fresh"]),
    ("premise", r"\b(obviously|clearly|surely|everyone knows|just need to|simply|right\?|isn't it|don't you (think|agree)|i('m| am) sure|always|never)\b",
     ["pushback"]),
]
SIMPLE = re.compile(r"^\s*(what('s| is) (the )?\w+( of)?|define|convert|rename|format|fix (the )?typo|how many|when (was|is))\b", re.I)


def route(prompt):
    p = prompt.lower()
    hits, modes = [], []
    for name, rx, ms in RULES:
        if re.search(rx, p):
            hits.append(name)
            modes += ms
    words = len(prompt.split())
    if not hits and (SIMPLE.search(prompt) or words < 8):
        return {"depth": "skip", "modes": [], "why": ["looks like a simple or mechanical request; just answer"], "signals": []}
    if not hits:
        modes = ["frame", "weigh", "commit"]
        hits = ["open-ended"]
    if "check" not in modes and any(h in hits for h in ("design", "plan", "decision")):
        modes.append("check")
    if len(set(m for m in modes if m not in ("fresh", "pushback"))) >= 3:
        modes.append("integrate")
    chain = [m for m in ORDER if m in set(modes)]
    stakes = re.search(r"\b(prod(uction)?|security|secure|money|legal|compliance|irreversible|delete|migrat\w*|customers?|outage|rewrite|port)\b", p)
    depth = "deep" if (len(chain) >= 5 or stakes) else "standard" if len(chain) >= 3 else "quick"
    why = [f"{h}: " + ", ".join(m for m in dict(RULES_BY_NAME)[h]) for h in hits if h in RULES_BY_NAME]
    if stakes:
        why.append(f"stakes word '{stakes.group(0)}': deep, keep a ledger file and run the auditor")
    return {"depth": depth, "modes": chain, "why": why, "signals": hits}


RULES_BY_NAME = {n: ms for n, _, ms in RULES}

LEDGER_HELP = {
    "frame": ["goal:", "real goal:", "constraints (hard):", "assumed:", "frame change:"],
    "widen": ["option A:", "option B:", "option C:", "operators used:"],
    "diagnose": ["expected vs observed:", "H1:", "H2:", "discriminating check:"],
    "check": ["claim: ... [verified: how]", "claim: ... [unverified: why]"],
    "fresh": ["time-sensitive: ... [checked: source, date]"],
    "weigh": ["criteria (weight):", "scores:", "critical fails:"],
    "commit": ["choice:", "tradeoff:", "would change if:"],
    "taste": ["point of view:", "job of the form:", "strongest change:"],
    "pushback": ["user premise:", "case against:", "verdict: holds | partly | wrong"],
    "integrate": ["through-line:", "tension kept:", "uncertainty shown:"],
}


def template(chain, prompt=""):
    out = ["# Think ledger", "", f"prompt: {prompt or '<the request, one line>'}", "depth: <quick|standard|deep>", "",
           "## Orient", "goal: ", "likely failure if answered fast: ", "evidence that could change the answer: ", "output: ", ""]
    for m in chain:
        out.append(f"## [ ] {m}")
        out += [f"- {line} " for line in LEDGER_HELP[m]]
        out += ["carry: ", ""]
    out += ["## Answer check", "- every load-bearing claim tagged [verified]/[unverified]/[assumed]",
            "- what would change my mind: ", ""]
    return "\n".join(out)


PLACEHOLDERS = {h.strip() for hs in LEDGER_HELP.values() for h in hs if "..." in h or "|" in h}

TAG = re.compile(r"\[(verified|unverified|assumed|checked)\b[^\]]*\]", re.I)


def parse(text):
    sections, cur = {}, None
    for line in text.splitlines():
        m = re.match(r"^##\s*(\[( |x|X|-)\])?\s*([A-Za-z-]+)\b", line)
        if m:
            cur = m.group(3).lower()
            sections[cur] = {"state": (m.group(2) or "").lower(), "lines": []}
            continue
        if cur and line.strip().lstrip("-* ").strip() not in PLACEHOLDERS:
            sections[cur]["lines"].append(line)
    return sections


def filled(lines, key):
    for ln in lines:
        s = ln.strip().lstrip("-* ").strip()
        if s.lower().startswith(key.lower()):
            rest = s[len(key):].strip()
            if rest and not rest.startswith("...") and not rest.startswith("<"):
                return rest
    return None


def lint(text):
    fs = []

    def add(sev, where, msg):
        fs.append({"severity": sev, "where": where, "msg": msg})
    sec = parse(text)
    modes = [k for k in sec if k in MODES]
    if not modes:
        add("error", "ledger", "no mode sections (## [x] frame, ## [x] weigh, ...)")
    orient = sec.get("orient")
    if not orient:
        add("warn", "orient", "no Orient section: goal and likely failure were never written down")
    else:
        for k in ("goal:", "likely failure if answered fast:"):
            if not filled(orient["lines"], k):
                add("warn", "orient", f"'{k}' is empty")
    for m in modes:
        s = sec[m]
        body = "\n".join(s["lines"])
        if s["state"] != "x":
            add("warn", m, "mode not marked done ([x]); say why if you stopped")
        if not filled(s["lines"], "carry:"):
            add("warn", m, "no 'carry:' line: what does this mode hand to the next one?")
        if m == "frame" and not (filled(s["lines"], "real goal:") or filled(s["lines"], "goal:")):
            add("warn", m, "frame without a goal")
        if m == "widen":
            opts = [ln for ln in s["lines"] if re.match(r"\s*[-*]\s*option\s+\w+:\s*\S", ln, re.I)]
            if len(opts) < 2:
                add("error", m, f"widen produced {len(opts)} option(s); need 2+ structurally different ones")
        if m == "diagnose":
            hyps = re.findall(r"^\s*[-*]\s*H\d+:\s*\S", body, re.M)
            if len(hyps) < 2:
                add("error", m, "one hypothesis is a story, not a diagnosis; list 2+ competing causes")
            if not filled(s["lines"], "discriminating check:"):
                add("warn", m, "no discriminating check: what evidence separates the hypotheses?")
        if m == "check":
            tags = TAG.findall(body)
            if not tags:
                add("error", m, "check mode with no claim tagged [verified: how] or [unverified: why]")
            v = [t for t in TAG.finditer(body) if t.group(1).lower() == "verified"]
            for t in v:
                if t.group(0).lower().strip("[]").strip() == "verified":
                    add("warn", m, "[verified] with no method; say how (test, source, run, calc)")
                    break
        if m == "fresh":
            if not re.search(r"\[(checked|verified)[^\]]*\]|\bno time-sensitive\b", body, re.I):
                add("error", m, "fresh mode found nothing checked: tag each fact [checked: source, date] or write 'no time-sensitive facts'")
        if m == "weigh":
            if not re.search(r"\(\s*(critical|high|medium|low|pass[/-]fail|\d+%?)\s*\)", body, re.I):
                add("warn", m, "criteria have no weights: (critical), (high), (low) ...")
        if m == "commit":
            if not filled(s["lines"], "choice:"):
                add("error", m, "commit mode with no choice")
            if not filled(s["lines"], "would change if:"):
                add("warn", m, "no 'would change if:' - name the evidence that flips the call")
            if not filled(s["lines"], "tradeoff:"):
                add("warn", m, "no tradeoff named")
            c = filled(s["lines"], "choice:") or ""
            if re.search(r"\b(it depends|both|either)\b", c, re.I) and not re.search(r"\bif\b", c, re.I):
                add("warn", m, "the choice hedges ('it depends', 'both'); commit, or give the rule that decides")
        if m == "pushback":
            v = filled(s["lines"], "verdict:")
            if not v or not re.match(r"(holds|partly|wrong)", v, re.I):
                add("error", m, "pushback needs 'verdict: holds | partly | wrong'")
            if not filled(s["lines"], "case against:"):
                add("error", m, "no case against the premise was written")
        if m == "taste" and not filled(s["lines"], "point of view:"):
            add("warn", m, "taste with no point of view is just preference")
        if m == "integrate" and not filled(s["lines"], "through-line:"):
            add("warn", m, "integrate with no through-line")
    untagged = 0
    for ln in text.splitlines():
        if re.match(r"\s*[-*]\s*claim:", ln, re.I) and not TAG.search(ln):
            untagged += 1
    if untagged:
        add("warn", "claims", f"{untagged} claim line(s) without [verified]/[unverified]/[assumed]")
    ac = sec.get("answer")
    if ac is not None and not filled(ac["lines"], "what would change my mind:"):
        add("info", "answer", "no 'what would change my mind'")
    if "check" not in modes and "fresh" not in modes and len(modes) >= 3:
        add("info", "ledger", "3+ modes and nothing checked against outside evidence; is that right?")
    return fs, modes


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("route")
    r.add_argument("prompt", nargs="+")
    r.add_argument("--json", action="store_true")
    t = sub.add_parser("template")
    t.add_argument("chain")
    t.add_argument("--prompt", default="")
    li = sub.add_parser("lint")
    li.add_argument("ledger")
    li.add_argument("--json", action="store_true")
    sub.add_parser("modes")
    a = ap.parse_args()
    if a.cmd == "modes":
        for m in ORDER:
            print(f"{m:10} {MODES[m]}")
        return 0
    if a.cmd == "route":
        res = route(" ".join(a.prompt))
        if a.json:
            print(json.dumps(res, indent=2))
        else:
            print(f"depth: {res['depth']}")
            print("modes: " + (" -> ".join(res["modes"]) or "(none)"))
            for w in res["why"]:
                print(f"  - {w}")
        return 0
    if a.cmd == "template":
        chain = [c.strip() for c in a.chain.replace("->", ",").split(",") if c.strip()]
        bad = [c for c in chain if c not in MODES]
        if bad:
            print(f"error: unknown mode(s) {', '.join(bad)}; see `think.py modes`", file=sys.stderr)
            return 2
        print(template(chain, a.prompt))
        return 0
    try:
        text = Path(a.ledger).read_text()
    except OSError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    fs, modes = lint(text)
    errs = sum(f["severity"] == "error" for f in fs)
    if a.json:
        print(json.dumps({"modes": modes, "findings": fs}, indent=2))
    else:
        for f in fs:
            print(f"{f['severity'].upper():5} {f['where']}: {f['msg']}")
        print(f"{len(modes)} modes ({' -> '.join(modes)}), {errs} errors, {sum(f['severity'] == 'warn' for f in fs)} warnings")
    return 1 if errs else 0


if __name__ == "__main__":
    sys.exit(main())
