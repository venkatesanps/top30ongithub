#!/usr/bin/env python3
"""Keep a DESIGN.md (Google's format: YAML tokens in front matter, prose sections below) and the
code that is meant to follow it in step.

  design_drift.py check DESIGN.md                     the file itself: front matter, references, sections, contrast
  design_drift.py drift DESIGN.md PATH [PATH ...]     code that strays from the tokens
  design_drift.py draft PATH [PATH ...]               a starting token block read from the code

check (offline; a subset of `npx @google/design.md lint`, which stays the reference):
  no-front-matter   no YAML block between --- lines at the top, or it doesn't parse
  missing-name      no name:
  unknown-key       a top-level key the format doesn't define
  broken-ref        a {group.token} reference that points nowhere
  missing-primary   colors has no primary
  section-order     ## sections out of the order Overview, Colors, Typography, Layout,
                    Elevation & Depth, Shapes, Components, Do's and Don'ts
  contrast          a component's textColor on its backgroundColor under 4.5:1 (hex colors only)

drift (reads .tsx/.jsx/.ts/.js/.mjs/.css/.scss; skips node_modules, dist, build, .next, out):
  hex-color         a hex color that isn't one of the colors tokens (the nearest token is named)
  undeclared-font   a font-family / fontFamily / font-['X'] that no typography token uses
  radius-off-scale  rounded-[Npx] or border-radius: Npx that isn't on the rounded scale
  arbitrary-shadow  Tailwind shadow-[...]: one-off elevation; name it in Elevation & Depth
When the DESIGN.md has no colors, the CSS custom properties found in the scanned CSS files are
used as the palette instead, so a project with only globals.css still gets a check.

draft prints a front-matter block (colors from CSS custom properties, the fonts and radii in use,
the most used hard-coded colors) to edit into a DESIGN.md. It never writes files.

Standard library only (uses PyYAML when installed). Exit 1 with --fail-on when findings at or
above that severity exist.
"""
import argparse
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

EXTS = {".tsx", ".jsx", ".ts", ".js", ".mjs", ".css", ".scss"}
SKIP_DIRS = {"node_modules", "dist", "build", ".next", ".git", "coverage", "out"}
SEV = {"error": 0, "warn": 1, "info": 2}
TOP_KEYS = {"version", "name", "description", "omitted", "colors", "typography", "rounded", "spacing", "components"}
SECTIONS = [
    ("overview", {"overview", "brand & style", "brand and style"}),
    ("colors", {"colors", "colours", "color"}),
    ("typography", {"typography"}),
    ("layout", {"layout", "layout & spacing", "layout and spacing", "spacing"}),
    ("elevation", {"elevation & depth", "elevation", "elevation and depth"}),
    ("shapes", {"shapes", "shape"}),
    ("components", {"components"}),
    ("dos", {"do's and don'ts", "dos and don'ts", "do's & don'ts", "dos and donts"}),
]
GENERIC_FONTS = {"sans-serif", "serif", "monospace", "system-ui", "ui-sans-serif", "ui-serif", "ui-monospace", "cursive",
                 "fantasy", "inherit", "initial", "unset", "-apple-system", "blinkmacsystemfont", "emoji", "math"}
HEX = re.compile(r"(?<![\w&/])#([0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])")


# ---------- front matter ----------
def _scalar(v):
    v = v.strip()
    if v.startswith("{") and v.endswith("}") and ":" in v:  # a one-level flow map: { a: 1, b: x }
        return {k.strip(): _scalar(x) for k, _, x in (p.partition(":") for p in v[1:-1].split(",") if p.strip())}
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    if re.fullmatch(r"-?\d+", v):
        return int(v)
    if re.fullmatch(r"-?\d*\.\d+", v):
        return float(v)
    return v


def _strip_comment(line):
    out, q = [], None
    for i, ch in enumerate(line):
        if q:
            q = None if ch == q else q
        elif ch in "\"'":
            q = ch
        elif ch == "#" and (i == 0 or line[i - 1] in " \t"):
            break
        out.append(ch)
    return "".join(out).rstrip()


def parse_simple_yaml(text):
    """The YAML subset DESIGN.md uses: nested maps by indentation, scalars, and simple lists."""
    root, stack = {}, [(-1, None)]
    stack[0] = (-1, root)
    lines = [(len(l) - len(l.lstrip(" ")), _strip_comment(l).strip()) for l in text.splitlines()]
    lines = [(ind, l) for ind, l in lines if l]
    for idx, (ind, line) in enumerate(lines):
        while stack and ind <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            item = line[2:].strip()
            if not isinstance(parent, list):
                raise ValueError(f"list item outside a list: {line}")
            if re.match(r"[\w-]+\s*:", item):
                k, _, v = item.partition(":")
                d = {k.strip(): _scalar(v)} if v.strip() else {k.strip(): {}}
                parent.append(d)
                stack.append((ind, d))
            else:
                parent.append(_scalar(item))
            continue
        k, sep, v = line.partition(":")
        if not sep:
            raise ValueError(f"not a key: value line: {line}")
        k = _scalar(k)
        if v.strip():
            parent[k] = _scalar(v)
        else:
            nxt = lines[idx + 1] if idx + 1 < len(lines) else (ind, "")
            child = [] if nxt[0] > ind and nxt[1].startswith("- ") else {}
            parent[k] = child
            stack.append((ind, child))
    return root


def front_matter(text):
    """(tokens dict or None, body, error)."""
    m = re.match(r"\A﻿?---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", text, re.S)
    if not m:
        return None, text, "no front matter"
    try:
        import yaml  # noqa: F401
        data = yaml.safe_load(m.group(1)) or {}
    except ImportError:
        try:
            data = parse_simple_yaml(m.group(1))
        except ValueError as e:
            return None, text[m.end():], str(e)
    except Exception as e:  # yaml.YAMLError
        return None, text[m.end():], str(e).split("\n")[0]
    if not isinstance(data, dict):
        return None, text[m.end():], "front matter is not a map"
    return data, text[m.end():], None


def lookup(tokens, path):
    cur = tokens
    for part in path.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def resolve(tokens, value, depth=0):
    m = re.fullmatch(r"\s*\{([\w.-]+)\}\s*", str(value)) if isinstance(value, str) else None
    if not m or depth > 8:
        return value
    return resolve(tokens, lookup(tokens, m.group(1)), depth + 1)


# ---------- colors ----------
def norm_hex(h):
    h = h.lstrip("#").lower()
    if len(h) in (3, 4):
        h = "".join(c * 2 for c in h)
    return "#" + h


def rgb(h):
    h = norm_hex(h)[1:7]
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def luminance(h):
    def ch(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (ch(c) for c in rgb(h))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a, b):
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def palette(tokens):
    """{normalized hex: token name} from the colors group (other color formats are skipped)."""
    out = {}
    for name, v in (tokens.get("colors") or {}).items():
        v = resolve(tokens, v)
        if isinstance(v, str) and HEX.fullmatch(v.strip()):
            out.setdefault(norm_hex(v.strip()), str(name))
    return out


def nearest(hexv, pal):
    if not pal:
        return None
    r = rgb(hexv)
    best = min(pal, key=lambda p: math.dist(r, rgb(p)))
    return best, pal[best], math.dist(r, rgb(best))


# ---------- check ----------
def check(path):
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    out = []

    def add(sev, rule, msg, line=1, found=""):
        out.append({"file": str(path), "line": line, "severity": sev, "rule": rule, "message": msg, "found": found})

    tokens, body, err = front_matter(text)
    if tokens is None:
        add("error", "no-front-matter", f"No usable token block ({err}). Start the file with --- , YAML tokens, then --- .")
        tokens = {}
    else:
        if not tokens.get("name"):
            add("error", "missing-name", "The token block needs a name: .")
        for k in tokens:
            if k not in TOP_KEYS:
                add("warn", "unknown-key", f"Top-level key {k!r} isn't part of the format (known: {', '.join(sorted(TOP_KEYS))}).", found=str(k))
        fm_lines = text[:len(text) - len(body)].splitlines()

        def walk(node, trail):
            if isinstance(node, dict):
                for k, v in node.items():
                    yield from walk(v, trail + [str(k)])
            elif isinstance(node, list):
                for v in node:
                    yield from walk(v, trail)
            elif isinstance(node, str):
                for ref in re.findall(r"\{([\w.-]+)\}", node):
                    yield trail, ref

        for trail, ref in walk({k: v for k, v in tokens.items() if k != "omitted"}, []):
            target = lookup(tokens, ref)
            if target is None:
                ln = next((i + 1 for i, l in enumerate(fm_lines) if "{" + ref + "}" in l), 1)
                add("error", "broken-ref", f"{'.'.join(trail)} refers to {{{ref}}}, which isn't defined.", ln, "{" + ref + "}")
            elif isinstance(target, dict) and trail[:1] != ["components"]:
                add("warn", "broken-ref", f"{'.'.join(trail)} refers to the group {{{ref}}}; outside components a reference must point at one value.", 1, "{" + ref + "}")
        omitted = {(o.get("section") if isinstance(o, dict) else str(o)) for o in tokens.get("omitted") or []}
        if "colors" not in omitted and "primary" not in (tokens.get("colors") or {}):
            add("warn", "missing-primary", "colors has no primary token, so tools can't tell which color is the brand color.")
        for comp, props in (tokens.get("components") or {}).items():
            if not isinstance(props, dict):
                continue
            bg, fg = resolve(tokens, props.get("backgroundColor")), resolve(tokens, props.get("textColor"))
            if isinstance(bg, str) and isinstance(fg, str) and HEX.fullmatch(bg.strip()) and HEX.fullmatch(fg.strip()):
                ratio = contrast(bg.strip(), fg.strip())
                if ratio < 4.5:
                    add("warn", "contrast", f"components.{comp}: text {fg} on {bg} is {ratio:.2f}:1; body text needs 4.5:1 (WCAG AA).", 1, comp)

    offset = text[:len(text) - len(body)].count("\n")
    last, seen = -1, {}
    for m in re.finditer(r"(?m)^##\s+(.+?)\s*#*\s*$", body):
        title = m.group(1).strip().lower().replace("’", "'")
        idx = next((i for i, (_, names) in enumerate(SECTIONS) if title in names), None)
        ln = offset + body.count("\n", 0, m.start()) + 1
        if idx is None:
            continue
        if idx in seen:
            add("warn", "section-order", f"Section '{m.group(1)}' appears twice (first at line {seen[idx]}).", ln, m.group(1))
            continue
        seen[idx] = ln
        if idx < last:
            add("warn", "section-order", f"Section '{m.group(1)}' comes after '{SECTIONS[last][0]}'; the format's order is "
                "Overview, Colors, Typography, Layout, Elevation & Depth, Shapes, Components, Do's and Don'ts.", ln, m.group(1))
        last = max(last, idx)
    out.sort(key=lambda x: (SEV[x["severity"]], x["line"]))
    return out, tokens


# ---------- drift ----------
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


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), src, flags=re.S)
    return re.sub(r"(?m)(^|[^:'\"`\\])//[^\n]*", lambda m: m.group(1), src)


def css_vars(texts):
    """{normalized hex: --name} for custom properties defined with a hex value in CSS files."""
    out = {}
    for f, t in texts.items():
        if f.suffix in (".css", ".scss"):
            for m in re.finditer(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\b", t):
                out.setdefault(norm_hex(m.group(2)), m.group(1))
    return out


def first_family(v, lower=True):
    v = v.strip().strip(";").split(",")[0].strip().strip("'\"` ")
    return v.lower() if lower else v


def px(value, unit):
    return float(value) * (16 if unit == "rem" else 1)


def drift(design, paths):
    tokens, _, _ = front_matter(Path(design).read_text(encoding="utf-8", errors="replace"))
    tokens = tokens or {}
    files = [f for f in collect(paths) if f.resolve() != Path(design).resolve()]
    texts = {}
    for f in files:
        try:
            texts[f] = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    pal, source = palette(tokens), "DESIGN.md colors"
    if not pal:
        pal, source = css_vars(texts), "CSS custom properties"
    fonts = {first_family(str(resolve(tokens, t.get("fontFamily", "")))) for t in (tokens.get("typography") or {}).values() if isinstance(t, dict)}
    fonts.discard("")
    radii = set()
    for v in (tokens.get("rounded") or {}).values():
        m = re.fullmatch(r"\s*(\d+(?:\.\d+)?)(px|rem)\s*", str(resolve(tokens, v)))
        if m:
            radii.add(round(px(*m.groups()), 2))
    out = []

    def add(f, t, pos, sev, rule, msg, found):
        out.append({"file": str(f), "line": t.count("\n", 0, pos) + 1, "severity": sev, "rule": rule, "message": msg, "found": found})

    for f, t in texts.items():
        if pal:
            for m in HEX.finditer(t):
                pre = t[max(0, m.start() - 6):m.start()]
                if re.search(r"(?:href|id|to)=['\"]?$|url\(\s*$", pre):
                    continue
                h = norm_hex(m.group(0))
                if h in pal or h[:7] in pal and len(h) == 9:
                    continue
                n = nearest(h, pal)
                hint = f" Nearest token: {n[1]} ({n[0]})." if n and n[2] < 60 else " Add it as a token or use an existing one."
                add(f, t, m.start(), "warn", "hex-color", f"{m.group(0)} isn't in the palette ({source}).{hint}", m.group(0))
        if fonts:
            for m in re.finditer(r"""font-family\s*:\s*([^;}\n]+)|\bfontFamily\s*:\s*['"`]([^'"`]+)['"`]|(?<![\w-])font-\[['"]?([^\]'"]+)['"]?\]""", t):
                fam = first_family(m.group(1) or m.group(2) or m.group(3).replace("_", " "))
                if not fam or fam in GENERIC_FONTS or fam.startswith(("var(", "theme(", "$", "{")) or fam in fonts:
                    continue
                add(f, t, m.start(), "warn", "undeclared-font", f"Font {fam!r} isn't used by any typography token (declared: {', '.join(sorted(fonts))}).", fam)
        if radii:
            for m in re.finditer(r"(?<![\w-])rounded(?:-[a-z]{1,2})?-\[(\d+(?:\.\d+)?)(px|rem)\]|border-radius\s*:\s*(\d+(?:\.\d+)?)(px|rem)\s*[;}\n]", t):
                v = px(m.group(1), m.group(2)) if m.group(1) else px(m.group(3), m.group(4))
                if round(v, 2) not in radii and v not in (0, 9999):
                    add(f, t, m.start(), "info", "radius-off-scale", f"Radius {v:g}px isn't on the rounded scale ({', '.join(f'{r:g}px' for r in sorted(radii))}).", m.group(0).strip())
        for m in re.finditer(r"(?<![\w-])shadow-\[[^\]]+\]", t):
            add(f, t, m.start(), "info", "arbitrary-shadow", "One-off shadow. Describe the elevation levels in Elevation & Depth and reuse them.", m.group(0)[:60])
    out.sort(key=lambda x: (SEV[x["severity"]], x["rule"], x["file"], x["line"]))
    return out, len(texts), source if pal else None


# ---------- draft ----------
def draft(paths):
    texts = {}
    for f in collect(paths):
        try:
            texts[f] = strip_comments(f.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            pass
    varcols = {}
    for f, t in texts.items():
        if f.suffix in (".css", ".scss"):
            for m in re.finditer(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8}\b|(?:oklch|oklab|rgba?|hsla?|lab|lch)\([^)]*\))", t):
                v = m.group(2)
                varcols.setdefault(m.group(1).lstrip("-").removeprefix("color-"), norm_hex(v) if v.startswith("#") else v)
    hexes = Counter(norm_hex(m.group(0)) for f, t in texts.items() for m in HEX.finditer(t))
    fonts = Counter(first_family(m.group(1) or m.group(2), lower=False) for t in texts.values()
                    for m in re.finditer(r"""font-family\s*:\s*([^;}\n]+)|\bfontFamily\s*:\s*['"`]([^'"`]+)['"`]""", t))
    fonts = Counter({k: v for k, v in fonts.items() if k and k.lower() not in GENERIC_FONTS and not k.startswith(("var(", "theme(", "$", "{"))})
    radii = Counter(f"{px(a, b):g}px" for t in texts.values() for a, b in re.findall(r"rounded(?:-[a-z]{1,2})?-\[(\d+(?:\.\d+)?)(px|rem)\]", t))
    lines = ["---", "version: alpha", "name: TODO", "description: TODO one line on the look and feel", "colors:"]
    used = set()
    for name, h in varcols.items():
        lines.append(f'  {name}: "{h}"')
        used.add(h)
        if len(varcols) > 40 and len(used) >= 40:
            lines.append(f"  # ... {len(varcols) - 40} more custom properties in the CSS")
            break
    for h, n in hexes.most_common(12):
        if h not in used:
            lines.append(f'  # TODO name this: "{h}" (used {n}x)')
    if not varcols and not hexes:
        lines.append('  primary: "#000000"  # TODO')
    lines.append("typography:")
    top = fonts.most_common(3)
    lines += ["  body-md:", f"    fontFamily: {top[0][0] if top else 'TODO'}", "    fontSize: 16px  # TODO", "    lineHeight: 1.5"]
    for fam, n in top[1:]:
        lines.append(f"  # also used ({n}x): {fam}")
    lines.append("rounded:")
    for r, n in radii.most_common(6):
        lines.append(f"  # TODO name this: {r} (used {n}x)")
    lines.append("  md: 8px  # TODO")
    lines += ["---", "", "## Overview", "", "TODO", "", "## Colors", "", "## Typography", "", "## Layout", "",
              "## Elevation & Depth", "", "## Shapes", "", "## Components", "", "## Do's and Don'ts", ""]
    return "\n".join(lines)


# ---------- CLI ----------
def report(name, findings, header, a):
    by = defaultdict(list)
    for f in findings:
        by[(f["severity"], f["rule"])].append(f)
    print(header)
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
    for name in ("check", "drift"):
        p = sub.add_parser(name)
        p.add_argument("design")
        if name == "drift":
            p.add_argument("paths", nargs="+")
        p.add_argument("--fail-on", choices=["error", "warn", "info"])
        p.add_argument("--json")
        p.add_argument("--show", type=int, default=5)
    p = sub.add_parser("draft")
    p.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "draft":
        print(draft(a.paths))
        return
    if not Path(a.design).is_file():
        sys.exit(f"not found: {a.design}")
    if a.cmd == "check":
        findings, tokens = check(a.design)
        c = Counter(f["severity"] for f in findings)
        n = {g: len(tokens.get(g) or {}) for g in ("colors", "typography", "rounded", "spacing", "components")}
        report("check", findings, f"design_drift check: {a.design}: {c['error']} error(s), {c['warn']} warning(s); tokens: "
               + ", ".join(f"{k} {v}" for k, v in n.items()), a)
    else:
        findings, nfiles, source = drift(a.design, a.paths)
        c = Counter(f["severity"] for f in findings)
        report("drift", findings, f"design_drift drift: {nfiles} file(s) against {a.design}"
               + (f" (palette from {source})" if source else " (no hex palette found: colors not checked)")
               + f": {c['warn']} warning(s), {c['info']} note(s)", a)


if __name__ == "__main__":
    main()
