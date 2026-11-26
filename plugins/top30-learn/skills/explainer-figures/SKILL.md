---
name: explainer-figures
description: Make one-idea explainer figures for a lesson, guide, README or design doc as clean SVG - a flow, a loop, a comparison table, bars, a hub, stat cards - with every number traced to code output or a named source. You write a short Python figure script with figkit; it lays out the header and footer, lints fit, overlaps and font sizes, and writes deterministic SVG (and PNG with rsvg-convert). Use for "/explainer", "make a figure/diagram/infographic for this lesson", "explain this visually", or to rebuild a figure you like in your own style.
---

# Explainer figures

One figure, one idea, every number sourced. In the lesson figures this skill was modelled on
(Agentic AI from Scratch, MIT), the numbers in each figure match what the lesson's own code
prints. That, more than the styling, is what makes them good.

`K` below is `python3 "${CLAUDE_PLUGIN_ROOT}/skills/explainer-figures/scripts/figkit.py"` (or the
path inside this skill folder). Python standard library only; PNG output needs `rsvg-convert`.

## Steps

1. **Pick the one idea.** Read the source (lesson doc, code, guide section) and write one
   sentence: "this figure shows that ___". That sentence becomes the subtitle. If you need two
   sentences, make two figures. Find the section that carries the idea with
   `grep -n "^#" <lesson>/docs/en.md`. Check: someone who only reads the title and subtitle
   learns the point.
2. **Get the real numbers.** Run the code the source already has, and copy numbers from its
   output, never from memory:
   ```bash
   cd <lesson>/code && python3 main.py | tee /tmp/fig-numbers.txt
   ```
   Confirm each number you plan to draw appears in `/tmp/fig-numbers.txt` or in the doc you
   cite. Only run code the user pointed you at in their own repo.
3. **Choose the shape** from what the idea is:

   | The idea is | Shape | Primitives |
   |---|---|---|
   | a process with failure points | flow left to right | `box`, `connect`, `decision` |
   | a cycle (agent loop, retry) | boxes around a loop | `box`, `connect`, `meter` |
   | many-to-many vs through a hub | two panels | `box`, `connect`, `divider`, `heading` |
   | which option wins on which test | table with tinted cells | `table`, `legend` |
   | how big each thing is | horizontal bars | `bars` |
   | a few headline results | stat cards | `cards` |

4. **Write the figure script** next to the doc, e.g. `docs/assets/agent-loop.py`. Copy the
   closest file in `examples/` (`snowflake-caches.py` is a table, `copy-load-metadata.py` a flow
   with a decision) and edit it. `fig = Figure(title, subtitle, kicker=, source=)` must be at
   module level; `source` says where every number came from. Check the API with:
   ```bash
   $K demo -o /tmp/figkit-demo.svg && grep -n "def " "$(dirname $K)/figkit.py"
   ```
5. **Build and lint.** Errors block the write:
   ```bash
   $K build docs/assets/agent-loop.py --png
   ```
   Expect `0 errors` and `wrote ...svg`. Then open the PNG (Read tool) and look for what the
   linter can't see: arrows crossing boxes, labels on the wrong arrow, a crowded corner.
6. **Link it** from the doc with alt text that states the idea, not "diagram":
   `![The loop stops only when the model answers without a tool call](assets/agent-loop.svg)`.
   Verify any SVG you didn't make with figkit before linking it:
   ```bash
   $K lint docs/assets/*.svg
   ```
   It should report `0 errors` for each file.

## Style rules figkit enforces

- Text at 12px or more on a 960px-wide canvas; data text in monospace, so its width is predictable.
- A `<title>`, `role="img"` and an `aria-label` on every figure; no scripts, no external links.
- At most three accent colours; green and red only for right/wrong or pass/fail.
- Nothing off the canvas, in the header or under the footer; no overlapping boxes or text.
- Same script, same bytes: commit the `.py` next to the `.svg` so anyone can rebuild it.

On a phone a 960px figure shows at about 40%, so 12px text becomes about 5px. For phone-first
reading, use `Figure(..., width=640, height=720)` and fewer elements rather than smaller text.

## When it fails

| Failure | Fix |
|---|---|
| `text likely too wide (N > M px)` | Shorten the label, widen the box or column, or move detail into the notes |
| `boxes overlap` / `text ... crosses the edge of` | Move one of them; keep 40px or more between boxes in a row |
| `runs into the footer` | Raise `height` in `Figure(...)` by 40 and rebuild |
| `source is empty` | Say where the numbers come from: `main.py output`, a doc section, a query |
| `define fig = Figure(...) at module level` | The script must leave a `fig` variable; don't wrap it in `main()` |
| `no rsvg-convert: skipped the PNG` | Install librsvg (`brew install librsvg`, `apt install librsvg2-bin`) or open the SVG in a browser |
| The PNG looks wrong but lint passes | Lint estimates text width; fonts differ by machine, so leave 10% slack in tight cells |
