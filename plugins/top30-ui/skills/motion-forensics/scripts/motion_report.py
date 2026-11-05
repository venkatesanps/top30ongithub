#!/usr/bin/env python3
"""Read a motion_probe.js result and say how the page's motion is built, why copying it fails,
and how to rebuild it.

  python3 motion_report.py probe.json [--out motion-report.md] [--json motion-report.json]

Standard library only. The probe JSON comes from running scripts/motion_probe.js in the page.
"""
import argparse
import json
import sys
from pathlib import Path

ARCH = {
    "procedural-canvas": (
        "Procedural Canvas 2D",
        "The motion is drawn by code into a <canvas> every frame. There are no elements to inspect: DevTools, "
        "component copiers and screenshot-to-code tools see one empty canvas, and a screen recording shows the "
        "output of math, not the math.",
        "Rebuild the scene as a pure function of progress (and time, for ambient motion): render(p, t). Use "
        "templates/scroll-scene.js: seeded random layout, per-item stagger, eased phases, a frame loop only "
        "while something on screen is alive."),
    "webgl": (
        "WebGL / shaders",
        "The look comes from GPU shaders (or a 3D scene). The visuals live in GLSL and textures, often minified "
        "into a bundle; pixels can't be read back reliably, so recordings are the only evidence.",
        "Identify the effect family (noise field, particles, displacement, raymarch, 3D model) and rebuild it "
        "with a small shader or Three.js scene of your own. Keep a Canvas 2D or CSS fallback."),
    "timeline-library": (
        "Animation library timelines",
        "Durations, easings and stagger are set in library calls (GSAP, Motion, anime.js, Framer, Webflow "
        "interactions) inside a bundle, often tied to ScrollTrigger-style scroll positions. The CSS you can "
        "inspect is only the start or end state.",
        "Read the timeline (search the bundle for to(/from(/timeline(/scrollTrigger), or record the element "
        "transforms per scroll step, then express it with the same library or with CSS + Element.animate."),
    "smooth-scroll": (
        "Smooth-scroll layer",
        "Wheel and touch are intercepted (Lenis, Locomotive, custom) and scroll is interpolated, so everything "
        "keyed to scroll lags and eases. Without that layer a rebuild feels stiff even when every number matches.",
        "Decide deliberately: add a small damped follower on the progress value (not on native scroll) if the "
        "feel needs it, and keep native scrolling, keyboard and find-in-page working."),
    "css-keyframes": (
        "CSS keyframes and transitions",
        "This part is copyable, but the easing usually sits inside the @keyframes steps (the running animation "
        "reports 'linear'), and the stagger is in per-element delays, so reading one element gets the timing wrong.",
        "Copy the pattern, not the values blindly: one keyframe, one easing curve, delays on a fixed step. "
        "Gate it behind a class set in <head> so there's no flash, and switch it off under reduced motion."),
    "css-scroll-driven": (
        "CSS scroll-driven animations",
        "animation-timeline: view()/scroll() ties CSS animations to scroll position with no JavaScript. Tools "
        "that only read time-based animations miss it, and browsers without support show the end state.",
        "Reuse the CSS with @supports (animation-timeline: view()) and give older browsers a static or "
        "IntersectionObserver-triggered version."),
    "vector-animation": (
        "Lottie / Rive files",
        "The motion is an exported animation file (JSON or .riv) played by a runtime. The page just hosts it.",
        "The file itself is someone's artwork: don't reuse it without permission. Recreate the idea in your "
        "own Lottie/Rive file, or in CSS/canvas."),
    "video": (
        "Video",
        "What looks like interface motion is a video. There's nothing to reverse engineer in code.",
        "Design the motion yourself (or record your own product), or rebuild the shown interaction live."),
    "waapi": (
        "Element.animate (Web Animations API)",
        "Short programmatic animations created from JavaScript at runtime; they exist only while running.",
        "Trigger the interaction while recording document.getAnimations(), or read the .animate([...]) calls."),
}


def has(d, *path, default=0):
    for p in path:
        d = d.get(p, {}) if isinstance(d, dict) else {}
    return d if d not in ({}, None) else default


def classify(pr):
    code, css, beh, libs, media = pr.get("code", {}), pr.get("css", {}), pr.get("behaviour", {}), pr.get("libraries", {}), pr.get("media", {})
    globs = set(libs.get("globals", [])) | set(libs.get("fromScriptUrls", []))
    dom = libs.get("domHints", {})
    vw, vh = (pr.get("viewport") or [1440, 900])[:2]
    big = [c for c in media.get("canvases", []) if c.get("cssW", 0) * c.get("cssH", 0) >= 0.15 * vw * vh and not c.get("hidden")]
    archs, evidence = [], {}

    def add(key, why):
        if key not in archs:
            archs.append(key)
        evidence.setdefault(key, []).append(why)

    webgl_libs = globs & {"THREE", "three", "PIXI", "pixi", "Spline", "spline"}
    if code.get("webgl") or code.get("shaders") or webgl_libs or dom.get("spline") or dom.get("modelViewer"):
        add("webgl", f"WebGL contexts in code: {code.get('webgl', 0)}, shader source: {code.get('shaders', 0)}"
            + (f", libraries: {', '.join(sorted(webgl_libs))}" if webgl_libs else ""))
    if big and code.get("ctx2d") and code.get("raf"):
        add("procedural-canvas", f"{len(big)} large canvas(es) ({', '.join(c['el'] for c in big[:4])}); "
            f"2D contexts in code: {code['ctx2d']}; requestAnimationFrame calls: {code['raf']}")
    elif big and not archs:
        add("procedural-canvas", f"{len(big)} large canvas(es) drawn by code the probe couldn't read")
    tl = globs & {"gsap", "ScrollTrigger", "TweenMax", "anime", "Motion", "motion", "framer", "Webflow", "webflow", "Barba", "barba", "Swup"}
    if tl or dom.get("framer") or dom.get("webflow"):
        add("timeline-library", "Libraries: " + ", ".join(sorted(tl | {k for k in ("framer", "webflow") if dom.get(k)})))
    ss = globs & {"Lenis", "lenis", "LocomotiveScroll"}
    if ss or code.get("wheelOrTouchHijack"):
        add("smooth-scroll", "Smooth scroll: " + (", ".join(sorted(ss)) if ss else f"{code['wheelOrTouchHijack']} non-passive wheel/touch handler(s)"))
    if css.get("scrollDriven") and any(a.get("timeline") in ("ScrollTimeline", "ViewTimeline") for a in pr.get("cssAnimations", [])):
        add("css-scroll-driven", f"{css['scrollDriven']} scroll-timeline rule(s), running on a scroll timeline")
    if pr.get("cssAnimations") or css.get("keyframes"):
        add("css-keyframes", f"{len(css.get('keyframes', []))} @keyframes, {len(pr.get('cssAnimations', []))} running")
    if globs & {"lottie", "bodymovin", "rive"} or dom.get("lottie") or dom.get("rive"):
        add("vector-animation", "Lottie/Rive runtime or player element found")
    vids = [v for v in media.get("videos", []) if v.get("autoplay") and v.get("cssW", 0) >= 0.3 * vw]
    if vids:
        add("video", f"{len(vids)} large autoplaying video(s)")
    if code.get("waapi"):
        add("waapi", f"{code['waapi']} Element.animate call(s)")

    traits = []
    if beh.get("canvasesChangeWithScroll") or beh.get("inlineStylesChangeWithScroll") or code.get("scrollYMath"):
        traits.append(("scroll-driven", "State is a function of scroll position: scrolling back rewinds it. Timing it with a stopwatch "
                       "measures how fast you scrolled, not the animation."))
    if beh.get("canvasesChangeOverTime") or beh.get("inlineStylesChangeOverTime"):
        traits.append(("ambient", "Something keeps moving with no input: a time-based loop runs alongside (or instead of) scroll."))
    if code.get("layoutAnchors"):
        traits.append(("layout-anchored", "Phase boundaries are measured from where page elements sit (getBoundingClientRect / "
                       "data-phase markers), so they move with viewport size and text wrapping. Constants measured at one "
                       "screen size won't hold at another."))
    if code.get("seededRandom"):
        traits.append(("seeded-procedural", "Layouts come from a seeded random generator: the same 'random' scatter every visit. "
                       "There are no assets to copy; the scatter is an algorithm and a seed."))
    if code.get("intersectionObserver"):
        traits.append(("lazy", "Scenes start and stop with IntersectionObserver: off screen, hidden tabs and headless "
                       "crawlers see blank or frozen canvases."))
    if "motion" in pr.get("htmlClass", "") or "js" in pr.get("htmlClass", "").split():
        traits.append(("class-gated", f"Motion is switched on by a class on <html> ('{pr.get('htmlClass', '').strip()}'), "
                       "set before first paint. Without the script, or with JavaScript off, nothing animates."))
    if code.get("reducedMotion") or css.get("reducedMotion"):
        traits.append(("reduced-motion-aware", "It honours prefers-reduced-motion: a probe run with that setting on sees a still page."))
    if code.get("devicePixelRatio"):
        traits.append(("hidpi", "Canvas backing stores are scaled by devicePixelRatio: rebuilds that skip this look soft on retina screens."))
    if any(f.get("minified") for f in code.get("files", [])):
        traits.append(("minified", "Scripts are minified: read behaviour from recordings and the probe, not from variable names."))
    return archs, evidence, traits


def stagger_step(anims):
    by = {}
    for a in anims:
        if a.get("iterations") == 1 and a.get("name"):
            by.setdefault(a["name"], []).append(a.get("delay") or 0)
    out = {}
    for name, ds in by.items():
        ds = sorted(set(ds))
        if len(ds) >= 3:
            diffs = sorted(b - a for a, b in zip(ds, ds[1:]))
            out[name] = {"delays": ds, "step": diffs[len(diffs) // 2]}  # median: one odd gap shouldn't set the beat
    return out


def report(pr):
    archs, ev, traits = classify(pr)
    code, css = pr.get("code", {}), pr.get("css", {})
    anims = pr.get("cssAnimations", [])
    st = stagger_step(anims)
    md = [f"# Motion report: {pr.get('url', '?')}", "",
          f"Probed at {pr.get('viewport', ['?', '?'])[0]}x{pr.get('viewport', ['?', '?'])[1]}, DPR {pr.get('dpr', '?')}"
          + (" (tab was hidden: timings may be throttled)" if pr.get("hidden") else "") + ".", ""]
    if not archs:
        md += ["No motion system detected. If the page clearly moves, re-run the probe after scrolling to the moving part, "
               "with the tab visible and reduced motion off.", ""]
    else:
        md += ["## How the motion is built", ""]
        for k in archs:
            title, why, how = ARCH[k]
            md += [f"### {title}", "", f"*Evidence:* {'; '.join(ev[k])}.", "", f"**Why copying fails:** {why}", "", f"**Rebuild:** {how}", ""]
    if traits:
        md += ["## What makes it hard to reproduce", ""] + [f"- **{k}**: {v}" for k, v in traits] + [""]
    libs_found = (pr.get("libraries", {}).get("globals") or []) + (pr.get("libraries", {}).get("fromScriptUrls") or [])
    md += ["## Numbers to reuse", ""]
    files = code.get("files", [])
    if files:
        md.append("- Motion code: " + ", ".join(f"`{f['src']}` ({f['bytes'] // 1024} KB, {f['lines']} lines{', minified' if f.get('minified') else ''})" for f in files))
    md.append("- Libraries: " + (", ".join(libs_found) if libs_found else "none (hand-written)"))
    if css.get("cubicBeziers"):
        md.append("- Easing curves in CSS: " + ", ".join(f"`{c}`" for c in css["cubicBeziers"][:8])
                  + (" (one overshoots past 1: a spring-like pop)" if any(_overshoot(c) for c in css["cubicBeziers"]) else ""))
    if anims:
        durs = sorted({a["duration"] for a in anims if isinstance(a.get("duration"), (int, float))})
        md.append(f"- CSS animation durations (ms): {', '.join(str(int(d)) for d in durs[:10])}")
        if all((a.get("easing") or "linear") == "linear" for a in anims):
            md.append("- Every running animation reports `linear`: the real easing is set per step inside the @keyframes rules. Read those.")
    for name, s in st.items():
        md.append(f"- `{name}` is staggered: delays {', '.join(str(int(d)) for d in s['delays'])} ms (step about {int(s['step'])} ms).")
    md += ["", "## Plan", ""]
    plan = ["Write a motion spec: for each scene, what drives it (scroll range, time, pointer), its phases, and what each element does in each phase."]
    if "procedural-canvas" in archs or "webgl" in archs:
        plan.append("Sample the original: scroll in 20 even steps and screenshot each (and a 2-second clip at rest) so phases can be compared side by side with the rebuild.")
        plan.append("Rebuild with templates/scroll-scene.js: render(progress, time) pure and deterministic, seeded layout, phases anchored to your own copy (data-phase), a frame loop only while a live scene is on screen.")
    if "timeline-library" in archs:
        plan.append("Extract each timeline (targets, from/to, duration, ease, stagger, scroll start/end) into the spec before writing code.")
    if "css-keyframes" in archs:
        plan.append("Reuse the keyframe pattern with your own values, gated by a class set in <head>, with a reduced-motion override.")
    plan += ["Match feel, not code: compare the 20-step strip of the original with the rebuild, adjust easing and stagger until phases line up.",
             "Ship the fallbacks the original has: reduced motion, no-JavaScript copy, DPR-correct canvases, pause when off screen.",
             "Write your own code and visuals. Don't copy the site's script, artwork, copy text or brand; borrow ideas and timing only."]
    md += [f"{i}. {p}" for i, p in enumerate(plan, 1)]
    return "\n".join(md) + "\n", {"architectures": archs, "evidence": ev, "traits": [k for k, _ in traits], "stagger": st}


def _overshoot(c):
    try:
        n = [float(x) for x in c[c.index("(") + 1:c.index(")")].split(",")]
        return n[1] > 1 or n[3] > 1 or n[1] < 0 or n[3] < 0
    except (ValueError, IndexError):
        return False


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("probe")
    ap.add_argument("--out", default="motion-report.md")
    ap.add_argument("--json")
    a = ap.parse_args(argv)
    try:
        pr = json.loads(Path(a.probe).read_text())
    except (OSError, ValueError) as e:
        sys.exit(f"can't read probe JSON: {e}")
    if pr.get("probe", "").split("/")[0] != "motion_probe":
        sys.exit("not a motion_probe.js result")
    md, summary = report(pr)
    Path(a.out).write_text(md)
    if a.json:
        Path(a.json).write_text(json.dumps(summary, indent=1) + "\n")
    print(f"motion_report: {', '.join(summary['architectures']) or 'nothing detected'} -> {a.out}")


if __name__ == "__main__":
    main()
