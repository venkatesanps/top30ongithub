#!/usr/bin/env python3
"""Turn an outline into a mind map: SVG (two-sided tree), Mermaid mindmap, OPML and a
collapsible HTML page.

  mindmap.py render OUTLINE.md [-o OUTDIR] [--name NAME] [--formats svg,mmd,opml,html]
  mindmap.py lint   OUTLINE.md [--json]
  mindmap.py template

Outline format (Markdown): the first `# Heading` is the centre; nested `-` bullets (2 or 4
space indent) are branches. A bullet may end with ` :: note` - the note shows on hover in
SVG/HTML and in OPML; Mermaid drops it (Mermaid mindmaps have no notes).
Standard library only; output is deterministic.
"""
import argparse
import html
import json
import re
import sys
from pathlib import Path

PALETTE = ["#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#65a30d"]
FONT = "-apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"

TEMPLATE = """# Central idea

- Branch one :: optional note shown on hover
  - Detail
  - Detail
- Branch two
  - Detail
    - Finer detail
- Branch three
"""


def parse(text):
    root, stack = None, []
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("<!--"):
            continue
        m = re.match(r"^#\s+(.+)", raw)
        if m and root is None:
            root = {"label": m.group(1).strip(), "note": "", "children": [], "line": 0}
            stack = [(-1, root)]
            continue
        m = re.match(r"^(\s*)[-*+]\s+(.+)", raw)
        if not m:
            continue
        if root is None:
            root = {"label": "Mind map", "note": "", "children": [], "line": 0}
            stack = [(-1, root)]
        indent = len(m.group(1).replace("\t", "    "))
        label, _, note = m.group(2).partition(" :: ")
        node = {"label": label.strip(), "note": note.strip(), "children": []}
        while stack and stack[-1][0] >= indent:
            stack.pop()
        stack[-1][1]["children"].append(node)
        stack.append((indent, node))
    if root is None:
        raise ValueError("empty outline: start with '# Central idea' and '-' bullets")
    return root


def walk(n, depth=0):
    yield n, depth
    for c in n["children"]:
        yield from walk(c, depth + 1)


def lint(root):
    fs = []

    def add(sev, msg):
        fs.append({"severity": sev, "msg": msg})

    b = len(root["children"])
    if b < 2:
        add("error", f"{b} main branch(es): a mind map needs at least 2")
    elif b > 8:
        add("warn", f"{b} main branches: 3-7 is easier to take in; group some")
    seen = {}
    for n, d in walk(root):
        words = len(n["label"].split())
        if d >= 4:
            add("warn", f"'{n['label']}' is {d} levels deep: move detail to a note or a second map")
        if words > 7 and d > 0:
            add("warn", f"'{n['label']}' is {words} words: a map label is a keyword or short phrase; put the sentence in ' :: note'")
        if len(n["children"]) > 7:
            add("warn", f"'{n['label']}' has {len(n['children'])} children: group them")
        key = n["label"].lower()
        if key in seen and d > 0:
            add("info", f"'{n['label']}' appears twice; if it's the same idea, link it once")
        seen[key] = 1
    return fs


def tw(s, size):
    """Rough text width in px for a sans font."""
    wide = sum(1 for ch in s if ch in "MWmw@%")
    narrow = sum(1 for ch in s if ch in "il.,:;'|!ftj ()")
    return (len(s) + 0.35 * wide - 0.4 * narrow) * size * 0.56


def layout(root):
    """Two-sided tree. Returns a list of placed nodes and edges."""
    ROW, GAP = 30, 34
    kids = root["children"]
    # balance sides by leaf count
    def leaves(n):
        return max(1, sum(leaves(c) for c in n["children"]))
    right, left, lr, ll = [], [], 0, 0
    for i, c in enumerate(kids):
        c["_color"] = PALETTE[i % len(PALETTE)]
        if lr <= ll:
            right.append(c)
            lr += leaves(c)
        else:
            left.append(c)
            ll += leaves(c)
    placed, edges = [], []
    rsize = 20
    rw = tw(root["label"], rsize) + 44
    root_box = {"n": root, "x": -rw / 2, "y": -24, "w": rw, "h": 48, "depth": 0, "color": "#111827"}
    placed.append(root_box)

    def size(d):
        return {1: 15, 2: 13.5}.get(d, 12.5)

    def side(nodes, sign):
        # widths per depth
        colw = {}
        for c in nodes:
            for n, d in walk(c, 1):
                colw[d] = max(colw.get(d, 0), tw(n["label"], size(d)) + (26 if d == 1 else 14))
        xs = {1: rw / 2 + GAP + 10}
        for d in range(2, max(colw, default=1) + 1):
            xs[d] = xs[d - 1] + colw[d - 1] + GAP
        total = sum(leaves(c) for c in nodes) * ROW
        cursor = [-total / 2]

        def place(n, d, color, parent_box):
            if n["children"]:
                ys = []
                boxes_before = len(placed)
                for c in n["children"]:
                    ys.append(place(c, d + 1, color, None))
                y = (ys[0] + ys[-1]) / 2
            else:
                y = cursor[0] + ROW / 2
                cursor[0] += ROW
            w = tw(n["label"], size(d)) + (26 if d == 1 else 14)
            h = 30 if d == 1 else 22
            x = xs[d] if sign > 0 else -xs[d] - w
            box = {"n": n, "x": x, "y": y - h / 2, "w": w, "h": h, "depth": d, "color": color, "sign": sign}
            placed.append(box)
            for c in n["children"]:
                cb = next(b for b in placed if b["n"] is c)
                edges.append((box, cb, color, d + 1))
            n["_box"] = box
            return y
        if sign > 0:
            order = nodes
        else:
            order = nodes
        for c in order:
            place(c, 1, c["_color"], root_box)
            edges.append((root_box, c["_box"], c["_color"], 1))

    side(right, 1)
    side(left, -1)
    return placed, edges


def edge_path(a, b):
    sign = b.get("sign", 1)
    if a["depth"] == 0:
        x1 = a["x"] + (a["w"] if sign > 0 else 0)
        y1 = a["y"] + a["h"] / 2
    else:
        x1 = a["x"] + (a["w"] if sign > 0 else 0)
        y1 = a["y"] + a["h"] / 2 if a["depth"] == 1 else a["y"] + a["h"]
    x2 = b["x"] if sign > 0 else b["x"] + b["w"]
    y2 = b["y"] + b["h"] / 2 if b["depth"] == 1 else b["y"] + b["h"]
    mx = (x1 + x2) / 2
    return f"M{x1:.1f},{y1:.1f} C{mx:.1f},{y1:.1f} {mx:.1f},{y2:.1f} {x2:.1f},{y2:.1f}"


def to_svg(root, title=None):
    placed, edges = layout(root)
    pad = 30
    minx = min(b["x"] for b in placed) - pad
    maxx = max(b["x"] + b["w"] for b in placed) + pad
    miny = min(b["y"] for b in placed) - pad - 10
    maxy = max(b["y"] + b["h"] for b in placed) + pad
    W, H = maxx - minx, maxy - miny
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="{minx:.0f} {miny:.0f} {W:.0f} {H:.0f}" '
           f'width="{W:.0f}" height="{H:.0f}" font-family="{FONT}" role="img" aria-label="{html.escape(root["label"])} mind map">',
           f'<title>{html.escape(title or root["label"])}</title>',
           f'<rect x="{minx:.0f}" y="{miny:.0f}" width="{W:.0f}" height="{H:.0f}" fill="#ffffff"/>']
    for a, b, color, d in edges:
        width = {1: 4, 2: 2.2}.get(d, 1.5)
        out.append(f'<path d="{edge_path(a, b)}" fill="none" stroke="{color}" stroke-width="{width}" stroke-linecap="round" opacity="0.85"/>')
    for b in placed:
        n, d = b["n"], b["depth"]
        label = html.escape(n["label"])
        note = f'<title>{html.escape(n["note"])}</title>' if n.get("note") else ""
        cx = b["x"] + b["w"] / 2
        if d == 0:
            out.append(f'<g>{note}<rect x="{b["x"]:.1f}" y="{b["y"]:.1f}" width="{b["w"]:.1f}" height="{b["h"]}" rx="24" fill="#111827"/>'
                       f'<text x="{cx:.1f}" y="{b["y"] + 31:.1f}" text-anchor="middle" font-size="20" font-weight="700" fill="#fff">{label}</text></g>')
        elif d == 1:
            out.append(f'<g>{note}<rect x="{b["x"]:.1f}" y="{b["y"]:.1f}" width="{b["w"]:.1f}" height="{b["h"]}" rx="15" fill="{b["color"]}"/>'
                       f'<text x="{cx:.1f}" y="{b["y"] + 20:.1f}" text-anchor="middle" font-size="15" font-weight="600" fill="#fff">{label}</text></g>')
        else:
            size = 13.5 if d == 2 else 12.5
            weight = "500" if d == 2 else "400"
            fill = "#111827" if d == 2 else "#374151"
            ul = f'<line x1="{b["x"]:.1f}" y1="{b["y"] + b["h"]:.1f}" x2="{b["x"] + b["w"]:.1f}" y2="{b["y"] + b["h"]:.1f}" stroke="{b["color"]}" stroke-width="{2.2 if d == 2 else 1.5}"/>'
            dot = " •" if n.get("note") else ""
            out.append(f'<g>{note}{ul}<text x="{cx:.1f}" y="{b["y"] + b["h"] - 6:.1f}" text-anchor="middle" font-size="{size}" '
                       f'font-weight="{weight}" fill="{fill}">{label}{dot}</text></g>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def mm_escape(s):
    s = re.sub(r"[()\[\]{}]", "", s)
    return s.replace('"', "'")


def to_mermaid(root):
    lines = ["mindmap", f"  root(({mm_escape(root['label'])}))"]
    for n, d in walk(root):
        if d == 0:
            continue
        lines.append("  " * (d + 1) + mm_escape(n["label"]))
    return "\n".join(lines) + "\n"


def to_opml(root):
    def node(n, ind):
        attrs = f'text="{html.escape(n["label"], quote=True)}"'
        if n.get("note"):
            attrs += f' _note="{html.escape(n["note"], quote=True)}"'
        if not n["children"]:
            return f'{ind}<outline {attrs}/>'
        inner = "\n".join(node(c, ind + "  ") for c in n["children"])
        return f'{ind}<outline {attrs}>\n{inner}\n{ind}</outline>'
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<opml version="2.0">\n'
            f'  <head><title>{html.escape(root["label"])}</title></head>\n  <body>\n'
            f'{node(root, "    ")}\n  </body>\n</opml>\n')


def to_html(root, svg):
    def li(n):
        note = f' <span class="note">{html.escape(n["note"])}</span>' if n.get("note") else ""
        if not n["children"]:
            return f"<li>{html.escape(n['label'])}{note}</li>"
        return (f"<li><details open><summary>{html.escape(n['label'])}{note}</summary><ul>"
                + "".join(li(c) for c in n["children"]) + "</ul></details></li>")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(root['label'])}</title>
<style>
:root{{--bg:#fff;--fg:#111827;--muted:#6b7280;--line:#e5e7eb}}
@media (prefers-color-scheme:dark){{:root:not([data-theme=light]){{--bg:#0b0f17;--fg:#e5e7eb;--muted:#9ca3af;--line:#1f2937}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 {FONT}}}
main{{max-width:1200px;margin:0 auto;padding:24px 16px}}
.map{{overflow:auto;border:1px solid var(--line);border-radius:12px;background:#fff}}
.map svg{{display:block;max-width:none}}
ul{{list-style:none;padding-left:18px;border-left:1px solid var(--line)}}
summary{{cursor:pointer;font-weight:600}} .note{{color:var(--muted);font-weight:400;font-size:13px}}
.bar{{display:flex;gap:8px;margin:12px 0}} button{{font:inherit;padding:4px 10px;border-radius:8px;border:1px solid var(--line);background:transparent;color:inherit;cursor:pointer}}
</style></head><body><main>
<h1>{html.escape(root['label'])}</h1>
<div class="map">{svg}</div>
<h2>Outline</h2>
<div class="bar"><button onclick="document.querySelectorAll('details').forEach(d=>d.open=true)">Expand all</button>
<button onclick="document.querySelectorAll('details').forEach(d=>d.open=false)">Collapse all</button></div>
<ul style="border:0;padding:0">{li(root)}</ul>
</main></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("outline")
    r.add_argument("-o", "--outdir", default=".")
    r.add_argument("--name")
    r.add_argument("--formats", default="svg,mmd,opml,html")
    li = sub.add_parser("lint")
    li.add_argument("outline")
    li.add_argument("--json", action="store_true")
    sub.add_parser("template")
    a = ap.parse_args()
    if a.cmd == "template":
        print(TEMPLATE, end="")
        return 0
    try:
        root = parse(Path(a.outline).read_text())
    except (OSError, ValueError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    fs = lint(root)
    if a.cmd == "lint":
        if a.json:
            print(json.dumps({"findings": fs}, indent=2))
        else:
            for f in fs:
                print(f"{f['severity'].upper():5} {f['msg']}")
            print(f"{sum(1 for _ in walk(root))} nodes, {len(root['children'])} branches")
        return 1 if any(f["severity"] == "error" for f in fs) else 0
    if any(f["severity"] == "error" for f in fs):
        for f in fs:
            print(f"{f['severity'].upper():5} {f['msg']}", file=sys.stderr)
        return 1
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    name = a.name or Path(a.outline).stem
    svg = to_svg(root)
    makers = {"svg": lambda: svg, "mmd": lambda: to_mermaid(root), "opml": lambda: to_opml(root),
              "html": lambda: to_html(root, svg)}
    for fmt in a.formats.split(","):
        fmt = fmt.strip()
        if fmt not in makers:
            print(f"unknown format {fmt}", file=sys.stderr)
            return 2
        p = out / f"{name}.{fmt}"
        p.write_text(makers[fmt]())
        print(f"wrote {p}")
    for f in fs:
        print(f"{f['severity'].upper():5} {f['msg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
