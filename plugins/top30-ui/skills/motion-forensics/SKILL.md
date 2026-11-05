---
name: motion-forensics
description: Find out how a website's motion is actually built before trying to reproduce it - procedural canvas, WebGL shaders, GSAP/Framer/Webflow timelines, smooth-scroll layers, CSS keyframes or scroll-driven CSS, Lottie, video - then rebuild it with the matching technique, including a scroll-driven canvas engine for the cases component copiers can't see. Use when the user can't reproduce a site's animation or transitions, asks "how was this built", or wants a scroll story or canvas effect like a site they admire.
---

# Motion forensics

Most "reverse engineer this site" attempts fail for one reason: they read the DOM and CSS,
and the motion isn't there. ZeroMark (zeromark.io) is the case this skill was built from. Its
motion is about 2,150 lines of hand-written Canvas 2D in one script: 1,600 shapes drawn every
frame by a function of scroll position, seeded random layouts, phase boundaries measured from
where the copy sits, and frame loops that only run while a scene is on screen. There's no
library, so there's nothing to inspect, recordings measure scroll speed rather than timing,
and crawlers see blank canvases.

So: **diagnose first, then pick the technique.**

## 1. Probe the page

Open the page in a real, visible browser tab, at desktop size, reduced motion off. Run
`scripts/motion_probe.js` in the page, through a browser tool's "run JavaScript" or by pasting
it into the DevTools console. It returns (and logs) a JSON object; save it as `probe.json`.

No browser tool? `scripts/probe_page.py <url> --out ./motion` does the same in headless
Chromium (Playwright) and also saves screenshots at evenly spaced scroll positions plus a
`strip.png` contact sheet. Static fetches (WebFetch, curl) can't diagnose motion: they never run
the scripts.

The probe lists libraries, running animations, stylesheet features, canvases, video, and what
the page's own scripts do. It also scrolls a little and waits a second to see what moves on
its own and what moves with scroll. It never calls `getContext()`: on a canvas the page hasn't
set up yet, that would claim the canvas and break the page's drawing. Don't do it by hand
either.

## 2. Read the report

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/motion-forensics/scripts/motion_report.py" probe.json --out motion-report.md
```

(Use the path inside this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set.) It classifies the
architecture (procedural canvas, WebGL, timeline library, smooth scroll, CSS keyframes,
scroll-driven CSS, Lottie/Rive, video, Web Animations API), says why copying fails for each,
lists the traits that make it hard (scroll-driven, ambient loop, layout-anchored phases, seeded
layout, lazy start, class-gated, reduced-motion aware, HiDPI, minified), and pulls out reusable
numbers: easing curves, durations, stagger beat.

## 3. Rebuild with the matching technique

| Architecture | Rebuild with |
|---|---|
| Procedural canvas, scroll-driven | `templates/scroll-scene.js` (below) |
| WebGL / shaders | your own small shader or Three.js scene for the same effect family, plus a 2D fallback |
| Timeline library | the same library, or CSS + `Element.animate`, from an extracted timeline spec |
| Smooth scroll | keep native scroll; optionally damp the progress value (`smoothing` option) |
| CSS keyframes | the same pattern with your values, gated by a `<head>` class, reduced-motion off-switch |
| Scroll-driven CSS | the CSS under `@supports (animation-timeline: view())` with a static fallback |
| Lottie / Rive / video | your own asset: these files are someone's artwork |

### The scroll-scene engine

`templates/scroll-scene.js` (no dependencies; `templates/scroll-scene-demo.html` is a working
example) gives you the structure the probe uncovers in sites like ZeroMark:

- `render(ctx, s)` draws everything from `s.p` (scroll progress 0..1) and `s.t` (time), so
  scrolling back rewinds exactly.
- `rng(seed)` makes the "random" layout identical on every visit and in every test screenshot.
- `phase(p, start, end, lag, spread, easing)` moves a crowd as a wave: each item's own lag,
  stagger kept inside the phase so the last item still finishes on time.
- `data-phase="name"` on your copy blocks becomes `s.a.name`: the progress at which that block
  is centred. Phases stay glued to the text at any screen size.
- `live(p)` says when time matters (an idle drift, a stream); otherwise no frames run.
- DPR capped at 2 with the backing store sized before the transform, ResizeObserver plus
  `pageshow` to re-fit, IntersectionObserver to pause off screen, one still frame under
  reduced motion, and `data-progress` on the canvas for tests.

## 4. Prove the match

1. Strip test: run `probe_page.py` on the original and on the rebuild with the same
   `--points` and viewport, and compare the two `strip.png` sheets side by side. Adjust easing, stagger
   and phase anchors until the strips line up.
2. Run the probe on the rebuild: its architecture and traits should match the original's.
3. Check both themes, a phone width, reduced motion, and a hidden tab.

## Rules

Learn the technique, timing and structure; write your own code, visuals, copy and brand.
Reading a site's public script to understand it is fine. Pasting it into a project is not,
unless its license allows that and you keep the notice.
