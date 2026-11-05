"""Checks motion_report.py against probe results: the real one from zeromark.io and three synthetic sites.
Also runs the scroll-scene engine tests (test_scene.mjs) when Node is installed.

python3 tests/motion_forensics/test_motion_report.py   (no dependencies, no network)
"""
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-ui/skills/motion-forensics/scripts/motion_report.py"
FIX = HERE / "fixtures"


def run(fixture, tmp):
    out, js = Path(tmp) / f"{fixture}.md", Path(tmp) / f"{fixture}.json"
    r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(FIX / f"{fixture}.json"), "--out", str(out), "--json", str(js)],
                       capture_output=True, text=True, timeout=60)
    return r, (out.read_text() if out.exists() else ""), (json.loads(js.read_text()) if js.exists() else {})


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        r, md, s = run("zeromark", tmp)
        check(r.returncode == 0, "report runs on the ZeroMark probe")
        check(s.get("architectures", [None])[0] == "procedural-canvas", "ZeroMark: motion is procedural Canvas 2D first")
        check("timeline-library" not in s["architectures"] and "webgl" not in s["architectures"], "ZeroMark: no library, no WebGL")
        for t in ("scroll-driven", "ambient", "layout-anchored", "seeded-procedural", "lazy", "class-gated", "reduced-motion-aware", "hidpi"):
            check(t in s["traits"], f"ZeroMark trait: {t}")
        check(s["stagger"].get("zm-rise", {}).get("step") == 120, "stagger beat read from per-element delays (median 120 ms)")
        check("real easing is set per step inside the @keyframes" in md, "flags that running animations report linear")
        check("overshoots past 1" in md, "spots the overshooting cubic-bezier")
        check("none (hand-written)" in md and "Don't copy the site's script" in md, "says it's hand-written and to write your own code")

        r, md, s = run("gsap_lenis", tmp)
        check(set(s["architectures"]) >= {"timeline-library", "smooth-scroll"}, "GSAP + Lenis + Webflow site: library and smooth scroll")
        check("minified" in s["traits"] and "procedural-canvas" not in s["architectures"], "minified bundle noted; no canvas claimed")

        r, md, s = run("css_scroll", tmp)
        check(s["architectures"][:1] == ["css-scroll-driven"], "CSS-only site: scroll-driven CSS animations")
        check("@supports (animation-timeline: view())" in md, "recommends a fallback for browsers without scroll timelines")

        r, md, s = run("webgl_video_lottie", tmp)
        check(set(s["architectures"]) >= {"webgl", "video", "vector-animation"}, "WebGL + video + Lottie detected")
        check("procedural-canvas" not in s["architectures"], "a WebGL canvas isn't mistaken for Canvas 2D")
        check("someone's artwork" in md, "Lottie files flagged as artwork you can't just reuse")

        bad = Path(tmp) / "bad.json"
        bad.write_text(json.dumps({"hello": 1}))
        r = subprocess.run([sys.executable, "-I", str(SCRIPT), str(bad)], capture_output=True, text=True, timeout=60)
        check(r.returncode != 0 and "not a motion_probe" in r.stderr, "rejects JSON that isn't a probe result")

    node = shutil.which("node")
    if node:
        r = subprocess.run([node, str(HERE / "test_scene.mjs")], capture_output=True, text=True, timeout=120)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[-300:])
        check(r.returncode == 0, "scroll-scene engine tests pass in Node")
    else:
        print("SKIP scroll-scene engine tests (node not installed)")

    probe = (ROOT / "plugins/top30-ui/skills/motion-forensics/scripts/motion_probe.js").read_text()
    check("getContext(" not in probe.split("*/", 1)[1], "the probe never calls getContext (it would break the page's canvases)")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
