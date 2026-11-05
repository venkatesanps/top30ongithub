/*
 * scroll-scene.js: a small engine for scroll-driven canvas scenes (no dependencies).
 *
 * The pattern that DOM-based reverse engineering can't see: one <canvas>, a scene that is a
 * pure function of scroll progress (plus time for ambient motion), a seeded layout, staggered
 * eased phases anchored to the page's own copy, and a frame loop that only runs while a live
 * part of the scene is on screen.
 *
 *   import { createScene, rng, phase, ease, mix } from './scroll-scene.js';
 *   createScene({
 *     canvas: document.querySelector('#field'),
 *     zone: document.querySelector('#story'),          // the scroll range that drives the scene
 *     seed: 7,
 *     setup: ({ random, w, h }) => ({ dots: Array.from({ length: 800 }, () => ({ x: random(), y: random(), lag: random() })) }),
 *     render: (ctx, s) => { ... draw from s.p (0..1), s.t (ms), s.a (anchors), s.w, s.h ... },
 *     live: (p) => p < 0.2,                             // ambient time loop only while this is true
 *   });
 *
 * Mark phase ends in your copy with data-phase="name": s.a.name is the progress at which that
 * element is centred on screen, so phases stay glued to the text at any viewport size.
 *
 * Part of the top30-ui plugin (github.com/venkatesanps/top30ongithub). MIT.
 */

/** Seeded PRNG (mulberry32): the same "random" layout on every visit and every screenshot. */
export function rng(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = a;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

export const clamp01 = (v) => (v < 0 ? 0 : v > 1 ? 1 : v);
export const mix = (a, b, t) => a + (b - a) * t;

export const ease = {
  linear: (t) => t,
  inCubic: (t) => t * t * t,
  outCubic: (t) => 1 - Math.pow(1 - t, 3),
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  inOutQuad: (t) => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
  /** Overshoots then settles: a spring-like pop without a physics step. */
  outBack: (t, s = 1.70158) => 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2),
};

/**
 * Progress of one item through a phase, 0..1, eased.
 * The phase runs from `start` to `end` (scene progress). Each item starts `lag * spread` of the
 * phase late, where lag is the item's own 0..1 number, so a crowd moves as a wave, not a block.
 * The stagger is a share of the phase, so the last item still finishes by `end`.
 */
export function phase(p, start, end, lag = 0, spread = 0.3, easing = ease.inOutCubic) {
  const run = end - start;
  if (run <= 0) return p >= end ? 1 : 0;
  const own = run * (1 - spread);
  return easing(clamp01((p - start - lag * spread * run) / own));
}

/** Scene progress for a scroll position: 0 when the zone's top reaches the viewport top, 1 when its bottom reaches the viewport bottom. */
export function progressFor(scrollY, zoneTop, zoneHeight, viewportH) {
  const range = Math.max(1, zoneHeight - viewportH);
  return clamp01((scrollY - zoneTop) / range);
}

/** Progress at which an element (absolute top, height) sits centred in the viewport. */
export function anchorProgress(elTop, elHeight, zoneTop, zoneHeight, viewportH) {
  return progressFor(elTop + elHeight / 2 - viewportH / 2, zoneTop, zoneHeight, viewportH);
}

/** Follows a target value with a frame-rate independent exponential ease (optional smoothing for the progress). */
export function damp(current, target, lambda, dtMs) {
  return mix(current, target, 1 - Math.exp(-lambda * (dtMs / 1000)));
}

export function createScene(opts) {
  const { canvas, zone, setup, render, live = () => false, seed = 1, smoothing = 0, maxDpr = 2 } = opts;
  const ctx = canvas.getContext('2d');
  const reduced = typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;
  let w = 0, h = 0, dpr = 1, data = null, anchorsCache = {}, zoneTop = 0, zoneH = 1;
  let p = 0, shown = 0, t = 0, last = 0, visible = true, raf = 0, queued = false, stopped = false;

  function measure() {
    const r = zone.getBoundingClientRect();
    zoneTop = r.top + scrollY;
    zoneH = r.height;
    anchorsCache = {};
    zone.querySelectorAll('[data-phase]').forEach((el) => {
      const e = el.getBoundingClientRect();
      anchorsCache[el.dataset.phase] = anchorProgress(e.top + scrollY, e.height, zoneTop, zoneH, innerHeight);
    });
  }

  function resize() {
    dpr = Math.min(maxDpr, devicePixelRatio || 1);
    w = canvas.clientWidth;
    h = canvas.clientHeight;
    // Backing store first: assigning width/height resets the context, transform included.
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    data = setup({ random: rng(seed), w, h, reduced });
    measure();
  }

  function draw() {
    ctx.clearRect(0, 0, w, h);
    render(ctx, { p: shown, t, w, h, a: anchorsCache, data, reduced });
    canvas.dataset.progress = shown.toFixed(3);
  }

  function frame(now) {
    raf = 0;
    if (stopped) return;
    const dt = last ? Math.min(now - last, 50) : 16;
    last = now;
    t += dt;
    shown = smoothing ? damp(shown, p, smoothing, dt) : p;
    draw();
    const settling = smoothing && Math.abs(shown - p) > 0.0005;
    if (visible && (live(shown) || settling)) raf = requestAnimationFrame(frame);
    else last = 0;
  }

  function kick() {
    if (!raf && !stopped) raf = requestAnimationFrame(frame);
  }

  function onScroll() {
    if (queued) return;
    queued = true;
    requestAnimationFrame(() => {
      queued = false;
      p = progressFor(scrollY, zoneTop, zoneH, innerHeight);
      kick();
    });
  }

  function refit() {
    if (canvas.clientWidth === w && canvas.clientHeight === h) { measure(); onScroll(); return; }
    resize();
    p = shown = progressFor(scrollY, zoneTop, zoneH, innerHeight);
    draw();
  }

  resize();
  p = shown = progressFor(scrollY, zoneTop, zoneH, innerHeight);
  if (reduced) {
    // A still: the scene's settled state, drawn once. No loop, no scroll coupling.
    shown = 1;
    draw();
    return { destroy() {}, progress: () => 1, redraw: draw };
  }
  draw();
  addEventListener('scroll', onScroll, { passive: true });
  addEventListener('resize', refit);
  addEventListener('pageshow', refit);
  const ro = typeof ResizeObserver === 'function' ? new ResizeObserver(refit) : null;
  if (ro) { ro.observe(canvas); ro.observe(zone); }
  const io = typeof IntersectionObserver === 'function'
    ? new IntersectionObserver((es) => { visible = es.some((e) => e.isIntersecting); if (visible) kick(); }, { threshold: 0 })
    : null;
  if (io) io.observe(canvas);
  kick();

  return {
    progress: () => shown,
    redraw: draw,
    destroy() {
      stopped = true;
      if (raf) cancelAnimationFrame(raf);
      removeEventListener('scroll', onScroll);
      removeEventListener('resize', refit);
      removeEventListener('pageshow', refit);
      if (ro) ro.disconnect();
      if (io) io.disconnect();
    },
  };
}
