// Tests for templates/scroll-scene.js with a fake browser. Run: node tests/motion_forensics/test_scene.mjs
import { createScene, rng, phase, ease, progressFor, anchorProgress, damp } from '../../plugins/top30-ui/skills/motion-forensics/templates/scroll-scene.js';

let failures = 0;
const check = (cond, msg) => { console.log((cond ? 'PASS ' : 'FAIL ') + msg); if (!cond) failures++; };
const close = (a, b, eps = 1e-9) => Math.abs(a - b) < eps;

// ---- pure helpers ----
const a = rng(42), b = rng(42), c = rng(43);
const sa = Array.from({ length: 5 }, a), sb = Array.from({ length: 5 }, b), sc = Array.from({ length: 5 }, c);
check(sa.join() === sb.join() && sa.join() !== sc.join(), 'rng: same seed, same sequence; different seed, different');
check(sa.every((x) => x >= 0 && x < 1), 'rng: values in [0, 1)');

check(phase(0.2, 0.2, 0.6, 0) === 0 && phase(0.6, 0.2, 0.6, 1) === 1, 'phase: first item starts at start, last item ends at end');
check(phase(0.3, 0.2, 0.6, 1) === 0 && phase(0.3, 0.2, 0.6, 0) > 0, 'phase: lag delays the item (a wave, not a block)');
let mono = true, prev = -1;
for (let p = 0; p <= 1.0001; p += 0.01) { const v = phase(p, 0.1, 0.5, 0.5); if (v < prev - 1e-12) mono = false; prev = v; }
check(mono, 'phase: never runs backwards as progress grows (so scrolling back rewinds exactly)');
check(phase(0.5, 0.5, 0.5) === 1 && phase(0.4, 0.5, 0.5) === 0, 'phase: zero-length phase is a step');

check(close(ease.inOutCubic(0.5), 0.5) && ease.inOutCubic(0) === 0 && close(ease.inOutCubic(1), 1), 'ease.inOutCubic endpoints and midpoint');
let peak = 0;
for (let t = 0; t <= 1; t += 0.01) peak = Math.max(peak, ease.outBack(t));
check(peak > 1.05 && close(ease.outBack(1), 1), 'ease.outBack overshoots then settles at 1');

check(progressFor(1000, 1000, 3000, 900) === 0 && progressFor(3100, 1000, 3000, 900) === 1, 'progressFor: 0 at zone top, 1 when zone bottom meets viewport bottom');
check(close(progressFor(2050, 1000, 3000, 900), 0.5), 'progressFor: linear in between');
check(close(anchorProgress(2500, 100, 1000, 3000, 900), (2550 - 450 - 1000) / 2100), 'anchorProgress: element centred in viewport');
let v = 0;
for (let i = 0; i < 120; i++) v = damp(v, 1, 8, 16);
check(v > 0.999 && damp(0, 1, 8, 16) > 0 && close(damp(0, 1, 8, 32), damp(damp(0, 1, 8, 16), 1, 8, 16), 1e-12), 'damp: converges and is frame-rate independent');

// ---- createScene with a fake DOM ----
function fakeWorld({ reduced = false, dpr = 3 } = {}) {
  const listeners = {}, rafQ = [];
  let now = 0;
  const g = globalThis;
  g.scrollY = 0; g.innerHeight = 900; g.devicePixelRatio = dpr;
  g.matchMedia = (q) => ({ matches: reduced && q.includes('reduce') });
  g.addEventListener = (ev, fn) => { (listeners[ev] = listeners[ev] || []).push(fn); };
  g.removeEventListener = (ev, fn) => { listeners[ev] = (listeners[ev] || []).filter((f) => f !== fn); };
  g.requestAnimationFrame = (fn) => { rafQ.push(fn); return rafQ.length; };
  g.cancelAnimationFrame = () => {};
  g.ResizeObserver = class { observe() {} disconnect() {} };
  g.IntersectionObserver = class { constructor(cb) { this.cb = cb; } observe() { this.cb([{ isIntersecting: true }]); } disconnect() {} };
  const calls = { clear: 0, draws: [] };
  const ctx = { setTransform: (...m) => { calls.transform = m; }, clearRect: () => calls.clear++ };
  const canvas = { clientWidth: 1440, clientHeight: 900, width: 0, height: 0, dataset: {}, getContext: () => ctx };
  const anchorEl = { dataset: { phase: 'sorted' }, getBoundingClientRect: () => ({ top: 2500 - g.scrollY, height: 100 }) };
  const zone = { getBoundingClientRect: () => ({ top: 1000 - g.scrollY, height: 3000 }), querySelectorAll: () => [anchorEl] };
  const flush = (n = 1, step = 16) => { for (let i = 0; i < n && rafQ.length; i++) { const q = rafQ.splice(0); now += step; q.forEach((f) => f(now)); } };
  const scroll = (y) => { g.scrollY = y; (listeners.scroll || []).forEach((f) => f()); };
  return { canvas, zone, calls, flush, scroll, rafQ, listeners };
}

{
  const W = fakeWorld();
  let setups = 0;
  const seen = [];
  const scene = createScene({
    canvas: W.canvas, zone: W.zone, seed: 9,
    setup: ({ random }) => { setups++; return { first: random() }; },
    render: (ctx, s) => seen.push(s),
    live: (p) => p < 0.1,
  });
  check(W.canvas.width === 2880 && W.canvas.height === 1800 && W.calls.transform[0] === 2, 'DPR capped at 2, backing store sized before the transform');
  check(setups === 1 && seen[0].data.first === rng(9)(), 'setup gets the seeded random (same layout every visit)');
  check(close(seen[0].a.sorted, (2550 - 450 - 1000) / 2100), 'data-phase anchors measured from the page copy');
  W.flush(5);
  const timeDraws = seen.length;
  check(timeDraws > 3 && seen.at(-1).t > seen[1].t, 'ambient loop runs while live(p) is true (time advances)');
  W.scroll(2050); W.flush(3);
  check(close(seen.at(-1).p, 0.5) && W.canvas.dataset.progress === '0.500', 'scrolling sets progress; canvas exposes data-progress for tests');
  const after = seen.length;
  W.flush(10);
  check(seen.length === after && W.rafQ.length === 0, 'outside live windows the loop stops: scroll-only, no idle frames');
  W.scroll(1000); W.flush(3);
  check(seen.at(-1).p === 0, 'scrolling back rewinds exactly');
  scene.destroy();
  check(!(W.listeners.scroll || []).length, 'destroy removes listeners');
}
{
  const W = fakeWorld({ reduced: true });
  const seen = [];
  createScene({ canvas: W.canvas, zone: W.zone, setup: () => ({}), render: (c, s) => seen.push(s), live: () => true });
  W.flush(5);
  check(seen.length === 1 && seen[0].p === 1 && seen[0].reduced && !(W.listeners.scroll || []).length,
    'reduced motion: one still frame of the settled state, no loop, no scroll coupling');
}
{
  const W = fakeWorld();
  const seen = [];
  createScene({ canvas: W.canvas, zone: W.zone, setup: () => ({}), render: (c, s) => seen.push(s.p), live: () => false, smoothing: 10 });
  W.scroll(2050); W.flush(2);
  const mid = seen.at(-1);
  W.flush(200);
  check(mid > 0 && mid < 0.5 && close(seen.at(-1), 0.5, 1e-3), 'smoothing: progress eases toward the scroll target, then the loop stops');
}

console.log(`\n${failures ? 'FAILED' : 'OK'}: ${failures} failure(s)`);
process.exit(failures ? 1 : 0);
