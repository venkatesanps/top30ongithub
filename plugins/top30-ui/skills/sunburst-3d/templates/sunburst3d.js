/*
 * sunburst3d.js: a tilted, extruded sunburst for hierarchies (disk usage, budgets, bundles).
 * Canvas 2D, no dependencies.
 *
 * The look: a sunburst laid flat and seen from above at an angle, so every ring is a thick
 * slab. Circles are drawn as ellipses squashed vertically (`tilt`), each arc has a top face plus
 * the walls you can see (outer walls on the near side, end walls where a ring stops), and the
 * walls are drawn back to front before the top faces. Hue follows angle; deeper rings get lighter.
 * Hover lifts an arc; click drills in with the children opening out to the full circle; the
 * center puck goes back up.
 *
 *   import { Sunburst3D } from './sunburst3d.js';
 *   const chart = new Sunburst3D(document.querySelector('#chart'), data, { rings: 4 });
 *   // data: { name: 'Home', children: [{ name: 'Movies', size: 52e9 }, { name: 'Library', children: [...] }] }
 *   chart.focus(['Home', 'Library']);   // drill by path; chart.up(); chart.destroy();
 *
 * Pure helpers (layout, projection, hit testing, colors, transitions) are exported for tests and
 * for drawing into any 2D context, e.g. a server-side canvas.
 *
 * Part of the top30-ui plugin (github.com/venkatesanps/top30ongithub). MIT.
 */

export const TAU = Math.PI * 2;

export const DEFAULTS = {
  rings: 4,             // rings shown below the focus
  tilt: 0.72,           // vertical squash of the circles: 1 is flat-on, smaller is more tilted
  thickness: 0.06,      // slab height as a share of the outer radius
  inner: 0.22,          // center puck radius as a share of the outer radius
  minAngle: 0.035,      // radians; smaller children merge into one "smaller items" arc
  maxArcs: 2500,
  hueStart: 200,        // hue at 12 o'clock; the full circle spans 360 degrees from here
  entranceMs: 560,      // per ring
  staggerMs: 60,        // delay between rings on entrance
  zoomMs: 650,
  liftFrac: 0.55,       // hover lift, as a share of the slab height
  pad: 12,
  seam: 'rgba(10, 11, 16, 0.38)',
  otherLabel: (n) => `${n} smaller item${n === 1 ? '' : 's'}`,
  formatSize: formatBytes,
};

// ---------- data ----------

/** Fill in `size` on folders (sum of children) and `path` (array of names) on every node. */
export function prepare(root) {
  const walk = (node, path) => {
    node.path = [...path, node.name];
    if (Array.isArray(node.children) && node.children.length) {
      let s = 0;
      for (const c of node.children) s += walk(c, node.path);
      node.size = Math.max(s, node.size || 0);
    } else node.size = Math.max(0, +node.size || 0);
    return node.size;
  };
  walk(root, []);
  return root;
}

export const pathKey = (path) => path.join('␟');

export function findNode(root, path) {
  let node = root;
  for (let i = 1; i < path.length; i++) {
    node = (node.children || []).find((c) => c.name === path[i]);
    if (!node) return null;
  }
  return node;
}

export function formatBytes(n) {
  if (!(n > 0)) return '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB'];
  let i = 0;
  while (n >= 1000 && i < units.length - 1) { n /= 1000; i++; }
  return `${n.toFixed(i === 0 || n >= 100 ? 0 : 1)} ${units[i]}`;
}

// ---------- layout ----------

/**
 * Arcs for the rings below `focus`. Each arc: { key, node, path, depth (1..rings), a0, a1 (radians,
 * clockwise from 12 o'clock), h0, h1 (hue range), kind: 'dir' | 'file' | 'other', count }.
 * Children are sorted largest first; any that would be thinner than minAngle merge into one
 * 'other' arc so the ring stays complete.
 */
export function partition(focus, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const arcs = [];
  let level = [{ node: focus, a0: 0, a1: TAU, h0: o.hueStart, h1: o.hueStart + 360 }];
  for (let depth = 1; depth <= o.rings && level.length; depth++) {
    const next = [];
    for (const p of level) {
      const kids = (p.node.children || []).filter((c) => c.size > 0).sort((a, b) => b.size - a.size);
      const total = p.node.size;
      if (!kids.length || !(total > 0)) continue;
      const span = p.a1 - p.a0, hspan = p.h1 - p.h0;
      let a = p.a0, used = 0, i = 0;
      for (; i < kids.length; i++) {
        const w = (span * kids[i].size) / total;
        if (w < o.minAngle || arcs.length >= o.maxArcs) break;
        const c = kids[i];
        const arc = {
          key: pathKey(c.path), node: c, path: c.path, depth, a0: a, a1: a + w,
          h0: p.h0 + (hspan * (a - p.a0)) / span, h1: p.h0 + (hspan * (a + w - p.a0)) / span,
          kind: c.children && c.children.length ? 'dir' : 'file', count: 1,
        };
        arcs.push(arc);
        if (arc.kind === 'dir') next.push(arc);
        a += w; used += c.size;
      }
      const restN = kids.length - i;
      if (restN > 0 && p.a1 - a > 1e-9) {
        arcs.push({
          key: pathKey([...p.node.path, '…']), node: { name: o.otherLabel(restN), size: Math.max(0, total - used), path: [...p.node.path, '…'] },
          path: [...p.node.path, '…'], depth, a0: a, a1: p.a1,
          h0: p.h0 + (hspan * (a - p.a0)) / span, h1: p.h1, kind: 'other', count: restN,
        });
      }
    }
    level = next;
  }
  return arcs;
}

/** Pixel geometry for a w x h box: center, outer radius R, puck radius, ring width, slab height. */
export function geometry(w, h, opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const R = Math.max(30, Math.min(w / 2 - o.pad, (h - 2 * o.pad) / (2 * o.tilt + o.thickness + o.thickness * o.liftFrac)));
  const inner = Math.max(18, R * o.inner);
  const ringW = (R - inner) / o.rings;
  const thick = Math.max(3, R * o.thickness);
  return { cx: w / 2, cy: h / 2 - thick / 2, R, inner, ringW, thick, tilt: o.tilt, rings: o.rings };
}

/** Screen point of polar (r px, angle) on a plane lifted z px above the top surface. */
export function project(g, r, angle, z = 0) {
  return [g.cx + r * Math.sin(angle), g.cy - r * Math.cos(angle) * g.tilt - z];
}

/** Angle (clockwise from 12) and radius on the top surface under a screen point. */
export function unproject(g, x, y) {
  const dx = x - g.cx, dy = (y - g.cy) / g.tilt;
  let a = Math.atan2(dx, -dy);
  if (a < 0) a += TAU;
  return { r: Math.hypot(dx, dy), a };
}

/** 'center', an arc from `arcs`, or null. Tests the top faces, which is what people aim at. */
export function hitTest(g, arcs, x, y) {
  const { r, a } = unproject(g, x, y);
  if (r < g.inner) return 'center';
  if (r > g.inner + g.ringW * g.rings) return null;
  const depth = Math.floor((r - g.inner) / g.ringW) + 1;
  return arcs.find((c) => c.depth === depth && a >= c.a0 && a < c.a1) || null;
}

// ---------- color ----------

export function hsl(h, s, l) {
  h = ((h % 360) + 360) % 360;
  const k = (n) => (n + h / 30) % 12, a = s * Math.min(l, 1 - l);
  const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, 9 - k(n), 1));
  return [f(0), f(8), f(4)].map((v) => Math.round(v * 255));
}

/** Top-face color: hue from the arc's place on the circle, lighter and calmer with depth. */
export function arcColor(arc) {
  const hue = (arc.h0 + arc.h1) / 2, d = arc.depth - 1;
  if (arc.kind === 'other') return hsl(hue, 0.16, 0.44);
  const s = Math.max(0.5, 0.74 - d * 0.04) * (arc.kind === 'file' ? 0.8 : 1);
  const l = Math.min(0.7, 0.54 + d * 0.04);
  return hsl(hue, s, l);
}

export const rgb = ([r, g, b], k = 1, a = 1) => {
  const c = (v) => Math.max(0, Math.min(255, Math.round(v * k)));
  return a >= 1 ? `rgb(${c(r)}, ${c(g)}, ${c(b)})` : `rgba(${c(r)}, ${c(g)}, ${c(b)}, ${a})`;
};

// ---------- motion ----------

export const ease = {
  outCubic: (t) => 1 - (1 - t) ** 3,
  inOutCubic: (t) => (t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2),
  outBack: (t) => { const c = 1.4; return 1 + (c + 1) * (t - 1) ** 3 + c * (t - 1) ** 2; },
};
const clamp01 = (t) => Math.max(0, Math.min(1, t));
const mix = (a, b, t) => a + (b - a) * t;

/** Ring-unit geometry of an arc at rest: u0..u1 where the puck edge is 0 and each ring is 1 wide. */
export const restState = (arc) => ({ a0: arc.a0, a1: arc.a1, u0: arc.depth - 1, u1: arc.depth, alpha: 1 });

/**
 * Where each new arc starts when the focus changes from `oldArcs` (around `oldFocus`) to `newArcs`.
 * Arcs that were on screen start where they were; the old focus starts as the puck; arcs that
 * appear inside a known ancestor open out of it; anything else fades in from just outside.
 */
export function transitionStarts(oldArcs, oldFocusPath, newArcs, innerU) {
  const old = new Map(oldArcs.map((c) => [c.key, restState(c)]));
  const starts = new Map();
  const oldFocusKey = pathKey(oldFocusPath);
  for (const c of newArcs) {
    if (old.has(c.key)) { starts.set(c.key, old.get(c.key)); continue; }
    if (c.key === oldFocusKey) { starts.set(c.key, { a0: 0, a1: TAU, u0: -innerU, u1: 0, alpha: 1 }); continue; }
    let anc = null;
    for (let i = c.path.length - 1; i > 0 && !anc; i--) {
      const k = pathKey(c.path.slice(0, i));
      const parent = newArcs.find((x) => x.key === k);
      if (parent && starts.has(k)) anc = { s: starts.get(k), p: parent };
    }
    if (anc) {
      const { s, p } = anc, span = p.a1 - p.a0 || 1, sspan = s.a1 - s.a0;
      starts.set(c.key, { a0: s.a0 + ((c.a0 - p.a0) / span) * sspan, a1: s.a0 + ((c.a1 - p.a0) / span) * sspan, u0: s.u1, u1: s.u1, alpha: 0 });
    } else starts.set(c.key, { a0: c.a0, a1: c.a1, u0: c.depth - 1 + 0.6, u1: c.depth + 0.6, alpha: 0 });
  }
  return starts;
}

/** Interpolated ring-unit state of every arc at time t (ms) of a transition. */
export function frameStates(arcs, tr, t) {
  const out = new Map();
  for (const c of arcs) {
    const end = restState(c);
    if (!tr) { out.set(c.key, end); continue; }
    if (tr.kind === 'entrance') {
      const k = clamp01((t - (c.depth - 1) * tr.staggerMs) / tr.ms);
      if (k >= 1) { out.set(c.key, end); continue; }
      const sweep = ease.outCubic(k), grow = ease.outBack(k);
      out.set(c.key, { a0: c.a0 * sweep, a1: c.a1 * sweep, u0: mix(-tr.innerU, end.u0, grow), u1: mix(-tr.innerU, end.u1, grow), alpha: clamp01(k * 2) });
    } else {
      if (t >= tr.ms) { out.set(c.key, end); continue; }
      const k = ease.inOutCubic(clamp01(t / tr.ms)), s = tr.starts.get(c.key) || end;
      out.set(c.key, { a0: mix(s.a0, end.a0, k), a1: mix(s.a1, end.a1, k), u0: mix(s.u0, end.u0, k), u1: mix(s.u1, end.u1, k), alpha: mix(s.alpha, 1, clamp01(k * 1.6)) });
    }
  }
  return out;
}

export function transitionDone(tr, t) {
  if (!tr) return true;
  return tr.kind === 'entrance' ? t >= tr.ms + (tr.rings - 1) * tr.staggerMs : t >= tr.ms;
}

// ---------- drawing ----------

function ringPath(ctx, g, r0, r1, a0, a1, z) {
  const e0 = a0 - Math.PI / 2, e1 = a1 - Math.PI / 2, cy = g.cy - z;
  ctx.moveTo(...project(g, r1, a0, z));
  ctx.ellipse(g.cx, cy, r1, r1 * g.tilt, 0, e0, e1, false);
  if (r0 > 0.5) ctx.ellipse(g.cx, cy, r0, r0 * g.tilt, 0, e1, e0, true);
  else ctx.lineTo(g.cx, cy);
  ctx.closePath();
}

/** The band below a ring edge between angles a0..a1: the side of the slab at radius r. */
function wallPath(ctx, g, r, a0, a1, zTop, zBottom) {
  const e0 = a0 - Math.PI / 2, e1 = a1 - Math.PI / 2;
  ctx.moveTo(...project(g, r, a0, zTop));
  ctx.ellipse(g.cx, g.cy - zTop, r, r * g.tilt, 0, e0, e1, false);
  ctx.lineTo(...project(g, r, a1, zBottom));
  ctx.ellipse(g.cx, g.cy - zBottom, r, r * g.tilt, 0, e1, e0, true);
  ctx.closePath();
}

function endPath(ctx, g, a, r0, r1, zTop, zBottom) {
  ctx.moveTo(...project(g, r0, a, zTop));
  ctx.lineTo(...project(g, r1, a, zTop));
  ctx.lineTo(...project(g, r1, a, zBottom));
  ctx.lineTo(...project(g, r0, a, zBottom));
  ctx.closePath();
}

// Light comes from the viewer's upper left: walls facing it are brighter.
const LIGHT = (() => { const x = -0.55, y = 1; const n = Math.hypot(x, y); return [x / n, y / n]; })();
const shade = (nx, ny) => 0.42 + 0.34 * Math.max(0, nx * LIGHT[0] + ny * LIGHT[1]);

/** Parts of [a0, a1] not covered by `covers` (sorted [b0, b1] ranges). */
function uncovered(a0, a1, covers) {
  const out = [];
  let a = a0;
  for (const [b0, b1] of covers) {
    if (b1 <= a + 1e-6) continue;
    if (b0 > a + 1e-6) out.push([a, Math.min(b0, a1)]);
    a = Math.max(a, b1);
    if (a >= a1 - 1e-6) break;
  }
  if (a < a1 - 1e-6) out.push([a, a1]);
  return out;
}

/**
 * The visible walls of a slab made of `items` ({ arc, s: state, px: {r0, r1}, z }), as draw jobs
 * sorted far to near. A wall is visible when it faces the viewer and nothing sits against it.
 */
export function wallJobs(g, items, lifted) {
  const jobs = [];
  const byDepth = new Map();
  for (const it of items) {
    if (!byDepth.has(it.arc.depth)) byDepth.set(it.arc.depth, []);
    byDepth.get(it.arc.depth).push(it);
  }
  const edges = (d) => (byDepth.get(d) || []).filter((x) => x !== lifted).map((x) => [x.s.a0, x.s.a1]).sort((p, q) => p[0] - q[0]);
  for (const it of items) {
    const { arc, s, px } = it, free = it === lifted;
    // A lifted arc's walls stop at the surface: below it the neighbours' own walls show the hole.
    const zTop = it.z, zBot = free ? 0 : -g.thick;
    // Outer wall: faces the viewer on the near half (cos a < 0); hidden where the next ring covers it.
    const outer = free ? [[s.a0, s.a1]] : uncovered(s.a0, s.a1, edges(arc.depth + 1));
    for (const [b0, b1] of outer) {
      const c0 = Math.max(b0, Math.PI / 2), c1 = Math.min(b1, (3 * Math.PI) / 2);
      if (c1 - c0 > 1e-4) jobs.push({ type: 'outer', it, a0: c0, a1: c1, r: px.r1, zTop, zBot, y: project(g, px.r1, (c0 + c1) / 2, zBot)[1] });
    }
    // Inner wall: only shows when the arc is lifted (the far half faces the viewer).
    if (free && px.r0 > 0.5) {
      const c0 = s.a0, c1 = s.a1;
      for (const [d0, d1] of [[c0, Math.min(c1, Math.PI / 2)], [Math.max(c0, (3 * Math.PI) / 2), c1]]) {
        if (d1 - d0 > 1e-4) jobs.push({ type: 'inner', it, a0: d0, a1: d1, r: px.r0, zTop, zBot, y: project(g, px.r0, (d0 + d1) / 2, zBot)[1] - 1e4 });
      }
    }
    // End walls: the a1 end faces the viewer when sin(a1) > 0, the a0 end when sin(a0) < 0.
    const same = free ? [] : edges(arc.depth);
    const full = s.a1 - s.a0 >= TAU - 1e-6;
    if (!full) {
      if (Math.sin(s.a1) > 1e-6 && (free || !same.some(([b0]) => Math.abs(b0 - s.a1) < 1e-6 || Math.abs(b0 + TAU - s.a1) < 1e-6)))
        jobs.push({ type: 'end', it, a: s.a1, n: [Math.cos(s.a1), Math.sin(s.a1)], zTop, zBot, y: project(g, (px.r0 + px.r1) / 2, s.a1, zBot)[1] });
      if (Math.sin(s.a0) < -1e-6 && (free || !same.some(([, b1]) => Math.abs(b1 - s.a0) < 1e-6 || Math.abs(b1 - TAU - s.a0) < 1e-6)))
        jobs.push({ type: 'end', it, a: s.a0, n: [-Math.cos(s.a0), -Math.sin(s.a0)], zTop, zBot, y: project(g, (px.r0 + px.r1) / 2, s.a0, zBot)[1] });
    }
  }
  return jobs.sort((p, q) => p.y - q.y);
}

/**
 * Draw one frame. `arcs` from partition(), `states` from frameStates(), `lift` a Map key -> 0..1,
 * `puck` { lift: 0..1, label?: ignored here }. Clears nothing: the caller owns the background.
 */
export function drawScene(ctx, g, arcs, states, lift = new Map(), opts = {}) {
  const o = { ...DEFAULTS, ...opts };
  const items = [];
  for (const arc of arcs) {
    const s = states.get(arc.key);
    if (!s || s.alpha <= 0.01 || s.a1 - s.a0 < 1e-5) continue;
    const r0 = Math.max(0, g.inner + s.u0 * g.ringW), r1 = Math.max(0, g.inner + s.u1 * g.ringW);
    if (r1 - r0 < 0.3) continue;
    items.push({ arc, s, px: { r0, r1 }, z: (lift.get(arc.key) || 0) * g.thick * o.liftFrac, color: arcColor(arc) });
  }
  const lifted = items.filter((it) => it.z > 0.05).sort((p, q) => p.z - q.z);
  const flat = items.filter((it) => it.z <= 0.05);

  const drawWalls = (jobs) => {
    for (const j of jobs) {
      const { color, s } = j.it;
      ctx.beginPath();
      if (j.type === 'end') {
        endPath(ctx, g, j.a, j.it.px.r0, j.it.px.r1, j.zTop, j.zBot);
        ctx.fillStyle = rgb(color, shade(j.n[0], j.n[1]), s.alpha);
      } else {
        wallPath(ctx, g, j.r, j.a0, j.a1, j.zTop, j.zBot);
        const sign = j.type === 'outer' ? 1 : -1;
        const [x0] = project(g, j.r, j.a0), [x1] = project(g, j.r, j.a1);
        const grad = ctx.createLinearGradient(Math.min(x0, x1, g.cx - j.r), 0, Math.max(x0, x1, g.cx + j.r), 0);
        // brightness across the curved wall: sample the facing at the left and right extremes
        grad.addColorStop(0, rgb(color, shade(-sign, 0.2 * sign), s.alpha));
        grad.addColorStop(0.5, rgb(color, shade(0, sign), s.alpha));
        grad.addColorStop(1, rgb(color, shade(sign, 0.2 * sign), s.alpha));
        ctx.fillStyle = grad;
      }
      ctx.fill();
      ctx.strokeStyle = o.seam;
      ctx.lineWidth = 0.75;
      ctx.stroke();
    }
  };
  const drawTop = (it) => {
    ctx.beginPath();
    ringPath(ctx, g, it.px.r0, it.px.r1, it.s.a0, it.s.a1, it.z);
    ctx.fillStyle = rgb(it.color, 1 + 0.12 * (it.z > 0.05 ? 1 : 0), it.s.alpha);
    ctx.fill();
    ctx.strokeStyle = o.seam;
    ctx.lineWidth = 1;
    ctx.stroke();
  };

  drawWalls(wallJobs(g, flat, null));
  for (const it of flat) drawTop(it);
  drawPuck(ctx, g, opts.puckLift || 0, o);
  for (const it of lifted) { drawWalls(wallJobs(g, [it], it)); drawTop(it); }
  return items.length;
}

/** The dark center puck; it rises a little when hot (hovered or focused from the keyboard). */
export function drawPuck(ctx, g, hot = 0, o = DEFAULTS) {
  // Only the part above the ring surface shows: the rings hide the rest of the cylinder.
  const r = g.inner, z = g.thick * (0.35 + 0.45 * hot);
  ctx.beginPath();
  ctx.ellipse(g.cx, g.cy, r, r * g.tilt, 0, 0, Math.PI);
  ctx.lineTo(g.cx - r, g.cy - z);
  ctx.ellipse(g.cx, g.cy - z, r, r * g.tilt, 0, Math.PI, 0, true);
  ctx.closePath();
  ctx.fillStyle = '#121318';
  ctx.fill();
  const top = ctx.createLinearGradient(0, g.cy - z - r * g.tilt, 0, g.cy - z + r * g.tilt);
  const v = (a, b) => { const k = Math.round(a + (b - a) * hot); return `rgb(${k}, ${k + 1}, ${k + 10})`; };
  top.addColorStop(0, v(52, 70));
  top.addColorStop(1, v(22, 30));
  ctx.beginPath();
  ctx.ellipse(g.cx, g.cy - z, r, r * g.tilt, 0, 0, TAU);
  ctx.fillStyle = top;
  ctx.fill();
  ctx.strokeStyle = `rgba(255, 255, 255, ${0.12 + 0.22 * hot})`;
  ctx.lineWidth = 1;
  ctx.stroke();
  void o;
  return z;
}

// ---------- the component ----------

const reducedMotion = () => typeof matchMedia === 'function' && matchMedia('(prefers-reduced-motion: reduce)').matches;

export class Sunburst3D {
  /**
   * container: an element (position relative is set). data: { name, size?, children? }.
   * opts: DEFAULTS plus onFocus(node), onHover(node | null), ariaLabel.
   */
  constructor(container, data, opts = {}) {
    this.o = { ...DEFAULTS, ...opts };
    this.el = container;
    this.el.classList.add('sb3d');
    if (getComputedStyle(this.el).position === 'static') this.el.style.position = 'relative';
    this.canvas = document.createElement('canvas');
    this.canvas.tabIndex = 0;
    this.canvas.setAttribute('role', 'img');
    this.canvas.style.cssText = 'display:block;width:100%;height:100%;touch-action:manipulation;outline-offset:4px;border-radius:12px';
    this.center = document.createElement('div');
    this.center.className = 'sb3d-center';
    this.center.setAttribute('aria-hidden', 'true');
    this.tip = document.createElement('div');
    this.tip.className = 'sb3d-tip';
    this.tip.setAttribute('aria-hidden', 'true');
    this.live = document.createElement('div');
    this.live.className = 'sb3d-sr';
    this.live.setAttribute('aria-live', 'polite');
    this.table = document.createElement('table');
    this.table.className = 'sb3d-sr';
    this.el.append(this.canvas, this.center, this.tip, this.live, this.table);
    this.ctx = this.canvas.getContext('2d');
    this.lift = new Map();
    this.puckHot = 0;
    this.hover = null;
    this.kbIndex = -1;
    this.raf = 0;
    this.setData(data);
    this._bind();
    this.ro = new ResizeObserver(() => this._resize());
    this.ro.observe(this.el);
    this._resize();
  }

  setData(data) {
    this.root = prepare(data);
    this.focusNode = this.root;
    this.arcs = partition(this.root, this.o);
    this._start({ kind: 'entrance' });
    this._describe();
  }

  /** Drill to a node by path (array of names from the root). */
  focus(path) {
    const node = findNode(this.root, path);
    if (!node || !node.children || !node.children.length || node === this.focusNode) return false;
    const oldArcs = this.arcs, oldPath = this.focusNode.path;
    this.focusNode = node;
    this.arcs = partition(node, this.o);
    this._start({ kind: 'zoom', starts: transitionStarts(oldArcs, oldPath, this.arcs, this.g ? this.g.inner / this.g.ringW : 1) });
    this._setHover(null);
    this._describe();
    this.o.onFocus?.(node);
    return true;
  }

  up() {
    const p = this.focusNode.path;
    return p.length > 1 ? this.focus(p.slice(0, -1)) : false;
  }

  destroy() {
    cancelAnimationFrame(this.raf);
    this.ro.disconnect();
    this._unbind();
    this.el.replaceChildren();
  }

  // -- internals --
  _start(spec) {
    const rm = reducedMotion();
    this.tr = rm ? null : {
      ...spec, rings: this.o.rings, staggerMs: this.o.staggerMs,
      ms: spec.kind === 'entrance' ? this.o.entranceMs : this.o.zoomMs,
      innerU: this.g ? this.g.inner / this.g.ringW : 1,
    };
    this.t0 = performance.now();
    this._kick();
  }

  _kick() { if (!this.raf) this.raf = requestAnimationFrame((t) => this._frame(t)); }

  _resize() {
    const r = this.el.getBoundingClientRect(), dpr = Math.min(2, window.devicePixelRatio || 1);
    if (r.width < 10 || r.height < 10) return;
    this.w = r.width; this.h = r.height;
    this.canvas.width = Math.round(r.width * dpr);
    this.canvas.height = Math.round(r.height * dpr);
    this.ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    this.g = geometry(r.width, r.height, this.o);
    if (this.tr) this.tr.innerU = this.g.inner / this.g.ringW;
    this._kick();
  }

  _frame(now) {
    this.raf = 0;
    if (!this.g) return;
    const rm = reducedMotion();
    const dt = Math.min(64, now - (this._last || now));
    this._last = now;
    const t = now - this.t0;
    const states = frameStates(this.arcs, this.tr, t);
    let moving = !transitionDone(this.tr, t);
    if (!moving) this.tr = null;
    // hover lift eases toward its target; snaps under reduced motion
    const k = rm ? 1 : 1 - Math.exp(-dt / 70);
    const target = this.hover && this.hover !== 'center' ? this.hover.key : null;
    if (target && !this.lift.has(target)) this.lift.set(target, 0);
    for (const [key, v] of this.lift) {
      const goal = key === target ? 1 : 0, nv = v + (goal - v) * k;
      if (Math.abs(goal - nv) < 0.004) { goal ? this.lift.set(key, 1) : this.lift.delete(key); } else { this.lift.set(key, nv); moving = true; }
    }
    const pg = this.hover === 'center' ? 1 : 0;
    this.puckHot += (pg - this.puckHot) * k;
    if (Math.abs(pg - this.puckHot) < 0.004) this.puckHot = pg; else moving = true;

    this.ctx.clearRect(0, 0, this.w, this.h);
    drawScene(this.ctx, this.g, this.arcs, states, this.lift, { ...this.o, puckLift: this.puckHot });
    this._placeCenter();
    if (moving) this._kick();
  }

  _placeCenter() {
    const g = this.g, z = g.thick * (0.35 + 0.45 * this.puckHot);
    const h = this.hover && this.hover !== 'center' ? this.hover : null;
    const node = h ? h.node : this.focusNode;
    const share = h ? ` · ${Math.max(0.1, (100 * node.size) / (this.focusNode.size || 1)).toFixed(node.size / this.focusNode.size >= 0.1 ? 0 : 1)}%` : '';
    const fs = Math.max(9, Math.min(14, g.inner * 0.2));
    this.center.style.cssText = `left:${g.cx}px;top:${g.cy - z}px;width:${g.inner * 1.7}px;font-size:${fs.toFixed(1)}px`;
    const name = this.center.firstChild?.textContent, size = `${this.o.formatSize(node.size)}${share}`;
    if (name !== node.name || this.center.lastChild?.textContent !== size) {
      this.center.innerHTML = '<div class="sb3d-name"></div><div class="sb3d-size"></div>';
      this.center.firstChild.textContent = node.name;
      this.center.lastChild.textContent = size;
    }
  }

  _setHover(h, x, y) {
    if (h === this.hover && !h) return;
    this.hover = h;
    this.canvas.style.cursor = h && (h === 'center' ? this.focusNode.path.length > 1 : h.kind === 'dir') ? 'pointer' : 'default';
    if (h && h !== 'center' && x != null) {
      const parent = findNode(this.root, h.path.slice(0, -1)) || this.focusNode;
      this.tip.innerHTML = '<b></b><span></span>';
      this.tip.firstChild.textContent = h.node.name;
      this.tip.lastChild.textContent = `${this.o.formatSize(h.node.size)} · ${Math.round((100 * h.node.size) / (parent.size || 1))}% of ${parent.name}${h.kind === 'dir' ? (this.lastPointer === 'touch' ? ' · tap again to open' : ' · click to open') : ''}`;
      const left = Math.min(Math.max(8, x + 14), this.w - 200), top = Math.max(8, y - 44);
      this.tip.style.cssText = `left:${left}px;top:${top}px;opacity:1`;
    } else this.tip.style.opacity = '0';
    this.o.onHover?.(h && h !== 'center' ? h.node : null);
    this._kick();
  }

  _point(e) { const r = this.canvas.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }

  _bind() {
    this.handlers = {
      move: (e) => { if (!this.g || e.pointerType === 'touch') return; const [x, y] = this._point(e); this._setHover(hitTest(this.g, this.arcs, x, y), x, y); },
      leave: (e) => { if (e.pointerType !== 'touch') this._setHover(null); },
      down: (e) => { this.lastPointer = e.pointerType; },
      click: (e) => {
        const [x, y] = this._point(e), hit = hitTest(this.g, this.arcs, x, y);
        const touch = this.lastPointer === 'touch' || this.lastPointer === 'pen';
        if (hit === 'center') { this.up(); return; }
        // Touch has no hover: the first tap selects (lift, tooltip, center label), a second tap opens.
        if (touch && hit !== this.hover) { this._setHover(hit, x, y); return; }
        if (hit && hit.kind === 'dir') this.focus(hit.path);
        else if (touch && !hit) this._setHover(null);
      },
      key: (e) => {
        const ring = this.arcs.filter((c) => c.depth === 1);
        if (!ring.length) return;
        if (e.key === 'ArrowRight' || e.key === 'ArrowDown') this.kbIndex = (this.kbIndex + 1) % ring.length;
        else if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') this.kbIndex = (this.kbIndex - 1 + ring.length) % ring.length;
        else if (e.key === 'Enter' || e.key === ' ') { const c = ring[this.kbIndex]; if (c && c.kind === 'dir') { this.focus(c.path); this.kbIndex = -1; } }
        else if (e.key === 'Escape' || e.key === 'Backspace') { if (this.up()) this.kbIndex = -1; }
        else return;
        e.preventDefault();
        const c = ring[this.kbIndex];
        if (c) {
          const mid = (c.a0 + c.a1) / 2, [x, y] = project(this.g, this.g.inner + this.g.ringW * 0.5, mid);
          this._setHover(c, x, y);
          this.live.textContent = `${c.node.name}, ${this.o.formatSize(c.node.size)}${c.kind === 'dir' ? ', press Enter to open' : ''}`;
        }
      },
    };
    this.canvas.addEventListener('pointerdown', this.handlers.down);
    this.canvas.addEventListener('pointermove', this.handlers.move);
    this.canvas.addEventListener('pointerleave', this.handlers.leave);
    this.canvas.addEventListener('click', this.handlers.click);
    this.canvas.addEventListener('keydown', this.handlers.key);
  }

  _unbind() {
    this.canvas.removeEventListener('pointerdown', this.handlers.down);
    this.canvas.removeEventListener('pointermove', this.handlers.move);
    this.canvas.removeEventListener('pointerleave', this.handlers.leave);
    this.canvas.removeEventListener('click', this.handlers.click);
    this.canvas.removeEventListener('keydown', this.handlers.key);
  }

  /** Screen-reader view: the focus and its children as a table, announced on change. */
  _describe() {
    const f = this.focusNode, kids = this.arcs.filter((c) => c.depth === 1);
    const label = `${this.o.ariaLabel || 'Sunburst chart'}: ${f.name}, ${this.o.formatSize(f.size)}, ${kids.length} parts. Arrow keys move, Enter opens, Escape goes up.`;
    this.canvas.setAttribute('aria-label', label);
    this.live.textContent = `${f.name}, ${this.o.formatSize(f.size)}`;
    this.table.innerHTML = '<caption></caption><thead><tr><th>Name</th><th>Size</th><th>Share</th></tr></thead><tbody></tbody>';
    this.table.caption.textContent = f.name;
    const tb = this.table.tBodies[0];
    for (const c of kids) {
      const tr = tb.insertRow();
      tr.insertCell().textContent = c.node.name;
      tr.insertCell().textContent = this.o.formatSize(c.node.size);
      tr.insertCell().textContent = `${Math.round((100 * c.node.size) / (f.size || 1))}%`;
    }
  }
}

/** Styles for the HTML overlay (center label, tooltip, screen-reader-only parts). Inject once. */
export const CSS = `
.sb3d{user-select:none;-webkit-user-select:none}
.sb3d-center{position:absolute;transform:translate(-50%,-50%);text-align:center;pointer-events:none;color:#f4f5f8;font-weight:600;line-height:1.2;font-family:system-ui,-apple-system,sans-serif}
.sb3d-center .sb3d-name{white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sb3d-center .sb3d-size{margin-top:1px;font-size:1.15em;font-variant-numeric:tabular-nums;color:#c9cdf5}
.sb3d-tip{position:absolute;pointer-events:none;opacity:0;transition:opacity .12s;max-width:200px;padding:7px 10px;border-radius:9px;background:rgba(22,23,30,.94);border:1px solid rgba(255,255,255,.12);color:#eef0f6;font:12.5px/1.35 system-ui,-apple-system,sans-serif;box-shadow:0 8px 24px -8px rgba(0,0,0,.6)}
.sb3d-tip b{display:block;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.sb3d-tip span{color:#a9adbd;font-variant-numeric:tabular-nums}
.sb3d-sr{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0);white-space:nowrap}
.sb3d canvas:focus-visible{outline:2px solid #8ea2ff}
@media (prefers-reduced-motion: reduce){.sb3d-tip{transition:none}}
`;
