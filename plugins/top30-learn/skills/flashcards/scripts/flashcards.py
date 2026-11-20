#!/usr/bin/env python3
"""Build a flashcard deck from one spec: Anki import file, printable cards, a self-contained
study page with spaced repetition, and Markdown.

  flashcards.py render DECK.json|DECK.csv [-o OUTDIR] [--name NAME] [--formats anki,print,study,md]
  flashcards.py lint   DECK.json|DECK.csv [--json]
  flashcards.py template

Spec (JSON): {"deck": "Name", "description": "...", "cards": [
    {"front": "Question?", "back": "Short answer", "tags": ["topic"], "source": "where it's from"},
    {"type": "cloze", "front": "The {{c1::issuer}} approves the auth", "tags": [...]} ]}
CSV: columns front,back,tags,source,type (tags separated by spaces).
Cloze cards use Anki syntax {{c1::answer}} or {{c1::answer::hint}}; the back is optional extra.
Standard library only; output is deterministic.
"""
import argparse
import csv
import html
import json
import re
import sys
from pathlib import Path

CLOZE = re.compile(r"\{\{c(\d+)::(.+?)(?:::(.+?))?\}\}")
TEMPLATE = {
    "deck": "Topic name",
    "description": "What this deck covers and who it is for",
    "cards": [
        {"front": "One clear question?", "back": "One short answer", "tags": ["basics"], "source": "doc, section"},
        {"type": "cloze", "front": "A sentence with the {{c1::key term}} hidden.", "back": "", "tags": ["basics"]},
    ],
}


def load(path):
    p = Path(path)
    if p.suffix.lower() == ".csv":
        cards = []
        with p.open(newline="") as f:
            for row in csv.DictReader(f):
                cards.append({"front": row.get("front", ""), "back": row.get("back", ""),
                              "tags": (row.get("tags") or "").split(), "source": row.get("source", ""),
                              "type": row.get("type") or ("cloze" if CLOZE.search(row.get("front", "")) else "basic")})
        return {"deck": p.stem.replace("-", " ").title(), "cards": cards}
    spec = json.loads(p.read_text())
    for c in spec.get("cards", []):
        c.setdefault("type", "cloze" if CLOZE.search(c.get("front", "")) else "basic")
        c.setdefault("tags", [])
    return spec


def words(s):
    return len(re.sub(r"<[^>]+>", " ", s or "").split())


def norm(s):
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


def lint(spec):
    fs = []

    def add(sev, i, msg):
        fs.append({"severity": sev, "card": i, "msg": msg})
    cards = spec.get("cards") or []
    if not cards:
        add("error", 0, "no cards")
    seen = {}
    for i, c in enumerate(cards, 1):
        f, b, t = c.get("front", ""), c.get("back", ""), c.get("type", "basic")
        if not f.strip():
            add("error", i, "empty front")
            continue
        if t == "cloze":
            if not CLOZE.search(f):
                add("error", i, "cloze card has no {{c1::...}} deletion")
            elif len(set(m.group(1) for m in CLOZE.finditer(f))) > 2:
                add("warn", i, "more than 2 cloze numbers on one card; split it")
        else:
            if not b.strip():
                add("error", i, "basic card has an empty back")
            if CLOZE.search(f):
                add("warn", i, "front has cloze syntax but type is basic")
        if words(b) > 30:
            add("warn", i, f"back is {words(b)} words; aim for <=30 (one idea per card)")
        if words(f) > 40:
            add("warn", i, f"front is {words(f)} words; shorten the question")
        nb = norm(b)
        if t != "cloze" and nb and len(nb) > 3 and nb in norm(f):
            add("warn", i, "the answer appears in the question")
        if t != "cloze" and re.search(r"\b(and|also)\b.*\?.*\?", f):
            add("warn", i, "front asks two questions; split it")
        if t != "cloze" and len(re.findall(r"\?", f)) > 1:
            add("warn", i, "more than one question mark; one question per card")
        k = norm(CLOZE.sub(lambda m: m.group(2), f))
        if k in seen:
            add("warn", i, f"duplicate of card {seen[k]}")
        else:
            seen[k] = i
        if not c.get("tags"):
            add("info", i, "no tags; tags let people study one topic")
    return fs


def cloze_html(front, reveal, active=None):
    def rep(m):
        n, ans, hint = m.group(1), m.group(2), m.group(3)
        if reveal or (active and n != active):
            return f'<b class="cz">{html.escape(ans)}</b>' if reveal else html.escape(ans)
        return f'<span class="cz">[{html.escape(hint) if hint else "..."}]</span>'
    out, last = [], 0
    for m in CLOZE.finditer(front):
        out.append(html.escape(front[last:m.start()]))
        out.append(rep(m))
        last = m.end()
    out.append(html.escape(front[last:]))
    return "".join(out)


def to_anki(spec):
    rows = ["#separator:tab", "#html:true", "#notetype column:1", "#deck column:2", "#tags column:5"]
    deck = spec.get("deck", "Deck").replace("\t", " ")

    def clean(s):
        return html.escape(s or "", quote=False).replace("\t", " ").replace("\n", "<br>")
    for c in spec["cards"]:
        tags = " ".join(t.replace(" ", "_") for t in c.get("tags", []))
        src = f'<br><small>{clean(c["source"])}</small>' if c.get("source") else ""
        if c.get("type") == "cloze":
            rows.append("\t".join(["Cloze", deck, clean(c["front"]), clean(c.get("back", "")) + src, tags]))
        else:
            rows.append("\t".join(["Basic", deck, clean(c["front"]), clean(c["back"]) + src, tags]))
    return "\n".join(rows) + "\n"


def to_md(spec):
    out = [f"# {spec.get('deck', 'Deck')}", ""]
    if spec.get("description"):
        out += [spec["description"], ""]
    for i, c in enumerate(spec["cards"], 1):
        if c.get("type") == "cloze":
            q = CLOZE.sub(lambda m: "_____", c["front"])
            a = CLOZE.sub(lambda m: f"**{m.group(2)}**", c["front"])
            out.append(f"{i}. {q}")
            out.append(f"   - {a}" + (f" ({c['back']})" if c.get("back") else ""))
        else:
            out.append(f"{i}. **{c['front']}**")
            out.append(f"   - {c['back']}")
        meta = []
        if c.get("tags"):
            meta.append("tags: " + ", ".join(c["tags"]))
        if c.get("source"):
            meta.append("source: " + c["source"])
        if meta:
            out.append(f"   - _{'; '.join(meta)}_")
    return "\n".join(out) + "\n"


CSS = """
:root{--bg:#f8fafc;--card:#fff;--ink:#0f172a;--muted:#64748b;--line:#e2e8f0;--accent:#2563eb;--good:#059669;--bad:#dc2626;--cz:#fef3c7}
@media (prefers-color-scheme:dark){:root{--bg:#0b1220;--card:#111a2e;--ink:#e2e8f0;--muted:#94a3b8;--line:#22304d;--accent:#60a5fa;--good:#34d399;--bad:#f87171;--cz:#3b2f0b}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:16px/1.5 -apple-system,'Segoe UI',Roboto,Helvetica,Arial,sans-serif}
.cz{background:var(--cz);padding:0 4px;border-radius:4px}b.cz{font-weight:700}
"""


def to_print(spec):
    """Two pages per sheet of 8 cards: fronts, then backs mirrored so they line up when printed double-sided (flip on long edge)."""
    cards = spec["cards"]
    pages = []
    for s in range(0, len(cards), 8):
        chunk = cards[s:s + 8]
        fronts, backs = [], []
        for i, c in enumerate(chunk, s + 1):
            if c.get("type") == "cloze":
                fq, bq = cloze_html(c["front"], False), cloze_html(c["front"], True) + (f"<p>{html.escape(c['back'])}</p>" if c.get("back") else "")
            else:
                fq, bq = html.escape(c["front"]), html.escape(c["back"])
            tag = html.escape(", ".join(c.get("tags", [])))
            fronts.append(f'<div class="pc"><span class="n">{i}</span><div class="q">{fq}</div><span class="t">{tag}</span></div>')
            src = f'<span class="t">{html.escape(c["source"])}</span>' if c.get("source") else ""
            backs.append(f'<div class="pc back"><span class="n">{i}</span><div class="a">{bq}</div>{src}</div>')
        while len(fronts) < 8:
            fronts.append('<div class="pc empty"></div>')
            backs.append('<div class="pc empty"></div>')
        # mirror each row of 2 so card 1's back sits behind card 1
        mb = []
        for r in range(0, 8, 2):
            mb += [backs[r + 1], backs[r]]
        pages.append(f'<section class="sheet">{"".join(fronts)}</section><section class="sheet">{"".join(mb)}</section>')
    title = html.escape(spec.get("deck", "Deck"))
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} - print</title><style>{CSS}
.sheet{{display:grid;grid-template-columns:1fr 1fr;grid-auto-rows:62mm;gap:0;width:190mm;margin:10mm auto;page-break-after:always;background:#fff;color:#0f172a}}
.pc{{border:1px dashed #94a3b8;padding:7mm 8mm;position:relative;display:flex;align-items:center;justify-content:center;text-align:center}}
.pc .q{{font-size:15pt;font-weight:600}}.pc .a{{font-size:13pt}}.pc.back{{background:#f8fafc}}
.n{{position:absolute;top:3mm;left:4mm;font-size:9pt;color:#64748b}}.t{{position:absolute;bottom:3mm;right:4mm;left:4mm;font-size:8pt;color:#64748b;text-align:right}}
.hint{{max-width:190mm;margin:10mm auto 0;color:var(--muted);font-size:14px}}
@media print{{.hint{{display:none}}.sheet{{margin:0 auto}}body{{background:#fff}}}}
@media (max-width:760px){{.sheet{{width:100%;grid-auto-rows:auto}}.pc{{min-height:150px}}}}
</style></head><body><p class="hint">{title}: {len(cards)} cards. Print double-sided, flip on the long edge, then cut along the dashed lines.</p>{"".join(pages)}</body></html>
"""


def to_study(spec):
    data = []
    for i, c in enumerate(spec["cards"]):
        if c.get("type") == "cloze":
            q, a = cloze_html(c["front"], False), cloze_html(c["front"], True) + (f"<p>{html.escape(c['back'])}</p>" if c.get("back") else "")
        else:
            q, a = html.escape(c["front"]), html.escape(c["back"])
        data.append({"id": i, "q": q, "a": a, "tags": c.get("tags", []), "src": c.get("source", "")})
    title = html.escape(spec.get("deck", "Deck"))
    key = re.sub(r"[^a-z0-9]+", "-", spec.get("deck", "deck").lower())
    desc = html.escape(spec.get("description", ""))
    js_data = json.dumps(data).replace("</", "<\\/")
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title><style>{CSS}
main{{max-width:720px;margin:0 auto;padding:24px 16px 48px}}h1{{font-size:24px;margin:0 0 4px}}.sub{{color:var(--muted);margin:0 0 16px}}
.bar{{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin-bottom:16px}}select,button{{font:inherit;padding:8px 12px;border-radius:10px;border:1px solid var(--line);background:var(--card);color:var(--ink);cursor:pointer}}
.boxes{{display:flex;gap:6px;margin-left:auto;font-size:13px;color:var(--muted)}}.boxes span{{border:1px solid var(--line);border-radius:8px;padding:2px 8px}}
.card{{perspective:1200px;height:300px;cursor:pointer}}.inner{{position:relative;width:100%;height:100%;transition:transform .45s;transform-style:preserve-3d}}
.card.flip .inner{{transform:rotateY(180deg)}}.face{{position:absolute;inset:0;backface-visibility:hidden;background:var(--card);border:1px solid var(--line);border-radius:18px;
padding:28px;display:flex;flex-direction:column;justify-content:center;align-items:center;text-align:center;box-shadow:0 6px 24px rgba(0,0,0,.06)}}
.face.b{{transform:rotateY(180deg)}}.face .txt{{font-size:21px;font-weight:600}}.face.b .txt{{font-weight:500;font-size:19px}}.meta{{position:absolute;bottom:12px;left:16px;right:16px;font-size:12px;color:var(--muted)}}
.lbl{{position:absolute;top:12px;left:16px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.06em}}
.grade{{display:flex;gap:10px;justify-content:center;margin-top:16px}}.grade button{{min-width:130px}}.grade .no{{border-color:var(--bad);color:var(--bad)}}.grade .yes{{border-color:var(--good);color:var(--good)}}
.done{{text-align:center;padding:48px 0;color:var(--muted)}}kbd{{border:1px solid var(--line);border-radius:4px;padding:0 4px;font-size:12px}}
.help{{color:var(--muted);font-size:13px;text-align:center;margin-top:12px}}
@media (max-width:520px){{.card{{height:340px}}.grade button{{min-width:0;flex:1}}}}
</style></head><body><main>
<h1>{title}</h1><p class="sub">{desc}</p>
<div class="bar"><select id="tag" aria-label="Topic"><option value="">All topics</option></select><button id="shuffle">Shuffle</button><button id="reset">Reset progress</button>
<div class="boxes" id="boxes" title="Leitner boxes: a card moves up a box when you know it and back to box 1 when you don't"></div></div>
<div id="stage"></div>
<p class="help">Click the card or press <kbd>Space</kbd> to flip. <kbd>1</kbd> = again, <kbd>2</kbd> = got it.</p>
</main><script>
const CARDS={js_data};const KEY="flashcards:{key}";
let st={{}};try{{st=JSON.parse(localStorage.getItem(KEY)||"{{}}")}}catch(e){{st={{}}}}
function save(){{try{{localStorage.setItem(KEY,JSON.stringify(st))}}catch(e){{}}}}
const box=id=>(st[id]||1);let queue=[],cur=null,flipped=false;
const tags=[...new Set(CARDS.flatMap(c=>c.tags))].sort();const sel=document.getElementById("tag");
tags.forEach(t=>{{const o=document.createElement("option");o.value=t;o.textContent=t;sel.appendChild(o)}});
function build(shuffle){{const t=sel.value;let cs=CARDS.filter(c=>!t||c.tags.includes(t));
cs.sort((a,b)=>box(a.id)-box(b.id)||a.id-b.id);if(shuffle){{for(let i=cs.length-1;i>0;i--){{const j=Math.floor(Math.random()*(i+1));[cs[i],cs[j]]=[cs[j],cs[i]]}}cs.sort((a,b)=>box(a.id)-box(b.id))}}
queue=cs.filter(c=>box(c.id)<5);next()}}
function boxes(){{const n=[0,0,0,0,0];CARDS.forEach(c=>n[box(c.id)-1]++);document.getElementById("boxes").innerHTML=n.map((v,i)=>`<span>Box ${{i+1}}: ${{v}}</span>`).join("")}}
function next(){{boxes();cur=queue.shift();flipped=false;const s=document.getElementById("stage");
if(!cur){{s.innerHTML='<div class="done">Nothing left in this set. Every card is in box 5. Reset progress to go again.</div>';return}}
s.innerHTML=`<div class="card" id="card" tabindex="0" role="button" aria-label="Flashcard, press space to flip"><div class="inner">
<div class="face"><span class="lbl">Question - box ${{box(cur.id)}}</span><div class="txt">${{cur.q}}</div><div class="meta">${{cur.tags.join(" · ")}}</div></div>
<div class="face b"><span class="lbl">Answer</span><div class="txt">${{cur.a}}</div><div class="meta">${{cur.src}}</div></div></div></div>
<div class="grade"><button class="no" id="no">Again (1)</button><button class="yes" id="yes">Got it (2)</button></div>`;
document.getElementById("card").onclick=flip;document.getElementById("no").onclick=()=>grade(false);document.getElementById("yes").onclick=()=>grade(true)}}
function flip(){{flipped=!flipped;document.getElementById("card").classList.toggle("flip",flipped)}}
function grade(ok){{if(!cur)return;st[cur.id]=ok?Math.min(5,box(cur.id)+1):1;save();if(!ok)queue.splice(Math.min(3,queue.length),0,cur);next()}}
document.addEventListener("keydown",e=>{{if(e.target.tagName==="SELECT")return;if(e.code==="Space"){{e.preventDefault();flip()}}if(e.key==="1")grade(false);if(e.key==="2")grade(true)}});
sel.onchange=()=>build(false);document.getElementById("shuffle").onclick=()=>build(true);
document.getElementById("reset").onclick=()=>{{st={{}};save();build(false)}};build(false);
</script></body></html>
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("spec")
    r.add_argument("-o", "--outdir", default=".")
    r.add_argument("--name")
    r.add_argument("--formats", default="anki,print,study,md")
    li = sub.add_parser("lint")
    li.add_argument("spec")
    li.add_argument("--json", action="store_true")
    sub.add_parser("template")
    a = ap.parse_args()
    if a.cmd == "template":
        print(json.dumps(TEMPLATE, indent=2))
        return 0
    try:
        spec = load(a.spec)
    except (OSError, json.JSONDecodeError, csv.Error) as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    fs = lint(spec)
    errs = [f for f in fs if f["severity"] == "error"]
    if a.cmd == "lint":
        if a.json:
            print(json.dumps({"cards": len(spec.get("cards") or []), "findings": fs}, indent=2))
        else:
            for f in fs:
                print(f"{f['severity'].upper():5} card {f['card']}: {f['msg']}")
            print(f"{len(spec.get('cards') or [])} cards, {len(errs)} errors, {sum(f['severity'] == 'warn' for f in fs)} warnings")
        return 1 if errs else 0
    if errs:
        for f in errs:
            print(f"ERROR card {f['card']}: {f['msg']}", file=sys.stderr)
        return 1
    out = Path(a.outdir)
    out.mkdir(parents=True, exist_ok=True)
    name = a.name or Path(a.spec).name.split(".")[0]
    makers = {"anki": (f"{name}.anki.txt", to_anki), "print": (f"{name}.print.html", to_print),
              "study": (f"{name}.html", to_study), "md": (f"{name}.md", to_md)}
    for fmt in [x.strip() for x in a.formats.split(",") if x.strip()]:
        if fmt not in makers:
            print(f"error: unknown format {fmt}", file=sys.stderr)
            return 2
        fn, mk = makers[fmt]
        (out / fn).write_text(mk(spec))
        print(f"wrote {out / fn}")
    for f in fs:
        if f["severity"] == "warn":
            print(f"WARN  card {f['card']}: {f['msg']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
