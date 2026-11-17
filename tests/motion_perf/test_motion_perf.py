"""Tests for motion_perf.py: each rule fires on a bad example and stays quiet on its fix.

python3 tests/motion_perf/test_motion_perf.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-ui/skills/motion-perf/scripts/motion_perf.py"
sys.path.insert(0, str(SCRIPT.parent))
import motion_perf as mp  # noqa: E402

BAD = """import { motion, useSpring, useTransform } from 'motion/react';
import gsap from 'gsap';
// animate={{ width: 100 }} in a comment is ignored
const panel = { open: { width: '97%' }, closed: { width: 48 } };
export function Bad({ items, el }) {
  const w = useSpring(useTransform(x, [0, 1], [40, 80]));
  window.addEventListener('scroll', () => { el.style.transform = `translateY(${window.scrollY}px)`; });
  function tick() { el.style.opacity = '1'; requestAnimationFrame(tick); }
  requestAnimationFrame(tick);
  items.forEach((n) => { const h = n.offsetHeight; n.style.height = h + 10 + 'px'; });
  return (
    <div className="transition-all hover:blur-xl will-change-transform">
      <motion.div animate={{ left: 120, width: 300 }} />
      <motion.div animate={{ left: ['-5%', '75%'] }} transition={{ duration: 4, repeat: Infinity }} />
      <motion.div variants={panel} />
      <motion.div style={{ width: w, willChange: 'transform' }} />
      <motion.div exit={{ filter: 'blur(12px)' }} />
      <div className="transition-[height,opacity]" style={{ transition: 'width 0.3s ease' }} />
    </div>
  );
}
"""

GOOD = """import { motion, useScroll, useTransform } from 'motion/react';
type Props = { willChange: any; open: boolean };
export function Good({ open, el, items }: Props) {
  const { scrollYProgress } = useScroll();
  const y = useTransform(scrollYProgress, [0, 1], [0, -40]);
  let id = 0;
  function tick(t) { el.style.transform = `scale(${t})`; if (t < 1) requestAnimationFrame(tick); }
  id = requestAnimationFrame(() => { const r = el.getBoundingClientRect(); el.style.transform = `translateX(${r.width}px)`; });
  const heights = items.map((n) => n.offsetHeight);
  return (
    <div className="transition-[transform,opacity] hover:blur-sm">
      <motion.div animate={{ height: open ? 'auto' : 0, opacity: 1 }} />
      <motion.div layout initial={{ width: '4rem' }} animate={{ width: open ? '20rem' : '4rem' }} />
      <motion.div animate={{ x: 120, scaleX: 2 }} />
      <motion.div style={{ y }} exit={{ filter: 'blur(6px)' }} />
      <motion.section initial={{ height: 0 }} animate={{ height: "auto" }} exit={{ height: 0, opacity: 0 }} />
      <motion.div variants={{ open: { height: "auto" }, closed: { height: 0 } }} animate={open ? "open" : "closed"} />
      <motion.div animate={{ width: open ? 320 : 64 }} transition={{ duration: 0.2 }} layout />
      <motion.div animate={{ x: open > 0 ? 8 : 0 }} layout="position" initial={{ width: 0 }} />
    </div>
  );
}
"""

BAD_CSS = """.panel { transition: width 200ms ease-out; will-change: transform; }
.fade { transition: all 150ms; }
@keyframes grow { from { height: 0; } to { height: 200px; } }
.card:hover { filter: blur(16px); }
.btn { @apply transition-all; }
"""

GOOD_CSS = """.panel { transition: transform 200ms ease-out, opacity 150ms; }
.card:hover { will-change: transform; filter: blur(6px); }
@keyframes rise { from { transform: translateY(8px); opacity: 0; } to { transform: none; opacity: 1; } }
.backdrop { backdrop-filter: blur(24px); }
"""


def run(files):
    with tempfile.TemporaryDirectory() as d:
        for name, text in files.items():
            (Path(d) / name).write_text(text)
        findings, n = mp.lint([d])
        return findings, n


def rules(findings, name):
    return Counter(f["rule"] for f in findings if f["file"].endswith(name))


def main():
    findings, n = run({"Bad.tsx": BAD, "Good.tsx": GOOD, "bad.css": BAD_CSS, "good.css": GOOD_CSS})
    assert n == 4, n
    bad, good = rules(findings, "Bad.tsx"), rules(findings, "Good.tsx")
    assert not good, f"good tsx should be clean, got {good}: {[f for f in findings if f['file'].endswith('Good.tsx')]}"
    # left + width, the looping left, two variant widths, the motion value width, transition-[height], inline width transition
    assert bad["layout-animation"] == 8, bad
    assert bad["transition-all"] == 1, bad
    assert bad["blur-large"] == 2, bad  # hover:blur-xl and the 12px exit
    assert bad["scroll-handler"] == 1, bad
    assert bad["raf-loop"] == 1, bad
    assert bad["layout-thrash"] == 1, bad
    assert bad["will-change"] == 2, bad
    assert bad["mixed-systems"] == 1, bad
    loops = [f for f in findings if f["rule"] == "layout-animation" and "loops" in f["message"]]
    assert len(loops) == 1 and loops[0]["line"] == 14, loops
    comment = [f for f in findings if f["file"].endswith("Bad.tsx") and f["line"] == 3]
    assert not comment, comment

    bc, gc = rules(findings, "bad.css"), rules(findings, "good.css")
    assert not gc, f"good css should be clean, got {gc}"
    assert bc == Counter({"layout-animation": 2, "transition-all": 2, "blur-large": 1, "will-change": 1}), bc

    sev = {f["severity"] for f in findings}
    assert sev <= {"warn", "info"}, sev  # nothing is an error: these are patterns

    # raf with a cancel is fine even without a condition
    f2, _ = run({"Loop.ts": "let id; function loop(){ id = requestAnimationFrame(loop) } loop(); export const stop = () => cancelAnimationFrame(id);"})
    assert not f2, f2

    # CLI: exit codes and JSON
    with tempfile.TemporaryDirectory() as d:
        (Path(d) / "Bad.tsx").write_text(BAD)
        (Path(d) / "node_modules").mkdir()
        (Path(d) / "node_modules" / "x.tsx").write_text(BAD)
        out = Path(d) / "out.json"
        r = subprocess.run([sys.executable, str(SCRIPT), "lint", d, "--json", str(out)], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert "warning(s) in 1 file(s)" in r.stdout, r.stdout
        data = json.loads(out.read_text())
        assert all("node_modules" not in f["file"] for f in data)
        r = subprocess.run([sys.executable, str(SCRIPT), "lint", d, "--fail-on", "warn"], capture_output=True, text=True)
        assert r.returncode == 1
        (Path(d) / "Bad.tsx").write_text(GOOD)
        r = subprocess.run([sys.executable, str(SCRIPT), "lint", d, "--fail-on", "warn"], capture_output=True, text=True)
        assert r.returncode == 0, r.stdout
    print("motion_perf tests passed")


if __name__ == "__main__":
    main()
