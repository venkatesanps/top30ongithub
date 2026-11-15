---
name: wensity-brand-preset
description: Give a Wensity UI project one theme and keep it consistent - pick or apply a Wensity preset (base color, theme color, chart palette, fonts, icons, radius), brand ramp, dark mode with next-themes, renaming chili-* tokens, and a read-only token check that also catches an unpinned Wensity MCP server and committed installer temp files. Use when starting a Wensity project, rebranding, adding dark mode, making several dashboards or sites look alike, or when components look off-brand.
---

# Wensity brand preset

Wensity themes with plain CSS variables in Tailwind v4's `@theme inline` block: no provider, no JS
config. Change one stylesheet and every installed component re-skins. Two layers: `@theme inline`
maps names to utilities (`bg-surface`, `text-foreground`); values live in `:root` (light) and
`.dark` (dark). Primitives also read a separate `--primitive-*` namespace (surfaces, controls,
status colors, radius, fonts, shadows); premium components don't, so editing those won't restyle
marketing components.

```bash
C="python3 ${CLAUDE_PLUGIN_ROOT}/skills/wensity-brand-preset/scripts/token_check.py"   # or this folder's scripts/
```

## One preset per project, reused across projects

1. Build the preset at ui.wensity.com/create-preset: base color, theme color, **chart palette**,
   heading and body font, icon library (Tabler or Lucide), radius. The result is a `wsty1.…` code
   and a shareable URL.
2. Apply it with the command from that page's **Get Code** panel (new project: the init command;
   existing project: the apply command, which writes `wensity.json` and the token blocks). Copy
   the command from the page, since flags may change. A `wsty1` code works with the Wensity CLI,
   not the shadcn CLI. Get Code can also export plain CSS tokens or a shadcn `globals.css`.
3. Record the code where the team will find it (README "Theme" line, or the project's CLAUDE.md),
   so every new dashboard starts from the same look. Primitives added later with `wensity add`
   pick up the same theme and icon library.

The CLI writes Base Tokens and Primitive Tokens between markers and updates them in place. Edits
outside the markers are kept, so put your overrides **after** the marked blocks.

## Brand color

- Wensity's accent ramp is `--color-chili-300/-500/-800`. Override those three in `@theme inline`
  and everything follows. For a full scale, define the whole ramp.
- To rename (e.g. `brand-*`): find-and-replace `chili-` across `src/` and the stylesheet, then
  define the new names. `$C` warns if any `chili-*` class is left.
- One accent plus neutrals. Borders at about 8–12% opacity in dark mode and 6–10% in light mode.
  Cards: flat shadow, 1px border. Change a token rather than adding `className` overrides.
- Change one component's look by overriding a variable on that element (primitives declare a
  `data-surface` role: control, field, panel, overlay, modal), not by rewriting its classes.

## Fonts and radius

`--font-display` sets type (default Cabinet Grotesk; one family for all roles). Load non-system
fonts with `@font-face` or `next/font`. `--primitive-radius` (or the preset's Radius) sets the base
radius that control, surface and item radii derive from.

## Dark mode

Class strategy: `.dark` on `<html>`. Wensity is tuned for dark mode first. With `next-themes`, use
`attribute="class"` and add `suppressHydrationWarning` to `<html>` in the root layout. Light-only
products can leave the `.dark` block alone.

## Check

`$C [project] [--fail-on warn] [--json]` (read-only). Errors: no `@theme inline`, MCP server on
`@latest` or with no version, `.wensity-tmp/` tracked by git. Warnings: dark mode used but no
`.dark` block, brand ramp missing a step, leftover `chili-*` after a rename, no chart colors,
missing `suppressHydrationWarning`, `.wensity-tmp/` not ignored. Notes: hard-coded hex colors in
your own files (Wensity's own files are skipped). Run it in CI with `--fail-on error`.
