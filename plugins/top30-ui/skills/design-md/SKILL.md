---
name: design-md
description: Write, update and enforce a DESIGN.md - the repo file that tells agents and people how the interface should look (Google's format - color, type, radius and spacing tokens in YAML front matter, then prose sections). Drafts one from existing code, checks references, section order and contrast, and finds code that drifts from it (stray hex colors, undeclared fonts, off-scale radii, one-off shadows). Use when a project has or needs a DESIGN.md, when UI keeps coming out inconsistent, or before handing UI work to an agent.
---

# DESIGN.md

A DESIGN.md sits at the repo root and settles visual choices once, so every agent and person
building UI makes the same ones. The rule that makes it work, as cult-ui's frontend-design skill
puts it: **DESIGN.md wins.** When it covers a choice, follow it; when it doesn't, make the call
and add the answer to the file.

## The format

Google's design.md (Apache-2.0, github.com/google-labs-code/design.md; the format is marked
alpha). Tokens go in YAML front matter; prose explains how to use them.

```markdown
---
version: alpha
name: Quiet Ledger
description: Calm, ink on paper.
colors:
  primary: "#1a1c1c"          # hex is the safest; rgb(), hsl(), oklch() also allowed
  on-primary: "#ffffff"
typography:
  body-md: { fontFamily: Geist Sans, fontSize: 16px, fontWeight: 400, lineHeight: 1.5 }
rounded:  { sm: 0.5rem, lg: 24px, full: 9999px }
spacing:  { unit: 8px }
components:
  button-primary:
    backgroundColor: "{colors.primary}"   # references use {group.token}
    textColor: "{colors.on-primary}"
    rounded: "{rounded.full}"
---

## Overview            (or "Brand & Style": personality, audience, density)
## Colors              ## Typography     ## Layout        ## Elevation & Depth
## Shapes              ## Components     ## Do's and Don'ts
```

Sections are optional but go in that order, as `##` headings. `omitted:` lists groups left
out on purpose. Shadows have no token group: describe the levels in Elevation & Depth.

## The script

```bash
D="python3 ${CLAUDE_PLUGIN_ROOT}/skills/design-md/scripts/design_drift.py"   # or this folder's scripts/
$D draft src app/globals.css > /tmp/design-draft.md   # starting tokens read from the code; writes nothing
$D check DESIGN.md                    # front matter, name, unknown keys, broken refs, primary, order, contrast
$D drift DESIGN.md src                # code that strays from the tokens
$D drift DESIGN.md src --fail-on warn # for CI
```

`drift` reports `hex-color` (with the nearest token), `undeclared-font`, `radius-off-scale` and
`arbitrary-shadow`. With no colors in the DESIGN.md it uses the CSS custom properties it finds
as the palette. It compares hex colors only: oklch or rgb tokens are read but not matched.

`check` is an offline subset of the official linter. The reference is
`npx @google/design.md lint DESIGN.md` (it also checks orphaned tokens and more contrast
pairs, and `export` turns the tokens into Tailwind or DTCG). It downloads a package from npm, so
ask the user before running it.

## Writing one from code

1. `draft` the tokens. Name each color by its job (`canvas`, `ink`, `accent`, `on-accent`), not
   its hue; merge near-duplicates; mark the brand color `primary`.
2. Fill the prose from what the code already does: the canonical screen (link it), type voices
   and where each is allowed, surfaces and rounding, motion rules (durations, what never
   animates), and a short checklist. Write rules as "always" and "never".
3. `check` until clean, then `drift` and decide for each finding: fix the code, or add a token
   if the value is intended.
4. Say what it governs. cult-ui's DESIGN.md covers its marketing site and docs and says registry
   components keep their own styling; state the scope the same way.

A prose-only DESIGN.md (cult-ui's is one) is still useful to people, but tools can't check it.
Add a token block above the prose without rewriting the prose; `check` reports
`no-front-matter` until you do.

## Keeping it true

When UI work makes a new choice, add it to the file in the same change. When `drift` finds the
same off-token value in several places, the file is probably what's out of date: ask before
changing either. Run `check` and `drift` in CI next to the `motion-budget` and `motion-perf`
checkers.
