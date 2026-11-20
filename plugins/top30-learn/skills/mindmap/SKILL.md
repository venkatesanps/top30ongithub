---
name: mindmap
description: Turn a topic, document, notes or a conversation into a mind map - a central idea with 4-8 branches - rendered as SVG, a collapsible HTML page, Mermaid and OPML (opens in XMind, MindNode, iThoughts). Claude's version of ChatGPT's /mindmap. Use when the user says "/mindmap", "mind map this", "map out", "visual outline", "brainstorm map", or wants to see how the parts of a subject connect.
---

# Mind map

You write a Markdown outline; `scripts/mindmap.py` lints it and draws it. Same outline, same
picture, every time. Standard library only.

## 1. Draft the outline

Start from what the user gave you (a file, a URL they pasted, notes, the conversation). If it's
just a topic, ask nothing - use what you know, and say at the end what you'd check.

```markdown
# Central idea in 2-5 words

- Branch one
  - Child :: optional note, shown on hover
  - Child
- Branch two
  - Child
    - Grandchild (use sparingly)
```

Rules that make a map readable (the linter checks them):

- **4-8 branches.** Fewer than 2 is an error. More than 8: group them.
- **Labels are keywords, not sentences** - 1-4 words, 7 at most. Put the explanation in the
  ` :: note`.
- **Depth 3 is plenty.** At depth 4 make a second map for that branch.
- **3-7 children per node.** Siblings should be the same kind of thing (all steps, all parties,
  all risks).
- **Every fact traceable.** When you build from a document, the notes paraphrase it; don't add
  numbers that aren't in the source.

Run `python3 "${CLAUDE_PLUGIN_ROOT}/skills/mindmap/scripts/mindmap.py" template` for a starter.

## 2. Lint and render

```bash
M="${CLAUDE_PLUGIN_ROOT}/skills/mindmap/scripts/mindmap.py"
python3 "$M" lint outline.md
python3 "$M" render outline.md -o mindmap/ --formats svg,html,mmd,opml
```

Fix every warning you can; render refuses on errors.

| File | Use |
|---|---|
| `.svg` | Two-sided map, branches balanced left and right. Drop into slides or docs. |
| `.html` | The SVG plus a collapsible outline; light and dark mode. Share this one. |
| `.mmd` | Mermaid `mindmap` for GitHub, Notion or Obsidian. Notes are dropped. |
| `.opml` | Import into XMind, MindNode, iThoughts, Logseq. |

## 3. Hand it over

Show the SVG or HTML, then in 2-3 lines: how many branches and nodes, which branch is thickest
(often the one worth its own map), and any fact you'd verify. Offer a flashcard deck or a
sketchnote from the same outline (`/flashcards`, `/sketchnotes`).
