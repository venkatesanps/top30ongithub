#!/usr/bin/env python3
"""Turn a CSV or JSON data sample into a Wensity dashboard plan.

Standard library only. Reads the file, infers a type per column, and writes:

  plan  (default)  Markdown: columns, row key, chart series, KPIs, filters, the
                   primitives to install and warnings (unsafe keys, no row id, size).
  ts               A TypeScript module: the row type, a raw-row mapper that renames
                   headers to CSS-safe keys and parses numbers/dates, column specs,
                   a chart config whose keys match the row keys, and KPI specs.
  json             The same plan as JSON, for agents.

Usage:
  schema_to_ui.py data.csv [--name Foreclosure] [--format plan|ts|json] [--out FILE]
                  [--id COLUMN] [--sample 2000]

The column specs are plain objects ({key, label, type, sortable, align, format}).
Wensity's Data Table takes `columns` of its own DataTableColumn type: after
`wensity add data-table`, read that type in components/wensity/data-table.tsx and
map the specs once (the skill shows how). Chart config uses the documented shape
{ <seriesKey>: { label, color } }; Wensity turns each key into --color-<key>, which
is why keys must be CSS-identifier safe.
"""
import argparse
import csv
import json
import re
import sys
from datetime import datetime
from pathlib import Path

SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
DATE_FORMATS = ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%d %H:%M:%S",
                "%m/%d/%Y", "%m/%d/%y", "%Y/%m/%d", "%d-%b-%Y", "%b %d, %Y", "%Y-%m")
TRUE_FALSE = {"true", "false", "yes", "no", "y", "n", "t", "f"}
NUM_CLEAN = re.compile(r"[,$%\s]")
BIG_ROWS = 5000
CATEGORY_MAX = 25           # distinct values at most, to be a filterable category
SELECT_MAX = 12             # up to this many options: Select; more: Combobox


def read_rows(path, limit):
    p = Path(path)
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() in (".json", ".ndjson", ".jsonl"):
        if p.suffix.lower() in (".ndjson", ".jsonl"):
            data = [json.loads(line) for line in text.splitlines() if line.strip()]
        else:
            data = json.loads(text)
            if isinstance(data, dict):  # {"rows": [...]} or {"data": [...]}
                data = next((v for v in data.values() if isinstance(v, list)), [])
        rows = [r for r in data if isinstance(r, dict)]
        headers = []
        for r in rows[:limit]:
            for k in r:
                if k not in headers:
                    headers.append(k)
        total = len(rows)
        return headers, [{h: ("" if r.get(h) is None else str(r.get(h))) for h in headers} for r in rows[:limit]], total
    reader = csv.DictReader(text.splitlines())
    headers = [h for h in (reader.fieldnames or []) if h is not None]
    rows, total = [], 0
    for r in reader:
        total += 1
        if len(rows) < limit:
            rows.append({h: (r.get(h) or "") for h in headers})
    return headers, rows, total


def safe_key(header, taken):
    words = re.findall(r"[A-Za-z0-9]+", header)
    if not words:
        base = "col"
    else:
        base = words[0].lower() + "".join(w[:1].upper() + w[1:].lower() for w in words[1:])
    if base[0].isdigit():
        base = "c" + base
    key, n = base, 2
    while key in taken:
        key, n = f"{base}{n}", n + 1
    taken.add(key)
    return key


def as_number(v):
    s = NUM_CLEAN.sub("", v)
    if s.startswith("(") and s.endswith(")"):
        s = "-" + s[1:-1]
    try:
        return float(s)
    except ValueError:
        return None


def date_format(values):
    for fmt in DATE_FORMATS:
        ok = 0
        for v in values:
            try:
                datetime.strptime(v.strip(), fmt)
                ok += 1
            except ValueError:
                break
        if values and ok == len(values):
            return fmt
    return None


def infer(header, values):
    vals = [v.strip() for v in values if v is not None and v.strip() != ""]
    info = {"nonEmpty": len(vals), "empty": len(values) - len(vals)}
    distinct = set(vals)
    info["distinct"] = len(distinct)
    if not vals:
        return {**info, "type": "text"}
    if {v.lower() for v in distinct} <= TRUE_FALSE and len(distinct) <= 2:
        return {**info, "type": "boolean"}
    fmt = date_format(vals[:200])
    if fmt:
        return {**info, "type": "date", "dateFormat": fmt}
    nums = [as_number(v) for v in vals]
    if all(n is not None for n in nums):
        looks_id = re.search(r"(^|_|\b)(id|zip|zipcode|postal|phone|code)$", header.strip().lower())
        if looks_id:
            return {**info, "type": "id-like"}
        money = any("$" in v for v in vals[:200])
        pct = any(v.endswith("%") for v in vals[:200])
        integer = all(float(n).is_integer() for n in nums)
        return {**info, "type": "number", "format": "currency" if money else "percent" if pct else
                "integer" if integer else "decimal", "min": min(nums), "max": max(nums)}
    repeats = len(distinct) <= len(vals) // 2 if len(vals) >= 20 else len(distinct) < len(vals)
    if len(distinct) <= CATEGORY_MAX and repeats:
        return {**info, "type": "category", "values": sorted(distinct)[:SELECT_MAX]}
    return {**info, "type": "text"}


def build_plan(headers, rows, total, id_col=None):
    taken, cols = set(), []
    for h in headers:
        meta = infer(h, [r.get(h, "") for r in rows])
        key = safe_key(h, taken)
        meta.update(header=h, key=key, label=h.strip() or key, renamed=(key != h))
        cols.append(meta)
    warnings, notes = [], []

    # row key: Data Table needs row.id or getRowId
    row_key = None
    if id_col:
        row_key = next((c for c in cols if c["header"] == id_col), None)
        if not row_key:
            warnings.append(f"--id {id_col!r} is not a column.")
    if not row_key:
        named = [c for c in cols if c["header"].strip().lower() in ("id", "_id", "uuid", "key")
                 or c["header"].strip().lower().endswith(("_id", " id"))]
        # an id-named column, else a unique text-like column (unique amounts or dates aren't ids)
        others = [c for c in cols if c not in named and c["type"] in ("id-like", "text")]
        for c in named + others:
            vals = [r.get(c["header"], "") for r in rows]
            if c["empty"] == 0 and len(set(vals)) == len(vals):
                row_key = c
                break
    if row_key:
        vals = [r.get(row_key["header"], "") for r in rows]
        if len(set(vals)) != len(vals) or row_key["empty"]:
            warnings.append(f"Row key {row_key['header']!r} has duplicates or blanks in the sample: "
                            "selection can't tell those rows apart.")
        if row_key["key"] != "id":
            notes.append(f"Pass getRowId={{(row) => String(row.{row_key['key']})}} to DataTable "
                         "(it defaults to row.id).")
    else:
        warnings.append("No unique column found. Data Table selection needs row.id or getRowId: "
                        "build an id from columns that are unique together, or add one upstream.")

    unsafe = [c for c in cols if not SAFE_KEY.match(c["header"])]
    if unsafe:
        warnings.append("Headers that aren't CSS-safe keys (chart colors become --color-<key>): "
                        + ", ".join(f"{c['header']!r} → {c['key']}" for c in unsafe[:12])
                        + ("…" if len(unsafe) > 12 else "") + ". Map raw rows through the generated mapper.")
    if total > BIG_ROWS:
        warnings.append(f"{total:,} rows. Data Table works on the array you pass it: page, filter or aggregate "
                        "on the server (or in DuckDB) and send it one page or a summary.")

    dates = [c for c in cols if c["type"] == "date"]
    numbers = [c for c in cols if c["type"] == "number"]
    cats = [c for c in cols if c["type"] == "category"]
    x_axis = dates[0] if dates else (cats[0] if cats else None)
    series = numbers[:4]
    if len(numbers) > 4:
        notes.append(f"{len(numbers)} numeric columns; charting the first 4. Pick the ones that matter.")

    if x_axis and x_axis["type"] == "date":
        chart = "ChartArea" if len(series) > 1 else "ChartLine"
    elif x_axis:
        chart = "ChartBar"
    else:
        chart = None
    if cats and numbers and len(cats[0].get("values", [])) <= 6:
        notes.append(f"Share of {numbers[0]['label']} by {cats[0]['label']}: ChartPie works for ≤ 6 slices.")

    kpis = []
    for c in numbers[:4]:
        agg = "avg" if c["format"] in ("percent", "decimal") else "sum"
        kpis.append({"label": c["label"], "key": c["key"], "aggregate": agg, "format": c["format"],
                     "sparkline": bool(dates)})
    kpis.insert(0, {"label": "Records", "key": None, "aggregate": "count", "format": "integer",
                    "sparkline": bool(dates)})

    filters = []
    for c in cats:
        filters.append({"key": c["key"], "label": c["label"],
                        "control": "select" if c["distinct"] <= SELECT_MAX else "combobox"})
    if dates:
        filters.insert(0, {"key": dates[0]["key"], "label": dates[0]["label"], "control": "date-picker"})
    texts = [c for c in cols if c["type"] == "text"]

    install = ["sidebar", "card", "tabs", "chart", "data-table", "skeleton", "empty-state", "badge"]
    if any(f["control"] == "select" for f in filters):
        install.append("select")
    if any(f["control"] == "combobox" for f in filters):
        install.append("combobox")
    if dates:
        install.append("date-picker")

    return {
        "rowsInSample": len(rows), "rowsTotal": total,
        "columns": [{k: c[k] for k in ("header", "key", "label", "type", "renamed", "distinct", "empty")
                     if k in c} | {k: c[k] for k in ("format", "dateFormat", "min", "max", "values") if k in c}
                    for c in cols],
        "rowKey": row_key["key"] if row_key else None,
        "search": [c["key"] for c in texts + cats][:5],
        "chart": {"component": chart, "x": x_axis["key"] if x_axis else None,
                  "series": [{"key": c["key"], "label": c["label"]} for c in series]},
        "kpis": kpis, "filters": filters,
        "install": {"primitives": install, "components": ["metric-sparkline-card"] if dates and numbers else []},
        "warnings": warnings, "notes": notes,
    }


def pascal(s):
    parts = re.findall(r"[A-Za-z0-9]+", s) or ["Data"]
    out = "".join(p[:1].upper() + p[1:] for p in parts)
    return ("D" + out) if out[0].isdigit() else out


TS_TYPES = {"number": "number", "boolean": "boolean", "date": "string", "category": "string",
            "text": "string", "id-like": "string"}


def render_ts(plan, name):
    N = pascal(name)
    n = N[:1].lower() + N[1:]
    lines = [f"// Generated by top30-wensity schema_to_ui.py from a {plan['rowsInSample']}-row sample. Edit freely.",
             "", f"export type {N}Row = {{"]
    for c in plan["columns"]:
        lines.append(f"  {c['key']}: {TS_TYPES.get(c['type'], 'string')}{' | null' if c['type'] == 'number' else ''};"
                     f"{'  // was ' + json.dumps(c['header']) if c['renamed'] else ''}")
    lines += ["};", "",
              "const toNumber = (v: unknown): number | null => {",
              "  if (typeof v === \"number\") return Number.isFinite(v) ? v : null;",
              "  const s = String(v ?? \"\").replace(/[,$%\\s]/g, \"\").replace(/^\\((.*)\\)$/, \"-$1\");",
              "  if (s === \"\") return null;",
              "  const x = Number(s);",
              "  return Number.isFinite(x) ? x : null;",
              "};",
              "const toBool = (v: unknown) => /^(true|yes|y|t|1)$/i.test(String(v ?? \"\").trim());",
              "",
              f"/** Raw row (original headers) → {N}Row (CSS-safe keys, parsed values). Dates stay as source strings. */",
              f"export function to{N}Row(raw: Record<string, unknown>): {N}Row {{",
              "  return {"]
    for c in plan["columns"]:
        src = f"raw[{json.dumps(c['header'])}]"
        val = {"number": f"toNumber({src})", "boolean": f"toBool({src})"}.get(c["type"], f"String({src} ?? \"\")")
        lines.append(f"    {c['key']}: {val},")
    lines += ["  };", "}", "",
              "export type ColumnSpec = {",
              f"  key: keyof {N}Row;",
              "  label: string;",
              "  type: \"number\" | \"date\" | \"category\" | \"text\" | \"boolean\" | \"id-like\";",
              "  sortable: boolean;",
              "  align: \"left\" | \"right\";",
              "  format?: \"currency\" | \"percent\" | \"integer\" | \"decimal\";",
              "};", "",
              "// Map these to Wensity's DataTableColumn once (see components/wensity/data-table.tsx).",
              f"export const {n}ColumnSpecs: ColumnSpec[] = ["]
    for c in plan["columns"]:
        fmt = f", format: {json.dumps(c['format'])}" if "format" in c else ""
        lines.append(f"  {{ key: {json.dumps(c['key'])}, label: {json.dumps(c['label'])}, type: {json.dumps(c['type'])}, "
                     "sortable: true, "
                     f"align: {json.dumps('right' if c['type'] == 'number' else 'left')}{fmt} }},")
    lines += ["];", "",
              f"export const {n}RowKey = {json.dumps(plan['rowKey'])};  // null: build an id before using selection",
              "", "// Keys match the row keys, so tooltips, legends and series share one --color-<key>.",
              "// No color set: Wensity falls back to the six theme chart colors (set by your preset).",
              f"export const {n}ChartConfig = {{"]
    for s in plan["chart"]["series"]:
        lines.append(f"  {s['key']}: {{ label: {json.dumps(s['label'])} }},")
    lines += ["};", "",
              f"export const {n}Chart = {json.dumps(plan['chart'])} as const;", "",
              f"export const {n}Kpis = {json.dumps(plan['kpis'], indent=2)} as const;", "",
              f"export const {n}Filters = {json.dumps(plan['filters'], indent=2)} as const;", ""]
    return "\n".join(lines)


def render_plan(plan, name, source):
    L = [f"# Dashboard plan: {name}", "",
         f"Source `{source}`: {plan['rowsTotal']:,} rows ({plan['rowsInSample']:,} sampled), "
         f"{len(plan['columns'])} columns. Row key: `{plan['rowKey'] or 'none'}`.", ""]
    if plan["warnings"]:
        L += ["## Fix first", ""] + [f"- {w}" for w in plan["warnings"]] + [""]
    L += ["## Columns", "", "| Header | Key | Type | Detail |", "|---|---|---|---|"]
    for c in plan["columns"]:
        d = c.get("format") or c.get("dateFormat") or (f"{c['distinct']} values" if c["type"] == "category" else "")
        L.append(f"| {c['header']} | `{c['key']}` | {c['type']} | {d}{' · ' + str(c['empty']) + ' blank' if c['empty'] else ''} |")
    ch = plan["chart"]
    L += ["", "## Layout", "",
          "1. **Sidebar** (`sidebar`) with the page sections; **Tabs** (`tabs`) for views.",
          "2. **Filter bar:** " + (", ".join(f"{f['label']} ({f['control']})" for f in plan["filters"]) or "search only")
          + (f"; search on {', '.join('`' + s + '`' for s in plan['search'])}" if plan["search"] else "") + ".",
          "3. **KPI row:** " + ", ".join(f"{k['label']} ({k['aggregate']})" for k in plan["kpis"])
          + (" with sparklines over time (`metric-sparkline-card`)" if plan["install"]["components"] else " in `card`s") + ".",
          f"4. **Chart:** {ch['component'] or 'none (no date or category axis found)'}"
          + (f", x = `{ch['x']}`, series = {', '.join('`' + s['key'] + '`' for s in ch['series'])}" if ch["component"] else "") + ".",
          "5. **Data Table** (`data-table`): sortable, filterable, paginated; numbers right-aligned; "
          "`skeleton` while loading, `empty-state` when filters match nothing.", ""]
    if plan["notes"]:
        L += ["## Notes", ""] + [f"- {x}" for x in plan["notes"]] + [""]
    L += ["## Install (free primitives)", "", "```bash",
          "npx wensity@latest add " + " ".join(plan["install"]["primitives"]), "```"]
    if plan["install"]["components"]:
        L += ["", "Components (check the tier with `wensity_search` first): "
              + ", ".join(f"`{c}`" for c in plan["install"]["components"])]
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("source")
    ap.add_argument("--name")
    ap.add_argument("--format", choices=("plan", "ts", "json"), default="plan")
    ap.add_argument("--out")
    ap.add_argument("--id", dest="id_col")
    ap.add_argument("--sample", type=int, default=2000)
    a = ap.parse_args(argv)
    if not Path(a.source).is_file():
        print(f"error: {a.source} not found", file=sys.stderr)
        return 2
    headers, rows, total = read_rows(a.source, a.sample)
    if not headers:
        print("error: no columns found (empty file or not CSV/JSON rows)", file=sys.stderr)
        return 2
    name = a.name or Path(a.source).stem
    plan = build_plan(headers, rows, total, a.id_col)
    out = {"plan": lambda: render_plan(plan, name, a.source), "ts": lambda: render_ts(plan, name),
           "json": lambda: json.dumps(plan, indent=2) + "\n"}[a.format]()
    if a.out:
        Path(a.out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.out).write_text(out)
        print(f"wrote {a.out}", file=sys.stderr)
    else:
        sys.stdout.write(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
