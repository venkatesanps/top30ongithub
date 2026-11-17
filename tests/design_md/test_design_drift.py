"""Tests for design_drift.py: check, drift and draft on files written to a temp folder.

python3 tests/design_md/test_design_drift.py   (no dependencies, no network)
"""
import json
import subprocess
import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SCRIPT = ROOT / "plugins/top30-ui/skills/design-md/scripts/design_drift.py"
sys.path.insert(0, str(SCRIPT.parent))
import design_drift as dd  # noqa: E402

GOOD = """---
version: alpha
name: Quiet Ledger
description: Calm, ink on paper.
colors:
  primary: "#1a1c1c"
  on-primary: "#ffffff"
  canvas: "#f6f5f2"
  accent: "#3ecf8e"  # the one brand color
typography:
  body-md:
    fontFamily: Geist Sans
    fontSize: 16px
    fontWeight: 400
    lineHeight: 1.5
  label-sm:
    fontFamily: "Geist Mono"
    fontSize: 10px
rounded:
  sm: 0.5rem
  lg: 24px
  full: 9999px
spacing:
  unit: 8px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.on-primary}"
    typography: "{typography.label-sm}"
    rounded: "{rounded.full}"
omitted:
  - section: spacing
    reason: one unit only
---

# Quiet Ledger

## Overview
Ink on paper.

## Colors
## Typography
## Shapes
## Components
## Do's and Don'ts
"""

BAD = """---
version: alpha
colors:
  ink: "#777777"
  paper: "#888888"
shadows:
  soft: 0 1px 2px
components:
  chip:
    backgroundColor: "{colors.paper}"
    textColor: "{colors.ink}"
    rounded: "{rounded.md}"
  label:
    textColor: "{colors}"
---

## Components
## Colors
## Colors
"""

CODE = """export const A = () => (
  <a href="#fff" className="bg-[#1A1C1C] text-[#fff] border-[#3ecf8f] rounded-[24px] rounded-[13px] shadow-[0_1px_2px_rgba(0,0,0,.1)]"
     style={{ fontFamily: 'Inter, sans-serif', color: '#123456' }}>
    <span style={{ fontFamily: 'Geist Mono' }} />
    <span className="font-['Geist_Sans'] font-[system-ui]" />
  </a>
);
"""
CSS = """:root { --ink: #1a1c1c; --paper: #F6F5F2; --radius: 8px; }
.card { color: #1a1c1c; background: #f6f5f3; border-radius: 0.5rem; font-family: var(--font-sans); }
.x { font-family: "Comic Sans MS", cursive; border-radius: 3px; }
"""


def rules(findings):
    return Counter(f["rule"] for f in findings)


def main():
    with tempfile.TemporaryDirectory() as d:
        d = Path(d)
        (d / "GOOD.md").write_text(GOOD)
        (d / "BAD.md").write_text(BAD)
        (d / "PROSE.md").write_text("# Design\n\nNo tokens here.\n")
        src = d / "src"
        src.mkdir()
        (src / "A.tsx").write_text(CODE)
        (src / "a.css").write_text(CSS)
        (src / "node_modules").mkdir()
        (src / "node_modules" / "x.tsx").write_text(CODE)

        # the fallback parser reads the same tokens PyYAML would
        fm = GOOD.split("---\n")[1]
        simple = dd.parse_simple_yaml(fm)
        assert simple["colors"]["accent"] == "#3ecf8e", simple["colors"]
        assert simple["typography"]["label-sm"]["fontFamily"] == "Geist Mono"
        assert simple["typography"]["body-md"]["fontWeight"] == 400
        assert dd.parse_simple_yaml("rounded: { sm: 0.5rem, full: 9999px }") == {"rounded": {"sm": "0.5rem", "full": "9999px"}}
        assert simple["omitted"] == [{"section": "spacing", "reason": "one unit only"}], simple["omitted"]
        try:
            import yaml
            assert yaml.safe_load(fm) == simple
        except ImportError:
            pass

        f, tokens = dd.check(d / "GOOD.md")
        assert not f, f
        assert len(tokens["colors"]) == 4

        f, _ = dd.check(d / "BAD.md")
        r = rules(f)
        assert r["missing-name"] == 1, r
        assert r["unknown-key"] == 1, r
        assert r["broken-ref"] == 1, r  # {rounded.md}; a group reference inside components is allowed by the format
        assert r["missing-primary"] == 1, r
        assert r["contrast"] == 1, r
        assert r["section-order"] == 2, r  # Colors after Components, and Colors twice
        assert any(x["rule"] == "broken-ref" and x["found"] == "{rounded.md}" and x["line"] == 12 for x in f), f

        f, _ = dd.check(d / "PROSE.md")
        assert rules(f) == Counter({"no-front-matter": 1}), f

        # drift against the tokens
        f, n, source = dd.drift(d / "GOOD.md", [src])
        assert n == 2 and source == "DESIGN.md colors", (n, source)
        r = rules(f)
        hexes = sorted(x["found"] for x in f if x["rule"] == "hex-color")
        # #1A1C1C, #fff, #1a1c1c are tokens (case and 3-digit forms normalised); href="#fff" is skipped
        assert hexes == ["#123456", "#3ecf8f", "#f6f5f3"], hexes  # --paper: #F6F5F2 is the canvas token
        near = next(x for x in f if x["found"] == "#3ecf8f")
        assert "accent" in near["message"], near
        fonts = sorted(x["found"] for x in f if x["rule"] == "undeclared-font")
        assert fonts == ["comic sans ms", "inter"], fonts
        radii = sorted(x["found"] for x in f if x["rule"] == "radius-off-scale")
        assert radii == ["border-radius: 3px;", "rounded-[13px]"], radii
        assert r["arbitrary-shadow"] == 1, r
        assert all("node_modules" not in x["file"] for x in f)

        # no colors in DESIGN.md: CSS custom properties become the palette
        (d / "NOCOLORS.md").write_text("---\nname: X\n---\n")
        f, _, source = dd.drift(d / "NOCOLORS.md", [src])
        assert source == "CSS custom properties", source
        hexes = sorted(x["found"] for x in f if x["rule"] == "hex-color")
        assert "#1A1C1C" not in hexes and "#f6f5f3" in hexes and "#123456" in hexes, hexes

        # draft writes a block that check can read
        out = dd.draft([src])
        assert out.startswith("---\nversion: alpha") and '  ink: "#1a1c1c"' in out and '  paper: "#f6f5f2"' in out, out
        (d / "DRAFT.md").write_text(out)
        f, tokens = dd.check(d / "DRAFT.md")
        assert not [x for x in f if x["severity"] == "error"], f
        assert tokens["colors"]["ink"] == "#1a1c1c"

        # CLI
        r = subprocess.run([sys.executable, str(SCRIPT), "check", str(d / "GOOD.md"), "--fail-on", "warn"], capture_output=True, text=True)
        assert r.returncode == 0 and "0 error(s), 0 warning(s)" in r.stdout, r.stdout + r.stderr
        r = subprocess.run([sys.executable, str(SCRIPT), "check", str(d / "BAD.md"), "--fail-on", "error"], capture_output=True, text=True)
        assert r.returncode == 1, r.stdout
        js = d / "drift.json"
        r = subprocess.run([sys.executable, str(SCRIPT), "drift", str(d / "GOOD.md"), str(src), "--json", str(js)], capture_output=True, text=True)
        assert r.returncode == 0 and "palette from DESIGN.md colors" in r.stdout, r.stdout + r.stderr
        assert len(json.loads(js.read_text())) == len(dd.drift(d / "GOOD.md", [src])[0])
    print("design_drift tests passed")


if __name__ == "__main__":
    main()
