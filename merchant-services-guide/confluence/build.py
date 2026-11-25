#!/usr/bin/env python3
"""Rebuild the Confluence versions of the guide from ../README.md.

Needs pandoc and the Mermaid CLI (mmdc) on PATH. Run from anywhere:
    python3 merchant-services-guide/confluence/build.py

It renders every Mermaid block in the README to diagrams/<name>.png (and keeps
the .mmd source), then writes:
    merchant-services-confluence.html      self-contained page to copy and paste
    merchant-services-confluence.wiki.txt  Confluence wiki markup; upload the PNGs first
"""
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
GUIDE = HERE.parent
README = GUIDE / "README.md"
DIAGRAMS = GUIDE / "diagrams"

# One name per Mermaid block, in the order they appear in README.md.
NAMES = [
    ("01-money-flow", "Money flow"),
    ("02-big-picture", "Big picture"),
    ("16-end-to-end-sequence", "End to end in one diagram"),
    ("03-merchant-hierarchy", "Merchant hierarchy"),
    ("04-authorization-sequence", "Authorization sequence"),
    ("05-chargeback-lifecycle", "Chargeback lifecycle"),
    ("06-order-timeline", "Order timeline"),
    ("07-channel-scenarios", "Channel scenarios"),
    ("08-fee-breakdown", "Fee breakdown"),
    ("09-hierarchy-tree", "Hierarchy tree"),
    ("10-hierarchy-funding", "Funding by FTI"),
    ("11-reporting-group", "Reporting group"),
    ("12-sale-rollup", "One sale rolling up"),
    ("14-payments-ecosystem", "Payments ecosystem above the merchant"),
    ("15-business-models", "Hierarchy under three business models"),
    ("13-older-hierarchies", "Older hierarchies"),
]

CSS = """
body{font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;max-width:1000px;margin:0 auto;padding:24px 16px;line-height:1.55;color:#172b4d;background:#fff}
h1{border-bottom:2px solid #dfe1e6;padding-bottom:6px;margin-top:48px}h2{margin-top:36px}
table{border-collapse:collapse;width:100%;margin:12px 0;font-size:14px}th,td{border:1px solid #c1c7d0;padding:6px 8px;vertical-align:top;text-align:left}th{background:#f4f5f7}
img{max-width:100%;height:auto;display:block;margin:12px auto}code{background:#f4f5f7;padding:1px 4px;border-radius:3px}
pre{background:#f4f5f7;padding:12px;overflow-x:auto}nav#TOC{background:#f4f5f7;padding:8px 20px;border-radius:6px}
"""


def run(cmd):
    subprocess.run(cmd, check=True)


def math_to_text(m):
    s = m.group(1).strip()
    s = re.sub(r"\\text\{([^}]*)\}", r"\1", s)
    for a, b in ((r"\times", "×"), (r"\pm", "±"), (r"\qquad", "  ·  "), (" - ", " − ")):
        s = s.replace(a, b)
    return f"**{' '.join(s.split())}**\n"


def main():
    md = README.read_text()
    blocks = re.findall(r"```mermaid\n(.*?)```", md, re.S)
    if len(blocks) != len(NAMES):
        sys.exit(f"README has {len(blocks)} Mermaid blocks but NAMES lists {len(NAMES)}; update NAMES.")

    DIAGRAMS.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        cfg = Path(tmp) / "mmd.json"
        cfg.write_text('{"theme":"default","flowchart":{"htmlLabels":true,"useMaxWidth":false}}')
        for (name, _), src in zip(NAMES, blocks):
            mmd = DIAGRAMS / f"{name}.mmd"
            mmd.write_text(src)
            run(["mmdc", "-q", "-i", str(mmd), "-o", str(DIAGRAMS / f"{name}.png"), "-s", "2", "-b", "white", "-c", str(cfg)])

        names = iter(NAMES)
        src = re.sub(r"```mermaid\n.*?```\n", lambda m: "![{1}](diagrams/{0}.png)\n".format(*next(names)), md, flags=re.S)
        src = re.sub(r"```math\n(.*?)```\n", math_to_text, src, flags=re.S)
        src = src.replace("- [ ] ", "- ☐ ")
        src = src.replace("Diagrams are written in Mermaid and render on GitHub.", "Diagrams are attached to this page as images.")
        src = re.sub(r"## Contents\n.*?\n---\n", "TOCPLACEHOLDER\n\n---\n", src, count=1, flags=re.S)
        src = re.sub(r"\[([^\]]+)\]\(#[^)]+\)", r"\1", src)  # in-page links don't survive the move
        src = re.sub(r"(?<!!)\[`?([^\]`]+)`?\]\((?!https?:)[^)]+\)", r"\1", src)  # nor do links to repo files

        # Confluence wiki markup
        wsrc = Path(tmp) / "wiki.md"
        wsrc.write_text(src)
        wout = Path(tmp) / "out.wiki"
        run(["pandoc", "-f", "gfm", "-t", "jira", str(wsrc), "-o", str(wout)])
        w = wout.read_text()
        w = w.replace("TOCPLACEHOLDER", "{toc:maxLevel=2|minLevel=1}").replace("!diagrams/", "!")
        w = re.sub(r"\{anchor:[^}]*\}", "", w)
        w = re.sub(r"\n(h[1-4]\. )", r"\n\n\1", w)
        w = re.sub(r"\n{3,}", "\n\n", w)
        w = w.split("\n", 1)[1].lstrip("\n")  # page title is the first h1; Confluence holds it
        (HERE / "merchant-services-confluence.wiki.txt").write_text(w)

        # Self-contained HTML
        hsrc = Path(tmp) / "html.md"
        hsrc.write_text(src.replace("TOCPLACEHOLDER\n\n", ""))
        css = Path(tmp) / "style.css"
        css.write_text(CSS)
        hout = HERE / "merchant-services-confluence.html"
        title = md.splitlines()[0].lstrip("# ").strip()
        run(["pandoc", "-f", "gfm", "-t", "html5", str(hsrc), "-s", "--toc", "--toc-depth=2", "--embed-resources",
             "--resource-path", str(GUIDE), "--css", str(css), "--metadata", f"title={title}", "-o", str(hout)])
        h = hout.read_text()
        h = re.sub(r"<h1 id=\"[^\"]*\">" + re.escape(title.replace("&", "&amp;")) + r"</h1>\n", "", h, count=1)
        hout.write_text(h)
    print(f"Rendered {len(NAMES)} diagrams and rebuilt the Confluence files.")


if __name__ == "__main__":
    main()
