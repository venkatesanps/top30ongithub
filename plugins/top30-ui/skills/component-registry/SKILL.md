---
name: component-registry
description: Turn a folder of React components into a shadcn GitHub registry that anyone installs with `npx shadcn@latest add owner/repo/name`, the way EasyUI ships its library - scaffold components with metadata and tests, generate registry.json from imports, validate it against the code, audit accessibility and reduced motion, and publish llms.txt for AI tools. Use when the user wants a team or personal component library, to publish components, or to check a registry before release.
---

# Component registry

`scripts/registry_kit.py` (Python standard library only) reproduces EasyUI's registry pipeline
for any repo. On EasyUI itself it rebuilds the same 132 items with identical dependencies and
metadata, and it follows imports all the way down. That surfaced a real bug: EasyUI's published
`command-menu` and `spotlight-search` import the site's own catalog file, which the registry
doesn't ship, so they don't compile after install. When the scan lists a file like that, the fix
is in the component (take the data as a prop), not in shipping site code.

```bash
K="python3 ${CLAUDE_PLUGIN_ROOT}/skills/component-registry/scripts/registry_kit.py"   # or this folder's scripts/
```

## Layout it expects

```
package.json                       declares every npm package components import
src/components/ui/Name.tsx         one component per file (or a folder: dot-field/DotField.tsx + meta.json)
src/components/ui/Name.meta.json   {"title", "description", "category"?, "props"?}  (.meta.ts also read)
src/components/ui/Name.test.tsx
src/lib/...                        shared code; shipped automatically when a component imports it
```

Different folders: `--ui-dir`; `@/` pointing somewhere other than `src`: `--src-alias`.

## Workflow

1. **New component:** `$K new MagneticCard` creates the component (reduced-motion aware, client
   component, accessible name), its meta and a test, plus `src/lib/motion-tokens.ts` if missing.
   Build it with the `motion-component-builder` skill.
2. **Build the registry:** `$K scan --name acme-ui --repo owner/repo --homepage https://...`
   writes `registry.json`: kebab-case names, npm dependencies from imports (react, clsx and
   tailwind-merge are left to the host project), and every local file the component needs,
   followed transitively (`src/lib` → `lib/`, `src/hooks` → `hooks/`, icons and companion CSS).
   Read its notes: undeclared packages and imports of files that don't exist.
3. **Validate:** `$K validate` fails on a wrong schema URL, duplicate or non-kebab names,
   missing title or description, missing files, undeclared dependencies, components missing from
   the registry or registry items with no component. Run it in CI.
4. **Audit:** `$K audit [--fail-on error]` flags `<img>` without alt (error); Motion without
   reduced-motion handling, clicks on non-interactive elements, focus outlines removed with no
   ring, icon-only buttons without labels (warnings); hard-coded hex colors, `as any`, missing
   `'use client'`, no test (notes). Heuristics: confirm each warning in the code before fixing.
5. **Publish for AI tools:** `$K llms --name acme-ui --repo owner/repo --homepage https://...`
   writes `public/llms.txt` with the install command and one line per component.
6. **Release:** push to GitHub. Test one install in a scratch project:
   `npx shadcn@latest view owner/repo/<name>`, then `npx shadcn@latest add owner/repo/<name>`.

For a team: keep the registry repo internal, add `validate` and `audit --fail-on error` to CI,
and review new components like code.
