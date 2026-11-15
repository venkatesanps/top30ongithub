"""Runs top30-wensity's schema_to_ui.py and token_check.py over invented data and projects.

python3 tests/wensity_kit/test_wensity_kit.py   (no dependencies, no network, no Node)
"""
import csv
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
PLUGIN = ROOT / "plugins/top30-wensity"
SCHEMA = PLUGIN / "skills/wensity-dashboard-kit/scripts/schema_to_ui.py"
TOKENS = PLUGIN / "skills/wensity-brand-preset/scripts/token_check.py"
SAFE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

SALES = """Sale Date,Property ID,County,Opening Bid ($),Est. Value,Status,Address
2026-11-03,DAL-001,Dallas,"$120,000",250000,Scheduled,12 Elm St
2026-11-03,DAL-002,Dallas,"$98,500",180000,Cancelled,4 Oak Ave
2026-12-01,COL-001,Collin,"$210,000",400000,Scheduled,9 Pine Rd
2026-12-01,TAR-001,Tarrant,"$75,000",150000,Postponed,77 Main St
2027-01-05,DEN-001,Denton,"$130,000",260000,Scheduled,5 Lake Dr
"""

GOOD_CSS = """@import "tailwindcss";
@theme inline {
  --color-background: var(--background);
  --color-brand-300: #93c5fd;
  --color-brand-500: #3b82f6;
  --color-brand-800: #1e3a8a;
  --color-chart-1: var(--chart-1);
}
:root { --background: #fff; --chart-1: #3b82f6; }
.dark { --background: #0a0a0a; --chart-1: #60a5fa; }
"""


def run(script, *args, cwd=None):
    return subprocess.run([sys.executable, "-I", str(script), *map(str, args)], capture_output=True,
                          text=True, timeout=60, cwd=cwd)


def write(root, files):
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def main():
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        t = Path(tmp)
        (t / "sales.csv").write_text(SALES)

        # --- schema_to_ui: plan / json / ts
        r = run(SCHEMA, t / "sales.csv", "--format", "json")
        check(r.returncode == 0, "schema_to_ui json runs")
        plan = json.loads(r.stdout)
        cols = {c["header"]: c for c in plan["columns"]}
        check(plan["rowKey"] == "propertyId", "row key is the unique Property ID column")
        check(cols["Sale Date"]["type"] == "date", "ISO dates detected")
        check(cols["Opening Bid ($)"]["type"] == "number" and cols["Opening Bid ($)"]["format"] == "currency",
              "'$120,000' parsed as a currency number")
        check(cols["County"]["type"] == "category" and cols["Status"]["type"] == "category", "categories detected")
        check(cols["Address"]["type"] == "text", "unique free text stays text")
        check(all(SAFE.match(c["key"]) for c in plan["columns"]), "every generated key is CSS-safe")
        check(any("CSS-safe" in w for w in plan["warnings"]), "warns about unsafe headers")
        check(plan["chart"]["x"] == "saleDate" and plan["chart"]["component"] == "ChartArea"
              and [s["key"] for s in plan["chart"]["series"]] == ["openingBid", "estValue"],
              "date axis + two numeric series → area chart on row keys")
        controls = {f["key"]: f["control"] for f in plan["filters"]}
        check(controls.get("saleDate") == "date-picker" and controls.get("county") == "select", "filters chosen")
        check("data-table" in plan["install"]["primitives"] and "date-picker" in plan["install"]["primitives"],
              "install list has data-table and date-picker")
        check(any("getRowId" in n for n in plan["notes"]), "tells you to pass getRowId when the key isn't id")

        r = run(SCHEMA, t / "sales.csv", "--name", "foreclosures")
        check(r.returncode == 0 and "# Dashboard plan: foreclosures" in r.stdout and "## Fix first" in r.stdout
              and "npx wensity@latest add" in r.stdout, "markdown plan renders")

        out = t / "src/dashboard/foreclosures.schema.ts"
        r = run(SCHEMA, t / "sales.csv", "--name", "foreclosures", "--format", "ts", "--out", out)
        ts = out.read_text() if out.is_file() else ""
        check(r.returncode == 0 and "export type ForeclosuresRow" in ts, "ts module written")
        check('openingBid: toNumber(raw["Opening Bid ($)"])' in ts, "mapper renames and parses the bid column")
        cfg = re.search(r"export const foreclosuresChartConfig = \{(.*?)\};", ts, re.S)
        cfg_keys = re.findall(r"^\s+(\w+): \{ label", cfg.group(1), re.M) if cfg else []
        row_keys = re.findall(r"^  (\w+): ", ts.split("export type ForeclosuresRow = {")[1].split("};")[0], re.M)
        check(cfg_keys == ["openingBid", "estValue"] and set(cfg_keys) <= set(row_keys),
              "chart config keys are row keys")
        check(ts.count("{") == ts.count("}") and ts.count("[") == ts.count("]"), "ts braces balance")

        # no unique column → warning, no row key
        (t / "nokey.csv").write_text("Region,Amount\nNorth,10\nNorth,12\nSouth,9\n")
        p2 = json.loads(run(SCHEMA, t / "nokey.csv", "--format", "json").stdout)
        check(p2["rowKey"] is None and any("No unique column" in w for w in p2["warnings"]),
              "warns when no row key exists")

        # JSON input, {"rows": [...]} wrapper, and an explicit --id
        (t / "rows.json").write_text(json.dumps({"rows": [{"id": i, "visa_type": "H-4", "approvals": i * 10,
                                                           "fiscal_year": f"{2015 + i}-10-01"} for i in range(1, 8)]}))
        p3 = json.loads(run(SCHEMA, t / "rows.json", "--format", "json").stdout)
        check(p3["rowKey"] == "id" and p3["chart"]["x"] == "fiscalYear", "JSON rows: id key and date axis")

        # big file → server-side warning
        with (t / "big.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["id", "amount"])
            w.writerows([[i, i % 97] for i in range(6000)])
        p4 = json.loads(run(SCHEMA, t / "big.csv", "--format", "json").stdout)
        check(p4["rowsTotal"] == 6000 and p4["rowsInSample"] == 2000 and any("6,000 rows" in w for w in p4["warnings"]),
              "large file: samples 2000 rows and warns to page on the server")

        r = run(SCHEMA, t / "missing.csv")
        check(r.returncode == 2 and "not found" in r.stderr, "missing file → exit 2")

        # --- token_check: a clean project
        good = t / "good"
        write(good, {
            "package.json": json.dumps({"dependencies": {"next": "16", "react": "19", "next-themes": "1"}}),
            "src/app/globals.css": GOOD_CSS,
            "src/app/layout.tsx": '<html lang="en" suppressHydrationWarning><body className="dark:bg-background" /></html>\n',
            "src/components/wensity/data-table.tsx": "const c = '#123456';\n",   # vendor file: skipped
            "src/app/page.tsx": "export default function P() { return <main className='text-brand-500' />; }\n",
            ".gitignore": "node_modules/\n.wensity-tmp/\n",
            ".mcp.json": json.dumps({"mcpServers": {"wensity": {"command": "npx", "args": ["-y", "@wensity/mcp@0.1.2"]}}}),
            "wensity.json": json.dumps({"style": "wsty1.eAKUL", "iconLibrary": "lucide"}),
        })
        r = run(TOKENS, good, "--json")
        res = json.loads(r.stdout)
        levels = [f["level"] for f in res["findings"]]
        check(r.returncode == 0 and "error" not in levels and "warn" not in levels,
              f"clean project passes (got {[f['msg'] for f in res['findings'] if f['level'] != 'note']})")
        check(res["css"] == "src/app/globals.css" and res["brand"] == ["brand"], "finds stylesheet and brand ramp")
        check(not any("hex" in f["msg"] for f in res["findings"]), "Wensity's own files are skipped for hex colors")

        # --- token_check: a project with problems
        bad = t / "bad"
        write(bad, {
            "package.json": json.dumps({"dependencies": {"next": "16", "next-themes": "1"}}),
            "app/globals.css": '@import "tailwindcss";\n@theme {\n  --color-brand-500: #f00;\n}\n:root { --x: 1; }\n',
            "app/layout.tsx": '<html lang="en"><body className="dark:bg-black" /></html>\n',
            "app/page.tsx": "export const P = () => <div className='bg-chili-500' style={{color: '#ff0000'}} />;\n",
            ".mcp.json": json.dumps({"mcpServers": {"wensity": {"command": "npx", "args": ["-y", "@wensity/mcp@latest"]}}}),
            ".wensity-tmp/plan.json": "{}",
        })
        subprocess.run(["git", "init", "-q", str(bad)], check=True)
        subprocess.run(["git", "-C", str(bad), "add", "-f", ".wensity-tmp/plan.json"], check=True)
        r = run(TOKENS, bad)
        o = r.stdout
        check(r.returncode == 1, "problem project fails with exit 1")
        check("not `@theme inline`" in o, "flags @theme without inline")
        check("@wensity/mcp@latest" in o and "pin an exact version" in o, "flags unpinned MCP server")
        check(".wensity-tmp/ is tracked" in o and "Add `.wensity-tmp/` to .gitignore" in o, "flags installer temp folder")
        check("no .dark block" in o, "flags dark mode used without .dark values")
        check("missing step(s) 300, 800" in o, "flags incomplete brand ramp")
        check("still use chili-*" in o, "flags leftover chili-* after rename")
        check("suppressHydrationWarning" in o, "flags missing suppressHydrationWarning with next-themes")
        check("hard-coded hex" in o and "app/page.tsx (1)" in o, "notes hex colors in the user's files")

        r = run(TOKENS, good, "--fail-on", "warn")
        check(r.returncode == 0, "--fail-on warn passes a clean project")
        empty = t / "empty"
        empty.mkdir()
        r = run(TOKENS, empty)
        check(r.returncode == 1 and "No stylesheet with an @theme block" in r.stdout, "no stylesheet → error")

    # --- plugin files are well formed
    pj = json.loads((PLUGIN / ".claude-plugin/plugin.json").read_text())
    market = json.loads((ROOT / ".claude-plugin/marketplace.json").read_text())
    check(pj["name"] == "top30-wensity" and any(p["name"] == "top30-wensity" and p["source"] == "./plugins/top30-wensity"
                                                for p in market["plugins"]), "plugin listed in marketplace.json")
    mcp = json.loads((PLUGIN / "templates/mcp.json").read_text())
    check(mcp["mcpServers"]["wensity"]["args"][-1].startswith("@wensity/mcp@0."), "MCP template is pinned")
    for md in sorted(PLUGIN.glob("skills/*/SKILL.md")) + sorted(PLUGIN.glob("agents/*.md")):
        head = md.read_text().split("---")
        fm = head[1] if len(head) > 2 else ""
        name = re.search(r"^name: (\S+)$", fm, re.M)
        want = md.parent.name if md.name == "SKILL.md" else md.stem
        check(bool(name) and name.group(1) == want and re.search(r"^description: .{40,}", fm, re.M) is not None,
              f"{md.relative_to(PLUGIN)} frontmatter")
    scout = (PLUGIN / "agents/wensity-ui-scout.md").read_text().split("---")[1]
    check("wensity_install" not in scout and "Write" not in scout and "Edit" not in scout, "scout has no write tools")

    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
