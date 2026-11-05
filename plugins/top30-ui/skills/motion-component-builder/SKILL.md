---
name: motion-component-builder
description: Build animated React components the way polished registries like EasyUI do - Tailwind plus Framer Motion with shared spring tokens, every state designed (hover, press, focus-visible, disabled, loading), reduced-motion support, keyboard and screen-reader access, a test and metadata, ready for a shadcn registry. Use when the user asks for an animated or "micro-interaction" component, a button, card, menu, toggle, dock, toast or loader with motion, or wants a component to feel like EasyUI, Aceternity or Magic UI.
---

# Motion component builder

The recipe EasyUI's 132 components follow, written down so any component can be built to the
same standard, plus the gaps an audit of that library found (most skip reduced motion; some
clickable elements aren't reachable by keyboard).

## 1. Tokens before components

Use one motion-tokens file for every spring and curve. If the project has none, copy
`templates/motion-tokens.ts` to `src/lib/motion-tokens.ts` (keep `THIRD_PARTY_NOTICE.md` with
it: the values are adapted from EasyUI under MIT). Pick by job:

| Token | For |
|---|---|
| `springSnappy` | press and hover feedback, dock icons (~200 ms) |
| `springGentle` | tabs, accordions, dialog content (~400 ms, no overshoot) |
| `springMorph` | shared-layout morphs with `layoutId` |
| `springResponsive` | magnetic return, toast stacks (small overshoot) |
| `easeSoft` / `easeFast` | color and opacity |

Colors, radii and shadows come from CSS variables (`bg-card`, `border-border`, the project's
theme), never hard-coded hex, so themes and brands can change them.

## 2. Design every state

Before writing JSX, list: idle, hover, press (`whileTap={{ scale: 0.96 }}`-scale feedback),
focus-visible (2 px ring with 2 px offset on `:focus-visible` only), disabled, loading, error,
empty, and what happens on touch (no hover) and on small screens.

## 3. Accessible by construction

- Use the real element: `<button>`, `<a>`, `<input>`. A styled `<div>` with `onClick` needs a
  role, `tabIndex` and key handling; usually it should just be a button.
- Icon-only controls get `aria-label`; decorative motion layers get `aria-hidden`.
- Respect `prefers-reduced-motion`: `const reduce = useReducedMotion()` and swap movement for a
  short fade (`pick(reduce, motionTransitions.springGentle)`). Never loop motion forever without a
  way to stop it.
- Keyboard: Tab reaches it, Enter/Space activates it, Escape closes anything that opened.
- `'use client'` at the top when it uses state, effects, refs or Motion (Next.js).

## 4. Performance

Animate `transform` and `opacity`, not layout properties. Cursor-follow effects use
`useSpring`/`useMotionValue` (no React state per mouse move). Canvas or particle effects pause
when off screen and stop under reduced motion.

## 5. Ship it as a registry item

Each component is `src/components/ui/Name.tsx` + `Name.meta.json` (`title`, `description`,
optional `category`, `props`) + `Name.test.tsx` that renders it and finds it by role and name.
Then use the `component-registry` skill: `registry_kit.py new Name` scaffolds all three, and
`scan`, `validate` and `audit` make it installable with `npx shadcn@latest add <owner>/<repo>/<name>`.

## 6. Show it

Give the user the component, a usage snippet, the props table, and what you did for reduced
motion and keyboard users. If they want to see it, render a live demo (an inline HTML/React
preview or a Design artifact) rather than describing it.

When the motion you're matching isn't in the DOM at all (a canvas scene, a shader, a scroll
story), use the `motion-forensics` skill instead: it diagnoses the technique and has a
scroll-driven canvas engine.

When recreating something seen elsewhere, follow the `ui-reverse-engineer` agent's rules: copy
behavior, not code, branding or assets, unless the source's license allows it and you keep its
notice.
