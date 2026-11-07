---
name: wensity-dashboard-kit
description: Build a data dashboard on Wensity UI's free React primitives (Sidebar, Tabs, filters, KPI cards, Recharts charts, Data Table) from a CSV/JSON sample or a table schema - infer columns, CSS-safe keys, row ids, chart series, KPIs and filters, then plan, install and wire the page. Use when the user wants a dashboard, admin page, analytics view or data table in a React/Next.js/Vite app with Wensity, or points at a data file and says "make a dashboard of this".
---

# Wensity dashboard kit

Wensity ships typed `.tsx` source into your repo (React 18.2+, TypeScript 5+, Tailwind CSS v4;
Next.js, Vite, Remix, Astro). All 57 primitives are free and MIT, including **Data Table**
(search, sort, selection, pagination, expandable rows, no TanStack) and **Chart** (Recharts: line,
bar, area, pie, radar, interactive bar). A dashboard needs no Pro license.

```bash
S="python3 ${CLAUDE_PLUGIN_ROOT}/skills/wensity-dashboard-kit/scripts/schema_to_ui.py"   # or this folder's scripts/
```

## 0. Check the fit first

- **Not React?** Streamlit, plain HTML or a Python app can't use Wensity as is. Say so, and
  offer a React (Vite) front end that reads the same data (an API, a JSON export or DuckDB-WASM).
- **One self-contained HTML file wanted?** Build with Vite + `vite-plugin-singlefile`; check the
  output opens from disk with no network.
- **Gaps:** there's no map component (use MapLibre GL or Leaflet), no app-shell block (compose
  Sidebar + Tabs + Card), and Data Table works on the array you hand it (page or aggregate on the
  server past a few thousand rows).

## 1. Profile the data

`$S data.csv --name <Thing>` prints a plan: column types, the row key, chart axis and series,
KPIs, filters, the install command, and **Fix first** warnings. `--format ts --out
src/dashboard/<thing>.schema.ts` writes the row type, a `to<Thing>Row()` mapper, column specs,
chart config and KPI/filter specs. `--format json` is for agents. `--id <column>` forces the key.

Two rules the script enforces, because both fail quietly:

- **Row ids.** Data Table tells rows apart by `row.id` or `getRowId`. Without a unique key, selecting
  one row selects others. Use the plan's row key, or build one upstream.
- **Keys = CSS identifiers.** Chart `config` keys must match data keys, and each key becomes
  `--color-<key>`. A header like `Opening Bid ($)` breaks the color variable. Map raw rows through
  the generated mapper so keys are camelCase.

## 2. Set up once per project

1. Theme first: follow `wensity-brand-preset` (one preset, chart palette included).
2. MCP server, pinned, project scope (Wensity advises against `@latest` for a server that writes files):
   `claude mcp add --transport stdio --scope project wensity -- npx -y @wensity/mcp@0.1.2`
   (or copy `${CLAUDE_PLUGIN_ROOT}/templates/mcp.json` to `.mcp.json`). Restart, then `/mcp`.
3. Commit or stash first: package-manager changes are **not** rolled back by the installer.

## 3. Plan, approve, install

Use the `wensity-ui-scout` agent (read-only) or the tools directly: `wensity_search` →
`wensity_get_item` → `wensity_inspect_project` → `wensity_plan_install`. Show the user the files,
the Tailwind token diff and the exact package command. Install with `wensity_install` **only after
they say yes**; plans expire after 10 minutes and run once, so re-plan if they took longer. Without
MCP: `npx wensity@latest add <slugs from the plan>`.

## 4. Wire the page

Layout, top to bottom: **Sidebar** (sections) · header with **Tabs** (views) · filter bar (Date
Picker for the date column, Select for ≤ 12 options, Combobox for more, Input search) · KPI row
(KPI Card with Sparkline when there's a date axis, else Card) · one main **Chart** · **Data Table**.

- Read `components/wensity/data-table.tsx` for the real `DataTableColumn` fields, then write one
  `toColumns(specs)` adapter from the generated specs. Don't guess prop names.
- Chart: wrap the Recharts chart in Wensity's container with the generated `config`; series keys
  are the row keys. No colors in config → theme chart colors from the preset.
- Numbers right-aligned, formatted with `Intl.NumberFormat` (currency, percent); dates parsed once.
- States: **Skeleton** while loading, **Empty State** when filters match nothing, **Alert** on
  load errors. Filters live in the URL (search params) so views can be shared.
- Charts read their colors from tokens; follow the `dataviz` skill if it's installed.

## 5. Check

Run the `wensity-ui-qa` agent, or at least: `npx tsc --noEmit`, lint, build (the installer does no
formatting or type checks), and `python3 ${CLAUDE_PLUGIN_ROOT}/skills/wensity-brand-preset/scripts/token_check.py`.
Look at it in light and dark, at 375 px wide, and with keyboard only.
