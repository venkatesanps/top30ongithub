---
name: sunburst-3d
description: Build a tilted, extruded 3D sunburst chart for hierarchical data (disk usage, folder sizes, budgets, bundle or cost breakdowns) - rings drawn as thick slabs seen from an angle, hue by position, hover to lift, click to drill in with children opening to the full circle, center puck to go back. Canvas 2D, no dependencies, with a folder scanner and a one-file export. Use when someone wants a "3D sunburst", a disk-analyzer style chart, or a drill-down radial chart that looks physical rather than flat.
---

# Tilted 3D sunburst

A sunburst laid flat and seen from above at an angle, so every ring is a slab with visible
walls. It reads as an object you can poke: hovering lifts a slice, clicking one zooms into it,
the dark puck in the middle takes you back up. Disk analyzers use it to show where space went.

The case this skill was built from is the hero chart on maczentra.com (a Mac disk analyzer).
It was studied in a browser: its behavior on load, hover and click, and its shipped (minified)
script, read for the technique (squashed-ellipse projection, which walls to draw and in what
order, how arcs move between levels). The code here was written fresh from those notes, with
its own defaults, shading, colors and sample data; none of that site's code, data, text or brand
is included. Touch, reduced motion and zoom-out on the original were not observed.

## Files

| File | What it is |
|---|---|
| `templates/sunburst3d.js` | The chart: an ES module, no dependencies. `Sunburst3D` component plus pure helpers. |
| `templates/sunburst3d-demo.html` | A working page with sample data, breadcrumb, Up button and a table view. |
| `scripts/dir_to_json.py` | Scans a folder into the chart's JSON tree (local only, standard library). |
| `scripts/build_standalone.py` | Inlines the module into a page to make one self-contained HTML file. |

## Quick start

1. Copy `sunburst3d.js` into the project (for example `src/lib/`).
2. Give it a sized container and data shaped as `{ name, size?, children? }` (sizes on leaves;
   folders are summed):

```html
<div id="chart" style="height: 480px"></div>
<script type="module">
  import { Sunburst3D, CSS } from './sunburst3d.js';
  document.head.insertAdjacentHTML('beforeend', `<style>${CSS}</style>`);
  const chart = new Sunburst3D(document.getElementById('chart'), data, {
    ariaLabel: 'Disk usage',
    onFocus: (node) => console.log('now showing', node.path.join(' / ')),
  });
</script>
```

API: `chart.focus(['Home', 'Library'])` drills by path, `chart.up()` goes back, `chart.setData(tree)`
replaces the data (with the entrance animation), `chart.destroy()` removes it and stops all work.

React: create it in an effect and destroy it on cleanup.

```tsx
"use client";
useEffect(() => {
  const chart = new Sunburst3D(ref.current!, data, { onFocus: setFocus });
  return () => chart.destroy();
}, [data]);
```

## Real data

```bash
python3 scripts/dir_to_json.py ~/Projects --depth 5 -o tree.json      # space on disk, 40 biggest per folder
python3 scripts/build_standalone.py templates/sunburst3d-demo.html my-disk.html --data tree.json
```

`dir_to_json.py` never follows symlinks or enters other volumes, merges entries under
`--min-size` (default 1 MB) into one "(N smaller items)" leaf, and reports unreadable folders
on stderr. The scan stays on the machine. Edit the demo's heading and caption for your data.

For other hierarchies (cost by service, budget lines, bundle modules), build the same
`{ name, size, children }` tree; pass `formatSize` for units that aren't bytes.

## Options

| Option | Default | Effect |
|---|---|---|
| `rings` | 4 | Levels shown below the focus. |
| `tilt` | 0.72 | Vertical squash of the circles; 1 is flat-on, lower tips it further back. |
| `thickness` | 0.06 | Slab height as a share of the radius. |
| `inner` | 0.22 | Puck radius as a share of the radius. |
| `minAngle` | 0.035 | Children thinner than this (radians) merge into one "smaller items" arc. |
| `hueStart` | 200 | Hue at 12 o'clock; the circle sweeps all 360 degrees from there. |
| `entranceMs` / `staggerMs` | 560 / 60 | Per-ring entrance and the delay between rings. |
| `zoomMs` | 650 | Drill in and out. Longer than a hover budget on purpose: it is a navigation. |
| `liftFrac` | 0.55 | Hover lift as a share of the slab height. |
| `formatSize`, `otherLabel`, `seam` | | Size text, merged-arc label, the seam color between faces. |

## How it is drawn (read before changing the renderer)

- **Projection.** Polar position (radius, angle clockwise from 12) maps to
  `x = cx + r·sin a`, `y = cy − r·cos a·tilt − z`. Every ring edge is a canvas `ellipse()` with
  radii `(r, r·tilt)`. `unproject` inverts it for hit testing, which uses the top faces.
- **Faces.** Each arc has a top face (an elliptical annular sector) and walls: the outer wall
  shows only on the near half (`π/2 < a < 3π/2`) and only where the next ring doesn't cover it;
  an end wall shows where a ring stops and it faces the viewer; inner walls appear only on a
  lifted arc. `wallJobs` decides this.
- **Order.** All visible walls far to near, then all top faces, then the puck, then lifted arcs
  with their own walls. Top faces never overlap, so this needs no per-pixel depth.
- **Shading.** Walls take the face color times a Lambert term with light from the viewer's upper
  left; curved walls get a horizontal gradient. Seams are a thin translucent stroke.
- **Color.** Each arc owns a slice of the hue circle inside its parent's slice, so a branch keeps
  one family of hues as you drill. Deeper rings get lighter and calmer; files are less saturated
  than folders; merged arcs are near-grey. Identity is never color alone: tooltip, center label
  and the table view name everything.
- **Input.** Mouse hovers to lift and clicks to open. Touch has no hover, so the first tap
  selects (lift, tooltip, center label) and a second tap on the same folder opens it.
- **Motion.** Entrance: each ring sweeps open from 12 o'clock (ease-out) and grows from the puck
  (ease-out-back), rings 60 ms apart. Drill: every arc on screen moves from where it was to where
  it ends (ease-in-out); arcs new to the screen open out of their parent; the old focus starts as
  the puck when zooming out. Hover lift eases with a 70 ms time constant.
- **Cost.** One canvas, redrawn only while something moves: the frame loop stops when the
  transition and the lift settle. `prefers-reduced-motion` skips the entrance and drill animation
  and snaps the lift. Device pixel ratio is capped at 2.

## Accessibility

The canvas is focusable with an `aria-label` that names the focus and its size; arrow keys walk
the first ring, Enter opens, Escape or Backspace goes up, and a polite live region announces
each move. A visually hidden table lists the focus's children with sizes and shares; the demo
also shows it behind "Show as a table". Text sits in HTML over the canvas, so it stays sharp and
selectable by assistive tech.

## Check your changes

```bash
node tests/sunburst_3d/test_sunburst.mjs     # layout, projection and hit testing, colors, transitions, walls
python3 tests/sunburst_3d/test_sunburst.py   # scanner, one-file build, and the Node tests
```

Then look at it: `tests/sunburst_3d/frames.html?scene=home|drill|entrance&t=300|zoom&t=325|lift`
renders fixed frames from `sample.json` when served next to the module. Check 3 and 9 o'clock
(end walls), the stepped outer edge, and a lifted arc on the far side.

Run the `motion-perf` checker on anything you add around it, and follow the
`motion-component-builder` skill for the page that hosts it.
