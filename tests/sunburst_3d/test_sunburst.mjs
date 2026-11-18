// Tests for the pure parts of sunburst3d.js: layout, projection and hit testing, colors,
// transitions and wall visibility. node tests/sunburst_3d/test_sunburst.mjs
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';
import * as sb from '../../plugins/top30-ui/skills/sunburst-3d/templates/sunburst3d.js';

const here = path.dirname(fileURLToPath(import.meta.url));
let fails = 0, passes = 0;
const check = (ok, msg) => { if (ok) passes++; else { fails++; console.log('FAIL', msg); } };
const close = (a, b, eps = 1e-6) => Math.abs(a - b) <= eps;

const data = JSON.parse(readFileSync(path.join(here, 'sample.json'), 'utf8'));
const root = sb.prepare(data);
check(root.size === root.children.reduce((s, c) => s + c.size, 0), 'folder size is the sum of its children');
check(sb.findNode(root, ['Home', 'Library', 'Caches'])?.name === 'Caches', 'findNode by path');

// partition
const arcs = sb.partition(root);
const ring1 = arcs.filter((a) => a.depth === 1);
check(close(ring1.reduce((s, a) => s + (a.a1 - a.a0), 0), sb.TAU, 1e-9), 'ring 1 spans the full circle');
check(Math.max(...arcs.map((a) => a.depth)) <= sb.DEFAULTS.rings, 'no arc deeper than the ring cap');
check(arcs.every((a) => a.kind === 'other' || a.a1 - a.a0 >= sb.DEFAULTS.minAngle - 1e-12), 'every named arc is at least minAngle wide');
check(new Set(arcs.map((a) => a.key)).size === arcs.length, 'arc keys are unique');
for (const p of arcs.filter((a) => a.kind === 'dir' && a.depth < sb.DEFAULTS.rings)) {
  const kids = arcs.filter((c) => c.depth === p.depth + 1 && c.path.length === p.path.length + 1 && c.path.slice(0, -1).join('/') === p.path.join('/'));
  if (!kids.length) continue;
  const lo = Math.min(...kids.map((k) => k.a0)), hi = Math.max(...kids.map((k) => k.a1));
  if (!(close(lo, p.a0, 1e-9) && close(hi, p.a1, 1e-9))) { check(false, `children of ${p.path.join('/')} fill its span`); break; }
  if (!kids.every((k) => k.h0 >= p.h0 - 1e-9 && k.h1 <= p.h1 + 1e-9)) { check(false, `hues of ${p.path.join('/')} children nest`); break; }
}
// merging: 40 tiny files become one "other" arc and the ring still closes
const tiny = sb.prepare({ name: 'r', children: [{ name: 'big', size: 1000 }, ...Array.from({ length: 40 }, (_, i) => ({ name: `f${i}`, size: 1 }))] });
const t = sb.partition(tiny);
check(t.length === 2 && t[1].kind === 'other' && t[1].count === 40 && t[1].node.size === 40, 'tiny children merge into one other arc with their total');
check(close(t[1].a1, sb.TAU, 1e-9), 'the other arc closes the ring');
check(sb.partition(sb.prepare({ name: 'empty', children: [] })).length === 0, 'an empty folder has no arcs');

// geometry, projection, hit testing round trip
for (const [w, h] of [[640, 460], [358, 300], [1200, 520]]) {
  const g = sb.geometry(w, h);
  check(g.cx + g.R <= w && g.cy - g.R * g.tilt >= 0 && g.cy + g.R * g.tilt + g.thick <= h + 1, `chart fits ${w}x${h}`);
  let ok = 0, n = 0;
  for (const a of arcs) {
    if (a.a1 - a.a0 < 0.01) continue;
    const mid = (a.a0 + a.a1) / 2, r = g.inner + (a.depth - 0.5) * g.ringW;
    const [x, y] = sb.project(g, r, mid);
    n++; if (sb.hitTest(g, arcs, x, y) === a) ok++;
  }
  check(n > 20 && ok === n, `hit test finds every arc from its projected middle at ${w}x${h} (${ok}/${n})`);
  check(sb.hitTest(g, arcs, g.cx, g.cy) === 'center', 'the middle is the center puck');
  check(sb.hitTest(g, arcs, 2, 2) === null, 'a corner hits nothing');
  const u = sb.unproject(g, ...sb.project(g, 100, 1.234));
  check(close(u.r, 100, 1e-6) && close(u.a, 1.234, 1e-9), 'unproject inverts project');
}

// colors
const c1 = sb.arcColor({ ...ring1[0] }), deep = arcs.find((a) => a.depth === 4 && a.kind !== 'other');
check(c1.every((v) => Number.isInteger(v) && v >= 0 && v <= 255), 'colors are rgb bytes');
const lum = ([r, g, b]) => 0.2126 * r + 0.7152 * g + 0.0722 * b;
const sameHue = { ...deep, depth: 1 };
check(lum(sb.arcColor(deep)) > lum(sb.arcColor(sameHue)), 'deeper rings are lighter at the same hue');
check(JSON.stringify(sb.hsl(0, 1, 0.5)) === '[255,0,0]' && JSON.stringify(sb.hsl(120, 1, 0.5)) === '[0,255,0]', 'hsl converts');

// easing ends
for (const [k, f] of Object.entries(sb.ease)) check(close(f(0), 0, 1e-9) && close(f(1), 1, 1e-9), `ease.${k} runs 0 to 1`);

// transitions
const g = sb.geometry(640, 460), innerU = g.inner / g.ringW;
const lib = sb.findNode(root, ['Home', 'Library']), libArcs = sb.partition(lib);
const starts = sb.transitionStarts(arcs, root.path, libArcs, innerU);
for (const a of libArcs) {
  const old = arcs.find((o) => o.key === a.key);
  if (old) { const s = starts.get(a.key); if (!(s.a0 === old.a0 && s.u0 === old.depth - 1)) { check(false, `zoom-in: ${a.key} starts where it was`); break; } }
}
check(libArcs.some((a) => !arcs.find((o) => o.key === a.key) && starts.get(a.key).alpha === 0), 'arcs new to the screen open out of an ancestor, faded');
const back = sb.transitionStarts(libArcs, lib.path, arcs, innerU);
const libArc = arcs.find((a) => a.key === sb.pathKey(lib.path));
check(back.get(libArc.key).u1 === 0 && back.get(libArc.key).a1 === sb.TAU, 'zoom-out: the old focus starts as the puck');
const tr = { kind: 'zoom', ms: 650, starts };
const end = sb.frameStates(libArcs, tr, 650), rest = sb.frameStates(libArcs, null, 0);
check(libArcs.every((a) => JSON.stringify(end.get(a.key)) === JSON.stringify(rest.get(a.key))), 'zoom ends exactly at rest');
check(sb.transitionDone(tr, 650) && !sb.transitionDone(tr, 300), 'zoom finishes on time');
const ent = { kind: 'entrance', ms: 560, staggerMs: 60, rings: 4, innerU };
const e0 = sb.frameStates(arcs, ent, 0), eEnd = sb.frameStates(arcs, ent, 560 + 3 * 60);
check(arcs.every((a) => e0.get(a.key).alpha === 0), 'entrance starts hidden');
check(arcs.every((a) => JSON.stringify(eEnd.get(a.key)) === JSON.stringify(sb.restState(a))), 'entrance ends at rest');
check(!sb.transitionDone(ent, 600) && sb.transitionDone(ent, 740), 'entrance waits for the last ring');

// walls: far-to-near order; covered outer walls and far-half walls are skipped
const items = arcs.map((arc) => ({ arc, s: sb.restState(arc), px: { r0: g.inner + (arc.depth - 1) * g.ringW, r1: g.inner + arc.depth * g.ringW }, z: 0 }));
const jobs = sb.wallJobs(g, items, null);
check(jobs.every((j, i) => i === 0 || jobs[i - 1].y <= j.y), 'walls are sorted far to near');
check(jobs.filter((j) => j.type === 'outer').every((j) => j.a0 >= Math.PI / 2 - 1e-9 && j.a1 <= 1.5 * Math.PI + 1e-9), 'outer walls only on the near half');
check(!jobs.some((j) => j.type === 'outer' && j.it.arc.depth === 1), 'ring 1 outer walls are covered by ring 2');
check(!jobs.some((j) => j.type === 'inner'), 'no inner walls while nothing is lifted');
const lifted = items.find((x) => x.arc.depth === 2 && x.s.a0 < 0.5);
lifted.z = 5;
const lj = sb.wallJobs(g, [lifted], lifted);
check(lj.some((j) => j.type === 'inner') || lifted.s.a0 > Math.PI / 2, 'a lifted arc on the far side shows its inner wall');

// drawScene runs against a recording context
const calls = [];
const rec = new Proxy({}, { get: (_, k) => (k === 'createLinearGradient' ? () => ({ addColorStop() {} }) : (...args) => calls.push(k)), set: () => true });
const drawn = sb.drawScene(rec, g, arcs, sb.frameStates(arcs, null, 0));
check(drawn === arcs.length && calls.includes('ellipse') && calls.includes('fill'), 'drawScene draws every arc');
check(sb.formatBytes(0) === '0 B' && sb.formatBytes(1536) === '1.5 KB' && sb.formatBytes(412e9) === '412 GB', 'formatBytes');

console.log(`${passes} passed, ${fails} failed`);
process.exit(fails ? 1 : 0);
