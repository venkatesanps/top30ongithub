#!/usr/bin/env python3
"""Render an educational comic from a script: one SVG per page, an HTML reader, and
image-generation prompts per panel (so you can redraw it with an image model, keeping
characters consistent).

  edu_comics.py render COMIC.json [-o OUTDIR] [--name NAME]
  edu_comics.py lint   COMIC.json [--json]
  edu_comics.py template

Spec: {"title", "subtitle", "style": "flat, friendly, ...",
       "characters": {"id": {"name", "role", "color", "hair", "accessory": "glasses|tie|apron|headset|cap|none",
                              "look": "text description for image prompts"}},
       "pages": [{"title", "panels": [{"scene", "setting": "shop|office|bank|phone|street|plain",
                   "caption", "cast": ["id", ...], "bubbles": [{"who", "text", "kind": "speech|thought|shout"}],
                   "props": ["card", ...], "lesson": "what this panel teaches"}]}],
       "footer": "source line"}
Props reuse the sketchnotes icon names. Standard library only; deterministic.
"""
import argparse
import html
import json
import math
import sys
from pathlib import Path

FONT = "'Comic Neue', 'Patrick Hand', 'Segoe Print', 'Comic Sans MS', 'Chalkboard SE', cursive"
INK = "#111827"
SKIN = ["#f2c7a5", "#d9a27e", "#a86b4a", "#7a4a33", "#f5d0b5"]
SETTINGS = {
    "shop": ("#fef3c7", "#fde68a"), "office": ("#e0f2fe", "#bae6fd"), "bank": ("#ede9fe", "#ddd6fe"),
    "phone": ("#dcfce7", "#bbf7d0"), "street": ("#e0e7ff", "#c7d2fe"), "plain": ("#f8fafc", "#e2e8f0"),
    "home": ("#fce7f3", "#fbcfe8"),
}
TEMPLATE = {
    "title": "Comic title",
    "subtitle": "What the reader will understand by the end",
    "style": "clean flat cartoon, thick outlines, soft colours",
    "characters": {
        "guide": {"name": "Sam", "role": "explains things", "color": "#2563eb", "hair": "#1f2937", "accessory": "glasses",
                  "look": "adult with short dark hair, round glasses, blue shirt"},
        "learner": {"name": "Ana", "role": "asks questions", "color": "#db2777", "hair": "#92400e", "accessory": "none",
                    "look": "adult with shoulder-length brown hair, pink sweater"},
    },
    "pages": [{"title": "Page 1", "panels": [
        {"scene": "Ana looks puzzled at a laptop", "setting": "office", "caption": "Monday morning.", "cast": ["learner", "guide"],
         "bubbles": [{"who": "learner", "text": "Why did this happen?"}, {"who": "guide", "text": "Let me show you, step by step."}],
         "props": ["phone"], "lesson": "Sets up the question the comic answers"}]}],
    "footer": "Source: ...",
}


def wrap(text, per):
    out, cur = [], ""
    for w in text.split():
        if len(cur) + len(w) + 1 > per and cur:
            out.append(cur)
            cur = w
        else:
            cur = (cur + " " + w).strip()
    if cur:
        out.append(cur)
    return out


def lint(spec):
    fs = []

    def add(sev, where, msg):
        fs.append({"severity": sev, "where": where, "msg": msg})
    chars = spec.get("characters") or {}
    if not spec.get("title"):
        add("error", "comic", "no title")
    if not spec.get("pages"):
        add("error", "comic", "no pages")
    if len(chars) > 4:
        add("warn", "comic", f"{len(chars)} characters; 2-3 are easier to follow")
    for cid, c in chars.items():
        if not c.get("look"):
            add("info", f"character {cid}", "no 'look' text; image prompts will be vague and characters may drift")
    for pi, pg in enumerate(spec.get("pages") or [], 1):
        panels = pg.get("panels") or []
        if not panels:
            add("error", f"page {pi}", "no panels")
        if len(panels) > 6:
            add("warn", f"page {pi}", f"{len(panels)} panels; keep to 4-6 per page")
        for qi, p in enumerate(panels, 1):
            w = f"page {pi} panel {qi}"
            bs = p.get("bubbles") or []
            if len(bs) > 2:
                add("warn", w, f"{len(bs)} bubbles; 1-2 per panel keeps it readable")
            for b in bs:
                if b.get("who") not in chars:
                    add("error", w, f"bubble speaker '{b.get('who')}' is not in characters")
                n = len(b.get("text", "").split())
                if n > 25:
                    add("warn", w, f"bubble is {n} words; keep to 25 or fewer")
                if b.get("kind", "speech") not in ("speech", "thought", "shout"):
                    add("warn", w, f"unknown bubble kind {b.get('kind')}")
            for cid in p.get("cast") or []:
                if cid not in chars:
                    add("error", w, f"cast member '{cid}' is not in characters")
            for b in bs:
                if b.get("who") in chars and b.get("who") not in (p.get("cast") or []):
                    add("info", w, f"'{b['who']}' speaks but isn't in the cast (off-panel voice)")
            if not p.get("lesson"):
                add("warn", w, "no lesson: say what this panel teaches, or cut it")
            if p.get("caption") and len(p["caption"].split()) > 20:
                add("warn", w, "caption over 20 words")
            if p.get("setting") and p["setting"] not in SETTINGS:
                add("info", w, f"setting '{p['setting']}' unknown; plain background used")
    return fs


# ---- drawing
def person(cid, c, x, y, s, facing=1):
    """A simple friendly figure standing with feet at (x, y). s = scale (1 = ~150px tall)."""
    col = c.get("color", "#2563eb")
    hair = c.get("hair", "#1f2937")
    skin = c.get("skin") or SKIN[sum(map(ord, cid)) % len(SKIN)]
    acc = c.get("accessory", "none")
    g = [f'<g transform="translate({x:.1f},{y:.1f}) scale({s * facing:.3f},{s:.3f})">']
    # legs and body
    g.append(f'<path d="M-14,0 L-11,-46 M14,0 L11,-46" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>')
    g.append(f'<path d="M-30,-44 Q-32,-96 0,-100 Q32,-96 30,-44 Z" fill="{col}" stroke="{INK}" stroke-width="3" stroke-linejoin="round"/>')
    if acc == "apron":
        g.append(f'<path d="M-18,-90 L18,-90 L22,-44 L-22,-44 Z" fill="#fff" stroke="{INK}" stroke-width="2.5"/>')
    if acc == "tie":
        g.append(f'<path d="M0,-98 L-6,-88 L0,-62 L6,-88 Z" fill="#dc2626" stroke="{INK}" stroke-width="2"/>')
    # arms
    g.append(f'<path d="M-28,-88 Q-44,-70 -36,-52 M28,-88 Q46,-76 44,-58" fill="none" stroke="{INK}" stroke-width="6" stroke-linecap="round"/>')
    # head
    g.append(f'<circle cx="0" cy="-124" r="25" fill="{skin}" stroke="{INK}" stroke-width="3"/>')
    style = c.get("hair_style", "short")
    if style == "long":
        g.append(f'<path d="M-27,-122 Q-30,-158 0,-156 Q30,-158 27,-122 L28,-96 L18,-100 L18,-132 Q0,-140 -18,-132 L-18,-100 L-28,-96 Z" fill="{hair}" stroke="{INK}" stroke-width="2.5"/>')
    elif style == "bun":
        g.append(f'<circle cx="0" cy="-156" r="10" fill="{hair}" stroke="{INK}" stroke-width="2.5"/>')
        g.append(f'<path d="M-26,-124 Q-28,-152 0,-151 Q28,-152 26,-124 Q16,-138 0,-138 Q-16,-138 -26,-124 Z" fill="{hair}" stroke="{INK}" stroke-width="2.5"/>')
    elif style == "bald":
        pass
    else:
        g.append(f'<path d="M-26,-122 Q-28,-154 0,-153 Q28,-154 26,-122 Q20,-138 4,-136 Q-14,-142 -26,-122 Z" fill="{hair}" stroke="{INK}" stroke-width="2.5"/>')
    # face (looks toward +x; the group is mirrored for facing=-1)
    g.append(f'<circle cx="7" cy="-126" r="2.8" fill="{INK}"/><circle cx="-6" cy="-126" r="2.8" fill="{INK}"/>')
    g.append(f'<path d="M-5,-114 Q2,-108 9,-114" fill="none" stroke="{INK}" stroke-width="2.5" stroke-linecap="round"/>')
    if acc == "glasses":
        g.append(f'<circle cx="7" cy="-126" r="7" fill="none" stroke="{INK}" stroke-width="2"/><circle cx="-6" cy="-126" r="7" fill="none" stroke="{INK}" stroke-width="2"/><path d="M0,-126 L0,-126" stroke="{INK}"/>')
    if acc == "headset":
        g.append(f'<path d="M-24,-128 Q-26,-156 0,-156 Q26,-156 24,-128" fill="none" stroke="{INK}" stroke-width="4"/><path d="M24,-124 Q26,-108 10,-106" fill="none" stroke="{INK}" stroke-width="3"/><circle cx="9" cy="-106" r="3" fill="{INK}"/>')
    if acc == "cap":
        g.append(f'<path d="M-26,-134 Q-24,-160 0,-158 Q24,-160 26,-134 Z M20,-136 L42,-134" fill="{col}" stroke="{INK}" stroke-width="3" stroke-linecap="round"/>')
    g.append("</g>")
    return "".join(g)


def bubble(x, y, w, text, kind, tail_to, color="#ffffff"):
    """Draw a bubble whose top-left is (x, y) and width w; returns (svg, height)."""
    lines = wrap(text, max(10, int(w / 9.2)))
    h = 20 + len(lines) * 20
    tx, ty = tail_to
    cx = min(max(tx, x + 24), x + w - 24)
    out = []
    if kind == "thought":
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{h / 2:.0f}" fill="{color}" stroke="{INK}" stroke-width="2.5" stroke-dasharray="1 0"/>')
        for k, r in enumerate((6, 4)):
            px = cx + (tx - cx) * (k + 1) / 3
            py = y + h + (ty - y - h) * (k + 1) / 3
            out.append(f'<circle cx="{px:.1f}" cy="{py:.1f}" r="{r}" fill="{color}" stroke="{INK}" stroke-width="2"/>')
    elif kind == "shout":
        pts = []
        n = 18
        for i in range(n):
            a = i / n * math.pi * 2
            rr = 1.0 if i % 2 == 0 else 1.12
            pts.append((x + w / 2 + (w / 2 + 6) * rr * math.cos(a), y + h / 2 + (h / 2 + 6) * rr * math.sin(a)))
        out.append(f'<path d="M{pts[0][0]:.1f},{pts[0][1]:.1f} ' + " ".join(f"L{p[0]:.1f},{p[1]:.1f}" for p in pts[1:]) + f' Z" fill="#fef9c3" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>')
        out.append(f'<path d="M{cx - 9:.1f},{y + h + 2} L{tx:.1f},{ty:.1f} L{cx + 9:.1f},{y + h + 2}" fill="#fef9c3" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>')
    else:
        out.append(f'<path d="M{cx - 10:.1f},{y + h - 2} L{tx:.1f},{ty:.1f} L{cx + 10:.1f},{y + h - 2}" fill="{color}" stroke="{INK}" stroke-width="2.5" stroke-linejoin="round"/>')
        out.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{color}" stroke="{INK}" stroke-width="2.5"/>')
        out.append(f'<rect x="{cx - 9:.1f}" y="{y + h - 5}" width="18" height="6" fill="{color}"/>')
    for k, ln in enumerate(lines):
        weight = "700" if kind == "shout" else "400"
        out.append(f'<text x="{x + w / 2:.1f}" y="{y + 25 + k * 20}" text-anchor="middle" font-size="16" font-weight="{weight}" fill="{INK}">{html.escape(ln)}</text>')
    return "".join(out), h


def backdrop(setting, x, y, w, h):
    a, b = SETTINGS.get(setting or "plain", SETTINGS["plain"])
    s = [f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{a}"/>',
         f'<rect x="{x}" y="{y + h * 0.78:.1f}" width="{w}" height="{h * 0.22:.1f}" fill="{b}"/>']
    if setting == "shop":
        s.append(f'<rect x="{x + w * 0.62:.1f}" y="{y + h * 0.56:.1f}" width="{w * 0.34:.1f}" height="{h * 0.22:.1f}" fill="#fff7ed" stroke="{INK}" stroke-width="2"/>')
        for i in range(4):
            s.append(f'<path d="M{x + i * w / 4:.1f},{y} h{w / 8:.1f} v18 h-{w / 8:.1f} Z" fill="#f97316" opacity="0.5"/>')
    elif setting == "office":
        s.append(f'<rect x="{x + w * 0.08:.1f}" y="{y + h * 0.18:.1f}" width="{w * 0.22:.1f}" height="{h * 0.2:.1f}" fill="#fff" stroke="{INK}" stroke-width="2"/>')
        s.append(f'<path d="M{x + w * 0.1:.1f},{y + h * 0.33:.1f} l{w * 0.05:.1f},-{h * 0.06:.1f} l{w * 0.04:.1f},{h * 0.03:.1f} l{w * 0.06:.1f},-{h * 0.07:.1f}" fill="none" stroke="#2563eb" stroke-width="2"/>')
    elif setting == "bank":
        for i in range(4):
            cx = x + w * (0.12 + i * 0.1)
            s.append(f'<rect x="{cx:.1f}" y="{y + h * 0.3:.1f}" width="10" height="{h * 0.48:.1f}" fill="#fff" stroke="{INK}" stroke-width="1.5" opacity="0.8"/>')
    elif setting == "home":
        s.append(f'<rect x="{x + w * 0.7:.1f}" y="{y + h * 0.14:.1f}" width="{w * 0.2:.1f}" height="{h * 0.24:.1f}" fill="#e0f2fe" stroke="{INK}" stroke-width="2"/>')
    elif setting == "street":
        s.append(f'<rect x="{x + w * 0.06:.1f}" y="{y + h * 0.2:.1f}" width="{w * 0.18:.1f}" height="{h * 0.58:.1f}" fill="#c7d2fe" stroke="{INK}" stroke-width="1.5"/>')
    return "".join(s)


def prop_icon(name, x, y, color):
    try:
        sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sketchnotes" / "scripts"))
        import sketchnotes  # noqa: E402
        return sketchnotes.icon(sketchnotes.Pen(len(name)), name, x, y, color)
    except Exception:
        return f'<circle cx="{x + 24}" cy="{y + 24}" r="18" fill="none" stroke="{color}" stroke-width="2"/>'


def render_page(spec, page, pno, total):
    chars = spec["characters"]
    panels = page["panels"]
    cols = 2 if len(panels) <= 4 else 3
    if len(panels) <= 2:
        cols = len(panels)
    rows = math.ceil(len(panels) / cols)
    W, margin, gap = 1200, 36, 22
    pw = (W - 2 * margin - gap * (cols - 1)) / cols
    ph = 470 if cols < 3 else 420
    top = 120
    H = top + rows * ph + (rows - 1) * gap + 70
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H:.0f}" width="{W}" height="{H:.0f}" font-family="{FONT}" role="img" '
           f'aria-label="{html.escape(spec["title"])} page {pno}">', f'<title>{html.escape(spec["title"])} - page {pno}</title>',
           f'<rect width="{W}" height="{H:.0f}" fill="#fffef8"/>']
    out.append(f'<text x="{margin}" y="62" font-size="38" font-weight="700" fill="{INK}">{html.escape(spec["title"])}</text>')
    if page.get("title"):
        out.append(f'<text x="{margin}" y="96" font-size="21" fill="#4b5563">Page {pno} of {total}: {html.escape(page["title"])}</text>')
    for i, p in enumerate(panels):
        r, c = divmod(i, cols)
        x, y = margin + c * (pw + gap), top + r * (ph + gap)
        cid = f"clip{pno}_{i}"
        out.append(f'<clipPath id="{cid}"><rect x="{x}" y="{y}" width="{pw:.1f}" height="{ph}" rx="6"/></clipPath><g clip-path="url(#{cid})">')
        out.append(backdrop(p.get("setting"), x, y, pw, ph))
        # props on the floor/counter, right side
        for k, pr in enumerate(p.get("props") or []):
            out.append(prop_icon(pr, x + pw - 70 - k * 58, y + ph * 0.62, "#374151"))
        cast = p.get("cast") or []
        floor = y + ph - 22
        n = max(1, len(cast))
        heads = {}
        sc = 1.15 if n <= 2 else 0.95
        for k, who in enumerate(cast):
            cx = x + pw * (k + 1) / (n + 1)
            facing = 1 if cx < x + pw / 2 else -1
            if n == 1:
                facing = 1
            out.append(person(who, chars.get(who, {}), cx, floor, sc, facing))
            heads[who] = (cx, floor - 150 * sc)
            out.append(f'<text x="{cx:.1f}" y="{floor + 16:.1f}" text-anchor="middle" font-size="13" fill="#374151">{html.escape(chars.get(who, {}).get("name", who))}</text>')
        by = y + (54 if p.get("caption") else 14)
        bubbles = p.get("bubbles") or []
        for k, b in enumerate(bubbles):
            who = b.get("who")
            hx, hy = heads.get(who, (x + pw - 20 if k else x + 20, y + ph * 0.5))
            bw = min(pw - 28, 330, max(150, len(b.get("text", "")) * 9 + 44))
            bx = x + 14 if (len(bubbles) == 1 and hx < x + pw / 2) or (len(bubbles) > 1 and k == 0) else x + pw - bw - 14
            if len(bubbles) == 1 and abs(hx - (x + pw / 2)) < 30:
                bx = x + (pw - bw) / 2
            svg, bh = bubble(bx, by, bw, b.get("text", ""), b.get("kind", "speech"), (hx, hy - 34))
            out.append(svg)
            by += bh + 16
        if p.get("caption"):
            cl = wrap(p["caption"], int((pw - 20) / 8.6))[:2]
            out.append(f'<rect x="{x}" y="{y}" width="{pw:.1f}" height="{14 + 20 * len(cl)}" fill="#fde68a" stroke="{INK}" stroke-width="2"/>')
            for k, ln in enumerate(cl):
                out.append(f'<text x="{x + 12}" y="{y + 22 + k * 20}" font-size="16" font-weight="700" fill="{INK}">{html.escape(ln)}</text>')
        out.append("</g>")
        out.append(f'<rect x="{x}" y="{y}" width="{pw:.1f}" height="{ph}" rx="6" fill="none" stroke="{INK}" stroke-width="4"/>')
        out.append(f'<text x="{x + pw - 10:.1f}" y="{y + ph - 8}" text-anchor="end" font-size="12" fill="#6b7280">{i + 1}</text>')
    if spec.get("footer"):
        out.append(f'<text x="{W / 2}" y="{H - 26:.0f}" text-anchor="middle" font-size="14" fill="#6b7280">{html.escape(spec["footer"])}</text>')
    out.append("</svg>")
    return "\n".join(out) + "\n"


def prompts_md(spec):
    chars = spec["characters"]
    style = spec.get("style", "clean flat cartoon, thick outlines")
    out = [f"# Image prompts: {spec['title']}", "",
           "One prompt per panel for an image model. Paste the character sheet into every prompt so the cast stays consistent.",
           "Speech is listed separately: add the bubbles in a layout tool, since image models garble text.", "",
           "## Character sheet", ""]
    sheet = []
    for cid, c in chars.items():
        line = f"- **{c.get('name', cid)}** ({c.get('role', '')}): {c.get('look', '')}"
        out.append(line)
        sheet.append(f"{c.get('name', cid)}: {c.get('look', '')}")
    out += ["", f"Style: {style}", ""]
    for pi, pg in enumerate(spec["pages"], 1):
        out.append(f"## Page {pi}: {pg.get('title', '')}")
        out.append("")
        for qi, p in enumerate(pg["panels"], 1):
            cast = [chars[c].get("name", c) for c in p.get("cast", []) if c in chars]
            out.append(f"### Panel {pi}.{qi}")
            out.append("")
            out.append(f"> {style}. Scene: {p.get('scene', '')}. Setting: {p.get('setting', 'plain')}. "
                       f"Characters: {'; '.join(s for s in sheet if s.split(':')[0] in cast) or 'none'}. "
                       f"Props: {', '.join(p.get('props', [])) or 'none'}. No text or lettering in the image.")
            out.append("")
            if p.get("caption"):
                out.append(f"- Caption: {p['caption']}")
            for b in p.get("bubbles", []):
                out.append(f"- {chars.get(b['who'], {}).get('name', b['who'])} ({b.get('kind', 'speech')}): \"{b['text']}\"")
            out.append(f"- Teaches: {p.get('lesson', '')}")
            out.append("")
    return "\n".join(out)


def reader_html(spec, files):
    title = html.escape(spec["title"])
    lessons = []
    for pi, pg in enumerate(spec["pages"], 1):
        for qi, p in enumerate(pg["panels"], 1):
            if p.get("lesson"):
                lessons.append(f"<li><b>{pi}.{qi}</b> {html.escape(p['lesson'])}</li>")
    imgs = "".join(f'<figure><img src="{f}" alt="{title} page {i}" loading="lazy"><figcaption>Page {i}</figcaption></figure>' for i, f in enumerate(files, 1))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>
:root{{--bg:#f8fafc;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--card:#fff}}
@media (prefers-color-scheme:dark){{:root{{--bg:#0b1220;--ink:#e2e8f0;--muted:#94a3b8;--line:#22304d;--card:#111a2e}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:16px/1.55 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 48px}}h1{{margin:0 0 4px}}.sub{{color:var(--muted);margin:0 0 20px}}
figure{{margin:0 0 24px}}img{{width:100%;height:auto;border-radius:10px;border:1px solid var(--line);background:#fff}}figcaption{{color:var(--muted);font-size:13px;text-align:center}}
.lessons{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:16px 20px}}.lessons li{{margin:4px 0}}
</style></head><body><main><h1>{title}</h1><p class="sub">{html.escape(spec.get("subtitle", ""))}</p>{imgs}
<section class="lessons"><h2>What each panel teaches</h2><ol style="list-style:none;padding:0">{"".join(lessons)}</ol></section>
<p class="sub">{html.escape(spec.get("footer", ""))}</p></main></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("spec")
    r.add_argument("-o", "--outdir", default=".")
    r.add_argument("--name")
    li = sub.add_parser("lint")
    li.add_argument("spec")
    li.add_argument("--json", action="store_true")
    sub.add_parser("template")
    a = ap.parse_args()
    if a.cmd == "template":
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    try:
        spec = json.loads(Path(a.spec).read_text())
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    fs = lint(spec)
    errs = [f for f in fs if f["severity"] == "error"]
    if a.cmd == "lint":
        if a.json:
            print(json.dumps({"findings": fs}, indent=2))
        else:
            for f in fs:
                print(f"{f['severity'].upper():5} {f['where']}: {f['msg']}")
            n = sum(len(p.get("panels") or []) for p in spec.get("pages") or [])
            print(f"{len(spec.get('pages') or [])} pages, {n} panels, {len(errs)} errors")
        return 1 if errs else 0
    if errs:
        for f in errs:
            print(f"ERROR {f['where']}: {f['msg']}", file=sys.stderr)
        return 1
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    name = a.name or Path(a.spec).name.split(".")[0]
    files = []
    for i, pg in enumerate(spec["pages"], 1):
        fn = f"{name}-page{i}.svg"
        (out / fn).write_text(render_page(spec, pg, i, len(spec["pages"])))
        files.append(fn)
        print(f"wrote {out / fn}")
    (out / f"{name}.prompts.md").write_text(prompts_md(spec))
    (out / f"{name}.html").write_text(reader_html(spec, files))
    print(f"wrote {out / (name + '.prompts.md')}\nwrote {out / (name + '.html')}")
    for f in fs:
        if f["severity"] == "warn":
            print(f"WARN  {f['where']}: {f['msg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
