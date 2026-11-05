#!/usr/bin/env python3
"""Load a page in headless Chromium, run motion_probe.js, and capture a scroll strip.

  python3 probe_page.py https://example.com [--out ./motion] [--points 8] [--width 1440 --height 900]
  python3 probe_page.py rebuild/index.html --out ./motion-rebuild      # a local file works too

Writes <out>/probe.json, <out>/frame_NN.png at evenly spaced scroll positions, and
<out>/strip.png (needs Pillow) so the original and a rebuild can be compared side by side.
Needs Playwright with Chromium: pip install playwright && playwright install chromium.
Only for pages you're allowed to load; it scrolls and screenshots, nothing else.
"""
import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url")
    ap.add_argument("--out", default="./motion")
    ap.add_argument("--points", type=int, default=8)
    ap.add_argument("--width", type=int, default=1440)
    ap.add_argument("--height", type=int, default=900)
    ap.add_argument("--settle", type=int, default=450, help="ms to wait after each scroll")
    a = ap.parse_args(argv)
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        sys.exit("needs Playwright: pip install playwright && playwright install chromium")
    url = a.url if "://" in a.url else Path(a.url).resolve().as_uri()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    probe_js = (HERE / "motion_probe.js").read_text()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": a.width, "height": a.height}, device_scale_factor=1)
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(url, wait_until="networkidle", timeout=60000)
        page.wait_for_timeout(1500)
        probe = page.evaluate(probe_js)
        probe["pageErrors"] = errors[:20]
        (out / "probe.json").write_text(json.dumps(probe, indent=1))
        span = page.evaluate("document.documentElement.scrollHeight - innerHeight")
        frames = []
        for i in range(a.points):
            f = i / max(1, a.points - 1)
            page.evaluate(f"scrollTo(0, {int(span * f)})")
            page.wait_for_timeout(a.settle)
            path = out / f"frame_{i:02d}.png"
            page.screenshot(path=str(path))
            frames.append(path)
        browser.close()
    try:
        from PIL import Image
        ims = [Image.open(f) for f in frames]
        scale = 360 / ims[0].width
        ims = [im.resize((int(im.width * scale), int(im.height * scale))) for im in ims]
        cols = 4
        sheet = Image.new("RGB", (ims[0].width * cols, ims[0].height * ((len(ims) + cols - 1) // cols)), "white")
        for i, im in enumerate(ims):
            sheet.paste(im, ((i % cols) * ims[0].width, (i // cols) * ims[0].height))
        sheet.save(out / "strip.png")
    except ImportError:
        pass
    print(f"probe_page: {len(frames)} frames, probe.json -> {out}" + (f" ({len(errors)} page error(s))" if errors else ""))
    print(f"next: python3 {HERE / 'motion_report.py'} {out / 'probe.json'} --out {out / 'motion-report.md'}")


if __name__ == "__main__":
    main()
