---
name: sketchnotes
description: Make a sketchnote - a one-page, hand-drawn-looking visual summary with doodle icons, short phrases, numbered steps and arrows, and one takeaway - as an SVG. Claude's version of ChatGPT's /sketchnotes. Use when the user says "/sketchnotes", "sketchnote", "visual notes", "one-page visual summary", "doodle notes", or wants a talk, article, process or meeting summarized as a picture.
---

# Sketchnotes

You write a small JSON spec; `scripts/sketchnotes.py` draws it with wobbly marker lines, a
handwriting font stack and 25 built-in doodle icons. The wobble is seeded, so the same spec
always gives the same drawing.

## 1. Pick the shape

- **path** - a process or story: sections are numbered and joined with arrows, snaking across
  rows so arrows never cross the page.
- **grid** - a topic with parts that aren't in order (pros and cons, the five parties, tips).

## 2. Write the spec

```json
{"title": "6 words or fewer", "subtitle": "who it's for or what it answers",
 "layout": "path", "columns": 3,
 "sections": [{"heading": "1-3 words", "icon": "card", "points": ["phrase", "phrase"], "note": "small aside"}],
 "takeaway": "The one sentence people should remember.",
 "footer": "Source: ..."}
```

- **4-9 sections**, 2-3 points each, each point 10 words or fewer. A sketchnote is a picture
  with words, not a page of notes.
- **Pick an icon per section** from `sketchnotes.py icons` (card, store, bank, network, shield,
  lock, clock, money, coins, doc, check, warning, bulb, person, cart, phone, globe, scale, chart,
  gear, terminal, calendar, arrows, magnifier, flag). Unknown names draw a "?".
- **One takeaway.** If you can't write it, the summary isn't done.
- From a document: keep its order for a path, its headings for a grid, and its facts only.

`python3 "${CLAUDE_PLUGIN_ROOT}/skills/sketchnotes/scripts/sketchnotes.py" template` prints a starter.

## 3. Lint and render

```bash
S="${CLAUDE_PLUGIN_ROOT}/skills/sketchnotes/scripts/sketchnotes.py"
python3 "$S" lint notes.json
python3 "$S" render notes.json -o sketchnote.svg      # --seed N for a different wobble
python3 "$S" icons -o icons.svg                       # the icon sheet
```

Look at the result before handing it over (on macOS, `qlmanage -t -s 1400 -o . sketchnote.svg`
makes a PNG). If a box is much taller than the others, a point is too long: shorten it.

## 4. Hand it over

Show the SVG and say in one line what the reader walks away with. It prints well on A4 or
Letter landscape and drops into slides as-is.
