#!/usr/bin/env python3
"""Run your own component library like EasyUI: a shadcn GitHub registry built from source.

  registry_kit.py new MagneticCard [--root .]              scaffold component + meta + test
  registry_kit.py scan  --name acme-ui [--repo owner/repo] [--homepage URL] [--root .]
                                                            write registry.json from src/components/ui
  registry_kit.py validate [--root .]                       check registry.json against the code
  registry_kit.py audit [--root .] [--fail-on error|warn]   accessibility, reduced motion, tokens, typing
  registry_kit.py llms --name acme-ui [--repo owner/repo] [--homepage URL]   write public/llms.txt

Conventions (EasyUI's, configurable with --ui-dir):
  src/components/ui/Name.tsx + Name.meta.json (or .meta.ts) per component, or a folder with
  Name.tsx + meta.json. Meta needs "title" and "description". Imports via "@/..." or relative
  paths are followed (transitively) and shipped as registry files; npm imports become
  "dependencies" if package.json declares them. Once pushed to GitHub, anyone installs with
  `npx shadcn@latest add <owner>/<repo>/<name>`.

Python 3 standard library only; reads your repo, writes registry.json / llms.txt / new files only.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCHEMA = "https://ui.shadcn.com/schema/registry.json"
SKIP_DEPS = {"react", "react-dom", "clsx", "tailwind-merge"}  # provided by any shadcn project
IMPORT = re.compile(r"""(?:import\s+(?:[\w*\s{},]*?\s+from\s+)?|export\s+[\w*\s{},]*?\s+from\s+|require\(\s*)['"]([^'"]+)['"]""")
EXTS = ["", ".ts", ".tsx", ".js", ".jsx", ".css", "/index.ts", "/index.tsx"]
SKIP_SUFFIX = (".meta.ts", ".meta.json", ".test.tsx", ".test.ts", ".stories.tsx", ".spec.tsx")


def kebab(name):
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    s = re.sub(r"([A-Z])([A-Z][a-z])", r"\1-\2", s)
    return s.lower().strip("-").replace("_", "-")


def read_meta(p):
    if p.suffix == ".json":
        return json.loads(p.read_text())
    t = p.read_text()  # .meta.ts: pull simple string fields without running TypeScript
    meta = {}
    for key in ("title", "description", "category", "tagline"):
        m = re.search(rf"""\b{key}\s*:\s*(['"`])((?:\\.|(?!\1).)*)\1""", t, re.S)
        if m:
            meta[key] = m.group(2).replace("\\'", "'").replace('\\"', '"')
    return meta


def discover(root, ui_dir):
    ui = root / ui_dir
    if not ui.is_dir():
        sys.exit(f"no component folder at {ui}")
    comps, problems = [], []
    for e in sorted(ui.iterdir()):
        if e.is_dir():
            prim = [f for f in sorted(e.iterdir()) if f.suffix == ".tsx" and not f.name.endswith(SKIP_SUFFIX)]
            if not prim:
                continue
            name = prim[0].stem
            meta_p = next((e / m for m in ("meta.json", "meta.ts", f"{name}.meta.json", f"{name}.meta.ts") if (e / m).exists()), None)
            extra = [f for f in sorted(e.iterdir()) if f.is_file() and f != prim[0] and f != meta_p and not f.name.endswith(SKIP_SUFFIX)]
            primary = prim[0]
        elif e.suffix == ".tsx" and not e.name.endswith(SKIP_SUFFIX):
            name, primary = e.stem, e
            meta_p = next((ui / f"{name}{s}" for s in (".meta.json", ".meta.ts") if (ui / f"{name}{s}").exists()), None)
            extra = [f for f in sorted(ui.iterdir()) if f.is_file() and f.stem.split(".")[0] == name and f != e
                     and f != meta_p and not f.name.endswith(SKIP_SUFFIX) and f.suffix in (".css", ".ts")]
        else:
            continue
        if not meta_p:
            problems.append(f"{primary.relative_to(root)}: no metadata file ({name}.meta.json)")
            continue
        comps.append({"name": name, "slug": kebab(name), "primary": primary, "extra": extra, "meta": read_meta(meta_p),
                      "meta_path": meta_p})
    return comps, problems


def code_only(src):
    """Drop comments and template literals, so an import shown in a docs string isn't followed."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    src = re.sub(r"`(?:\\.|[^`\\])*`", "``", src, flags=re.S)
    return re.sub(r"(?m)^\s*//.*$", "", src)


def resolve(spec, from_file, root, src_alias):
    base = (root / src_alias / spec[2:]) if spec.startswith("@/") else (from_file.parent / spec)
    for ext in EXTS:
        c = Path(str(base) + ext)
        if c.is_file():
            return c.resolve()
    return None


def analyze(files, root, src_alias, declared):
    """Follow local imports transitively. Returns (npm deps, local files, unresolved local imports)."""
    deps, local, missing, todo, seen = set(), set(), [], list(files), set()
    while todo:
        f = todo.pop()
        if f in seen or f.suffix not in (".ts", ".tsx", ".js", ".jsx"):
            continue
        seen.add(f)
        for spec in IMPORT.findall(code_only(f.read_text(encoding="utf-8", errors="replace"))):
            if spec.startswith((".", "@/")):
                r = resolve(spec, f, root, src_alias)
                if r:
                    if r not in local:
                        local.add(r)
                        todo.append(r)
                else:
                    missing.append(f"{f.relative_to(root)} imports {spec}, which doesn't exist")
            else:
                pkg = "/".join(spec.split("/")[:2]) if spec.startswith("@") else spec.split("/")[0]
                if pkg in SKIP_DEPS or spec.startswith(("node:", "react/")):
                    continue
                deps.add(pkg)
    undeclared = sorted(d for d in deps if declared is not None and d not in declared)
    return sorted(deps), local, missing, undeclared


def target_for(rel, slug_of):
    """Where a shipped file lands in the consumer's project (EasyUI's mapping)."""
    if rel.startswith("src/lib/"):
        return "registry:lib", rel[len("src/"):]
    if rel.startswith("src/hooks/"):
        return "registry:hook", rel[len("src/"):]
    p = Path(rel)
    if "/components/" in rel:
        sub = rel.split("/components/", 1)[1].split("/")[0]
        if sub in ("ui", "icons"):
            return "registry:ui", f"components/{sub}/{slug_of.get(rel, kebab(p.stem.split('.')[0]))}{p.suffix}"
    return "registry:lib", f"lib/{p.name}"


def declared_deps(root):
    pj = root / "package.json"
    if not pj.exists():
        return None
    d = json.loads(pj.read_text())
    return set(d.get("dependencies", {})) | set(d.get("devDependencies", {})) | set(d.get("peerDependencies", {}))


def build(root, a):
    comps, problems = discover(root, a.ui_dir)
    declared = declared_deps(root)
    slug_of = {}
    for c in comps:
        slug_of[c["primary"].relative_to(root).as_posix()] = c["slug"]
        for x in c["extra"]:
            slug_of[x.relative_to(root).as_posix()] = c["slug"]
    items, notes = [], list(problems)
    for c in comps:
        deps, local, missing, undeclared = analyze([c["primary"], *c["extra"]], root, a.src_alias, declared)
        notes += missing + [f"{c['slug']}: imports {d}, which package.json doesn't declare" for d in undeclared]
        files = [{"path": c["primary"].relative_to(root).as_posix(), "type": "registry:ui",
                  "target": f"components/ui/{c['slug']}{c['primary'].suffix}"}]
        for x in c["extra"]:
            files.append({"path": x.relative_to(root).as_posix(), "type": "registry:ui",
                          "target": f"components/ui/{c['slug']}{x.suffix}"})
        have = {f["path"] for f in files}
        for f in sorted(local):
            rel = f.relative_to(root).as_posix()
            if rel not in have:
                t, tgt = target_for(rel, slug_of)
                files.append({"path": rel, "type": t, "target": tgt})
                have.add(rel)
        item = {"name": c["slug"], "type": "registry:ui", "title": c["meta"].get("title", ""),
                "description": c["meta"].get("description", "")}
        if deps:
            item["dependencies"] = deps
        item["files"] = files
        items.append(item)
    reg = {"$schema": SCHEMA, "name": a.name}
    if a.homepage:
        reg["homepage"] = a.homepage
    reg["items"] = sorted(items, key=lambda i: i["name"])
    return reg, notes


def cmd_scan(a):
    root = Path(a.root).resolve()
    reg, notes = build(root, a)
    (root / "registry.json").write_text(json.dumps(reg, indent=2) + "\n")
    for n in notes:
        print("  note:", n)
    print(f"registry.json: {len(reg['items'])} component(s)" + (f"; install with npx shadcn@latest add {a.repo}/<name>" if a.repo else ""))


def validate(root, ui_dir="src/components/ui"):
    errs, warns = [], []
    p = root / "registry.json"
    if not p.exists():
        return ["registry.json not found: run scan"], warns
    try:
        reg = json.loads(p.read_text())
    except ValueError as e:
        return [f"registry.json is not valid JSON: {e}"], warns
    if reg.get("$schema") != SCHEMA:
        errs.append(f'"$schema" must be {SCHEMA}')
    if not reg.get("name"):
        errs.append('registry "name" is missing')
    items = reg.get("items") or []
    if not items:
        errs.append('"items" is empty')
    declared, seen_names, seen_titles = declared_deps(root), set(), defaultdict(list)
    for it in items:
        n = it.get("name", "")
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", n):
            errs.append(f"{n or it}: name must be kebab-case")
        if n in seen_names:
            errs.append(f"{n}: duplicate name")
        seen_names.add(n)
        for k in ("title", "description"):
            if not str(it.get(k, "")).strip():
                errs.append(f"{n}: missing {k}")
        seen_titles[it.get("title")].append(n)
        files = it.get("files") or []
        if not files:
            errs.append(f"{n}: no files")
        if not any(f.get("type") == "registry:ui" for f in files):
            errs.append(f"{n}: no registry:ui file")
        for f in files:
            if not (root / f.get("path", "")).is_file():
                errs.append(f"{n}: file {f.get('path')} doesn't exist")
            if not f.get("target"):
                warns.append(f"{n}: {f.get('path')} has no target path")
        for d in it.get("dependencies") or []:
            if declared is not None and d not in declared:
                errs.append(f"{n}: dependency {d} isn't in package.json")
    for t, ns in seen_titles.items():
        if t and len(ns) > 1:
            warns.append(f"title {t!r} used by {', '.join(ns)}")
    # registry matches the code
    try:
        comps, problems = discover(root, ui_dir)
        errs += problems
        listed = {it.get("name") for it in items}
        for c in comps:
            if c["slug"] not in listed:
                errs.append(f"{c['slug']}: component exists but isn't in registry.json (run scan)")
        for n in listed - {c["slug"] for c in comps}:
            errs.append(f"{n}: in registry.json but no component file found")
    except SystemExit as e:
        errs.append(str(e))
    return errs, warns


def cmd_validate(a):
    errs, warns = validate(Path(a.root).resolve(), a.ui_dir)
    for w in warns:
        print("  warn:", w)
    for e in errs:
        print("  ERROR:", e)
    print(f"validate: {len(errs)} error(s), {len(warns)} warning(s)")
    sys.exit(1 if errs else 0)


# ---------- audit ----------
AUDIT = [  # (rule, severity, test(src) -> bool, message)
    ("reduced-motion", "warn",
     lambda s: re.search(r"from ['\"](framer-motion|motion/react)['\"]", s) and not re.search(
         r"useReducedMotion|MotionConfig|prefers-reduced-motion|reducedMotion", s),
     "Animates with Motion but ignores prefers-reduced-motion. Use useReducedMotion() (or MotionConfig reducedMotion=\"user\") to drop movement, keep fades."),
    ("clickable-div", "warn", lambda s: clickable_divs(s),
     "A div or span handles clicks with no role or key handling. Check there's a keyboard path (a real <button> or <input> it forwards to is fine); otherwise use a <button>."),
    ("img-alt", "error", lambda s: re.search(r"<img\b(?![^>]*\balt=)[^>]*>", s), "<img> without alt text."),
    ("icon-button-label", "warn",
     lambda s: re.search(r"<(button|motion\.button)\b(?![^>]*aria-label)[^>]*>\s*<[A-Z]\w*(Icon)?\b[^>]*/>\s*</(button|motion\.button)>", s),
     "Icon-only button without aria-label."),
    ("focus-visible", "warn",
     lambda s: re.search(r"outline-none|outline:\s*none", s) and not re.search(r"focus-visible|focus-ring|ring-", s),
     "Removes the focus outline without a visible replacement (focus-visible ring)."),
    ("hardcoded-color", "info",
     lambda s: len(re.findall(r"#[0-9a-fA-F]{6}\b", s)) >= 3,
     "Several hard-coded hex colors: move them to theme tokens (CSS variables) so dark/light themes and brands can change them."),
    ("any-spread", "info", lambda s: re.search(r"as any\b", s), "`as any` hides prop type errors from consumers."),
    ("use-client", "info",
     lambda s: re.search(r"\buse(State|Effect|Ref)\b|framer-motion|onClick=", s) and not re.match(r"\s*['\"]use client['\"]", s),
     "Uses client-only React features without 'use client' at the top: breaks in Next.js server components."),
]
SEV = {"error": 0, "warn": 1, "info": 2}
TAG = re.compile(r"<(div|span|li|motion\.div|motion\.span|motion\.li)\b((?:=>|[^>])*)>", re.S)


def clickable_divs(src):
    """Non-interactive elements with onClick and no role/keyboard handling (backdrops marked aria-hidden are fine)."""
    for m in TAG.finditer(src):
        body = m.group(2)
        if re.search(r"\bonClick=", body) and not re.search(r"\brole=|onKeyDown=|onKeyUp=|aria-hidden|tabIndex=", body):
            return True
    return False


def cmd_audit(a):
    root = Path(a.root).resolve()
    comps, problems = discover(root, a.ui_dir)
    fs = [{"component": "-", "rule": "metadata", "severity": "error", "message": p} for p in problems]
    for c in comps:
        src = c["primary"].read_text(encoding="utf-8", errors="replace")
        for rule, sev, test, msg in AUDIT:
            if test(src):
                fs.append({"component": c["slug"], "rule": rule, "severity": sev, "message": msg})
        folder = c["primary"].parent != (root / a.ui_dir)
        has_test = any(c["primary"].parent.glob("*.test.ts*")) if folder else any(
            (c["primary"].parent / f"{c['name']}{x}").exists() for x in (".test.tsx", ".test.ts"))
        if not has_test:
            fs.append({"component": c["slug"], "rule": "no-test", "severity": "info",
                       "message": "No test file: at least render it and check its accessible name and keyboard path."})
    fs.sort(key=lambda f: (SEV[f["severity"]], f["rule"], f["component"]))
    by = defaultdict(list)
    for f in fs:
        by[(f["severity"], f["rule"])].append(f["component"])
    print(f"audit: {len(comps)} component(s)")
    for (sev, rule), names in sorted(by.items(), key=lambda kv: (SEV[kv[0][0]], -len(kv[1]))):
        msg = next(f["message"] for f in fs if f["rule"] == rule)
        print(f"  [{sev}] {rule} x{len(names)}: {', '.join(names[:8])}{' ...' if len(names) > 8 else ''}\n      {msg}")
    out = root / "registry-audit.json"
    if a.json:
        out.write_text(json.dumps(fs, indent=1) + "\n")
    if a.fail_on and any(SEV[f["severity"]] <= SEV[a.fail_on] for f in fs):
        sys.exit(1)


# ---------- llms.txt ----------
def cmd_llms(a):
    root = Path(a.root).resolve()
    reg, _ = build(root, a)
    lines = [f"# {a.name}", "", f"> {a.summary or 'Components installable with the shadcn CLI.'}", "",
             "## Install", ""]
    lines += [f"- `npx shadcn@latest add {a.repo}/<name>`" if a.repo else "- `npx shadcn@latest add <registry-item-url>`", ""]
    lines += ["## Components", ""]
    for it in reg["items"]:
        url = f"{a.homepage.rstrip('/')}/components/{it['name']}" if a.homepage else it["name"]
        lines.append(f"- [{it['title']}]({url}): {it['description']}")
    out = root / "public" / "llms.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n")
    print(f"wrote {out.relative_to(root)} ({len(reg['items'])} components)")


# ---------- new ----------
COMPONENT_TSX = """'use client';

import * as React from 'react';
import {{ motion, useReducedMotion }} from 'framer-motion';
import {{ cn }} from '@/lib/utils';
import {{ motionTransitions }} from '@/lib/motion-tokens';

export interface {name}Props extends React.HTMLAttributes<HTMLDivElement> {{
  /** Visible label; also the accessible name. */
  label: string;
}}

export function {name}({{ label, className, ...props }}: {name}Props) {{
  const reduce = useReducedMotion();
  return (
    <motion.div
      role="group"
      aria-label={{label}}
      initial={{reduce ? {{ opacity: 0 }} : {{ opacity: 0, y: 8 }}}}
      animate={{{{ opacity: 1, y: 0 }}}}
      transition={{reduce ? motionTransitions.easeFast : motionTransitions.springGentle}}
      className={{cn('rounded-xl border border-border bg-card p-4 text-card-foreground', className)}}
      {{...props}}
    >
      {{label}}
    </motion.div>
  );
}}
"""
TEST_TSX = """import {{ render, screen }} from '@testing-library/react';
import {{ describe, expect, it }} from 'vitest';
import {{ {name} }} from './{name}';

describe('{name}', () => {{
  it('renders with an accessible name', () => {{
    render(<{name} label="Example" />);
    expect(screen.getByRole('group', {{ name: 'Example' }})).toBeTruthy();
  }});
}});
"""


def cmd_new(a):
    root = Path(a.root).resolve()
    name = a.component
    if not re.fullmatch(r"[A-Z][A-Za-z0-9]+", name):
        sys.exit("component name must be PascalCase, e.g. MagneticCard")
    ui = root / a.ui_dir
    ui.mkdir(parents=True, exist_ok=True)
    targets = {ui / f"{name}.tsx": COMPONENT_TSX.format(name=name),
               ui / f"{name}.test.tsx": TEST_TSX.format(name=name),
               ui / f"{name}.meta.json": json.dumps({"title": re.sub(r"(?<!^)([A-Z])", r" \1", name),
                                                     "description": "TODO: one sentence on what it does and when to use it.",
                                                     "category": "Motion"}, indent=2) + "\n"}
    for p in targets:
        if p.exists():
            sys.exit(f"{p.relative_to(root)} already exists")
    for p, body in targets.items():
        p.write_text(body)
        print("created", p.relative_to(root))
    tokens = root / "src" / "lib" / "motion-tokens.ts"
    if not tokens.exists():
        tpl = Path(__file__).resolve().parents[2] / "motion-component-builder" / "templates" / "motion-tokens.ts"
        if tpl.exists():
            tokens.parent.mkdir(parents=True, exist_ok=True)
            tokens.write_text(tpl.read_text())
            notice = tokens.parent / "motion-tokens.NOTICE.md"  # the values are adapted from EasyUI (MIT)
            notice.write_text((tpl.parent / "THIRD_PARTY_NOTICE.md").read_text())
            print("created", tokens.relative_to(root), "and", notice.relative_to(root))
    print(f"Next: write the description in {name}.meta.json, then scan and validate.")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--root", default=".")
        p.add_argument("--ui-dir", default="src/components/ui")
        p.add_argument("--src-alias", default="src", help='folder that "@/" points to (default src)')

    p = sub.add_parser("new")
    p.add_argument("component")
    common(p)
    for name in ("scan", "llms"):
        p = sub.add_parser(name)
        common(p)
        p.add_argument("--name", required=True)
        p.add_argument("--repo", help="owner/repo on GitHub, for install commands")
        p.add_argument("--homepage")
        if name == "llms":
            p.add_argument("--summary")
    p = sub.add_parser("validate")
    common(p)
    p = sub.add_parser("audit")
    common(p)
    p.add_argument("--fail-on", choices=["error", "warn"])
    p.add_argument("--json", action="store_true", help="also write registry-audit.json")
    a = ap.parse_args(argv)
    {"new": cmd_new, "scan": cmd_scan, "validate": cmd_validate, "audit": cmd_audit, "llms": cmd_llms}[a.cmd](a)


if __name__ == "__main__":
    main()
