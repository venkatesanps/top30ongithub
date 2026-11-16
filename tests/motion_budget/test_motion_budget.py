"""Tests for motion_budget.py: spring physics and each lint rule, on files written to a temp folder.

python3 tests/motion_budget/test_motion_budget.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-ui/skills/motion-budget/scripts/motion_budget.py"
sys.path.insert(0, str(SCRIPT.parent))
import motion_budget as mb  # noqa: E402

BAD = """import { motion } from 'motion/react';
import { LineChart, Line, Bar } from 'recharts';
// duration: 9 in a comment is ignored
export const Bad = ({ items }) => (
  <div className="transition-all duration-500 ease-in">
    <motion.div animate={{ opacity: 1 }} transition={{ duration: 0.6 }} />
    <motion.div animate={{ y: 0 }} transition={{ duration: 1.2, ease: 'easeIn' }} />
    <motion.div animate={{ rotate: 360 }} transition={{ duration: 2, repeat: Infinity }} />
    <motion.div transition={{ type: 'spring', stiffness: 100, damping: 10 }} />
    <motion.div transition={{ type: 'spring' }} />
    <motion.div transition={{ type: 'spring', stiffness: 400, damping: 28 }} />
    <motion.div transition={{ type: 'spring', duration: 0.25, bounce: 0 }} />
    {items.map((x, i) => <motion.li key={x} transition={{ delay: i * 0.08 }} />)}
    {items.map((x, i) => <motion.li key={x} transition={{ delay: Math.min(i * 0.015, 0.05) }} />)}
    {items.map((x, i) => <motion.i key={x} animate={{ y: 4 }} transition={{ delay: i * 0.15, repeat: Infinity, duration: 1 }} />)}
    <motion.ul variants={{ show: { transition: { staggerChildren: 0.12 } } }} />
    <LineChart><Line dataKey="a" /><Bar dataKey="b" animationDuration={280} /></LineChart>
    <span className="animate-spin duration-1000" />
  </div>
);
"""
GOOD = """import { motion, useReducedMotion } from 'motion/react';
export const Good = () => { const r = useReducedMotion();
  return <motion.button className="duration-200" whileTap={{ scale: 0.96 }}
    transition={r ? { duration: 0.15 } : { type: 'spring', stiffness: 400, damping: 28 }} />; };
"""
CSS = """.a { transition: opacity 450ms ease-in; }
.b { transition: transform .2s cubic-bezier(0.16, 1, 0.3, 1); }
.c { animation: spin 2s linear infinite; }
.d { animation-duration: 1.5s; }
/* .e { transition: all 9s; } */
"""


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    t, z = mb.spring_settle(400, 28, 1)
    check(abs(t - 8 / 28) < 1e-9 and z < 1, "underdamped spring: settle = 8 * mass / damping (400/28 -> 286 ms)")
    t, z = mb.spring_settle(100, 10, 1)
    check(abs(t - 0.8) < 1e-9, "Motion's default spring (100/10) takes 0.8 s")
    t, z = mb.spring_settle(100, 40, 1)
    check(z > 1 and abs(t - 4 / ((40 - (1600 - 400) ** 0.5) / 2)) < 1e-9, "overdamped spring uses the slow pole, so more damping isn't always faster")
    check(mb.spring_settle(400, 28, 2)[0] > mb.spring_settle(400, 28, 1)[0], "more mass settles slower")
    check(mb.damping_for(0.3) == 27 and mb.spring_settle(400, mb.damping_for(0.3))[0] <= 0.3, "damping_for gives the smallest damping inside the budget")

    with tempfile.TemporaryDirectory() as tmp:
        d = Path(tmp)
        (d / "src").mkdir()
        (d / "node_modules/x").mkdir(parents=True)
        (d / "src/Bad.tsx").write_text(BAD)
        (d / "src/Good.tsx").write_text(GOOD)
        (d / "src/site.css").write_text(CSS)
        (d / "node_modules/x/Slow.tsx").write_text("const t = { duration: 5 };")
        fs, n, app = mb.lint([d])
        bad = [f for f in fs if f["file"].endswith("Bad.tsx")]
        got = {(f["rule"], f["line"]) for f in bad}
        check(n == 3, "node_modules is skipped")
        for want, msg in [(("duration-over", 6), "0.6 s tween over budget"), (("duration-over", 7), "1.2 s tween over budget"),
                          (("ease-in", 7), "easeIn flagged"), (("ease-in", 5), "Tailwind ease-in flagged"),
                          (("tailwind-duration", 5), "duration-500 flagged"), (("spring-settle", 9), "slow spring flagged from its physics"),
                          (("spring-default", 10), "bare spring flagged"), (("stagger-uncapped", 13), "uncapped stagger flagged"),
                          (("stagger-slow", 16), "staggerChildren 0.12 noted"), (("recharts-default", 17), "Recharts series without animationDuration")]:
            check(want in got, msg)
        check(sum(1 for f in bad if f["rule"] == "duration-over") == 2, "the infinite rotate loop and the comment are not flagged")
        check(not any(f["line"] in (11, 12, 14, 15) for f in bad), "400/28 spring, duration-style spring, capped stagger and a loader's loop offsets pass")
        check(sum(1 for f in bad if f["rule"] == "recharts-default") == 1, "the Bar with animationDuration passes")
        check(not any(f["line"] == 18 for f in bad), "animate-spin with duration-1000 is a loop, not a transition")
        check(next(f for f in bad if (f["rule"], f["line"]) == ("duration-over", 7))["severity"] == "error", "1 s or more is an error")
        check(not any(f["file"].endswith("Good.tsx") for f in fs), "the good component is clean")
        css = {(f["rule"], f["line"]) for f in fs if f["file"].endswith(".css")}
        check(css == {("css-duration", 1), ("ease-in", 1), ("css-duration", 4)}, f"CSS: 450 ms and 1.5 s flagged; 200 ms, infinite and commented rules pass ({sorted(css)})")
        check(any(f["rule"] == "no-reduced-motion" and f["file"].endswith("Bad.tsx") for f in fs), "no reduced-motion handling noted")
        (d / "src/App.tsx").write_text("export const App = () => <MotionConfig reducedMotion=\"user\"><Bad /></MotionConfig>;")
        fs2, _, app2 = mb.lint([d])
        check(app2 and not any(f["rule"] == "no-reduced-motion" for f in fs2), "an app-wide MotionConfig satisfies reduced motion for every file")
        fs3, _, _ = mb.lint([d / "src/Bad.tsx"], budget_ms=700)
        check(not any(f["line"] == 6 for f in fs3) and any(f["line"] == 7 for f in fs3), "--budget-ms changes the line")

        def run(*args):
            return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True, timeout=60)

        r = run("lint", d / "src", "--json", d / "out.json")
        check(r.returncode == 0 and "spring-settle" in r.stdout and json.loads((d / "out.json").read_text()), "CLI prints a summary and writes JSON")
        check(run("lint", d / "src", "--fail-on", "error").returncode == 1 and run("lint", d / "src/Good.tsx", "--fail-on", "warn").returncode == 0, "--fail-on exit codes")
        r = run("spring", "--stiffness", "100", "--damping", "10")
        check(r.returncode == 1 and "800 ms" in r.stdout and "damping 27 or more" in r.stdout, "spring calculator explains a slow spring")
        check(run("spring", "--stiffness", "400", "--damping", "28").returncode == 0, "spring calculator passes 400/28")
        r = run("spring", "--stiffness", "170", "--damping", "26", "--mass", "0.9")
        check(r.returncode == 1 and "raise stiffness to about 188" in r.stdout, "an overdamped spring is told to add stiffness, not damping")
        check(mb.spring_settle(188, 26, 0.9)[0] <= 0.3, "and that advice lands inside the budget")

    tpl = (ROOT / "plugins/top30-ui/skills/motion-component-builder/templates/use-feedback.ts").read_text()
    check("navigator.vibrate" in tpl and "prefers-reduced-motion" in tpl and "sound = false" in tpl, "feedback hook template: vibration, reduced motion respected, sound off by default")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
