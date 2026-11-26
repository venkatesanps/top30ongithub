"""Checks figkit (the explainer-figures skill): every primitive renders, output is
byte-deterministic, the linter catches the layout mistakes it promises to, the SVG lint catches
unsafe or inaccessible SVGs, the examples and the Snowflake guide figures are up to date, and the
SKILL.md lints clean.

python3 tests/explainer_figures/test_figkit.py   (no dependencies; PNG checks skip without rsvg-convert)
"""
import shutil
import subprocess
import sys
import tempfile
import xml.dom.minidom
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SK = ROOT / "plugins/top30-learn/skills/explainer-figures"
K = SK / "scripts/figkit.py"
sys.path.insert(0, str(K.parent))
import figkit  # noqa: E402
from figkit import Figure  # noqa: E402

GUIDE = ROOT / "guide/snowflake-de-architecture/figures"
EXAMPLES = {"snowflake-caches": GUIDE / "snowflake-caches.svg", "copy-load-metadata": GUIDE / "copy-load-metadata.svg"}


def run(*args, cwd=None):
    return subprocess.run([sys.executable, str(K), *map(str, args)], capture_output=True, text=True, cwd=cwd)


def errors(f):
    return [m for lvl, m in f.lint() if lvl == "error"]


def main():
    fails = []

    def check(cond, msg):
        if not cond:
            fails.append(msg)

    # every primitive renders to well-formed, accessible, deterministic SVG
    demo = figkit.demo()
    svg = demo.svg()
    check(not errors(demo), f"demo lints clean: {errors(demo)}")
    try:
        xml.dom.minidom.parseString(svg)
    except Exception as e:  # noqa: BLE001
        fails.append(f"demo SVG is not well-formed XML: {e}")
    check(svg == figkit.demo().svg(), "same figure, same bytes")
    for part in ('role="img"', "aria-label=", "<title>Every primitive, once</title>", 'viewBox="0 0 960 560"',
                 "source: figkit.py demo", "<circle", "marker-end"):
        check(part in svg, f"demo SVG has {part}")
    check(figkit.lint_svg(svg) == [], f"figkit's own output passes the SVG lint: {figkit.lint_svg(svg)}")

    # the linter catches what it promises
    def fig(**kw):
        return Figure("A title", "A subtitle", kicker="k", source=kw.pop("source", "test"), **kw)

    f = fig(source="")
    check(any("source is empty" in m for m in errors(f)), "missing source is an error")
    f = fig()
    f.box(40, 150, 100, 50, "a label far too long for this box")
    check(any("too wide" in m for m in errors(f)), "text that won't fit is an error")
    f = fig()
    f.box(40, 150, 200, 60, "one", id="a")
    f.box(150, 170, 200, 60, "two", id="b")
    check(any("boxes overlap" in m for m in errors(f)), "overlapping boxes are an error")
    f = fig()
    f.box(40, 150, 200, 60, "outer", id="a")
    f.text(220, 180, "sticks out of the box", 13)
    check(any("crosses the edge" in m for m in errors(f)), "text across a box edge is an error")
    f = fig()
    f.text(40, 200, "tiny", 9)
    check(any("below 12" in m for m in errors(f)), "font under 12px is an error")
    f = fig()
    f.box(900, 150, 120, 60, "edge")
    check(any("off the canvas" in m for m in errors(f)), "off-canvas marks are an error")
    f = fig(height=300)
    f.box(40, 240, 200, 50, "low")
    check(any("footer" in m for m in errors(f)), "content under the footer is an error")
    f = fig()
    f.box(40, 60, 200, 50, "high")
    check(any("header" in m for m in errors(f)), "content in the header is an error")
    f = fig()
    for i, t in enumerate(["blue", "orange", "teal", "purple"]):
        f.box(40 + i * 220, 150, 180, 60, t, tn=t)
    check(any("accent colours" in m for lvl, m in f.lint() if lvl == "warning"), "four accents warn")
    f = Figure("x" * 80, source="s")
    check(any("title is" in m for m in errors(f)), "long titles are an error")
    try:
        fig().box(40, 150, 100, 60, "x", tn="pink")
        fails.append("unknown tone accepted")
    except ValueError:
        pass
    f = fig()
    f.text(40, 200, '<script>alert(1)</script> & "q"', 13)
    check("<script>" not in f.svg() and "&lt;script&gt;" in f.svg(), "text is escaped")
    f = fig()
    f.notes(40, 150, ["word " * 60], 400)
    check(not errors(f) and f.svg().count("<text") > 6, "notes wrap inside their width")

    # SVG lint for figures made elsewhere
    bad = '<svg xmlns="http://www.w3.org/2000/svg"><script>x()</script><image href="https://x/y.png"/>' \
          '<text font-size="9">a</text></svg>'
    msgs = " | ".join(m for _, m in figkit.lint_svg(bad))
    for want in ("no <title>", "no viewBox", "scripts", "external href", "below 12px"):
        check(want in msgs, f"SVG lint reports {want!r}: {msgs}")
    check(figkit.lint_svg("hello") == [("error", "not an SVG")], "non-SVG rejected")

    # CLI: build refuses lint errors, writes on success, PNG optional
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td / "bad.py").write_text('from figkit import Figure\nfig = Figure("t", source="")\n')
        r = run("build", td / "bad.py")
        check(r.returncode == 1 and not (td / "bad.svg").exists() and "source is empty" in r.stdout,
              f"build refuses lint errors: {r.stdout}{r.stderr}")
        r = run("build", td / "bad.py", "--force")
        check((td / "bad.svg").exists(), "--force writes anyway")
        (td / "nofig.py").write_text("x = 1\n")
        r = run("build", td / "nofig.py")
        check(r.returncode == 2 and "define `fig" in r.stderr, "a script without fig is refused")
        (td / "ok.py").write_text('from figkit import Figure\nfig = Figure("Fine", "sub", source="test")\n'
                                  'fig.box(40, 150, 200, 60, "box", "sub", "teal")\n')
        r = run("build", td / "ok.py", "-o", td / "out.svg", "--png")
        check(r.returncode == 0 and (td / "out.svg").exists(), f"build writes the SVG: {r.stdout}{r.stderr}")
        if shutil.which("rsvg-convert"):
            check((td / "out.png").exists(), "--png writes a PNG when rsvg-convert exists")
        else:
            check("skipped the PNG" in r.stdout, "--png skips cleanly without rsvg-convert")
        r = run("lint", td / "out.svg")
        check(r.returncode == 0 and "0 errors" in r.stdout, f"lint CLI: {r.stdout}")
        r = run("demo", "-o", td / "demo.svg")
        check(r.returncode == 0 and (td / "demo.svg").exists(), "demo CLI")

        # examples rebuild to the committed guide figures, byte for byte
        for name, committed in EXAMPLES.items():
            out = td / f"{name}.svg"
            r = run("build", SK / "examples" / f"{name}.py", "-o", out)
            check(r.returncode == 0 and "0 errors, 0 warnings" in r.stdout, f"example {name} lints clean: {r.stdout}")
            check(committed.exists() and out.read_bytes() == committed.read_bytes(),
                  f"{committed.relative_to(ROOT)} is stale: rebuild it from examples/{name}.py")

    readme = (ROOT / "guide/snowflake-de-architecture/README.md").read_text()
    for name in EXAMPLES:
        check(f"figures/{name}.svg" in readme, f"the Snowflake guide links figures/{name}.svg")

    # SKILL.md and agent
    lint = subprocess.run([sys.executable, str(ROOT / "scripts/skill_lint.py"), str(SK)], capture_output=True, text=True)
    check(lint.returncode == 0 and "0 findings" in lint.stdout, f"SKILL.md lints clean: {lint.stdout}")
    agent = (ROOT / "plugins/top30-learn/agents/figure-maker.md").read_text()
    check(agent.startswith("---\nname: figure-maker\n") and "Never invent" in agent and "no network" in agent,
          "figure-maker agent: frontmatter, sourcing rule, no-network rule")
    check((ROOT / "plugins/top30-learn/claude-ai/explainer-figures.zip").exists(), "claude-ai zip present")

    if fails:
        print(f"FAIL ({len(fails)})")
        for f in fails:
            print(" -", f)
        return 1
    print("ok - figkit: primitives, determinism, layout lint, SVG lint, CLI, examples, skill")
    return 0


if __name__ == "__main__":
    sys.exit(main())
