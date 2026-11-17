---
name: motion-perf
description: Find and fix animation that is expensive to render - layout properties (width, height, left, margin) animated instead of transforms, transition-all, scroll handlers that drive styles, requestAnimationFrame loops that never stop, layout reads mixed with style writes, large animated blurs, permanent will-change. Use when an animation stutters or drops frames, when a page gets hot or janky on scroll, when reviewing animated React/Tailwind/CSS components, or before publishing a component library.
---

# Motion performance

Smooth motion is mostly about which work the browser has to redo each frame. Changing
`transform` or `opacity` is composited: the GPU moves a layer it already has. Changing
`filter` or a color repaints the element. Changing `width`, `height`, `top`, `left`, `margin`
or `padding` re-runs layout for the element and often its neighbours, then paints. At 60
frames a second that difference is the stutter. `scripts/motion_perf.py` finds the patterns
that cause it.

The rules below follow the categories in cult-ui's `fixing-motion-performance` skill (MIT,
github.com/nolly-studio/cult-ui). The checker is an independent implementation.

## Run the checker

```bash
P="python3 ${CLAUDE_PLUGIN_ROOT}/skills/motion-perf/scripts/motion_perf.py"   # or this folder's scripts/
$P lint src/components            # .tsx/.jsx/.ts/.js/.css; skips node_modules, dist, build
$P lint src --fail-on warn        # for CI
$P lint src --json perf.json      # every finding, for a review
```

| Rule | What it means | Fix |
|---|---|---|
| `layout-animation` | `width`, `height`, `left`, `top`, `margin`, `padding` animated: in Motion targets or variants, a motion value in `style`, CSS keyframes or transitions, Tailwind `transition-[width]`. Flagged louder when it loops. | `x`/`y`/`scale` instead; `scaleX` for progress bars and tab indicators; Motion's `layout` or `layoutId` for size and position changes (it animates with transforms). `height: "auto"` for open and close is allowed. |
| `transition-all` | Every property that changes animates, layout ones included. | Name them: `transition-colors`, `transition-opacity`, `transition-transform`, `transition-[transform,opacity]`. |
| `scroll-handler` | A scroll listener in a file that writes styles or state: main-thread work on every scroll event. | Motion's `useScroll` with `useTransform` into `y`/`opacity`; CSS `animation-timeline: scroll()` or `view()`; `IntersectionObserver` for enter and leave. If a listener is needed: `{ passive: true }`, one `requestAnimationFrame` per frame (that form isn't flagged). |
| `raf-loop` | A `requestAnimationFrame` loop with no `cancelAnimationFrame` and no condition: it runs forever, off screen too. | Keep the id and cancel it on unmount; stop when the value settles; pause when the element leaves the viewport. |
| `layout-thrash` | A loop or frame callback reads layout (`getBoundingClientRect`, `offsetHeight`) and writes `.style`: each read after a write forces a new layout. | Read everything first, then write. For measured motion use FLIP: measure once, animate a transform. |
| `blur-large` | A blur over 8px that animates (Motion target, keyframes, `:hover`, `hover:blur-xl`). | Animate 8px or less on small elements, or cross-fade an already-blurred copy with `opacity`. |
| `will-change` (note) | Set permanently, it keeps a GPU layer alive. | Add it on the state that animates, or from script just before; fine on something that moves all the time. |
| `mixed-systems` (note) | Motion plus GSAP, react-spring or anime.js in one file. | One system per element; don't migrate libraries just for this. |

## Fixing what it finds

1. Open each finding first. It is a pattern match, so confirm the value really animates. A
   width set once, or a dock that deliberately grows icons, may be a fair trade.
2. Fix loops first: a layout property animated on `repeat: Infinity` costs every frame, for
   ever. Then interaction motion (hover, press, tabs), then one-shot entrances.
3. Swap mechanism, not timing. A glow moved with `left: ["-5%", "75%"]` goes inside a
   wrapper as wide as the track, and the wrapper moves with `x: ["-5%", "75%"]` (a percentage
   in `x` is a share of the element's own width, so it has to be the wrapper that moves). A tab
   indicator animating `left` and `width` becomes `layoutId`, or `x` plus `scaleX` with
   `transform-origin: left`.
4. Keep the look: compare before and after side by side, then re-run until clean.
5. If something still stutters, record it in the browser's Performance panel: long purple
   (layout) or green (paint) bars on each frame point at what is left.

Not checked by the script, check by eye: animating CSS custom properties that feed
`transform` (each change restyles), view transitions used for in-page motion instead of
navigation, and anything huge being repainted (full-screen gradients, big shadows).

Pair it with `motion-budget`: that one checks motion is fast enough, this one that it is cheap
enough to stay smooth.
