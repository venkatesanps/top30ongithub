#!/usr/bin/env python3
"""Find animation code that is expensive to render: motion that makes the browser redo layout or
paint on every frame, or that keeps running when nothing is changing.

  motion_perf.py lint PATH [PATH ...] [--fail-on warn] [--json out.json] [--show 5]

Reads .tsx/.jsx/.ts/.js/.mjs/.css files (folders are walked; node_modules, dist, build, .next,
coverage and out are skipped) and reports:

  layout-animation   width, height, top, left, margin or padding animated (Motion targets and
                     variants, motion values in style, CSS keyframes and transitions, Tailwind
                     transition-[width]). Each frame re-runs layout. height: "auto" accordions and
                     Motion's layout prop (which animates with transforms) are allowed.
  transition-all     transition-all / transition: all. Every property that changes animates,
                     including layout ones, and the cost is invisible in review.
  scroll-handler     a scroll event listener in a file that also writes styles or state. Use
                     Motion's useScroll, CSS scroll-driven animation or IntersectionObserver.
  raf-loop           a requestAnimationFrame loop with no cancelAnimationFrame and no condition
                     around the call, so it runs every frame forever, even off screen.
  layout-thrash      a loop or frame callback that reads layout (getBoundingClientRect,
                     offsetWidth...) and writes .style: each read forces a fresh layout.
  blur-large         blur over 8px that animates (Motion targets, keyframes, hover/focus/state
                     styles, Tailwind hover:blur-xl). Large blurs are re-rasterized each frame.
  will-change        will-change set permanently (CSS rule, style object, Tailwind class). Each
                     one keeps a GPU layer alive; set it just before a motion, remove it after.
  mixed-systems      one file animating with Motion and also GSAP, react-spring or anime.js.

will-change and mixed-systems are notes; the rest are warnings. Nothing is an error: these are
patterns, so open each finding and check before changing it, and measure in the Performance panel
when in doubt. The categories follow cult-ui's fixing-motion-performance skill (MIT,
github.com/nolly-studio/cult-ui); this checker is an independent implementation. Standard library
only.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

EXTS = {".tsx", ".jsx", ".ts", ".js", ".mjs", ".css"}
SKIP_DIRS = {"node_modules", "dist", "build", ".next", ".git", "coverage", "out"}
SEV = {"warn": 1, "info": 2}
LAYOUT_KEYS = r"(?:width|height|minWidth|minHeight|maxWidth|maxHeight|top|left|right|bottom|margin\w*|padding\w*)"
LAYOUT_CSS = r"(?:(?:min-|max-)?width|(?:min-|max-)?height|top|left|right|bottom|margin(?:-\w+)?|padding(?:-\w+)?|inset(?:-\w+)?)"
TARGET_PROPS = r"(?:animate|initial|exit|whileHover|whileTap|whileInView|whileFocus|whileDrag)"
MOTION_IMPORT = re.compile(r"""from\s+['"](motion/react|framer-motion|motion|motion/react-client)['"]""")
OTHER_SYSTEMS = re.compile(r"""from\s+['"](gsap(?:/[\w-]+)?|@react-spring/[\w-]+|react-spring|animejs|animejs/[\w-]+)['"]""")
LAYOUT_READ = re.compile(r"\b(getBoundingClientRect|getComputedStyle|offset(?:Width|Height|Top|Left)|client(?:Width|Height)|scroll(?:Width|Height))\b")
STYLE_WRITE = re.compile(r"\.style\.\w+\s*=(?!=)|\.style\.setProperty\(|\.style\.cssText\s*=")
STATE_STYLE_SEL = re.compile(r":hover|:focus|:active|\[data-|\[aria-|\.is-|\.active\b|\.open\b")


# ---------- text helpers ----------
def strip_comments(src):
    """Blank out comments, keeping line numbers. Leaves // after a colon alone (URLs)."""
    src = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    return re.sub(r"(?m)(^|[^:'\"`\\])//[^\n]*", lambda m: m.group(1), src)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


def block_at(text, i):
    """(start, end) of the {...} that opens at text[i] == '{', end exclusive."""
    depth = 0
    for j in range(i, len(text)):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return i, j + 1
    return i, len(text)


def snippet(text, pos, n=70):
    end = text.find("\n", pos)
    return " ".join(text[pos:end if end != -1 else len(text)].split())[:n]


def blur_px(value, unit):
    v = float(value)
    return v * 16 if unit == "rem" else v


TW_BLUR = {"xs": 4, "sm": 8, "": 8, "md": 12, "lg": 16, "xl": 24, "2xl": 40, "3xl": 64}


# ---------- JS / TSX ----------
def motion_targets(src):
    """Spans of objects Motion animates to: target props, variants (inline or named), animate()/start() calls."""
    spans = []
    for m in re.finditer(rf"\b{TARGET_PROPS}\s*=\s*\{{\s*\{{", src):
        spans.append(block_at(src, src.index("{", src.index("{", m.start()) + 1)))
    for m in re.finditer(r"\bvariants\s*=\s*\{\s*\{", src):
        spans.append(block_at(src, src.index("{", src.index("{", m.start()) + 1)))
    names = set(re.findall(r"\bvariants\s*=\s*\{\s*(\w+)\s*\}", src))
    names |= set(re.findall(r"\b(?:const|let)\s+(\w+)\s*:\s*Variants\b", src))
    for name in names:
        for m in re.finditer(rf"\b(?:const|let)\s+{re.escape(name)}\b[^=;]*=\s*\{{", src):
            spans.append(block_at(src, m.end() - 1))
    for m in re.finditer(r"\b(?:animate|\.start)\(\s*(?:[\w.\[\]\"']+\s*,\s*)?\{", src):
        spans.append(block_at(src, m.end() - 1))
    return spans


def has_layout_prop(src, pos):
    """True when the motion element whose props hold pos also has Motion's layout prop (FLIP, transform-based)."""
    tag = src.rfind("<motion.", 0, pos)
    if tag == -1 or ">" in re.sub(r"=>|\{[^{}]*\}", "", src[tag:pos]).replace("->", ""):
        return False
    return bool(re.search(r"\slayout(?:\s*=\s*(?:\{true\}|['\"](?:position|size|preserve-aspect)['\"]))?(?=[\s/>])", src[tag:pos]))


def inside(pos, spans):
    return any(a <= pos < b for a, b in spans)


def lint_js(path, raw):
    out, src = [], strip_comments(raw)

    def add(sev, rule, pos, msg, found=None):
        out.append({"file": str(path), "line": line_of(src, pos), "severity": sev, "rule": rule, "message": msg,
                    "found": found if found is not None else snippet(src, pos)})

    is_motion = bool(MOTION_IMPORT.search(src))
    targets = motion_targets(src) if is_motion else []

    # layout-animation: keys inside Motion targets
    seen = set()
    for a, b in targets:
        obj = src[a:b]
        for m in re.finditer(rf"(?<![\w.-])['\"]?({LAYOUT_KEYS})['\"]?\s*:\s*([^,}}\n]+)", obj):
            val = m.group(2)
            if re.search(r"""['"]auto['"]""", val) or re.fullmatch(r"\s*0\s*", val) and m.group(1).startswith(("margin", "padding")):
                continue  # height: "auto" accordions; padding 0 resets
            pos = a + m.start()
            if pos in seen or has_layout_prop(src, pos):
                continue
            seen.add(pos)
            loops = re.search(r"\brepeat\s*:\s*(?!0\b)", src[b:b + 600].split("<motion.")[0])
            add("warn", "layout-animation", pos,
                f"Animating {m.group(1)} re-runs layout every frame" + (", and this one loops, so it never stops" if loops else "")
                + ". Use transform (x, y, scale) or Motion's layout prop; for open/close, height: \"auto\" is fine.", snippet(src, pos))

    # layout-animation: motion values driving layout keys in style={{ }}
    mvals = set(re.findall(r"\b(?:const|let)\s+(\w+)\s*=\s*use(?:Transform|Spring|MotionValue|Velocity|MotionTemplate)\b", src))
    for m in re.finditer(r"\b(?:const|let)\s*\{([^}]*)\}\s*=\s*useScroll\b", src):
        mvals |= {p.split(":")[-1].strip() for p in m.group(1).split(",") if p.strip()}
    if mvals:
        for m in re.finditer(r"\bstyle\s*=\s*\{\s*\{", src):
            a, b = block_at(src, src.index("{", src.index("{", m.start()) + 1))
            for k in re.finditer(rf"(?<![\w.-])({LAYOUT_KEYS})\s*:\s*([^,}}\n]+)", src[a:b]):
                if any(re.search(rf"\b{re.escape(v)}\b", k.group(2)) for v in mvals):
                    add("warn", "layout-animation", a + k.start(),
                        f"A motion value drives {k.group(1)}, so layout runs on every change. Map it to scaleX/scaleY, x or y instead.")

    # inline CSS strings and Tailwind arbitrary transitions
    for m in re.finditer(rf"""\btransition(?:Property)?\s*:\s*[`'"][^`'"]*\b{LAYOUT_CSS}\b""", src):
        add("warn", "layout-animation", m.start(), "This CSS transition animates a layout property. Transition transform or opacity instead.")
    for m in re.finditer(r"(?<![\w-])transition-\[([^\]]+)\]", src):
        if re.search(rf"(?<![\w-]){LAYOUT_CSS}(?![\w-])", m.group(1)):
            add("warn", "layout-animation", m.start(), f"{m.group(0)} animates a layout property. Animate transform or opacity instead.", m.group(0))
    for m in re.finditer(r"(?<![\w-])transition-all(?![\w-])", src):
        add("warn", "transition-all", m.start(),
            "transition-all animates every property that changes, layout ones included. Name them: transition-colors, transition-opacity, "
            "transition-transform, or transition-[transform,opacity].", "transition-all")
    for m in re.finditer(r"""\btransition\s*:\s*[`'"]\s*all\b""", src):
        add("warn", "transition-all", m.start(), "transition: all animates every property that changes. List the properties.")

    # blur-large
    blur_spans = targets + [block_at(src, mm.end() - 1) for mm in re.finditer(r"\bkeyframes\s*=\s*\{|@keyframes[^{]*\{", src)]
    for m in re.finditer(r"blur\(\s*(\d+(?:\.\d+)?)(px|rem)\s*\)", src):
        px = blur_px(m.group(1), m.group(2))
        if px > 8 and inside(m.start(), blur_spans):
            add("warn", "blur-large", m.start(), f"Animating a {px:g}px blur re-rasterizes the element every frame. Keep animated blur at 8px or less, "
                "on small elements, or cross-fade to a pre-blurred copy.", m.group(0))
    for m in re.finditer(r"(?<![\w-])((?:[\w-]+:)*?(?:hover|focus|focus-visible|active|group-hover|peer-hover|data-\[[^\]]+\]|aria-\[[^\]]+\]|open):)(?:backdrop-)?blur(?:-(xs|sm|md|lg|xl|2xl|3xl)|-\[(\d+(?:\.\d+)?)(px|rem)\])?(?![\w-])", src):
        px = blur_px(m.group(3), m.group(4)) if m.group(3) else TW_BLUR.get(m.group(2) or "", 8)
        if px > 8:
            add("warn", "blur-large", m.start(), f"{m.group(0)} changes a {px:g}px blur on interaction; with a transition it is re-rasterized every frame.", m.group(0))

    # scroll-handler
    writes = STYLE_WRITE.search(src) or re.search(r"\bset[A-Z]\w*\(", src) or re.search(r"\b(?:\w+\.)?set\(", src)
    if writes:
        for m in re.finditer(r"""addEventListener\(\s*['"]scroll['"][^)]*\)|\bonScroll\s*=\s*\{""", src):
            if re.search(r"passive\s*:\s*true", m.group(0)) and "requestAnimationFrame" in src:
                continue  # passive and frame-throttled: the recommended form when a listener is needed
            add("warn", "scroll-handler", m.start(),
                "A scroll handler that writes styles or state runs on the main thread for every scroll event. Use Motion's useScroll, "
                "CSS animation-timeline: scroll()/view(), or IntersectionObserver for enter/leave. If you keep it: passive listener, "
                "one requestAnimationFrame per frame, transform-only writes.")

    # raf-loop
    if "requestAnimationFrame" in src and "cancelAnimationFrame" not in src:
        loops_seen = set()
        for m in re.finditer(r"\brequestAnimationFrame\(\s*(\w+)\s*\)", src):
            line_start = src.rfind("\n", 0, m.start()) + 1
            before = src[line_start:m.start()]
            prev = src[src.rfind("\n", 0, max(0, line_start - 1)) + 1:line_start]
            if re.search(r"\bif\s*\(|\?|&&|\|\|", before) or re.search(r"\b(?:if|while)\s*\(.*\)\s*\{?\s*$", prev):
                continue  # conditional: the loop has a stop
            if not re.search(rf"\b(?:function\s+{re.escape(m.group(1))}\b|(?:const|let)\s+{re.escape(m.group(1))}\s*=)", src):
                continue  # not a loop over a local function
            if m.group(1) in loops_seen:
                continue  # the kick-off call and the call inside the loop are one loop
            loops_seen.add(m.group(1))
            add("warn", "raf-loop", m.start(),
                "requestAnimationFrame loop with no cancelAnimationFrame and no condition: it runs every frame for the life of the page, "
                "even off screen. Keep the id, cancel it on unmount, and stop when the animation settles or leaves the viewport.")

    # layout-thrash: read + write in one loop body or frame callback
    # A loop body that both reads and writes interleaves them across iterations. In a frame
    # callback, reading first is fine (layout is still clean); a read after a write is not.
    bodies = [(block_at(src, m.end() - 1), True) for m in
              re.finditer(r"\bfor\s*\([^)]*\)\s*\{|\.forEach\(\s*(?:\([^)]*\)|\w+)\s*=>\s*\{", src)]
    bodies += [(block_at(src, m.end() - 1), False) for m in
               re.finditer(r"\brequestAnimationFrame\(\s*(?:\([^)]*\)|\w+)?\s*=>\s*\{", src)]
    flagged = set()
    for (a, b), is_loop in bodies:
        body = src[a:b]
        w = STYLE_WRITE.search(body)
        if not w:
            continue
        r = next((rr for rr in LAYOUT_READ.finditer(body) if is_loop or rr.start() > w.start()), None)
        if r and a + r.start() not in flagged:
            flagged.add(a + r.start())
            add("warn", "layout-thrash", a + r.start(),
                f"Reads layout ({r.group(1)}) and writes .style in the same {'loop' if is_loop else 'frame, read after write'}: "
                "each read after a write forces a fresh layout. Read everything first, then write.", r.group(1))

    # will-change (note)
    styles = [block_at(src, src.index("{", src.index("{", mm.start()) + 1)) for mm in re.finditer(r"\bstyle\s*=\s*\{\s*\{", src)]
    for m in re.finditer(r"""\bwillChange\s*\??:\s*(['"`]?)([\w.-]+)|\.style\.willChange\s*=\s*(['"`])(\w[\w, -]*)""", src):
        if m.group(4):
            if m.group(4).strip() == "auto":
                continue
        elif not (inside(m.start(), styles) or inside(m.start(), targets)):
            continue  # an object key that isn't a style
        elif not m.group(1) and m.group(2) in ("any", "string", "boolean", "number", "unknown", "React.CSSProperties", "undefined", "auto"):
            continue  # a type annotation, or auto
        if m.group(1) and m.group(2) == "auto":
            continue
        add("info", "will-change", m.start(), "will-change set in a style object stays on: each one keeps a GPU layer. Set it just before a motion and remove it after.")
    for m in re.finditer(r"(?<![\w:-])will-change-(transform|opacity|contents|scroll|\[[^\]]+\])(?![\w-])", src):
        add("info", "will-change", m.start(), f"{m.group(0)} keeps a GPU layer for the element's whole life. Fine on something that animates continuously; otherwise add it only while animating.", m.group(0))

    if is_motion:
        other = OTHER_SYSTEMS.search(src)
        if other:
            add("info", "mixed-systems", other.start(), f"This file animates with Motion and {other.group(1)}. Two systems can fight over the same "
                "properties and each runs its own frame loop; keep one per element.", other.group(1))
    return out


# ---------- CSS ----------
def lint_css(path, raw):
    out, src = [], strip_comments(raw)

    def add(sev, rule, pos, msg, found=None):
        out.append({"file": str(path), "line": line_of(src, pos), "severity": sev, "rule": rule, "message": msg,
                    "found": found if found is not None else snippet(src, pos)})

    kf = [block_at(src, m.end() - 1) for m in re.finditer(r"@keyframes\s+[\w-]+\s*\{", src)]
    for a, b in kf:
        props = set()
        for m in re.finditer(rf"(?<![\w-])({LAYOUT_CSS})\s*:", src[a:b]):
            if m.group(1) in props:
                continue  # one finding per property per @keyframes
            props.add(m.group(1))
            add("warn", "layout-animation", a + m.start(), f"These keyframes animate {m.group(1)}, which re-runs layout every frame. Use transform.")
    for m in re.finditer(r"(?<![\w-])(transition|transition-property)\s*:\s*([^;}]+)", src):
        decl = m.group(2)
        if re.match(r"\s*all\b", decl) or re.search(r",\s*all\b", decl):
            add("warn", "transition-all", m.start(), "transition: all animates every property that changes, layout ones included. List the properties.")
        elif re.search(rf"(?:^|[\s,]){LAYOUT_CSS}(?:\s|,|$)", decl):
            add("warn", "layout-animation", m.start(), "This transition animates a layout property. Transition transform or opacity instead.")
    for m in re.finditer(r"@apply[^;]*?(?<![\w-])transition-all(?![\w-])", src):
        add("warn", "transition-all", m.start(), "transition-all animates every property that changes. Name them.", "@apply transition-all")

    # blur in keyframes or interaction-state rules
    for m in re.finditer(r"blur\(\s*(\d+(?:\.\d+)?)(px|rem)\s*\)", src):
        px = blur_px(m.group(1), m.group(2))
        if px <= 8:
            continue
        rule_start = src.rfind("}", 0, m.start())
        brace = src.rfind("{", 0, m.start())
        selector = src[rule_start + 1:brace] if brace > rule_start else ""
        if inside(m.start(), kf) or STATE_STYLE_SEL.search(selector):
            add("warn", "blur-large", m.start(), f"A {px:g}px blur that animates is re-rasterized every frame. Keep animated blur at 8px or less.", m.group(0))

    for m in re.finditer(r"(?<![\w-])will-change\s*:\s*([^;}]+)", src):
        if m.group(1).strip() in ("auto", "initial", "unset"):
            continue
        rule_start = src.rfind("}", 0, m.start())
        brace = src.rfind("{", 0, m.start())
        selector = src[rule_start + 1:brace] if brace > rule_start else ""
        if not STATE_STYLE_SEL.search(selector):
            add("info", "will-change", m.start(), "will-change in a base rule keeps a GPU layer alive permanently. Add it on the state that animates, or from script just before.")
    return out


# ---------- driver ----------
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


def lint(paths):
    findings, n = [], 0
    for f in collect(paths):
        try:
            t = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        n += 1
        findings += lint_css(f, t) if f.suffix == ".css" else lint_js(f, t)
    findings.sort(key=lambda x: (SEV[x["severity"]], x["rule"], x["file"], x["line"]))
    return findings, n


def cmd_lint(a):
    findings, n = lint(a.paths)
    by = defaultdict(list)
    for f in findings:
        by[(f["severity"], f["rule"])].append(f)
    c = {s: sum(1 for f in findings if f["severity"] == s) for s in SEV}
    files_hit = len({f["file"] for f in findings if f["severity"] == "warn"})
    print(f"motion_perf: {n} file(s): {c['warn']} warning(s) in {files_hit} file(s), {c['info']} note(s)")
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


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("lint")
    p.add_argument("paths", nargs="+")
    p.add_argument("--fail-on", choices=["warn", "info"])
    p.add_argument("--json")
    p.add_argument("--show", type=int, default=5, help="examples to print per rule")
    a = ap.parse_args(argv)
    cmd_lint(a)


if __name__ == "__main__":
    main()
