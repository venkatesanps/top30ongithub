"""Builds a small component library in a temp folder and runs registry_kit.py over it.

python3 tests/registry_kit/test_registry_kit.py   (no dependencies, no network, no Node)
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-ui/skills/component-registry/scripts/registry_kit.py"

FILES = {
    "package.json": json.dumps({"dependencies": {"react": "19", "framer-motion": "13", "lucide-react": "1", "clsx": "2",
                                                 "tailwind-merge": "3"}}),
    "src/lib/utils.ts": "import { clsx } from 'clsx';\nimport { twMerge } from 'tailwind-merge';\nexport const cn = (...a: any[]) => twMerge(clsx(a));\n",
    "src/lib/motion-tokens.ts": "import { easing } from './easing';\nexport const motionTransitions = { springGentle: { type: 'spring', ...easing } };\n",
    "src/lib/easing.ts": "export const easing = { stiffness: 170, damping: 26 };\n",
    # good component: reduced motion, button, test, meta
    "src/components/ui/MagneticCard.tsx": (
        "'use client';\nimport * as React from 'react';\nimport { motion, useReducedMotion } from 'framer-motion';\n"
        "import { cn } from '@/lib/utils';\nimport { motionTransitions } from '../../lib/motion-tokens';\n"
        "const DOCS = `\nimport { nothing } from './not-a-real-file';\n`;\n"
        "export function MagneticCard() { const r = useReducedMotion(); return <motion.button aria-label=\"Open\" "
        "onClick={() => r} className={cn('focus-visible:ring-2')} transition={motionTransitions.springGentle}>Open</motion.button>; }\n"),
    "src/components/ui/MagneticCard.meta.json": json.dumps({"title": "Magnetic Card", "description": "A card that leans toward the cursor."}),
    "src/components/ui/MagneticCard.test.tsx": "import { MagneticCard } from './MagneticCard';\n",
    # problem component: clickable div, img without alt, no reduced motion, undeclared dep, hex colors
    "src/components/ui/GlowBadge.tsx": (
        "import { motion } from 'framer-motion';\nimport confetti from 'canvas-confetti';\n"
        "export const GlowBadge = () => (<motion.div onClick={() => confetti()} style={{color: '#FAFAFA', "
        "background: '#050505', borderColor: '#1F1F1F'}}><img src=\"/x.png\" /></motion.div>);\n"),
    "src/components/ui/GlowBadge.meta.ts": "export default {\n  title: 'Glow Badge',\n  description: \"A badge that glows when it's clicked.\",\n};\n",
    # folder component with companion css and an icon
    "src/components/ui/dot-field/DotField.tsx": "import './DotField.css';\nimport { Sparkle } from '@/components/icons/Sparkle';\nexport const DotField = () => <div role=\"img\" aria-label=\"dots\"><Sparkle /></div>;\n",
    "src/components/ui/dot-field/DotField.css": ".dot { color: red; }\n",
    "src/components/ui/dot-field/meta.json": json.dumps({"title": "Dot Field", "description": "A field of dots."}),
    "src/components/icons/Sparkle.tsx": "export const Sparkle = () => <svg aria-hidden />;\n",
}


def run(*args, cwd=None):
    return subprocess.run([sys.executable, "-I", str(SCRIPT), *map(str, args)], capture_output=True, text=True,
                          timeout=60, cwd=cwd)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lib"
        for rel, body in FILES.items():
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_text(body)

        r = run("scan", "--root", root, "--name", "acme-ui", "--repo", "acme/ui", "--homepage", "https://ui.acme.dev")
        check(r.returncode == 0, f"scan runs ({r.stderr.strip()[:200]})")
        reg = json.loads((root / "registry.json").read_text())
        items = {i["name"]: i for i in reg["items"]}
        check(reg["$schema"] == "https://ui.shadcn.com/schema/registry.json" and reg["name"] == "acme-ui", "shadcn registry header")
        check(sorted(items) == ["dot-field", "glow-badge", "magnetic-card"], f"kebab-case names from PascalCase files {sorted(items)}")
        mc = items["magnetic-card"]
        paths = {f["path"]: f for f in mc["files"]}
        check(mc["dependencies"] == ["framer-motion"], "npm deps from imports; react/clsx/tailwind-merge left to the host project")
        check("src/lib/easing.ts" in paths and paths["src/lib/easing.ts"]["target"] == "lib/easing.ts",
              "a lib file imported by a lib file is shipped too (transitive)")
        check(paths["src/lib/utils.ts"]["type"] == "registry:lib", "@/ alias resolves to src/")
        check("not-a-real-file" not in r.stdout and not any("not-a-real-file" in p for p in paths),
              "an import inside a docs string is ignored")
        check("canvas-confetti, which package.json doesn't declare" in r.stdout, "undeclared npm import reported")
        check(items["glow-badge"]["title"] == "Glow Badge" and "it's clicked" in items["glow-badge"]["description"],
              "metadata read from a .meta.ts file")
        df = {f["target"] for f in items["dot-field"]["files"]}
        check({"components/ui/dot-field.tsx", "components/ui/dot-field.css", "components/icons/sparkle.tsx"} <= df,
              f"folder component ships its css and icon ({sorted(df)})")

        r = run("validate", "--root", root)
        check(r.returncode == 1 and "canvas-confetti isn't in package.json" in r.stdout,
              "validate fails on the undeclared dependency")
        pj = json.loads((root / "package.json").read_text())
        pj["dependencies"]["canvas-confetti"] = "1"
        (root / "package.json").write_text(json.dumps(pj))
        r = run("validate", "--root", root)
        check(r.returncode == 0, f"validate passes once declared ({r.stdout.strip()[-200:]})")

        r = run("new", "OrbitLoader", "--root", root)
        check(r.returncode == 0 and (root / "src/components/ui/OrbitLoader.meta.json").exists(), "new scaffolds component + meta + test")
        new_src = (root / "src/components/ui/OrbitLoader.tsx").read_text()
        check("useReducedMotion" in new_src and "'use client'" in new_src, "scaffold respects reduced motion and is a client component")
        check((root / "src/lib/motion-tokens.ts").read_text().startswith("import"), "existing motion tokens are not overwritten")
        r = run("validate", "--root", root)
        check(r.returncode == 1 and "orbit-loader: component exists but isn't in registry.json" in r.stdout,
              "validate catches a component missing from the registry")
        run("scan", "--root", root, "--name", "acme-ui")
        (root / "src/components/ui/MagneticCard.meta.json").unlink()
        r = run("validate", "--root", root)
        check(r.returncode == 1 and "no metadata file" in r.stdout and "in registry.json but no component file" in r.stdout,
              "validate catches a missing meta file")
        (root / "src/components/ui/MagneticCard.meta.json").write_text(json.dumps({"title": "Magnetic Card", "description": "x"}))
        run("scan", "--root", root, "--name", "acme-ui")

        r = run("audit", "--root", root, "--json")
        fs = json.loads((root / "registry-audit.json").read_text())
        got = {(f["component"], f["rule"]) for f in fs}
        for want in [("glow-badge", "clickable-div"), ("glow-badge", "img-alt"), ("glow-badge", "reduced-motion"),
                     ("glow-badge", "hardcoded-color"), ("glow-badge", "use-client"), ("glow-badge", "no-test")]:
            check(want in got, f"audit flags {want[1]} on {want[0]}")
        check(not any(c == "magnetic-card" and rule in ("reduced-motion", "clickable-div", "no-test") for c, rule in got),
              "the well-built component passes those rules")
        check(run("audit", "--root", root, "--fail-on", "error").returncode == 1, "--fail-on error fails on img without alt")

        fresh = Path(tmp) / "fresh"
        r = run("new", "PressButton", "--root", fresh)
        tok = fresh / "src/lib/motion-tokens.ts"
        check(tok.exists() and "springSnappy" in tok.read_text() and "pick(" in tok.read_text(),
              "new copies the motion tokens template into a project without one")
        check("Suraj Maurya" in (fresh / "src/lib/motion-tokens.NOTICE.md").read_text(), "and keeps EasyUI's MIT notice with it")
        r = run("new", "PressButton", "--root", fresh)
        check(r.returncode != 0 and "already exists" in r.stderr, "new refuses to overwrite a component")

        r = run("llms", "--root", root, "--name", "acme-ui", "--repo", "acme/ui", "--homepage", "https://ui.acme.dev")
        llms = (root / "public/llms.txt").read_text()
        check("npx shadcn@latest add acme/ui/<name>" in llms and "[Magnetic Card](https://ui.acme.dev/components/magnetic-card)" in llms,
              "llms.txt lists install command and components")

    print(f"\n{'FAILED' if failures else 'OK'}: {len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
