#!/usr/bin/env python3
"""figkit: small, deterministic SVG explainer figures for lessons and guides.

One idea per figure, with every number coming from somewhere you can name. You write a short
Python figure script that builds `fig = Figure(...)` from a few primitives (box, arrow, node,
table, bars, cards, notes, legend); figkit lays out the header and footer, keeps the style
consistent, lints the layout (font sizes, text that won't fit, overlaps, out-of-canvas marks,
a missing source) and writes the SVG. The same script always writes the same bytes.

    figkit.py build fig.py [-o out.svg] [--png]   # run a figure script, lint, write SVG (+PNG)
    figkit.py lint any.svg [...]                   # check any SVG: title, aria-label, fonts, no scripts
    figkit.py demo [-o demo.svg]                   # a figure that uses every primitive

The look (header kicker, title and italic subtitle, mono data text, tinted boxes) was inspired by
the lesson figures in Agentic AI from Scratch (github.com/Ramakm/agentic-ai-from-scratch, MIT);
the code and palette here are our own. Python standard library only; --png needs rsvg-convert.
"""
import argparse
import math
import os
import re
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from xml.sax.saxutils import escape

# Validated-for-contrast tones: stroke, fill tint, text-on-white. Text stays dark.
TONES = {
    "ink":    ("#22252a", "#f1f1ef", "#22252a"),
    "muted":  ("#8a8f98", "#f4f4f2", "#5d626b"),
    "blue":   ("#2f6fd6", "#e8f0fc", "#1d4f9e"),
    "orange": ("#d07a1f", "#fcf0e2", "#94520c"),
    "teal":   ("#16897c", "#e2f4f1", "#0d5f56"),
    "purple": ("#7e57c6", "#f0eafa", "#56368f"),
    "good":   ("#2e8b4f", "#e5f4ea", "#1f6438"),
    "bad":    ("#cc3f3f", "#fbe9e8", "#992626"),
}
ACCENTS = {"blue", "orange", "teal", "purple"}
FONTS = {
    "sans": "'Inter','Segoe UI','Helvetica Neue',Helvetica,Arial,sans-serif",
    "mono": "ui-monospace,SFMono-Regular,Menlo,Consolas,'Liberation Mono',monospace",
    "serif": "Georgia,'Times New Roman',serif",
}
# Conservative average glyph width as a fraction of font size, used to check fit.
WIDTH = {"sans": 0.58, "sans-bold": 0.63, "mono": 0.62, "serif": 0.53}
MIN_FONT = 12
BG = "#fbfbf9"


def tone(name):
    if name not in TONES:
        raise ValueError(f"unknown tone {name!r}; use one of {', '.join(TONES)}")
    return TONES[name]


def num(v):
    """Stable number formatting for coordinates."""
    v = round(float(v), 1)
    return str(int(v)) if v == int(v) else str(v)


def text_width(s, size, font="sans", bold=False):
    key = "sans-bold" if (font == "sans" and bold) else font
    return len(str(s)) * size * WIDTH[key]


class Figure:
    def __init__(self, title, subtitle="", kicker="", source="", width=960, height=540, credit=""):
        self.w, self.h = width, height
        self.title, self.subtitle, self.kicker = title, subtitle, kicker
        self.source, self.credit = source, credit
        self.items = []          # SVG strings, in paint order
        self.texts = []          # (x0, y0, x1, y1, text, size) for collision checks
        self.boxes = []          # (x0, y0, x1, y1, id)
        self.issues = []         # (level, message)
        self.tones = set()
        self.markers = set()
        self.top = 132 if subtitle else 108
        self.bottom = height - 40

    # ---- low-level -------------------------------------------------------------------------
    def _note(self, level, msg):
        self.issues.append((level, msg))

    def _bounds(self, x0, y0, x1, y1, what):
        if x0 < 0 or y0 < 0 or x1 > self.w or y1 > self.h:
            self._note("error", f"{what} runs off the canvas ({num(x0)},{num(y0)})-({num(x1)},{num(y1)})")

    def text(self, x, y, s, size=14, tn="ink", font="sans", anchor="start", bold=False, italic=False,
             fit=None, halo=False, _track=True):
        """Draw text with its baseline at y. fit=max width; warns when it likely won't fit."""
        s = str(s)
        if size < MIN_FONT:
            self._note("error", f"font size {size} below {MIN_FONT}: {s[:40]!r}")
        wdt = text_width(s, size, font, bold)
        if fit is not None and wdt > fit:
            self._note("error", f"text likely too wide ({num(wdt)} > {num(fit)}px): {s[:50]!r}")
        x0 = x - wdt / 2 if anchor == "middle" else x - wdt if anchor == "end" else x
        box = (x0, y - size * 0.8, x0 + wdt, y + size * 0.25)
        self._bounds(*box, f"text {s[:30]!r}")
        if _track:
            self.texts.append((*box, s, size))
        col = TONES[tn][2] if tn in TONES else tn
        attrs = [f'x="{num(x)}"', f'y="{num(y)}"', f'font-family="{FONTS[font]}"', f'font-size="{num(size)}"',
                 f'fill="{col}"']
        if anchor != "start":
            attrs.append(f'text-anchor="{anchor}"')
        if bold:
            attrs.append('font-weight="700"')
        if italic:
            attrs.append('font-style="italic"')
        if halo:
            attrs.append(f'stroke="{BG}" stroke-width="4" paint-order="stroke" stroke-linejoin="round"')
        self.items.append(f'<text {" ".join(attrs)}>{escape(s)}</text>')
        return wdt

    def _rect(self, x, y, w, h, tn, dashed=False, fill=True, rx=8, sw=1.5):
        st, fl, _ = tone(tn)
        self.tones.add(tn)
        d = ' stroke-dasharray="5 4"' if dashed else ""
        f = fl if fill else "none" if fill is False else fill
        self.items.append(f'<rect x="{num(x)}" y="{num(y)}" width="{num(w)}" height="{num(h)}" rx="{rx}" '
                          f'fill="{f}" stroke="{st}" stroke-width="{sw}"{d}/>')

    # ---- primitives ------------------------------------------------------------------------
    def box(self, x, y, w, h, title, sub="", tn="ink", id=None, dashed=False, align="middle", title_size=15,
            sub_size=12.5, mono_sub=True, mono=False):
        """A labelled box. Returns its id for arrows; anchors via fig.anchor(id, side)."""
        self._bounds(x, y, x + w, y + h, f"box {title!r}")
        self.boxes.append((x, y, x + w, y + h, id or title))
        self._rect(x, y, w, h, tn, dashed)
        cx = x + w / 2 if align == "middle" else x + 12
        pad = 24
        lines = 1 + (1 if sub else 0)
        ty = y + h / 2 + (title_size * 0.35 if lines == 1 else -2)
        self.text(cx, ty, title, title_size, tn if not mono else "ink", "mono" if mono else "sans",
                  align if align == "middle" else "start", bold=not mono, fit=w - pad, _track=False)
        if sub:
            self.text(cx, ty + sub_size + 6, sub, sub_size, "muted", "mono" if mono_sub else "sans",
                      align if align == "middle" else "start", fit=w - pad, _track=False)
        if h < (title_size + (sub_size + 8 if sub else 0) + 12):
            self._note("error", f"box {title!r} is too short for its text ({h}px)")
        self._last = (x, y, w, h)
        return id or title

    def anchor(self, id, side="right", t=0.5):
        for x0, y0, x1, y1, bid in self.boxes:
            if bid == id:
                return {"right": (x1, y0 + (y1 - y0) * t), "left": (x0, y0 + (y1 - y0) * t),
                        "top": (x0 + (x1 - x0) * t, y0), "bottom": (x0 + (x1 - x0) * t, y1)}[side]
        raise KeyError(f"no box {id!r}")

    def arrow(self, points, label="", tn="ink", dashed=False, label_side="above", both=False, label_at=None):
        """A polyline arrow through points [(x,y), ...]; the head is at the last point."""
        st = tone(tn)[0]
        self.markers.add(tn)
        d = "M" + " L".join(f"{num(x)} {num(y)}" for x, y in points)
        dash = ' stroke-dasharray="5 4"' if dashed else ""
        start = f' marker-start="url(#ar-{tn})"' if both else ""
        self.items.append(f'<path d="{d}" fill="none" stroke="{st}" stroke-width="1.6"{dash} '
                          f'marker-end="url(#ar-{tn})"{start}/>')
        for x, y in points:
            self._bounds(x, y, x, y, "arrow point")
        if label:
            segs = list(zip(points, points[1:]))
            (ax, ay), (bx, by) = segs[label_at] if label_at is not None else max(
                segs, key=lambda s: math.dist(*s))
            mx, my = (ax + bx) / 2, (ay + by) / 2
            if abs(by - ay) > abs(bx - ax):        # vertical segment: label to the right
                self.text(mx + 8, my + 4, label, 12, "muted", "mono", halo=True)
            else:
                self.text(mx, my - 7 if label_side == "above" else my + 16, label, 12, "muted", "mono",
                          "middle", halo=True)

    def connect(self, a, b, label="", tn="ink", dashed=False, sides=("right", "left"), via=None, **kw):
        """Arrow from box a to box b, straight or with elbows through `via` points."""
        p0, p1 = self.anchor(a, sides[0]), self.anchor(b, sides[1])
        pts = [p0] + list(via or []) + [p1]
        self.arrow(pts, label, tn, dashed, **kw)

    def node(self, cx, cy, r, label, sub="", tn="ink", id=None):
        """A circle with a label, for cycles and hubs."""
        self._bounds(cx - r, cy - r, cx + r, cy + r, f"node {label!r}")
        st, fl, _ = tone(tn)
        self.tones.add(tn)
        self.boxes.append((cx - r, cy - r, cx + r, cy + r, id or label))
        self.items.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" fill="{fl}" stroke="{st}" '
                          f'stroke-width="1.5"/>')
        self.text(cx, cy + (5 if not sub else -2), label, 15, tn, "sans", "middle", bold=True, fit=2 * r - 10,
                  _track=False)
        if sub:
            self.text(cx, cy + 16, sub, 12, "muted", "mono", "middle", fit=2 * r - 10, _track=False)
        return id or label

    def decision(self, cx, cy, w, h, label, tn="ink", id=None):
        """A diamond for a yes/no question. Anchors work like a box's (left/right/top/bottom)."""
        x0, y0 = cx - w / 2, cy - h / 2
        self._bounds(x0, y0, x0 + w, y0 + h, f"decision {label!r}")
        self.boxes.append((x0, y0, x0 + w, y0 + h, id or label))
        st, fl, _ = tone(tn)
        self.tones.add(tn)
        pts = f"{num(cx)},{num(y0)} {num(x0 + w)},{num(cy)} {num(cx)},{num(y0 + h)} {num(x0)},{num(cy)}"
        self.items.append(f'<polygon points="{pts}" fill="{fl}" stroke="{st}" stroke-width="1.5"/>')
        self.text(cx, cy + 5, label, 14, tn, "mono", "middle", fit=w * 0.62, _track=False)
        return id or label

    def meter(self, x, y, used, total, label="", tn="bad", cell=14, gap=4):
        """A row of squares, e.g. a step budget: `used` filled out of `total`."""
        st = tone(tn)[0]
        self.tones.add(tn)
        lx = x
        if label:
            lx += self.text(x, y + cell - 2, label.upper(), 12, "ink", "mono") + 12
        for i in range(total):
            fill = st if i < used else "none"
            stroke = st if i < used else TONES["ink"][0]
            self.items.append(f'<rect x="{num(lx + i * (cell + gap))}" y="{num(y)}" width="{cell}" height="{cell}" '
                              f'rx="2" fill="{fill}" stroke="{stroke}" stroke-width="1.2"/>')
        end = lx + total * (cell + gap) - gap
        self._bounds(x, y, end, y + cell, "meter")
        self.boxes.append((lx, y, end, y + cell, f"meter {label}"))
        return end

    def ring(self, cx, cy, r, label="", tn="muted"):
        """A dashed circle, e.g. the path of a loop."""
        st = tone(tn)[0]
        self.items.append(f'<circle cx="{num(cx)}" cy="{num(cy)}" r="{num(r)}" fill="none" stroke="{st}" '
                          f'stroke-width="1.4" stroke-dasharray="4 5"/>')
        if label:
            self.text(cx, cy + r + 18, label, 12, "muted", "mono", "middle")

    def heading(self, x, y, s, tn="ink", size=13):
        """A small upper-case section label."""
        self.text(x, y, s.upper(), size, tn, "mono", bold=False)

    def table(self, x, y, cols, rows, col_w, row_h=30, head_tn="muted", zebra=True):
        """rows: lists of cells; a cell is text or (text, tone) to tint it (good/bad/accent)."""
        if len(col_w) != len(cols):
            raise ValueError("col_w needs one width per column")
        cx = [x]
        for w in col_w:
            cx.append(cx[-1] + w)
        self._bounds(x, y, cx[-1], y + row_h * (len(rows) + 1), "table")
        self.boxes.append((x, y, cx[-1], y + row_h * (len(rows) + 1), "table"))
        for i, c in enumerate(cols):
            anchor = "start" if i == 0 else "middle"
            tx = cx[i] + 8 if i == 0 else (cx[i] + cx[i + 1]) / 2
            self.text(tx, y + row_h * 0.62, str(c).upper(), 12, head_tn, "mono", anchor, fit=col_w[i] - 8,
                      _track=False)
        self.items.append(f'<line x1="{num(x)}" y1="{num(y + row_h)}" x2="{num(cx[-1])}" y2="{num(y + row_h)}" '
                          f'stroke="{TONES["ink"][0]}" stroke-width="1"/>')
        for r, row in enumerate(rows):
            ry = y + row_h * (r + 1)
            if zebra and r % 2 == 1:
                self.items.append(f'<rect x="{num(x)}" y="{num(ry)}" width="{num(cx[-1] - x)}" '
                                  f'height="{num(row_h)}" fill="#f2f2ef"/>')
            for i, cell in enumerate(row):
                txt, tn = (cell if isinstance(cell, tuple) else (cell, None))
                if tn:
                    st, fl, _ = tone(tn)
                    self.tones.add(tn)
                    self.items.append(f'<rect x="{num(cx[i] + 3)}" y="{num(ry + 3)}" width="{num(col_w[i] - 6)}" '
                                      f'height="{num(row_h - 6)}" rx="4" fill="{fl}" stroke="{st}" '
                                      f'stroke-width="1"/>')
                anchor = "start" if i == 0 else "middle"
                tx = cx[i] + 8 if i == 0 else (cx[i] + cx[i + 1]) / 2
                self.text(tx, ry + row_h * 0.64, txt, 13, tn or "ink", "sans" if i == 0 else "mono", anchor,
                          bold=(tn in ("good", "bad")), fit=col_w[i] - 12, _track=False)
        return cx[-1], y + row_h * (len(rows) + 1)

    def bars(self, x, y, w, items, label_w=150, bar_h=18, gap=12, vmax=None, value_w=70):
        """Horizontal bars: items = [(label, value, tone, value_text?), ...]."""
        vmax = vmax or max(v for _, v, *_ in items) or 1
        track = w - label_w - value_w
        for i, it in enumerate(items):
            label, v, tn = it[0], it[1], it[2]
            vt = it[3] if len(it) > 3 else f"{v:g}"
            by = y + i * (bar_h + gap)
            self.text(x, by + bar_h * 0.75, label, 13, "ink", "sans", fit=label_w - 10)
            bw = max(2, track * v / vmax)
            st, fl, _ = tone(tn)
            self.tones.add(tn)
            self.items.append(f'<rect x="{num(x + label_w)}" y="{num(by)}" width="{num(bw)}" height="{bar_h}" rx="3" '
                              f'fill="{st}"/>')
            self.text(x + label_w + bw + 8, by + bar_h * 0.75, vt, 13, "ink", "mono", fit=value_w + track - bw - 8)
        end = y + len(items) * (bar_h + gap) - gap
        self._bounds(x, y, x + w, end, "bars")
        self.boxes.append((x, y, x + w, end, "bars"))
        return end

    def cards(self, x, y, w, items, h=64, gap=14):
        """Stat cards in a row: items = [(label, value, tone), ...]."""
        cw = (w - gap * (len(items) - 1)) / len(items)
        for i, (label, value, tn) in enumerate(items):
            cx = x + i * (cw + gap)
            self.boxes.append((cx, y, cx + cw, y + h, f"card {label}"))
            self._bounds(cx, y, cx + cw, y + h, f"card {label!r}")
            self._rect(cx, y, cw, h, tn)
            self.text(cx + 12, y + 22, label, 12, "muted", "mono", fit=cw - 20, _track=False)
            self.text(cx + 12, y + h - 14, value, 22, tn, "sans", bold=True, fit=cw - 20, _track=False)
        return y + h

    def notes(self, x, y, lines, w, size=13, gap=8, tn="ink", font="sans", bullet="·"):
        """A short list. Wraps by words to width w; returns the y below it."""
        yy = y
        for line in lines:
            words, cur, out = str(line).split(), "", []
            for wd in words:
                trial = (cur + " " + wd).strip()
                if text_width(bullet + " " + trial, size, font) > w and cur:
                    out.append(cur)
                    cur = wd
                else:
                    cur = trial
            out.append(cur)
            indent = text_width(bullet + " ", size, font) if bullet else 0
            for j, ln in enumerate(out):
                if j == 0:
                    self.text(x, yy + size, (bullet + " " if bullet else "") + ln, size, tn, font, fit=w)
                else:  # continuation lines line up under the first word (SVG collapses leading spaces)
                    self.text(x + indent, yy + size, ln, size, tn, font, fit=w - indent)
                yy += size + 5
            yy += gap
        return yy

    def legend(self, x, y, items):
        """items = [(tone, label), ...] in one row."""
        cx = x
        for tn, label in items:
            st, fl, _ = tone(tn)
            self.tones.add(tn)
            self.items.append(f'<rect x="{num(cx)}" y="{num(y - 10)}" width="12" height="12" rx="2" fill="{fl}" '
                              f'stroke="{st}" stroke-width="1.2"/>')
            cx += 18 + self.text(cx + 18, y, label, 12, "muted", "mono") + 18

    def divider(self, x, y0, y1):
        self.items.append(f'<line x1="{num(x)}" y1="{num(y0)}" x2="{num(x)}" y2="{num(y1)}" stroke="#d9d9d4" '
                          f'stroke-width="1"/>')

    # ---- output ----------------------------------------------------------------------------
    def lint(self):
        issues = list(self.issues)
        if not self.source.strip():
            issues.append(("error", "source is empty: say where every number and claim comes from"))
        if len(self.title) > 70:
            issues.append(("error", f"title is {len(self.title)} characters; keep it under 70"))
        if len(self.subtitle) > 120:
            issues.append(("warning", f"subtitle is {len(self.subtitle)} characters; keep it under 120"))
        acc = sorted(t for t in self.tones if t in ACCENTS)
        if len(acc) > 3:
            issues.append(("warning", f"{len(acc)} accent colours ({', '.join(acc)}); 3 or fewer reads faster"))
        n = len(self.items)
        if n > 220:
            issues.append(("warning", f"{n} marks; a figure that busy usually holds two ideas"))
        for i, a in enumerate(self.texts):
            for b in self.texts[i + 1:]:
                if a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]:
                    issues.append(("error", f"text overlaps: {a[4][:30]!r} and {b[4][:30]!r}"))
        for i, a in enumerate(self.boxes):
            for b in self.boxes[i + 1:]:
                inter = a[0] < b[2] and b[0] < a[2] and a[1] < b[3] and b[1] < a[3]
                nested = (a[0] <= b[0] and a[1] <= b[1] and a[2] >= b[2] and a[3] >= b[3]) or \
                         (b[0] <= a[0] and b[1] <= a[1] and b[2] >= a[2] and b[3] >= a[3])
                if inter and not nested:
                    issues.append(("error", f"boxes overlap: {a[4]!r} and {b[4]!r}"))
        for t in self.texts:
            for b in self.boxes:
                inter = t[0] < b[2] - 1 and b[0] + 1 < t[2] and t[1] < b[3] - 1 and b[1] + 1 < t[3]
                inside = t[0] >= b[0] and t[2] <= b[2] and t[1] >= b[1] and t[3] <= b[3]
                if inter and not inside:
                    issues.append(("error", f"text {t[4][:30]!r} crosses the edge of {b[4]!r}"))
        floor = self.h - 34
        for t in self.texts:
            if t[3] > floor:
                issues.append(("error", f"text {t[4][:30]!r} runs into the footer; make the figure taller"))
        for b in self.boxes:
            if b[3] > floor:
                issues.append(("error", f"{b[4]!r} runs into the footer; make the figure taller"))
            if b[1] < self.top - 8:
                issues.append(("error", f"{b[4]!r} starts inside the header (content starts at y={self.top})"))
        if self.bottom < self.top + 120:
            issues.append(("error", "canvas too short for a header, a footer and content"))
        return issues

    def svg(self):
        head = []
        if self.kicker:
            head.append(self._raw_text(40, 40, self.kicker.upper(), 12, TONES["blue"][2], "mono",
                                       spacing=1.5))
        head.append(self._raw_text(40, 74, self.title, 26, TONES["ink"][2], "sans", bold=True))
        if self.subtitle:
            head.append(self._raw_text(40, 100, self.subtitle, 15, TONES["muted"][2], "serif", italic=True))
        rule_y = self.top - 14
        head.append(f'<line x1="40" y1="{rule_y}" x2="{self.w - 40}" y2="{rule_y}" stroke="#d9d9d4" '
                    f'stroke-width="1"/>')
        foot = [self._raw_text(40, self.h - 16, "source: " + self.source, 12, TONES["muted"][2], "mono")]
        if self.credit:
            foot.append(self._raw_text(self.w - 40, self.h - 16, self.credit, 12, TONES["muted"][2], "mono",
                                       anchor="end"))
        defs = []
        for tn in sorted(self.markers):
            defs.append(f'<marker id="ar-{tn}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" '
                        f'markerHeight="7" orient="auto-start-reverse"><path d="M0 0L10 5L0 10z" '
                        f'fill="{TONES[tn][0]}"/></marker>')
        label = escape(self.title + (". " + self.subtitle if self.subtitle else ""), {'"': "&quot;"})
        return "\n".join([
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{self.w}" height="{self.h}" '
            f'viewBox="0 0 {self.w} {self.h}" role="img" aria-label="{label}">',
            f"<title>{escape(self.title)}</title>",
            f"<defs>{''.join(defs)}</defs>",
            f'<rect width="{self.w}" height="{self.h}" fill="{BG}"/>',
            *head, *self.items, *foot, "</svg>", ""])

    def _raw_text(self, x, y, s, size, col, font, bold=False, italic=False, anchor="start", spacing=0):
        a = [f'x="{num(x)}"', f'y="{num(y)}"', f'font-family="{FONTS[font]}"', f'font-size="{size}"', f'fill="{col}"']
        if bold:
            a.append('font-weight="700"')
        if italic:
            a.append('font-style="italic"')
        if anchor != "start":
            a.append(f'text-anchor="{anchor}"')
        if spacing:
            a.append(f'letter-spacing="{spacing}"')
        wdt = text_width(s, size, font, bold) + (len(s) * spacing)
        if wdt > self.w - 80:
            self.issues.append(("error", f"header/footer text too wide: {s[:50]!r}"))
        return f'<text {" ".join(a)}>{escape(s)}</text>'

    def save(self, path):
        Path(path).write_text(self.svg(), encoding="utf-8")


# ---- lint for any SVG file -----------------------------------------------------------------
def lint_svg(text):
    issues = []
    head = text[:2000]
    if "<svg" not in head:
        return [("error", "not an SVG")]
    if not re.search(r"<title>[^<]+</title>", text):
        issues.append(("error", "no <title> (screen readers and search need it)"))
    if 'role="img"' not in head or "aria-label=" not in head:
        issues.append(("warning", 'add role="img" and aria-label on the <svg> element'))
    if "viewBox=" not in head:
        issues.append(("error", "no viewBox, so it won't scale"))
    if re.search(r"<script|<foreignObject|\son[a-z]+\s*=", text, re.I):
        issues.append(("error", "scripts, event handlers or foreignObject: not allowed in a figure"))
    if re.search(r'(?:xlink:)?href\s*=\s*"(?!#)', text):
        issues.append(("error", "external href: figures must be self-contained"))
    sizes = [float(s) for s in re.findall(r'font-size="([0-9.]+)', text)]
    sizes += [float(s) for s in re.findall(r"font-size:\s*([0-9.]+)px", text)]
    small = [s for s in sizes if s < MIN_FONT]
    if small:
        issues.append(("warning", f"{len(small)} text elements below {MIN_FONT}px (smallest {min(small):g}); "
                                  "hard to read on a phone"))
    return issues


def to_png(svg_path, png_path, width=1920):
    exe = shutil.which("rsvg-convert")
    if not exe:
        return False
    subprocess.run([exe, "-w", str(width), str(svg_path), "-o", str(png_path)], check=True)
    return True


def report(issues, name):
    errs = [m for lvl, m in issues if lvl == "error"]
    warns = [m for lvl, m in issues if lvl == "warning"]
    for m in errs:
        print(f"{name}: error: {m}")
    for m in warns:
        print(f"{name}: warning: {m}")
    print(f"{name}: {len(errs)} errors, {len(warns)} warnings")
    return 1 if errs else 0


def demo():
    f = Figure("Every primitive, once", "A box, arrows, a node, a table, bars, cards, notes and a legend.",
               kicker="figkit · demo", source="figkit.py demo (made-up numbers)", height=560)
    f.box(40, 140, 150, 60, "Input", "a box", "blue", id="a")
    f.box(260, 140, 150, 60, "Step", "dashed", "orange", id="b", dashed=True)
    f.connect("a", "b", "arrow")
    f.node(500, 172, 34, "Node", tn="teal", id="n")
    f.connect("b", "n", sides=("right", "left"))
    f.table(40, 236, ["case", "result", "score"],
            [["first", ("PASS", "good"), "1.00"], ["second", ("FAIL", "bad"), "0.57"]], [150, 110, 110])
    f.bars(460, 250, 460, [("alpha", 5.2, "blue"), ("beta", 2.7, "orange"), ("gamma", 0.4, "teal")],
           label_w=90)
    f.cards(40, 360, 420, [("cards", "3/10", "purple"), ("show", "9/10", "good")])
    f.notes(500, 360, ["notes wrap by words to the width you give them", "one idea per figure"], 400)
    f.legend(40, 470, [("good", "pass"), ("bad", "fail"), ("blue", "accent")])
    return f


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="run a figure script that defines `fig`, lint it, write the SVG")
    b.add_argument("script")
    b.add_argument("-o", "--out")
    b.add_argument("--png", action="store_true", help="also write a PNG (needs rsvg-convert)")
    b.add_argument("--force", action="store_true", help="write even with lint errors")
    l = sub.add_parser("lint", help="check SVG files")
    l.add_argument("svg", nargs="+")
    d = sub.add_parser("demo")
    d.add_argument("-o", "--out", default="figkit-demo.svg")
    a = ap.parse_args(argv)

    if a.cmd == "lint":
        rc = 0
        for p in a.svg:
            rc |= report(lint_svg(Path(p).read_text(encoding="utf-8", errors="replace")), p)
        return rc
    if a.cmd == "demo":
        f = demo()
        rc = report(f.lint(), "demo")
        f.save(a.out)
        print(f"wrote {a.out}")
        return rc
    script = Path(a.script)
    sys.modules.setdefault("figkit", sys.modules[__name__])  # `from figkit import Figure` gets this module
    ns = runpy.run_path(str(script), run_name="figure")
    f = ns.get("fig")
    if not isinstance(f, Figure):
        print(f"{script}: define `fig = Figure(...)` at module level", file=sys.stderr)
        return 2
    rc = report(f.lint(), script.name)
    if rc and not a.force:
        print("not written: fix the errors above (or --force)", file=sys.stderr)
        return rc
    out = Path(a.out or script.with_suffix(".svg"))
    f.save(out)
    print(f"wrote {out}")
    if a.png:
        png = out.with_suffix(".png")
        print(f"wrote {png}" if to_png(out, png) else "no rsvg-convert: skipped the PNG")
    return rc


if __name__ == "__main__":
    sys.exit(main())
