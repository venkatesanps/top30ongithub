#!/usr/bin/env python3
"""Check a Wensity project's theme tokens, dark mode setup and install hygiene.

Standard library only, read-only. Finds the stylesheet that holds Tailwind v4's
`@theme` block and reports:

  error  no `@theme inline` block; MCP server not pinned (`@latest` or no version);
         `.wensity-tmp/` tracked by git
  warn   no `.dark` block while the code toggles dark mode; brand ramp missing a step
         (300/500/800); renamed ramp but `chili-*` classes still used; `.dark` class
         strategy with next-themes but no suppressHydrationWarning on <html>;
         `.wensity-tmp/` not in .gitignore; no chart colors defined
  note   hard-coded hex colors in your own components (Wensity's files are skipped);
         preset and style recorded in wensity.json

Usage: token_check.py [PROJECT_DIR] [--css FILE] [--json] [--fail-on error|warn]
Exit 1 when a finding at or above --fail-on exists (default: error).
"""
import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

SKIP_DIRS = {"node_modules", ".git", ".next", "dist", "build", "out", ".turbo", ".vercel", ".wensity-tmp", "coverage"}
CSS_GUESSES = ["src/app/globals.css", "app/globals.css", "src/styles/globals.css", "styles/globals.css",
               "src/index.css", "src/globals.css", "src/styles.css", "app/app.css", "src/styles/global.css"]
HEX = re.compile(r"(?<![\w&])#(?:[0-9a-fA-F]{3}){1,2}(?:[0-9a-fA-F]{2})?\b")
RAMP = re.compile(r"--color-([a-z][a-z0-9-]*?)-(300|500|800)\s*:")


def files(root, exts):
    for p in root.rglob("*"):
        if p.is_file() and p.suffix in exts and not (set(p.relative_to(root).parts) & SKIP_DIRS):
            yield p


def block(css, selector):
    """Body of the first `selector {` block, braces balanced."""
    m = re.search(rf"(^|[\s,}}]){re.escape(selector)}\s*\{{", css)
    if not m:
        return None
    i, depth = m.end(), 1
    while i < len(css) and depth:
        depth += {"{": 1, "}": -1}.get(css[i], 0)
        i += 1
    return css[m.end():i - 1]


def find_css(root, explicit):
    if explicit:
        p = (root / explicit) if not Path(explicit).is_absolute() else Path(explicit)
        return p if p.is_file() else None
    for g in CSS_GUESSES:
        if (root / g).is_file() and "@theme" in (root / g).read_text(errors="ignore"):
            return root / g
    for p in files(root, {".css"}):
        if "@theme" in p.read_text(errors="ignore"):
            return p
    return None


def git_tracked(root, path):
    try:
        r = subprocess.run(["git", "-C", str(root), "ls-files", "--", path], capture_output=True, text=True, timeout=20)
        return bool(r.stdout.strip())
    except (OSError, subprocess.TimeoutExpired):
        return False


def check(root, css_arg=None):
    out = []
    add = lambda level, msg: out.append({"level": level, "msg": msg})
    pkg = {}
    if (root / "package.json").is_file():
        try:
            j = json.loads((root / "package.json").read_text())
            pkg = {**j.get("dependencies", {}), **j.get("devDependencies", {})}
        except json.JSONDecodeError:
            add("warn", "package.json is not valid JSON.")
    else:
        add("warn", "No package.json: run this from the project root (or pass PROJECT_DIR).")

    css_path = find_css(root, css_arg)
    css = css_path.read_text(errors="ignore") if css_path else ""
    if not css_path:
        add("error", "No stylesheet with an @theme block. Run `npx wensity@latest init` (or apply your preset) first.")
    else:
        rel = css_path.relative_to(root) if css_path.is_relative_to(root) else css_path
        if not re.search(r"@theme\s+inline\s*\{", css):
            add("error", f"{rel}: has @theme but not `@theme inline`; Wensity maps tokens through `@theme inline`.")
        if not re.search(r"@import\s+[\"']tailwindcss[\"']", css):
            add("warn", f"{rel}: no `@import \"tailwindcss\"`; Wensity needs Tailwind CSS v4.")
        if block(css, ":root") is None:
            add("warn", f"{rel}: no :root block with light values.")

    src = {p: p.read_text(errors="ignore") for p in files(root, {".tsx", ".ts", ".jsx", ".js", ".astro", ".mdx"})}
    uses_dark = any(re.search(r"\bdark:|next-themes|classList\.(add|toggle)\(\s*[\"']dark", t) for t in src.values())
    if css_path and uses_dark and block(css, ".dark") is None:
        add("warn", "The code uses dark mode but the stylesheet has no .dark block: dark values never apply.")

    ramps = {}
    for name, step in RAMP.findall(css):
        ramps.setdefault(name, set()).add(step)
    brand = [n for n, s in ramps.items() if not n.startswith(("chart", "primitive"))]
    if css_path and not brand:
        add("warn", "No brand ramp (--color-<name>-300/-500/-800) found; components use it for accents.")
    for n in brand:
        missing = {"300", "500", "800"} - ramps[n]
        if missing:
            add("warn", f"Brand ramp `{n}` is missing step(s) {', '.join(sorted(missing))}.")
    if css_path and any(n != "chili" for n in brand) and "chili" not in ramps:
        used = sorted(str(p.relative_to(root)) for p, t in src.items() if re.search(r"\bchili-\d{3}\b", t))
        if used:
            add("warn", f"Ramp renamed from chili-* but {len(used)} file(s) still use chili-* classes: "
                        + ", ".join(used[:5]) + ("…" if len(used) > 5 else ""))
    if css_path and not re.search(r"--(color-)?chart-\d|--chart-", css):
        add("warn", "No chart colors (--chart-1…) in the stylesheet; set a chart palette in your preset.")

    if "next-themes" in pkg:
        layouts = [p for p in src if p.name in ("layout.tsx", "layout.jsx", "_document.tsx", "root.tsx")]
        if layouts and not any("suppressHydrationWarning" in src[p] for p in layouts):
            add("warn", "next-themes is installed but <html> has no suppressHydrationWarning: expect hydration warnings.")

    # Wensity installs into components/wensity/...; only check the user's own files
    ours = {p: t for p, t in src.items() if "wensity" not in p.relative_to(root).parts}
    hex_hits = {str(p.relative_to(root)): len(HEX.findall(t)) for p, t in ours.items() if HEX.search(t)}
    if hex_hits:
        top = sorted(hex_hits.items(), key=lambda kv: -kv[1])[:5]
        add("note", f"{sum(hex_hits.values())} hard-coded hex color(s) in {len(hex_hits)} of your files "
                    f"(prefer tokens): " + ", ".join(f"{f} ({n})" for f, n in top))

    gi = (root / ".gitignore").read_text() if (root / ".gitignore").is_file() else ""
    if not re.search(r"^/?\.wensity-tmp/?\s*$", gi, re.M):
        add("warn", "Add `.wensity-tmp/` to .gitignore (the installer's scratch folder; never commit it).")
    if git_tracked(root, ".wensity-tmp"):
        add("error", ".wensity-tmp/ is tracked by git: `git rm -r --cached .wensity-tmp`.")

    mcp = root / ".mcp.json"
    if mcp.is_file():
        try:
            servers = json.loads(mcp.read_text()).get("mcpServers", {})
        except json.JSONDecodeError:
            servers = {}
            add("warn", ".mcp.json is not valid JSON.")
        for name, cfg in servers.items():
            args = " ".join(cfg.get("args", []))
            m = re.search(r"@wensity/mcp(@[\w.\-]+)?", args)
            if m and (not m.group(1) or m.group(1) in ("@latest", "@next")):
                add("error", f".mcp.json server `{name}` runs {m.group(0)}: pin an exact version "
                             "(e.g. @wensity/mcp@0.1.2); the server writes files and runs your package manager.")

    wj = root / "wensity.json"
    if wj.is_file():
        try:
            w = json.loads(wj.read_text())
            keep = {k: w[k] for k in ("style", "preset", "iconLibrary", "icons", "baseColor", "radius") if k in w}
            add("note", "wensity.json: " + (json.dumps(keep) if keep else "present"))
        except json.JSONDecodeError:
            add("warn", "wensity.json is not valid JSON.")
    else:
        add("note", "No wensity.json yet (written by `wensity init` or applying a preset).")
    return {"css": str(css_path.relative_to(root)) if css_path else None, "brand": brand, "findings": out}


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("project", nargs="?", default=".")
    ap.add_argument("--css")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--fail-on", choices=("error", "warn"), default="error")
    a = ap.parse_args(argv)
    root = Path(a.project).resolve()
    if not root.is_dir():
        print(f"error: {root} is not a folder", file=sys.stderr)
        return 2
    res = check(root, a.css)
    if a.json:
        print(json.dumps(res, indent=2))
    else:
        print(f"Wensity token check: {root.name}  (stylesheet: {res['css'] or 'not found'}; "
              f"brand ramp: {', '.join(res['brand']) or 'none'})")
        for lvl in ("error", "warn", "note"):
            for f in res["findings"]:
                if f["level"] == lvl:
                    print(f"  {lvl.upper():5} {f['msg']}")
        n = {l: sum(f["level"] == l for f in res["findings"]) for l in ("error", "warn", "note")}
        print(f"{n['error']} error(s), {n['warn']} warning(s), {n['note']} note(s)")
    bad = {"error"} if a.fail_on == "error" else {"error", "warn"}
    return 1 if any(f["level"] in bad for f in res["findings"]) else 0


if __name__ == "__main__":
    sys.exit(main())
