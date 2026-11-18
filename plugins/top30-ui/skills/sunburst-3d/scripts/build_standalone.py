#!/usr/bin/env python3
"""Turn a page that imports sunburst3d.js into one self-contained HTML file (module inlined), so it
can be emailed, opened from disk, or published where only one file is allowed.

  build_standalone.py PAGE.html OUT.html [--data data.json]

PAGE.html must load the chart with `import { ... } from './sunburst3d.js';` inside a
<script type="module">. The module is read from the same folder as PAGE.html (or --module).
With --data, the page's sample data block (from `const data = {` to the matching `};`, or the
`// Sample data` section in the demo) is replaced by the JSON file, e.g. one written by
dir_to_json.py. Standard library only.
"""
import argparse
import json
import re
import sys
from pathlib import Path


def inline(page: str, module: str) -> str:
    m = re.search(r"import\s*\{([^}]*)\}\s*from\s*['\"]\./sunburst3d\.js['\"];?", page)
    if not m:
        sys.exit("no `import { ... } from './sunburst3d.js'` found in the page")
    names = [n.strip() for n in m.group(1).split(",") if n.strip()]
    body = re.sub(r"(?m)^export\s+(?=(const|function|class|let)\b)", "", module)
    exported = set(re.findall(r"(?m)^export\s+(?:const|function|class|let)\s+(\w+)", module))
    missing = [n.split(" as ")[0].strip() for n in names if n.split(" as ")[0].strip() not in exported]
    if missing:
        sys.exit(f"the page imports names the module doesn't export: {', '.join(missing)}")
    aliases = "".join(f"const {n.split(' as ')[1].strip()} = {n.split(' as ')[0].strip()};\n" for n in names if " as " in n)
    # Wrap the module in a block so its private helpers don't collide with the page's own names.
    wrapped = "const { " + ", ".join(sorted(exported)) + " } = (() => {\n" + body + "\nreturn { " + ", ".join(sorted(exported)) + " };\n})();\n" + aliases
    return page[: m.start()] + wrapped + page[m.end():]


def swap_data(page: str, data: dict) -> str:
    start = page.find("// Sample data")
    end = page.find("document.head.insertAdjacentHTML", start)
    if start == -1 or end == -1:
        m = re.search(r"const data = \{", page)
        if not m:
            sys.exit("couldn't find the sample data block to replace")
        start, depth, i = m.start(), 0, m.end() - 1
        for i in range(m.end() - 1, len(page)):
            depth += {"{": 1, "}": -1}.get(page[i], 0)
            if depth == 0:
                break
        end = page.find(";", i) + 1
        return page[:start] + "const data = " + json.dumps(data) + ";" + page[end:]
    return page[:start] + "const data = " + json.dumps(data) + ";\n\n" + page[end:]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("page")
    ap.add_argument("out")
    ap.add_argument("--module", help="path to sunburst3d.js (default: next to the page)")
    ap.add_argument("--data", help="JSON tree ({name, size?, children?}) to use instead of the sample")
    a = ap.parse_args(argv)
    page_path = Path(a.page)
    module = Path(a.module) if a.module else page_path.with_name("sunburst3d.js")
    html = inline(page_path.read_text(encoding="utf-8"), module.read_text(encoding="utf-8"))
    if a.data:
        html = swap_data(html, json.loads(Path(a.data).read_text(encoding="utf-8")))
    Path(a.out).write_text(html, encoding="utf-8")
    print(f"wrote {a.out} ({len(html) // 1024} KB)")


if __name__ == "__main__":
    main()
