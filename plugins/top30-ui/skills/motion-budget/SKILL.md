---
name: motion-budget
description: Check that interface motion is fast - every one-shot animation inside a time budget (300 ms by default), springs that settle in time, exits shorter than entrances, capped stagger, no ease-in, no slow chart defaults. Use when reviewing or writing animated React/Tailwind/CSS components, when an interface feels sluggish or "floaty", when tuning spring stiffness and damping, or before publishing a component library.
---

# Motion budget

Motion that confirms an action has to finish before the person's next thought. The rule, from
Amicro's design system: **every one-shot animation finishes in under 300 ms.** Loops (spinners,
loaders, ambient motion) are exempt, because their time is a period, not a wait.
`scripts/motion_budget.py` enforces it.

## The numbers

| Motion | Target |
|---|---|
| Hover, press | 150-200 ms |
| Enter | about 250 ms |
| Exit | about 140 ms: shorter than the entrance, since the person has already moved on |
| Hard ceiling | 280-300 ms |
| Tailwind | `duration-150`, `duration-200`, `duration-250`; never `duration-300` or more |
| Stagger | `delay: Math.min(index * 0.015, 0.05)`, so a whole grid lands inside the budget |
| Easing | ease-out, e.g. `[0.16, 1, 0.3, 1]`; never ease-in on interface motion |
| Recharts | `animationDuration={280}`; its default is 1500 ms |

**Springs.** A spring has no duration, so compute its settle time. Underdamped (it overshoots):
about `8 x mass / damping` seconds. With mass 1 that means damping 27 or more for 300 ms;
`{ type: 'spring', stiffness: 400, damping: 28 }` is a good hover default. Overdamped springs are
slower than that formula says, and adding damping makes them slower still: raise stiffness
instead. A bare `type: 'spring'` uses Motion's default (stiffness 100, damping 10), about 800 ms.

**Layout is the exception.** Shared-layout morphs, accordions and dialogs moving real distance can
take up to about 400 ms. Check those files with `--budget-ms 400` rather than loosening everything.

## Run the checker

```bash
B="python3 ${CLAUDE_PLUGIN_ROOT}/skills/motion-budget/scripts/motion_budget.py"   # or this folder's scripts/
$B lint src/components                 # .tsx/.jsx/.ts/.js/.css; skips node_modules, dist, build
$B lint src --fail-on warn             # for CI
$B lint src/components/layout --budget-ms 400
$B spring --stiffness 170 --damping 26 --mass 0.9   # settle time, damping ratio, and the fix
```

It reports by rule, worst first: `duration-over`, `tailwind-duration`, `css-duration`,
`spring-settle`, `spring-default`, `ease-in`, `stagger-uncapped`, `stagger-slow`,
`recharts-default`, and `no-reduced-motion` (a note, dropped when the scanned files contain an
app-wide `<MotionConfig reducedMotion="user">` or a CSS `prefers-reduced-motion` block).

## Fixing what it finds

1. Open each finding before changing it: the checker matches patterns, so confirm the animation
   is a one-shot and not a deliberate long reveal (a hero entrance, a scroll story).
2. Shorten in this order: exits first, then hover and press, then entrances.
3. For springs, run `spring` with the current values and apply its suggestion; check the feel.
4. Re-run until clean, then add `--fail-on warn` to CI so it stays that way.

Not checked by the script, check by eye: that each exit is shorter than its entrance, and that
nothing animates layout properties (`width`, `top`) where `transform` would do.

Reference results (2026-11-15, default budget): Amicro's own 157 registry components produce 9
warnings; EasyUI's 278 component files produce 6 errors and 97 warnings. Both leave reduced motion
to the app, so add the `MotionConfig` wrapper when you copy components from either.
