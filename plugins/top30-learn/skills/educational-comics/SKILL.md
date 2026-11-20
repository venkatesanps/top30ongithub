---
name: educational-comics
description: Explain a concept, process or policy as a short educational comic - a few recurring characters, 4-6 panels per page, speech bubbles, captions and one lesson per panel - rendered as SVG pages with an HTML reader, plus per-panel image-generation prompts with a consistent character sheet. Claude's version of ChatGPT's /educationalcomics. Use when the user says "/educationalcomics", "educational comic", "explain this as a comic", "comic strip", "storyboard this lesson", or wants training material people will actually read.
---

# Educational comics

A comic teaches by putting a concept inside a small story: someone has a problem, someone
explains, something happens, the reader sees why. You write the script as JSON;
`scripts/edu_comics.py` lints it and draws simple, friendly pages. It also writes image prompts
if the user wants a richer art style from an image model.

## 1. Plan the story

- **One question the comic answers** ("What happens when a customer disputes a payment?").
- **2-3 characters**: someone who has the problem, someone who knows, maybe the person on the
  other side. Fictional people; no real brands, logos or real employees.
- **A beat sheet, 4-12 panels**: setup -> each step of the concept -> twist or consequence ->
  resolution. Every panel has a `lesson`, the one thing it teaches. A panel without one is cut.
- **Dialogue does the teaching**, in plain words; 25 words per bubble at most, 1-2 bubbles per
  panel. Captions carry time and place ("Five weeks later.").
- From a document: every claim in a bubble comes from the source.

## 2. Write the script

```json
{"title": "...", "subtitle": "...", "style": "clean flat cartoon, thick outlines",
 "characters": {"sam": {"name": "Sam", "role": "...", "color": "#2563eb", "hair": "#1f2937",
                "hair_style": "short|long|bun|bald", "accessory": "glasses|tie|apron|headset|cap|none",
                "look": "description for image prompts"}},
 "pages": [{"title": "...", "panels": [{"scene": "...", "setting": "shop|office|bank|home|street|phone|plain",
   "caption": "...", "cast": ["sam"], "props": ["card"],
   "bubbles": [{"who": "sam", "text": "...", "kind": "speech|thought|shout"}],
   "lesson": "..."}]}],
 "footer": "Source: ..."}
```

Props use the sketchnotes icon names. `edu_comics.py template` prints a starter.

## 3. Lint and render

```bash
C="${CLAUDE_PLUGIN_ROOT}/skills/educational-comics/scripts/edu_comics.py"
python3 "$C" lint comic.json
python3 "$C" render comic.json -o comic/
```

Outputs: `<name>-page<N>.svg` per page, `<name>.html` (reader with a "what each panel teaches"
list), and `<name>.prompts.md` (one image prompt per panel, the character sheet repeated in each
so faces stay consistent, and the dialogue listed separately - image models garble lettering, so
add bubbles in a layout tool).

Look at each page before handing it over. If a bubble covers a face, shorten the text.

## 4. Hand it over

Show the pages, then list the lessons in order: that list is the comic's syllabus, and the user
can check it against what they wanted taught. Offer flashcards from the same lessons.
