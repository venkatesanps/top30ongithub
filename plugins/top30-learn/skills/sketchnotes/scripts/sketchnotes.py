#!/usr/bin/env python3
"""Render a sketchnote - a one-page, hand-drawn-looking visual summary - as SVG.

  sketchnotes.py render SPEC.json [-o OUT.svg] [--seed N]
  sketchnotes.py lint   SPEC.json [--json]
  sketchnotes.py template          # a starter spec
  sketchnotes.py icons             # the doodle icons you can use

Spec: {"title", "subtitle", "layout": "path" | "grid", "columns": 3,
       "sections": [{"heading", "icon", "points": [...], "note"}],
       "takeaway": "one sentence", "footer": "source line"}
"path" numbers the sections and joins them with arrows (a process); "grid" doesn't (a topic).
Wobble is seeded, so the same spec gives the same drawing. Standard library only.
"""
import argparse
import html
import json
import math
import random
import sys
from pathlib import Path

HAND = "'Patrick Hand', 'Comic Neue', 'Segoe Print', 'Bradley Hand', 'Comic Sans MS', 'Chalkboard SE', cursive"
INK = "#1f2937"
INKS = ["#2563eb", "#db2777", "#059669", "#d97706", "#7c3aed", "#dc2626", "#0891b2", "#65a30d"]
WASH = ["#dbeafe", "#fce7f3", "#d1fae5", "#fef3c7", "#ede9fe", "#fee2e2", "#cffafe", "#ecfccb"]

TEMPLATE = {
    "title": "Topic in one line",
    "subtitle": "Who it's for, or the question it answers",
    "layout": "path",
    "columns": 3,
    "sections": [
        {"heading": "First step", "icon": "person", "points": ["Short phrase", "Another phrase"]},
        {"heading": "Second step", "icon": "gear", "points": ["What happens", "Why it matters"]},
        {"heading": "Third step", "icon": "check", "points": ["The result"]},
    ],
    "takeaway": "The one thing to remember.",
    "footer": "Source: where the facts came from",
}


class Pen:
    def __init__(self, seed):
        self.r = random.Random(seed)

    def j(self, a=1.6):
        return self.r.uniform(-a, a)

    def line(self, x1, y1, x2, y2, color=INK, w=2.0, extra=""):
        mx, my = (x1 + x2) / 2 + self.j(2), (y1 + y2) / 2 + self.j(2)
        return (f'<path d="M{x1 + self.j():.1f},{y1 + self.j():.1f} Q{mx:.1f},{my:.1f} {x2 + self.j():.1f},{y2 + self.j():.1f}" '
                f'fill="none" stroke="{color}" stroke-width="{w}" stroke-linecap="round" {extra}/>')

    def rect(self, x, y, w, h, color=INK, sw=2.2, fill="none", r=10):
        # two passes, slightly different, like a marker going round twice
        out = []
        for k in range(2):
            pts = []
            for (px, py) in [(x + r, y), (x + w - r, y), (x + w, y + r), (x + w, y + h - r), (x + w - r, y + h), (x + r, y + h),
                             (x, y + h - r), (x, y + r)]:
                pts.append((px + self.j(1.8), py + self.j(1.8)))
            d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f} L{pts[1][0]:.1f},{pts[1][1]:.1f} Q{x + w + self.j():.1f},{y + self.j():.1f} {pts[2][0]:.1f},{pts[2][1]:.1f} " \
                f"L{pts[3][0]:.1f},{pts[3][1]:.1f} Q{x + w + self.j():.1f},{y + h + self.j():.1f} {pts[4][0]:.1f},{pts[4][1]:.1f} " \
                f"L{pts[5][0]:.1f},{pts[5][1]:.1f} Q{x + self.j():.1f},{y + h + self.j():.1f} {pts[6][0]:.1f},{pts[6][1]:.1f} " \
                f"L{pts[7][0]:.1f},{pts[7][1]:.1f} Q{x + self.j():.1f},{y + self.j():.1f} {pts[0][0]:.1f},{pts[0][1]:.1f}"
            out.append(f'<path d="{d}" fill="{fill if k == 0 else "none"}" stroke="{color}" stroke-width="{sw if k == 0 else sw * 0.55}" '
                       f'stroke-linejoin="round" opacity="{1 if k == 0 else 0.6}"/>')
        return "".join(out)

    def circle(self, cx, cy, r, color=INK, sw=2, fill="none"):
        pts = []
        start = self.r.uniform(0, math.pi * 2)
        for i in range(13):
            a = start + i / 12 * math.pi * 2.08
            rr = r + self.j(r * 0.06)
            pts.append((cx + rr * math.cos(a), cy + rr * math.sin(a)))
        d = f"M{pts[0][0]:.1f},{pts[0][1]:.1f} " + " ".join(f"L{p[0]:.1f},{p[1]:.1f}" for p in pts[1:])
        return f'<path d="{d}" fill="{fill}" stroke="{color}" stroke-width="{sw}" stroke-linejoin="round" stroke-linecap="round"/>'

    def arrow(self, x1, y1, x2, y2, color=INK, w=2.4, bend=0.0):
        mx = (x1 + x2) / 2 - (y2 - y1) * bend + self.j(3)
        my = (y1 + y2) / 2 + (x2 - x1) * bend + self.j(3)
        ang = math.atan2(y2 - my, x2 - mx)
        h1 = (x2 - 13 * math.cos(ang - 0.45), y2 - 13 * math.sin(ang - 0.45))
        h2 = (x2 - 13 * math.cos(ang + 0.45), y2 - 13 * math.sin(ang + 0.45))
        return (f'<path d="M{x1:.1f},{y1:.1f} Q{mx:.1f},{my:.1f} {x2:.1f},{y2:.1f}" fill="none" stroke="{color}" stroke-width="{w}" '
                f'stroke-linecap="round"/><path d="M{h1[0]:.1f},{h1[1]:.1f} L{x2:.1f},{y2:.1f} L{h2[0]:.1f},{h2[1]:.1f}" fill="none" '
                f'stroke="{color}" stroke-width="{w}" stroke-linecap="round" stroke-linejoin="round"/>')

    def underline(self, x, y, w, color):
        return self.line(x, y, x + w, y + self.j(1.5), color, 3.2, 'opacity="0.8"')


# ---- doodle icons, drawn in a 48x48 box at (x, y)
def icon(p, name, x, y, c):
    s = []
    L = lambda a, b, cc, d, w=2.2: s.append(p.line(x + a, y + b, x + cc, y + d, c, w))
    R = lambda a, b, w, h, f="none", r=6: s.append(p.rect(x + a, y + b, w, h, c, 2.0, f, r))
    C = lambda a, b, r, f="none": s.append(p.circle(x + a, y + b, r, c, 2.0, f))
    T = lambda a, b, t, size=12: s.append(f'<text x="{x + a}" y="{y + b}" font-family="{HAND}" font-size="{size}" fill="{c}" text-anchor="middle" font-weight="700">{t}</text>')
    if name == "card":
        R(4, 10, 40, 28); L(4, 18, 44, 18, 4); R(9, 26, 9, 6, "none", 2); L(26, 31, 38, 31)
    elif name == "store":
        L(6, 18, 42, 18); L(6, 18, 10, 8); L(42, 18, 38, 8); L(10, 8, 38, 8); R(9, 18, 30, 24, "none", 2); R(20, 28, 9, 14, "none", 2)
    elif name == "bank":
        L(4, 16, 24, 6); L(24, 6, 44, 16); L(4, 16, 44, 16)
        for xx in (10, 20, 29, 38):
            L(xx, 19, xx, 36)
        L(4, 40, 44, 40); L(6, 36, 42, 36)
    elif name == "network":
        C(24, 24, 6); C(8, 10, 4); C(40, 10, 4); C(8, 38, 4); C(40, 38, 4)
        L(12, 13, 19, 20); L(36, 13, 29, 20); L(12, 35, 19, 28); L(36, 35, 29, 28)
    elif name == "shield":
        s.append(f'<path d="M{x+24},{y+4} L{x+40},{y+10} Q{x+40},{y+34} {x+24},{y+44} Q{x+8},{y+34} {x+8},{y+10} Z" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>')
        L(17, 24, 22, 30); L(22, 30, 32, 18)
    elif name == "lock":
        R(10, 20, 28, 22, "none", 4); s.append(f'<path d="M{x+16},{y+20} V{y+13} Q{x+16},{y+5} {x+24},{y+5} Q{x+32},{y+5} {x+32},{y+13} V{y+20}" fill="none" stroke="{c}" stroke-width="2.2"/>'); C(24, 30, 3)
    elif name == "clock":
        C(24, 24, 18); L(24, 24, 24, 12); L(24, 24, 32, 28)
    elif name == "money":
        R(4, 12, 40, 24, "none", 4); C(24, 24, 7); T(24, 28, "$", 11)
    elif name == "coins":
        for i, yy in enumerate((34, 27, 20)):
            s.append(f'<ellipse cx="{x+24}" cy="{y+yy}" rx="14" ry="5" fill="none" stroke="{c}" stroke-width="2"/>')
        T(24, 17, "$", 11)
    elif name == "doc":
        s.append(f'<path d="M{x+10},{y+4} H{x+30} L{x+38},{y+12} V{y+44} H{x+10} Z" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>')
        for yy in (18, 25, 32):
            L(15, yy, 33, yy, 1.6)
    elif name == "check":
        C(24, 24, 18); L(15, 25, 22, 32, 3); L(22, 32, 34, 16, 3)
    elif name == "warning":
        s.append(f'<path d="M{x+24},{y+5} L{x+44},{y+41} H{x+4} Z" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>')
        L(24, 17, 24, 30, 3); C(24, 35, 1.5, c)
    elif name == "bulb":
        C(24, 19, 13); L(18, 32, 18, 38); L(30, 32, 30, 38); L(18, 38, 30, 38); L(20, 42, 28, 42)
        L(24, 1, 24, 3); L(5, 19, 8, 19); L(40, 19, 43, 19)
    elif name == "person":
        C(24, 13, 8); s.append(f'<path d="M{x+8},{y+44} Q{x+8},{y+25} {x+24},{y+25} Q{x+40},{y+25} {x+40},{y+44}" fill="none" stroke="{c}" stroke-width="2.2"/>')
    elif name == "cart":
        L(4, 8, 11, 8); L(11, 8, 16, 32); L(16, 32, 38, 32); L(13, 14, 42, 14); L(42, 14, 38, 26); L(38, 26, 15, 26); C(19, 39, 3); C(35, 39, 3)
    elif name == "phone":
        R(14, 4, 20, 40, "none", 4); L(21, 9, 27, 9, 1.6); C(24, 38, 1.8)
    elif name == "globe":
        C(24, 24, 18); s.append(f'<ellipse cx="{x+24}" cy="{y+24}" rx="8" ry="18" fill="none" stroke="{c}" stroke-width="1.8"/>'); L(6, 24, 42, 24, 1.8); L(9, 15, 39, 15, 1.4); L(9, 33, 39, 33, 1.4)
    elif name == "scale":
        L(24, 6, 24, 40); L(14, 40, 34, 40); L(8, 12, 40, 12)
        s.append(f'<path d="M{x+2},{y+26} L{x+8},{y+12} L{x+14},{y+26} Q{x+8},{y+31} {x+2},{y+26}" fill="none" stroke="{c}" stroke-width="2"/>')
        s.append(f'<path d="M{x+34},{y+26} L{x+40},{y+12} L{x+46},{y+26} Q{x+40},{y+31} {x+34},{y+26}" fill="none" stroke="{c}" stroke-width="2"/>')
    elif name == "chart":
        L(6, 6, 6, 42); L(6, 42, 44, 42); R(11, 28, 7, 14, "none", 1); R(22, 18, 7, 24, "none", 1); R(33, 10, 7, 32, "none", 1)
    elif name == "gear":
        C(24, 24, 12); C(24, 24, 4)
        for i in range(8):
            a = i * math.pi / 4
            L(24 + 12 * math.cos(a), 24 + 12 * math.sin(a), 24 + 18 * math.cos(a), 24 + 18 * math.sin(a), 3)
    elif name == "terminal":
        R(8, 4, 32, 40, "none", 4); R(13, 9, 22, 12, "none", 2)
        for yy in (28, 35):
            for xx in (15, 24, 33):
                C(xx, yy, 2)
    elif name == "calendar":
        R(6, 9, 36, 33, "none", 3); L(6, 18, 42, 18); L(15, 5, 15, 12); L(33, 5, 33, 12); T(24, 36, "31", 13)
    elif name == "arrows":
        s.append(p.arrow(x + 6, y + 16, x + 42, y + 16, c, 2)); s.append(p.arrow(x + 42, y + 32, x + 6, y + 32, c, 2))
    elif name == "magnifier":
        C(20, 20, 13); L(30, 30, 43, 43, 3.5)
    elif name == "flag":
        L(10, 4, 10, 44); s.append(f'<path d="M{x+10},{y+6} Q{x+24},{y+1} {x+28},{y+8} T{x+42},{y+8} V{y+24} Q{x+34},{y+28} {x+28},{y+24} T{x+10},{y+24}" fill="none" stroke="{c}" stroke-width="2.2"/>')
    else:
        C(24, 24, 16); T(24, 29, "?", 16)
    return "".join(s)


ICONS = ["card", "store", "bank", "network", "shield", "lock", "clock", "money", "coins", "doc", "check", "warning", "bulb",
         "person", "cart", "phone", "globe", "scale", "chart", "gear", "terminal", "calendar", "arrows", "magnifier", "flag"]


def wrap(text, width_px, size):
    per = max(6, int(width_px / (size * 0.5)))
    words, lines, cur = text.split(), [], ""
    for w in words:
        if len(cur) + len(w) + 1 > per and cur:
            lines.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        lines.append(cur)
    return lines


def lint(spec):
    fs = []

    def add(sev, msg):
        fs.append({"severity": sev, "msg": msg})
    secs = spec.get("sections") or []
    if not spec.get("title"):
        add("error", "no title")
    if not secs:
        add("error", "no sections")
    if len(secs) > 9:
        add("warn", f"{len(secs)} sections: a sketchnote reads best with 4-8; split it")
    for i, s in enumerate(secs, 1):
        h = s.get("heading", "")
        if not h:
            add("error", f"section {i} has no heading")
        if len(h.split()) > 5:
            add("warn", f"section {i} heading is {len(h.split())} words; keep it to 1-4")
        if s.get("icon") and s["icon"] not in ICONS:
            add("warn", f"section {i}: unknown icon '{s['icon']}' (see `icons`); a ? is drawn")
        pts = s.get("points") or []
        if len(pts) > 4:
            add("warn", f"section {i} has {len(pts)} points; 2-3 keeps it visual")
        for pnt in pts:
            if len(pnt.split()) > 10:
                add("warn", f"section {i}: '{pnt[:40]}...' is {len(pnt.split())} words; sketchnote points are phrases (<=10 words)")
    if not spec.get("takeaway"):
        add("info", "no takeaway: one sentence at the bottom is what people remember")
    if spec.get("layout", "path") not in ("path", "grid"):
        add("error", "layout must be 'path' or 'grid'")
    return fs


def render(spec, seed=7):
    p = Pen(seed)
    secs = spec["sections"]
    cols = int(spec.get("columns") or (3 if len(secs) > 4 else len(secs)))
    cols = max(1, min(cols, 4))
    rows = math.ceil(len(secs) / cols)
    W = 1200
    margin, gapx, gapy = 50, 56, 64
    cw = (W - 2 * margin - gapx * (cols - 1)) / cols
    # cell height from content
    def cell_h(s):
        n = sum(len(wrap(pt, cw - 50, 19)) for pt in s.get("points", []))
        return 120 + n * 26 + (30 if s.get("note") else 0)
    ch = max(cell_h(s) for s in secs)
    top = 190 if spec.get("subtitle") else 160
    H = top + rows * ch + (rows - 1) * gapy + (150 if spec.get("takeaway") else 50) + (30 if spec.get("footer") else 0)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" height="{H:.0f}" font-family="{HAND}" role="img" '
           f'aria-label="{html.escape(spec["title"])} sketchnote">', f'<title>{html.escape(spec["title"])}</title>',
           f'<rect width="{W}" height="{H:.0f}" fill="#fffdf7"/>']
    # faint dot grid, like a notebook
    out.append('<defs><pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse"><circle cx="2" cy="2" r="1" fill="#e7e2d3"/></pattern></defs>')
    out.append(f'<rect width="{W}" height="{H:.0f}" fill="url(#dots)"/>')
    # title banner
    t = html.escape(spec["title"])
    tw = min(W - 120, len(spec["title"]) * 24 + 80)
    tx = (W - tw) / 2
    out.append(p.rect(tx, 34, tw, 76, INK, 3, "#fde68a", 16))
    out.append(f'<text x="{W / 2}" y="85" text-anchor="middle" font-size="44" font-weight="700" fill="{INK}">{t}</text>')
    if spec.get("subtitle"):
        out.append(f'<text x="{W / 2}" y="148" text-anchor="middle" font-size="24" fill="#4b5563">{html.escape(spec["subtitle"])}</text>')
    path = spec.get("layout", "path") == "path"
    centers = []
    for i, s in enumerate(secs):
        r, c = divmod(i, cols)
        if path and r % 2 == 1:
            c = cols - 1 - c  # serpentine, so arrows don't cross the page
        x = margin + c * (cw + gapx)
        y = top + r * (ch + gapy)
        ink, wash = INKS[i % len(INKS)], WASH[i % len(WASH)]
        out.append(p.rect(x, y, cw, ch, ink, 2.4, "#ffffff", 14))
        out.append(f'<rect x="{x + 14}" y="{y + 14}" width="64" height="64" rx="32" fill="{wash}"/>')
        out.append(icon(p, s.get("icon", ""), x + 22, y + 22, ink))
        if path:
            out.append(p.circle(x + cw - 26, y + 28, 17, ink, 2.4, wash))
            out.append(f'<text x="{x + cw - 26}" y="{y + 36}" text-anchor="middle" font-size="22" font-weight="700" fill="{ink}">{i + 1}</text>')
        hlines = wrap(s.get("heading", ""), cw - 150, 27)
        hy = y + 46 - (len(hlines) - 1) * 14
        for k, hl in enumerate(hlines):
            out.append(f'<text x="{x + 92}" y="{hy + k * 28:.0f}" font-size="27" font-weight="700" fill="{INK}">{html.escape(hl)}</text>')
        out.append(p.underline(x + 92, hy + (len(hlines) - 1) * 28 + 10, min(cw - 150, max(len(l) for l in hlines) * 13), ink))
        yy = y + 120
        for pt in s.get("points", []):
            lines = wrap(pt, cw - 50, 19)
            out.append(p.circle(x + 26, yy - 6, 4, ink, 2, ink))
            for k, ln in enumerate(lines):
                out.append(f'<text x="{x + 40}" y="{yy + k * 24}" font-size="20" fill="{INK}">{html.escape(ln)}</text>')
            yy += len(lines) * 24 + 4
        if s.get("note"):
            out.append(f'<text x="{x + 26}" y="{y + ch - 18}" font-size="17" fill="{ink}" font-style="italic">{html.escape(s["note"])}</text>')
        centers.append((x, y, cw, ch, r))
    if path:
        for i in range(len(centers) - 1):
            x1, y1, w1, h1, r1 = centers[i]
            x2, y2, w2, h2, r2 = centers[i + 1]
            if r1 == r2:
                if x2 > x1:
                    out.append(p.arrow(x1 + w1 + 6, y1 + h1 / 2, x2 - 8, y2 + h2 / 2, INK, 2.6, 0.12))
                else:
                    out.append(p.arrow(x1 - 6, y1 + h1 / 2, x2 + w2 + 8, y2 + h2 / 2, INK, 2.6, 0.12))
            else:
                out.append(p.arrow(x1 + w1 / 2, y1 + h1 + 6, x2 + w2 / 2, y2 - 8, INK, 2.6, 0.0))
    if spec.get("takeaway"):
        ty = top + rows * ch + (rows - 1) * gapy + 40
        out.append(p.rect(margin, ty, W - 2 * margin, 80, "#b45309", 2.6, "#fef3c7", 18))
        out.append(icon(p, "bulb", margin + 18, ty + 16, "#b45309"))
        tl = wrap(spec["takeaway"], W - 2 * margin - 110, 24)
        for k, ln in enumerate(tl[:2]):
            out.append(f'<text x="{margin + 80}" y="{ty + (40 if len(tl) > 1 else 50) + k * 28}" font-size="25" font-weight="700" fill="#78350f">{html.escape(ln)}</text>')
    if spec.get("footer"):
        out.append(f'<text x="{W / 2}" y="{H - 18:.0f}" text-anchor="middle" font-size="15" fill="#6b7280">{html.escape(spec["footer"])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def icon_sheet():
    p = Pen(3)
    cols, size = 8, 110
    rows = math.ceil(len(ICONS) / cols)
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {cols * size} {rows * size}" width="{cols * size}" height="{rows * size}" font-family="{HAND}">',
           f'<rect width="100%" height="100%" fill="#fffdf7"/>']
    for i, n in enumerate(ICONS):
        r, c = divmod(i, cols)
        out.append(icon(p, n, c * size + 31, r * size + 14, INKS[i % len(INKS)]))
        out.append(f'<text x="{c * size + 55}" y="{r * size + 90}" text-anchor="middle" font-size="16" fill="{INK}">{n}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("spec")
    r.add_argument("-o", "--out")
    r.add_argument("--seed", type=int, default=7)
    li = sub.add_parser("lint")
    li.add_argument("spec")
    li.add_argument("--json", action="store_true")
    sub.add_parser("template")
    ic = sub.add_parser("icons")
    ic.add_argument("-o", "--out")
    a = ap.parse_args()
    if a.cmd == "template":
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    if a.cmd == "icons":
        if a.out:
            Path(a.out).write_text(icon_sheet())
            print(f"wrote {a.out}")
        else:
            print(" ".join(ICONS))
        return 0
    try:
        spec = json.loads(Path(a.spec).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    fs = lint(spec)
    if a.cmd == "lint":
        if a.json:
            print(json.dumps({"findings": fs}, indent=2))
        else:
            for f in fs:
                print(f"{f['severity'].upper():5} {f['msg']}")
            print(f"{len(spec.get('sections') or [])} sections")
        return 1 if any(f["severity"] == "error" for f in fs) else 0
    if any(f["severity"] == "error" for f in fs):
        for f in fs:
            print(f"{f['severity'].upper():5} {f['msg']}", file=sys.stderr)
        return 1
    out = Path(a.out or Path(a.spec).with_suffix("").with_suffix(".svg").name)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(spec, a.seed))
    print(f"wrote {out}")
    for f in fs:
        print(f"{f['severity'].upper():5} {f['msg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
