"""Checks the four top30-learn renderers: mindmap, sketchnotes, flashcards, educational-comics.
Lint rules, outputs, determinism, and that the merchant-services sample pack still renders clean.

python3 tests/learn_kit/test_learn_kit.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SK = ROOT / "plugins/top30-learn/skills"
MM = SK / "mindmap/scripts/mindmap.py"
SN = SK / "sketchnotes/scripts/sketchnotes.py"
FC = SK / "flashcards/scripts/flashcards.py"
EC = SK / "educational-comics/scripts/edu_comics.py"
PACK = ROOT / "examples/merchant-services-study-pack"


def run(script, *args):
    return subprocess.run([sys.executable, str(script), *map(str, args)], capture_output=True, text=True)


def findings(script, path):
    r = run(script, "lint", path, "--json")
    return r.returncode, json.loads(r.stdout)["findings"]


def xml_ok(path):
    xml.dom.minidom.parse(str(path))
    return True


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    with tempfile.TemporaryDirectory() as td:
        t = Path(td)

        # ---- mindmap
        (t / "ok.md").write_text("# Root\n\n- A\n  - a1 :: note\n  - a2\n- B\n  - b1\n- C\n")
        (t / "thin.md").write_text("# Root\n\n- Only branch\n")
        (t / "deep.md").write_text("# R\n\n- A\n  - B\n    - C\n      - D\n        - E\n- F\n")
        code, fs = findings(MM, t / "ok.md")
        check(code == 0 and not [f for f in fs if f["severity"] != "info"], f"mindmap ok.md: {fs}")
        code, fs = findings(MM, t / "thin.md")
        check(code == 1, "mindmap: one branch should be an error")
        code, fs = findings(MM, t / "deep.md")
        check(any("levels deep" in f["msg"] for f in fs), f"mindmap: depth warning missing: {fs}")
        r = run(MM, "render", t / "ok.md", "-o", t / "mm")
        check(r.returncode == 0, f"mindmap render failed: {r.stderr}")
        for ext in ("svg", "mmd", "opml", "html"):
            check((t / "mm" / f"ok.{ext}").exists(), f"mindmap: ok.{ext} missing")
        check(xml_ok(t / "mm/ok.svg") and xml_ok(t / "mm/ok.opml"), "mindmap: svg/opml not valid XML")
        check((t / "mm/ok.mmd").read_text().startswith("mindmap"), "mindmap: mermaid header")
        check("note" in (t / "mm/ok.opml").read_text(), "mindmap: note missing from OPML")
        first = (t / "mm/ok.svg").read_text()
        run(MM, "render", t / "ok.md", "-o", t / "mm")
        check(first == (t / "mm/ok.svg").read_text(), "mindmap: output not deterministic")
        check(run(MM, "render", t / "thin.md", "-o", t / "mm").returncode == 1, "mindmap: render should refuse on errors")

        # ---- sketchnotes
        good = {"title": "T", "layout": "path", "sections": [
            {"heading": "One", "icon": "card", "points": ["a", "b"]},
            {"heading": "Two", "icon": "bank", "points": ["c"]},
            {"heading": "Three", "icon": "check", "points": ["d"]},
            {"heading": "Four", "icon": "money", "points": ["e"]}], "takeaway": "x"}
        (t / "s.json").write_text(json.dumps(good))
        bad = dict(good, layout="spiral", sections=good["sections"] + [
            {"heading": "Five", "icon": "unicorn", "points": ["one two three four five six seven eight nine ten eleven"] * 5}])
        (t / "sb.json").write_text(json.dumps(bad))
        code, fs = findings(SN, t / "s.json")
        check(code == 0 and not fs, f"sketchnotes good: {fs}")
        code, fs = findings(SN, t / "sb.json")
        msgs = " ".join(f["msg"] for f in fs)
        check(code == 1, "sketchnotes: bad layout should be an error")
        for needle in ("unknown icon", "points", "words"):
            check(needle in msgs, f"sketchnotes: '{needle}' finding missing")
        r = run(SN, "render", t / "s.json", "-o", t / "s.svg")
        check(r.returncode == 0 and xml_ok(t / "s.svg"), f"sketchnotes render: {r.stderr}")
        a = (t / "s.svg").read_text()
        run(SN, "render", t / "s.json", "-o", t / "s.svg")
        check(a == (t / "s.svg").read_text(), "sketchnotes: same seed should give same SVG")
        run(SN, "render", t / "s.json", "-o", t / "s2.svg", "--seed", "99")
        check(a != (t / "s2.svg").read_text(), "sketchnotes: different seed should change the wobble")
        check(a.count('font-weight="700" fill="') >= 4 and ">1<" in a and ">4<" in a, "sketchnotes: path numbers missing")
        r = run(SN, "icons", "-o", t / "icons.svg")
        check(r.returncode == 0 and xml_ok(t / "icons.svg"), "sketchnotes: icon sheet")

        # ---- flashcards
        deck = {"deck": "D", "cards": [
            {"front": "What is X?", "back": "A thing.", "tags": ["t"]},
            {"type": "cloze", "front": "The {{c1::issuer}} approves.", "tags": ["t"]},
            {"front": "What is X?", "back": "Again.", "tags": ["t"]},
            {"front": "Who pays the issuer fee?", "back": "issuer fee", "tags": ["t"]},
            {"front": "Long?", "back": " ".join(["word"] * 35), "tags": ["t"]},
            {"type": "cloze", "front": "No deletion here", "tags": ["t"]},
            {"front": "Empty back?", "back": ""}]}
        (t / "d.json").write_text(json.dumps(deck))
        code, fs = findings(FC, t / "d.json")
        by = {}
        for f in fs:
            by.setdefault(f["card"], []).append(f["msg"])
        check(code == 1, "flashcards: errors should give exit 1")
        check(any("duplicate" in m for m in by.get(3, [])), f"flashcards: duplicate not flagged {by}")
        check(any("answer appears" in m for m in by.get(4, [])), "flashcards: leak not flagged")
        check(any("30" in m for m in by.get(5, [])), "flashcards: long back not flagged")
        check(any("cloze" in m for m in by.get(6, [])), "flashcards: bad cloze not flagged")
        check(any("empty back" in m for m in by.get(7, [])), "flashcards: empty back not flagged")
        ok = {"deck": "Test deck", "cards": deck["cards"][:2]}
        (t / "ok.json").write_text(json.dumps(ok))
        r = run(FC, "render", t / "ok.json", "-o", t / "fc")
        check(r.returncode == 0, f"flashcards render: {r.stderr}")
        anki = (t / "fc/ok.anki.txt").read_text().splitlines()
        check(anki[0] == "#separator:tab" and any(l.startswith("Cloze\t") for l in anki), "flashcards: anki file")
        check(all(len(l.split("\t")) == 5 for l in anki if not l.startswith("#")), "flashcards: anki rows need 5 columns")
        study = (t / "fc/ok.html").read_text()
        check("localStorage" in study and "try{" in study and "[...]" in study, "flashcards: study page")
        check("issuer" in (t / "fc/ok.md").read_text(), "flashcards: markdown")
        (t / "c.csv").write_text("front,back,tags,source,type\nWhat is Y?,Why.,a b,src,\n")
        r = run(FC, "render", t / "c.csv", "-o", t / "fc", "--formats", "md")
        check(r.returncode == 0 and "What is Y?" in (t / "fc/c.md").read_text(), "flashcards: CSV input")

        # ---- educational comics
        comic = json.loads(run(EC, "template").stdout)
        (t / "c.json").write_text(json.dumps(comic))
        code, fs = findings(EC, t / "c.json")
        check(code == 0, f"comics template should lint clean: {fs}")
        broken = json.loads(json.dumps(comic))
        p = broken["pages"][0]["panels"][0]
        p["bubbles"].append({"who": "ghost", "text": "boo"})
        p["bubbles"][0]["text"] = " ".join(["word"] * 30)
        del p["lesson"]
        (t / "cb.json").write_text(json.dumps(broken))
        code, fs = findings(EC, t / "cb.json")
        msgs = " ".join(f["msg"] for f in fs)
        check(code == 1 and "ghost" in msgs and "lesson" in msgs and "25" in msgs and "bubbles" in msgs,
              f"comics: lint findings missing: {msgs}")
        r = run(EC, "render", t / "c.json", "-o", t / "ec")
        check(r.returncode == 0, f"comics render: {r.stderr}")
        check(xml_ok(t / "ec/c-page1.svg"), "comics: page SVG invalid")
        pr = (t / "ec/c.prompts.md").read_text()
        check("No text or lettering" in pr and "round glasses" in pr, "comics: prompts need the character sheet")
        check("c-page1.svg" in (t / "ec/c.html").read_text(), "comics: reader links pages")

        # ---- sample pack renders clean and matches what's committed
        specs = PACK / "specs"
        check(run(MM, "lint", specs / "payment-lifecycle.mindmap.md").returncode == 0, "pack: mind map lint")
        check(run(SN, "lint", specs / "life-of-a-100-order.sketchnote.json").returncode == 0, "pack: sketchnote lint")
        code, fs = findings(FC, specs / "merchant-services.flashcards.json")
        check(code == 0 and not [f for f in fs if f["severity"] == "warn"], f"pack: flashcards lint {fs}")
        check(run(EC, "lint", specs / "disputed-order.comic.json").returncode == 0, "pack: comic lint")
        run(SN, "render", specs / "life-of-a-100-order.sketchnote.json", "-o", t / "pack.svg")
        check((t / "pack.svg").read_text() == (PACK / "sketchnote/life-of-a-100-order.svg").read_text(),
              "pack: committed sketchnote is stale; re-render it")
        run(EC, "render", specs / "disputed-order.comic.json", "-o", t / "pc")
        check((t / "pc/disputed-order-page2.svg").read_text() == (PACK / "comic/disputed-order-page2.svg").read_text(),
              "pack: committed comic is stale; re-render it")
        run(FC, "render", specs / "merchant-services.flashcards.json", "-o", t / "pf", "--formats", "anki")
        check((t / "pf/merchant-services.anki.txt").read_text() == (PACK / "flashcards/merchant-services.anki.txt").read_text(),
              "pack: committed Anki deck is stale; re-render it")

    if fails:
        print(f"FAIL ({len(fails)})")
        for f in fails:
            print(" -", f)
        return 1
    print("ok - learn kit: mindmap, sketchnotes, flashcards, educational-comics, sample pack")
    return 0


if __name__ == "__main__":
    sys.exit(main())
