#!/usr/bin/env python3
"""Check that interface motion is fast: every one-shot animation inside a time budget.

  motion_budget.py lint PATH [PATH ...] [--budget-ms 300] [--fail-on error|warn] [--json out.json]
  motion_budget.py spring --stiffness 400 --damping 28 [--mass 1] [--budget-ms 300]

lint reads .tsx/.jsx/.ts/.js/.css files (folders are walked; node_modules, dist and build are
skipped) and flags:
  duration-over       a Motion/JS duration above the budget (seconds), outside a repeating loop
  tailwind-duration   a Tailwind duration-N class above the budget
  css-duration        a CSS transition or animation time above the budget, unless infinite
  spring-settle       a spring whose settle time is above the budget (computed from its physics)
  spring-default      type: "spring" with no numbers (Motion's default spring takes about 0.8 s)
  ease-in             ease-in on interface motion (it starts slow, so the UI feels late)
  stagger-uncapped    delay: index * x with no cap, so a long list keeps animating
  stagger-slow        staggerChildren above 0.05 s
  recharts-default    a Recharts series with no animationDuration (the default is 1500 ms)
  no-reduced-motion   a file animates with Motion and nothing handles prefers-reduced-motion

The budget rule and the spring estimate come from Amicro's design-system skill (MIT,
github.com/Subhan-code/Amicro--Micro-transitions-); this checker is an independent implementation.
Pattern-based: confirm a finding in the code before changing it. Standard library only.
"""
import argparse
import json
import math
import re
import sys
from collections import defaultdict
from pathlib import Path

EXTS = {".tsx", ".jsx", ".ts", ".js", ".mjs", ".css"}
SKIP_DIRS = {"node_modules", "dist", "build", ".next", ".git", "coverage", "out"}
SEV = {"error": 0, "warn": 1, "info": 2}
NUM = r"(\d+(?:\.\d+)?|\.\d+)"
LOOP = re.compile(r"\brepeat\s*:|\binfinite\b|repeatType|\banimate-(spin|pulse|ping|bounce)\b", re.I)
MOTION_IMPORT = re.compile(r"""from\s+['"](motion/react|framer-motion|motion)['"]""")
REDUCED = re.compile(r"useReducedMotion|MotionConfig|prefers-reduced-motion|reducedMotion")


# ---------- spring physics ----------
def spring_settle(stiffness=100.0, damping=10.0, mass=1.0):
    """Seconds for a spring to get within about 2% of rest, and its damping ratio.

    Underdamped (ratio < 1): the envelope decays as exp(-damping/(2*mass) * t), so 2% is about
    8 * mass / damping. Critically or over-damped: the slow pole sets the time, about 4 / |pole|.
    """
    k, c, m = float(stiffness), float(damping), float(mass)
    if k <= 0 or c <= 0 or m <= 0:
        return float("inf"), 0.0
    zeta = c / (2 * math.sqrt(k * m))
    if zeta < 1:
        return 8 * m / c, zeta
    slow = (c - math.sqrt(max(0.0, c * c - 4 * k * m))) / (2 * m)
    return (4 / slow if slow > 0 else float("inf")), zeta


def damping_for(budget_s, mass=1.0):
    """Smallest damping that settles an underdamped spring inside the budget."""
    return math.ceil(8 * mass / budget_s)


# ---------- text helpers ----------
def strip_comments(src):
    """Blank out comments, keeping line numbers. Leaves // inside strings alone when it follows a colon (URLs)."""
    src = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    return re.sub(r"(?m)(^|[^:'\"`\\])//[^\n]*", lambda m: m.group(1), src)


def enclosing(text, pos, levels=2):
    """The text of the object literal(s) around pos: the innermost {...} and up to `levels` outer ones."""
    start, end = pos, pos
    for _ in range(levels):
        depth, i = 0, start - 1
        while i >= 0:
            ch = text[i]
            if ch == "}":
                depth += 1
            elif ch == "{":
                if depth == 0:
                    break
                depth -= 1
            i -= 1
        if i < 0:
            break
        depth, j = 0, end
        while j < len(text):
            ch = text[j]
            if ch == "{":
                depth += 1
            elif ch == "}":
                if depth == 0:
                    break
                depth -= 1
            j += 1
        start, end = i, min(j + 1, len(text))
        yield text[start:end]


def innermost(text, pos):
    return next(enclosing(text, pos, 1), "")


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def secs(value, unit):
    v = float(value)
    return v / 1000 if unit == "ms" else v


# ---------- rules ----------
def lint_js(path, raw, budget):
    out, src = [], strip_comments(raw)

    def add(sev, rule, pos, msg, found=""):
        out.append({"file": str(path), "line": line_of(src, pos), "severity": sev, "rule": rule, "message": msg, "found": found})

    def looping(pos):
        return any(LOOP.search(obj) for obj in enclosing(src, pos, 2))

    # springs first, so their duration isn't judged as a tween
    for m in re.finditer(r"""type\s*:\s*['"]spring['"]""", src):
        obj = innermost(src, m.start())
        if looping(m.start()):
            continue

        def val(key):
            mm = re.search(rf"\b{key}\s*:\s*{NUM}", obj)
            return float(mm.group(1)) if mm else None

        k, c, mass, dur = val("stiffness"), val("damping"), val("mass"), val("duration")
        if dur is not None and k is None and c is None:
            if dur > budget:
                add("warn", "spring-settle", m.start(), f"Duration-style spring of {dur:g}s is over the {budget * 1000:g} ms budget.", f"duration: {dur:g}")
            continue
        if k is None and c is None:
            if re.search(r"\b(bounce|visualDuration)\s*:", obj):
                continue
            add("warn", "spring-default", m.start(), "Spring with no numbers: Motion's default (stiffness 100, damping 10) takes about 0.8 s to settle. "
                f"Set stiffness and damping, e.g. stiffness 400, damping {damping_for(budget)}.", "type: 'spring'")
            continue
        t, zeta = spring_settle(k if k is not None else 100, c if c is not None else 10, mass if mass is not None else 1)
        if t > budget * 1.02:
            m_, c_ = (mass if mass is not None else 1), (c if c is not None else 10)
            if zeta < 1:
                fix = f"Raise damping to {damping_for(budget, m_)} or more" + (" (or lower mass)." if m_ > 1 else ".")
            else:  # overdamped: more damping makes it slower; it needs more stiffness
                c_need = max(c_, damping_for(budget, m_))
                fix = (f"It's overdamped, so more damping slows it further: raise stiffness to about {c_need * c_need / (4 * m_):.0f}"
                       + (f" with damping {c_need}." if c_need != c_ else "."))
            add("warn" if t < 2 * budget else "error", "spring-settle", m.start(),
                f"Spring settles in about {t * 1000:.0f} ms (damping ratio {zeta:.2f}); budget is {budget * 1000:g} ms. " + fix,
                f"stiffness {k if k is not None else 100:g}, damping {c_:g}, mass {m_:g}")

    def in_spring(pos):
        return bool(re.search(r"type\s*:\s*['\"]spring", innermost(src, pos)))

    for m in re.finditer(rf"\bduration\s*:\s*{NUM}\b", src):
        d = float(m.group(1))
        if d <= budget or d > 60 or in_spring(m.start()) or looping(m.start()):
            continue
        add("error" if d >= 1 else "warn", "duration-over", m.start(),
            f"{d * 1000:g} ms one-shot animation; budget is {budget * 1000:g} ms. Hover/press 150-200 ms, enter 250 ms, exit about 140 ms.", m.group(0))

    for m in re.finditer(r"(?<![\w-])duration-(?:(\d+)|\[(\d+(?:\.\d+)?)(ms|s)\])(?![\w-])", src):
        d = float(m.group(1)) / 1000 if m.group(1) else secs(m.group(2), m.group(3))
        if d > budget * 0.999 and d >= 0.3:
            line_start = src.rfind("\n", 0, m.start()) + 1
            line_text = src[line_start:src.find("\n", m.start()) if "\n" in src[m.start():] else len(src)]
            if LOOP.search(line_text):
                continue
            add("warn" if d < 1 else "error", "tailwind-duration", m.start(),
                f"Tailwind {m.group(0)} is {d * 1000:g} ms; stay at duration-150, duration-200 or duration-250.", m.group(0))

    for m in re.finditer(r"""\bease\s*:\s*['"]easeIn['"]|(?<![\w-])ease-in(?![\w-])""", src):
        add("warn", "ease-in", m.start(), "Ease-in starts slow, so the interface feels late. Use an ease-out curve such as [0.16, 1, 0.3, 1].", m.group(0))

    for m in re.finditer(rf"\bdelay\s*:\s*([^,}}\n]*\b(?:i|idx|index|n)\b\s*\*\s*{NUM}[^,}}\n]*)", src):
        if "Math.min" in m.group(1) or looping(m.start()):
            continue  # capped, or a loader's phase offset inside a repeating loop
        add("warn", "stagger-uncapped", m.start(), "Stagger grows with the list. Cap it: delay: Math.min(index * 0.015, 0.05).", m.group(0)[:60])
    for m in re.finditer(rf"\bstaggerChildren\s*:\s*{NUM}", src):
        if float(m.group(1)) > 0.05:
            add("info", "stagger-slow", m.start(), f"staggerChildren {m.group(1)}s: with 10 items the last starts {float(m.group(1)) * 10:.1f}s late. Keep it at or under 0.05.", m.group(0))

    if re.search(r"""from\s+['"]recharts['"]""", src):
        for m in re.finditer(r"<(Line|Bar|Area|Pie|Radar|Scatter|RadialBar|Funnel)\b(?![A-Za-z])([^>]*)>", src, re.S):
            if "animationDuration" not in m.group(2) and "isAnimationActive={false}" not in m.group(2):
                add("warn", "recharts-default", m.start(), "Recharts animates for 1500 ms by default. Set animationDuration={280} (or isAnimationActive={false}).", f"<{m.group(1)}>")
    return out


def lint_css(path, raw, budget):
    out, src = [], strip_comments(raw)
    for m in re.finditer(r"(?<![\w-])(transition|transition-duration|animation|animation-duration)\s*:\s*([^;}]+)", src):
        decl = m.group(2)
        if LOOP.search(decl):
            continue
        times = [secs(v, u) for v, u in re.findall(rf"{NUM}(ms|s)\b", decl)]
        if m.group(1) in ("transition", "animation") and len(times) > 1:
            times = times[:1] if "," not in decl else times  # first time in a shorthand is the duration
        worst = max(times, default=0)
        if worst > budget * 1.001:
            out.append({"file": str(path), "line": line_of(src, m.start()), "severity": "error" if worst >= 1 else "warn", "rule": "css-duration",
                        "message": f"{worst * 1000:g} ms {m.group(1)}; budget is {budget * 1000:g} ms.", "found": " ".join(m.group(0).split())[:70]})
        if re.search(r"(?<![\w-])ease-in(?![\w-])", decl):
            out.append({"file": str(path), "line": line_of(src, m.start()), "severity": "warn", "rule": "ease-in",
                        "message": "Ease-in starts slow, so the interface feels late. Use ease-out or cubic-bezier(0.16, 1, 0.3, 1).",
                        "found": " ".join(m.group(0).split())[:70]})
    return out


def collect(paths):
    files = []
    for p in map(Path, paths):
        if p.is_file():
            files.append(p)
        elif p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix in EXTS and not (set(f.parts) & SKIP_DIRS)
                            and not f.name.endswith((".d.ts", ".min.js")))
        else:
            sys.exit(f"not found: {p}")
    return files


def lint(paths, budget_ms=300):
    budget, files, findings = budget_ms / 1000, collect(paths), []
    texts = {}
    for f in files:
        try:
            texts[f] = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    app_wide = any(re.search(r"<MotionConfig[^>]*reducedMotion", t) for t in texts.values()) or \
        any(f.suffix == ".css" and "prefers-reduced-motion" in t for f, t in texts.items())
    for f, t in texts.items():
        findings += lint_css(f, t, budget) if f.suffix == ".css" else lint_js(f, t, budget)
        if f.suffix != ".css" and MOTION_IMPORT.search(t) and not REDUCED.search(t) and not app_wide:
            findings.append({"file": str(f), "line": 1, "severity": "info", "rule": "no-reduced-motion",
                             "message": "Animates with Motion and nothing here (or app-wide in the scanned files) handles prefers-reduced-motion. "
                                        "Wrap the app in <MotionConfig reducedMotion=\"user\"> or use useReducedMotion().", "found": ""})
    findings.sort(key=lambda x: (SEV[x["severity"]], x["file"], x["line"]))
    return findings, len(texts), app_wide


def cmd_lint(a):
    findings, n, app_wide = lint(a.paths, a.budget_ms)
    by = defaultdict(list)
    for f in findings:
        by[(f["severity"], f["rule"])].append(f)
    c = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV}
    print(f"motion_budget: {n} file(s), budget {a.budget_ms:g} ms: {c['error']} error(s), {c['warn']} warning(s), {c['info']} note(s)"
          + ("; reduced motion handled app-wide" if app_wide else ""))
    for (sev, rule), fs in sorted(by.items(), key=lambda kv: (SEV[kv[0][0]], -len(kv[1]))):
        print(f"\n[{sev}] {rule} x{len(fs)}: {fs[0]['message']}")
        for f in fs[: a.show]:
            print(f"    {f['file']}:{f['line']}  {f['found']}")
        if len(fs) > a.show:
            print(f"    ... {len(fs) - a.show} more (--show N, or --json for all)")
    if a.json:
        Path(a.json).write_text(json.dumps(findings, indent=1) + "\n")
    if a.fail_on and any(SEV[f["severity"]] <= SEV[a.fail_on] for f in findings):
        sys.exit(1)


def cmd_spring(a):
    t, zeta = spring_settle(a.stiffness, a.damping, a.mass)
    kind = "underdamped (overshoots)" if zeta < 1 else "critically damped" if abs(zeta - 1) < 0.02 else "overdamped (no overshoot)"
    ok = t <= a.budget_ms / 1000 * 1.02
    print(f"stiffness {a.stiffness:g}, damping {a.damping:g}, mass {a.mass:g}: settles in about {t * 1000:.0f} ms, damping ratio {zeta:.2f}, {kind}")
    if ok:
        print(f"inside the {a.budget_ms:g} ms budget")
    else:
        need = max(a.damping, damping_for(a.budget_ms / 1000, a.mass)) if zeta >= 1 else damping_for(a.budget_ms / 1000, a.mass)
        print(f"over the {a.budget_ms:g} ms budget; " + (f"use damping {need} or more at this mass" if zeta < 1 else
              f"overdamped: raise stiffness to about {need * need / (4 * a.mass):.0f} with damping {need:g}"))
    sys.exit(0 if ok else 1)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint")
    p.add_argument("paths", nargs="+")
    p.add_argument("--budget-ms", type=float, default=300)
    p.add_argument("--fail-on", choices=["error", "warn"])
    p.add_argument("--json")
    p.add_argument("--show", type=int, default=5, help="examples to print per rule")
    p = sub.add_parser("spring")
    p.add_argument("--stiffness", type=float, default=100)
    p.add_argument("--damping", type=float, default=10)
    p.add_argument("--mass", type=float, default=1)
    p.add_argument("--budget-ms", type=float, default=300)
    a = ap.parse_args(argv)
    {"lint": cmd_lint, "spring": cmd_spring}[a.cmd](a)


if __name__ == "__main__":
    main()
