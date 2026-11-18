"""Tests for the sunburst-3d skill: dir_to_json.py and build_standalone.py, plus the engine tests
(test_sunburst.mjs) when Node is installed.

python3 tests/sunburst_3d/test_sunburst.py   (no network)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SKILL = HERE.parent.parent / "plugins/top30-ui/skills/sunburst-3d"
SCAN = SKILL / "scripts/dir_to_json.py"
BUILD = SKILL / "scripts/build_standalone.py"
fails = 0


def check(ok, msg):
    global fails
    print(("ok   " if ok else "FAIL ") + msg)
    fails += 0 if ok else 1


def run(*args):
    return subprocess.run([sys.executable, "-I", *map(str, args)], capture_output=True, text=True, timeout=60)


with tempfile.TemporaryDirectory() as d:
    d = Path(d)
    root = d / "home"
    (root / "big").mkdir(parents=True)
    (root / "big" / "deep" / "deeper").mkdir(parents=True)
    (root / "big" / "a.bin").write_bytes(b"x" * 3_000_000)
    (root / "big" / "deep" / "deeper" / "b.bin").write_bytes(b"x" * 2_000_000)
    for i in range(30):
        (root / f"small{i}.txt").write_bytes(b"y" * 100)
    (root / "empty").mkdir()
    os.symlink(root / "big", root / "link-to-big")

    r = run(SCAN, root, "--depth", "2", "--top", "5", "--min-size", "1KB", "--apparent")
    check(r.returncode == 0, "dir_to_json runs")
    tree = json.loads(r.stdout)
    names = [c["name"] for c in tree["children"]]
    check(tree["name"] == "home" and names[0] == "big", "largest folder first")
    check("link-to-big" not in names, "symlinks are not followed")
    other = [c for c in tree["children"] if c["name"].startswith("(")]
    check(len(other) == 1 and other[0]["name"] == "(30 smaller items)" and other[0]["size"] == 3000, "small files merge into one leaf with their total")
    big = tree["children"][0]
    deep = next(c for c in big["children"] if c["name"] == "deep")
    check("children" not in deep and deep["size"] == 2_000_000, "below --depth a folder is one leaf with its total")

    out = d / "tree.json"
    r = run(SCAN, root, "-o", out, "--name", "My files")
    check(r.returncode == 0 and json.loads(out.read_text())["name"] == "My files", "-o and --name")

    page = d / "page.html"
    r = run(BUILD, SKILL / "templates/sunburst3d-demo.html", page, "--data", out)
    html = page.read_text()
    check(r.returncode == 0, "build_standalone runs")
    check("from './sunburst3d.js'" not in html.split("<script type=\"module\">", 1)[1].split("*/", 1)[1], "the module import is inlined")
    check('"My files"' in html and "bunch('Profile'" not in html, "--data replaces the sample data")
    node = shutil.which("node")
    if node:
        # the inlined page's script must at least parse
        script = html.split('<script type="module">', 1)[1].split("</script>", 1)[0]
        js = d / "page.mjs"
        js.write_text(script)
        r = subprocess.run([node, "--check", str(js)], capture_output=True, text=True, timeout=60)
        check(r.returncode == 0, "the inlined script parses" + ("" if r.returncode == 0 else ": " + r.stderr[:300]))
        r = subprocess.run([node, str(HERE / "test_sunburst.mjs")], capture_output=True, text=True, timeout=120)
        print(r.stdout.strip().splitlines()[-1] if r.stdout.strip() else r.stderr[:500])
        check(r.returncode == 0, "sunburst engine tests pass in Node")
    else:
        print("SKIP engine tests (node not installed)")

print(f"OK: {fails} failure(s)" if not fails else f"FAILED: {fails}")
sys.exit(1 if fails else 0)
