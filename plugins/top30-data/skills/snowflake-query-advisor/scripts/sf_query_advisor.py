#!/usr/bin/env python3
"""Read Snowflake SQL and explain how it will run: an estimated plan tree, what will be expensive,
and specific changes to make it faster and cheaper. Optionally reads the real plan and runtime
statistics the user exports from Snowflake, which turn estimates into measurements.

  sf_query_advisor.py analyze PATH [PATH ...] [options]   report on .sql files or folders
  sf_query_advisor.py queries PATH                        print the read-only SQL to run in Snowflake

analyze options (all optional; each one adds evidence):
  --explain FILE      output of EXPLAIN USING JSON (or SYSTEM$EXPLAIN_PLAN_JSON, or a CSV/TSV of
                      EXPLAIN USING TABULAR). Repeat it for several statements, in order.
  --stats FILE        GET_QUERY_OPERATOR_STATS(<query_id>) rows, CSV or JSON
  --history FILE      QUERY_HISTORY rows for the query, CSV or JSON (time, size, spill, queueing)
  --tables FILE       INFORMATION_SCHEMA.TABLES rows (ROW_COUNT, BYTES, CLUSTERING_KEY), CSV or JSON
  --columns FILE      INFORMATION_SCHEMA.COLUMNS rows (TABLE_NAME, COLUMN_NAME, DATA_TYPE): type checks on joins and
                      filters, checked date rewrites, SELECT * expanded to the real column list
  --attribution FILE  QUERY_ATTRIBUTION_HISTORY rows for the run, and/or the per-pattern summary `queries` prints:
                      Snowflake's own per-query credits instead of rate x time (repeatable)
  --warehouse SIZE    XS..6XL, used for the credit estimate when history doesn't say
  --generation 1|2    warehouse generation (default 1; pass 2 only for a warehouse you know is Gen2)
  --cloud aws|azure|gcp   for Gen2 rates (default aws)
  --credit-price USD  per credit, for dollar figures (default 3.00)
  --runs-per-day N    to turn per-run cost into a daily figure
  --md FILE / --json FILE   write the report / findings (Markdown goes to stdout otherwise)
  --sarif FILE        findings as SARIF 2.1.0 (GitHub code scanning and other SARIF viewers)
  --brief             one line per finding on stdout (path:line: [severity] rule: title), for hooks and CI logs
  --fail-on SEVERITY  exit 1 if any finding is at least this severe (high, medium, low, info)
  --changed-only [REF]  only files changed against REF's merge base (default HEAD), plus untracked files
  --config FILE / --no-config   settings file; by default the nearest .sf-advisor.toml or .sf-advisor.json
                      up to the git root (keys: disable, severity, exclude, fail_on, generation, cloud,
                      credit_price, warehouse). Command-line options win.

Turn a rule off for one spot with a SQL comment: `-- sf-advisor: disable=select-star` on the line it reports,
`-- sf-advisor: disable-next-line=rule[,rule]` above it, or `-- sf-advisor: disable-file=rule` anywhere.
Without `=rules` the comment turns off every rule. Turned-off findings are listed in the report.

It never connects to Snowflake and never runs the SQL: it reads files only. Needs sqlglot
(pip install sqlglot). Statements it can't parse are reported and still get text-level checks.
Rates and rules are from Snowflake documentation checked 2026-11-19 (references/execution-facts.md).
"""
import argparse
import csv
import fnmatch
import hashlib
import io
import json
import os
import re
import subprocess
import sys
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

try:
    import sqlglot
    from sqlglot import exp
except ImportError:  # pragma: no cover
    sys.exit("sf_query_advisor needs sqlglot: pip install sqlglot")

SEV_ORDER = {"high": 0, "medium": 1, "low": 2, "info": 3}
SIZES = ["XS", "S", "M", "L", "XL", "2XL", "3XL", "4XL", "5XL", "6XL"]
SIZE_ALIASES = {"XSMALL": "XS", "X-SMALL": "XS", "SMALL": "S", "MEDIUM": "M", "LARGE": "L", "XLARGE": "XL", "X-LARGE": "XL",
                "XXLARGE": "2XL", "X2LARGE": "2XL", "2X-LARGE": "2XL", "XXXLARGE": "3XL", "X3LARGE": "3XL", "3X-LARGE": "3XL",
                "X4LARGE": "4XL", "4X-LARGE": "4XL", "X5LARGE": "5XL", "5X-LARGE": "5XL", "X6LARGE": "6XL", "6X-LARGE": "6XL"}
GEN2_FACTOR = {"aws": 1.35, "gcp": 1.35, "azure": 1.25}
NONDETERMINISTIC = {"RANDOM", "UUID_STRING", "RANDSTR"}  # the examples Snowflake's result-reuse docs give
TIME_NOW = {"CURRENT_TIMESTAMP", "SYSDATE", "GETDATE", "LOCALTIMESTAMP", "CURRENT_TIME", "SYSTIMESTAMP"}
GB = 1024 ** 3
VERSION = "0.3.0"
HOME = "https://github.com/venkatesanps/top30ongithub/tree/main/plugins/top30-data/skills/snowflake-query-advisor"


# ---------------------------------------------------------------- input handling

def norm_size(s):
    if not s:
        return None
    s = str(s).strip().upper().replace(" ", "").replace("_", "")
    s = SIZE_ALIASES.get(s, s)
    return s if s in SIZES else None


def credits_per_hour(size, generation=1, cloud="aws"):
    size = norm_size(size)
    if not size:
        return None
    base = 2 ** SIZES.index(size)
    if generation == 2:
        if size in ("5XL", "6XL"):
            return None  # Gen2 isn't offered at 5XL/6XL
        return round(base * GEN2_FACTOR.get(cloud, 1.35), 4)
    return base


def strip_jinja(text):
    """dbt/Jinja to plain SQL with the same line numbers. ref() and source() become table names,
    config() and set/do blocks disappear, the first branch of each if is kept, loop bodies are kept
    once, and other expressions become the placeholder __jinja__."""
    found = bool(re.search(r"\{\{|\{%|\{#", text))
    if not found:
        return text, False

    def blank(m, repl=""):
        return repl + "\n" * m.group(0).count("\n")

    text = re.sub(r"\{#.*?#\}", blank, text, flags=re.S)
    # keep the first branch of if/elif/else: blank from {% elif/else %} to the matching {% endif %}
    out, depth, skip_at, pos = [], 0, None, 0
    for m in re.finditer(r"\{%-?\s*(if|elif|else|endif|for|endfor)\b.*?-?%\}", text, flags=re.S):
        tag = m.group(1)
        chunk = text[pos:m.start()]
        out.append(re.sub(r"[^\n]", " ", chunk) if skip_at is not None else chunk)
        if tag == "if":
            depth += 1
        elif tag in ("elif", "else") and skip_at is None:
            skip_at = depth
        elif tag == "endif":
            if skip_at == depth:
                skip_at = None
            depth -= 1
        out.append(re.sub(r"[^\n]", " ", m.group(0)))
        pos = m.end()
    tail = text[pos:]
    out.append(re.sub(r"[^\n]", " ", tail) if skip_at is not None else tail)
    text = "".join(out)
    text = re.sub(r"\{%.*?%\}", blank, text, flags=re.S)
    text = re.sub(r"\{\{-?\s*config\s*\(.*?\)\s*-?\}\}", blank, text, flags=re.S)
    text = re.sub(r"\{\{-?\s*ref\(\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]([^'\"]+)['\"]\s*)?\)\s*-?\}\}",
                  lambda m: blank(m, m.group(2) or m.group(1)), text)
    text = re.sub(r"\{\{-?\s*source\(\s*['\"]([^'\"]+)['\"]\s*,\s*['\"]([^'\"]+)['\"]\s*\)\s*-?\}\}",
                  lambda m: blank(m, f"{m.group(1)}.{m.group(2)}"), text)
    types = {"timestamp": "TIMESTAMP", "string": "VARCHAR", "int": "NUMBER", "bigint": "NUMBER", "numeric": "NUMBER",
             "float": "FLOAT", "boolean": "BOOLEAN", "date": "DATE"}
    text = re.sub(r"\{\{-?\s*(?:[\w]+\.)?type_(\w+)\s*\([^}]*\)\s*-?\}\}",
                  lambda m: blank(m, types.get(m.group(1).lower(), "VARCHAR")), text)
    text = re.sub(r"\{\{.*?\}\}", lambda m: blank(m, "__jinja__"), text, flags=re.S)
    return text, True


def split_statements(text):
    """[(sql, first_line)] split on top-level semicolons; strings, comments and $$ bodies respected."""
    out, buf_start, i, n = [], 0, 0, len(text)
    line_at = lambda pos: text.count("\n", 0, pos) + 1  # noqa: E731
    while i < n:
        c = text[i]
        if text.startswith("--", i) or text.startswith("//", i):
            j = text.find("\n", i)
            i = n if j == -1 else j
        elif text.startswith("/*", i):
            j = text.find("*/", i + 2)
            i = n if j == -1 else j + 2
        elif text.startswith("$$", i):
            j = text.find("$$", i + 2)
            i = n if j == -1 else j + 2
        elif c in ("'", '"'):
            j = i + 1
            while j < n:
                if text[j] == "\\" and c == "'":
                    j += 2
                    continue
                if text[j] == c:
                    if j + 1 < n and text[j + 1] == c:
                        j += 2
                        continue
                    break
                j += 1
            i = j + 1
        elif c == ";":
            chunk = text[buf_start:i]
            if chunk.strip():
                out.append(chunk)
            buf_start = i + 1
            i += 1
        else:
            i += 1
    if text[buf_start:].strip():
        out.append(text[buf_start:])
    res = []
    pos = 0
    for chunk in out:
        k = text.find(chunk, pos)
        pos = k + len(chunk)
        lead = len(chunk) - len(chunk.lstrip())
        res.append((chunk.strip(), line_at(k + lead)))
    return [(s, ln) for s, ln in res if re.sub(r"(--|//)[^\n]*|/\*.*?\*/", "", s, flags=re.S).strip()]


def read_rows(path):
    """Rows from CSV/TSV/JSON (a list of objects, or {"data"/"rows": [...]}); keys upper-cased."""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace").strip()
    rows = None
    if raw[:1] in "[{":
        try:
            data = json.loads(raw)
            if isinstance(data, dict):
                data = data.get("data") or data.get("rows") or data.get("result") or [data]
            rows = data
        except json.JSONDecodeError:
            rows = None
    if rows is None:
        dialect = csv.excel_tab if raw.split("\n", 1)[0].count("\t") > raw.split("\n", 1)[0].count(",") else csv.excel
        rows = list(csv.DictReader(io.StringIO(raw), dialect=dialect))
    out = []
    for r in rows:
        if isinstance(r, dict):
            out.append({str(k).strip().upper(): v for k, v in r.items()})
    return out


def as_obj(v):
    """VARIANT cells arrive as JSON text from CSV exports, or already as objects from JSON."""
    if isinstance(v, (dict, list)):
        return v
    if v in (None, "", "NULL", "null"):
        return {}
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return {}


def num(v, default=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------- EXPLAIN plans

def load_explain(path):
    """Normalized plan: {'global': {...}, 'ops': [{step,id,parents,operation,objects,alias,expressions,pt,pa,ba}]}"""
    raw = Path(path).read_text(encoding="utf-8-sig", errors="replace").strip()
    data = None
    for _ in range(3):  # a JSON string inside a JSON string inside a CSV cell, etc.
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            break
        if isinstance(data, str):
            raw = data.strip()
            continue
        break
    if data is None:
        # a CSV export (any header) with the JSON in one of its cells
        try:
            for row in csv.reader(io.StringIO(raw)):
                cell = next((c for c in row if c.strip().startswith("{") and "Operations" in c), None)
                if cell:
                    data = json.loads(cell)
                    break
        except (json.JSONDecodeError, csv.Error):
            data = None
    if isinstance(data, list) and data and isinstance(data[0], dict) and any(k.upper().startswith("SYSTEM$EXPLAIN") or k.upper() == "EXPLAIN" for k in data[0]):
        data = json.loads(next(iter(data[0].values())))
    if isinstance(data, dict) and "Operations" in data:
        ops = []
        for step_no, step in enumerate(data.get("Operations") or [], 1):
            for o in step:
                ops.append({"step": step_no, "id": o.get("id"), "parents": o.get("parentOperators") or [],
                            "operation": o.get("operation", "?"), "objects": o.get("objects") or [], "alias": o.get("alias"),
                            "expressions": o.get("expressions") or [], "pt": o.get("partitionsTotal"),
                            "pa": o.get("partitionsAssigned"), "ba": o.get("bytesAssigned")})
        return {"global": data.get("GlobalStats") or {}, "ops": ops}
    # tabular export
    rows = read_rows(path)
    if rows and "OPERATION" in rows[0]:
        g, ops = {}, []
        for r in rows:
            if (r.get("OPERATION") or "").strip() == "GlobalStats":
                g = {"partitionsTotal": num(r.get("PARTITIONSTOTAL")), "partitionsAssigned": num(r.get("PARTITIONSASSIGNED")),
                     "bytesAssigned": num(r.get("BYTESASSIGNED"))}
                continue
            parents = re.findall(r"\d+", str(r.get("PARENTOPERATORS") or ""))
            ops.append({"step": int(num(r.get("STEP"), 1) or 1), "id": int(num(r.get("ID"), 0)), "parents": [int(p) for p in parents],
                        "operation": r.get("OPERATION"), "objects": [x for x in [r.get("OBJECTS")] if x and x != "NULL"],
                        "alias": r.get("ALIAS") if r.get("ALIAS") not in ("", "NULL") else None,
                        "expressions": [x for x in [r.get("EXPRESSIONS")] if x and x != "NULL"],
                        "pt": num(r.get("PARTITIONSTOTAL"), None), "pa": num(r.get("PARTITIONSASSIGNED"), None),
                        "ba": num(r.get("BYTESASSIGNED"), None)})
        return {"global": g, "ops": ops}
    raise SystemExit(f"{path}: not an EXPLAIN plan (expected EXPLAIN USING JSON output or a TABULAR export)")


def render_explain(plan):
    lines = []
    by_step = defaultdict(list)
    for o in plan["ops"]:
        by_step[o["step"]].append(o)
    for step, ops in sorted(by_step.items()):
        if len(by_step) > 1:
            lines.append(f"Step {step}")
        ids = {o["id"]: o for o in ops}
        kids = defaultdict(list)
        for o in ops:
            for p in o["parents"]:
                kids[p].append(o)
        roots = [o for o in ops if not o["parents"] or not any(p in ids for p in o["parents"])]

        def walk(o, prefix, last, depth):
            label = o["operation"]
            if o["objects"]:
                label += " " + ", ".join(map(str, o["objects"]))
            if o["alias"]:
                label += f" AS {o['alias']}"
            if o["pt"] is not None and o["operation"] in ("TableScan", "ExternalScan"):
                label += f"  [partitions {fmt_int(o['pa'])} of {fmt_int(o['pt'])}, {fmt_bytes(o['ba'])}]"
            elif o["expressions"]:
                e = "; ".join(map(str, o["expressions"]))
                label += "  " + (e[:110] + "…" if len(e) > 110 else e)
            lines.append(prefix + ("" if depth == 0 else ("└─ " if last else "├─ ")) + label)
            ch = kids.get(o["id"], [])
            for k, c in enumerate(ch):
                walk(c, prefix + ("" if depth == 0 else ("   " if last else "│  ")), k == len(ch) - 1, depth + 1)

        for r in roots:
            walk(r, "", True, 0)
    return "\n".join(lines)


def fmt_int(v):
    return "?" if v is None else f"{int(v):,}"


def fmt_bytes(b):
    if b is None:
        return "? bytes"
    b = float(b)
    for unit in ("bytes", "KB", "MB", "GB", "TB", "PB"):
        if b < 1024 or unit == "PB":
            return f"{b:,.0f} {unit}" if unit == "bytes" else f"{b:,.1f} {unit}"
        b /= 1024
    return f"{b:.1f} PB"


# ---------------------------------------------------------------- SQL helpers

def line_of(node, base):
    for ident in [node] + list(node.find_all(exp.Identifier, exp.Literal, exp.Star)):
        meta = getattr(ident, "meta", None) or {}
        if meta.get("line"):
            return base + meta["line"] - 1
    return base


def snippet(node, n=90):
    try:
        s = node.sql(dialect="snowflake")
    except Exception:  # pragma: no cover
        s = str(node)
    s = " ".join(s.split())
    return s if len(s) <= n else s[: n - 1] + "…"


def unparen(e):
    while isinstance(e, exp.Paren):
        e = e.this
    return e


def conjuncts(e):
    e = unparen(e)
    if isinstance(e, exp.And):
        return conjuncts(e.this) + conjuncts(e.expression)
    return [e] if e is not None else []


def disjuncts(e):
    e = unparen(e)
    if isinstance(e, exp.Or):
        return disjuncts(e.this) + disjuncts(e.expression)
    return [e]


def cols(e):
    return list(e.find_all(exp.Column)) if e is not None else []


def is_constant(e):
    return e is not None and not cols(e) and not e.find(exp.Select)


def table_name(t):
    parts = [p for p in (t.catalog, t.db, t.name) if p]
    return ".".join(parts)


def own_select(node):
    """The SELECT a node belongs to (not crossing into subqueries)."""
    p = node.parent
    while p is not None and not isinstance(p, exp.Select):
        p = p.parent
    return p


def source_alias_map(sel):
    """alias -> (kind, name, node) for FROM and JOIN sources of one SELECT."""
    out = {}
    srcs = []
    f = sel.args.get("from_") or sel.args.get("from")
    if f is not None:
        srcs.append(f.this)
    for j in sel.args.get("joins") or []:
        srcs.append(j.this)
    for s in srcs:
        if isinstance(s, exp.Table) and isinstance(s.this, exp.Identifier):
            out[(s.alias_or_name or "").lower()] = ("table", table_name(s), s)
        elif isinstance(s, exp.Subquery):
            out[(s.alias or f"subquery{len(out)}").lower()] = ("subquery", None, s)
        else:
            out[(getattr(s, "alias", "") or f"src{len(out)}").lower()] = ("function", None, s)
    return out


def ctes_of(stmt):
    return {c.alias.lower(): c for c in stmt.find_all(exp.CTE) if c.alias}


# ---------------------------------------------------------------- the estimated plan

def node(op, detail="", children=None, **kw):
    return {"op": op, "detail": detail, "children": children or [], **kw}


def is_join_equality(p, alias=None):
    """col = col between two sources. Unqualified columns (TPC-H style l_orderkey = o_orderkey) can't be
    attributed to a table, so a pair with an unqualified side counts as a join equality."""
    p = unparen(p)
    if not isinstance(p, exp.EQ):
        return False
    lc, rc = cols(p.this), cols(p.expression)
    if not lc or not rc:
        return False
    lt, rt = {(c.table or "").lower() for c in lc}, {(c.table or "").lower() for c in rc}
    if "" in lt or "" in rt:
        return {c.sql() for c in lc} != {c.sql() for c in rc} and (alias is None or alias in lt | rt or "" in lt | rt)
    return lt != rt and (alias is None or alias in lt | rt)


def join_linked(alias, preds):
    """True if a WHERE predicate joins `alias` to another source; an OR counts when every branch does."""
    for p in preds:
        p = unparen(p)
        if is_join_equality(p, alias):
            return True
        if isinstance(p, exp.Or) and all(any(is_join_equality(c, alias) for c in conjuncts(d)) for d in disjuncts(p)):
            return True
    return False


def one_row(src, ctes):
    """A subquery or CTE that aggregates with no GROUP BY returns one row."""
    q = None
    if isinstance(src, exp.Subquery):
        q = src.this
    elif isinstance(src, exp.Table) and src.name.lower() in ctes:
        q = ctes[src.name.lower()].this
    q = unparen(q) if q is not None else None
    return isinstance(q, exp.Select) and q.args.get("group") is None and bool(q.expressions) \
        and all(e.find(exp.AggFunc) or e.find(exp.Literal) and not cols(e) for e in q.expressions)


def plan_query(q, ctes):
    q = unparen(q)
    if isinstance(q, exp.Subquery):
        return plan_query(q.this, ctes)
    if isinstance(q, (exp.Union, exp.Intersect, exp.Except)):
        kind = {exp.Union: "UnionAll", exp.Intersect: "Intersect", exp.Except: "Except"}[type(q)]
        n = node(kind, "", [plan_query(q.this, ctes), plan_query(q.expression, ctes)])
        if isinstance(q, exp.Union) and q.args.get("distinct"):
            n = node("Aggregate", "UNION removes duplicates", [n])
        return n
    if not isinstance(q, exp.Select):
        return node(type(q).__name__)
    aliases = source_alias_map(q)
    where = q.args.get("where")
    preds = conjuncts(where.this) if where is not None else []
    pushed = defaultdict(list)
    rest = []
    for p in preds:
        tabs = {(c.table or "").lower() for c in cols(p)}
        if p.find(exp.Select):
            rest.append(p)
        elif len(tabs) == 1 and next(iter(tabs)) in aliases:
            pushed[next(iter(tabs))].append(p)
        elif tabs == {""} and len(aliases) == 1:
            pushed[next(iter(aliases))].append(p)
        else:
            rest.append(p)
    used = defaultdict(set)
    for c in q.find_all(exp.Column):
        if own_select(c) is not q:
            continue
        key = (c.table or "").lower()
        if not key and len(aliases) == 1:
            key = next(iter(aliases))
        used[key].add(c.name)
    star = any(isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star)) for e in q.expressions)
    unqualified = len(aliases) > 1 and bool(used.get(""))

    def scan_of(alias):
        kind, name, src = aliases[alias]
        flt = " AND ".join(snippet(p, 70) for p in pushed.get(alias, []))
        if kind == "table" and name.lower() in ctes:
            n = node("WithReference", name, alias=alias)
        elif kind == "table":
            colinfo = "* (all columns)" if star else ", ".join(sorted(used.get(alias, set())))
            if unqualified:
                colinfo = (colinfo + " + " if colinfo else "") + "unqualified columns"
            n = node("TableScan", name, alias=alias, table=name, columns=colinfo or "no named columns", filter=flt or None,
                     unknown_filter=unqualified and not flt)
            return n
        elif kind == "subquery":
            n = plan_query(src.this, ctes)
        else:
            n = node("Flatten" if src.find(exp.Explode) or "FLATTEN" in snippet(src).upper() else "TableFunction", snippet(src, 50))
        if flt:
            n = node("Filter", flt, [n])
        return n

    order = list(aliases)
    cur = scan_of(order[0]) if order else node("Generator", "no FROM")
    for j, a in zip(q.args.get("joins") or [], order[1:]):
        on = j.args.get("on")
        kind = (j.args.get("kind") or "").upper()
        side = (j.args.get("side") or "").upper()
        if isinstance(j.this, (exp.Lateral, exp.Unnest, exp.TableFromRows)) or aliases[a][0] == "function":
            op = "Flatten (lateral)"
        elif kind == "CROSS" or (on is None and not j.args.get("using")):
            linked = join_linked(a, rest)
            op = "InnerJoin (keys in WHERE)" if linked else "CartesianJoin"
        else:
            op = {"LEFT": "LeftOuterJoin", "RIGHT": "RightOuterJoin", "FULL": "FullOuterJoin"}.get(side, "InnerJoin")
            if kind in ("SEMI", "ANTI"):
                op = kind.title() + "Join"
        cond = snippet(on, 80) if on is not None else (f"USING ({', '.join(snippet(x) for x in j.args.get('using'))})" if j.args.get("using") else "")
        cur = node(op, cond, [cur, scan_of(a)])
    if rest:
        cur = node("Filter", " AND ".join(snippet(p, 60) for p in rest), [cur])
    aggs = [e for e in q.expressions if any(own_select(f) is q and not f.find_ancestor(exp.Window) for f in e.find_all(exp.AggFunc))]
    group = q.args.get("group")
    if group is not None or aggs:
        keys = ", ".join(snippet(g, 30) for g in (group.expressions if group is not None else []))
        cur = node("Aggregate", (f"group by {keys}" if keys else "whole input") + (f"; {len(aggs)} aggregate(s)" if aggs else ""), [cur])
    if q.args.get("having") is not None:
        cur = node("Filter", "HAVING " + snippet(q.args["having"].this, 60), [cur])
    wins = [w for w in q.find_all(exp.Window) if own_select(w) is q]
    if wins:
        parts = {snippet(exp.Tuple(expressions=w.args.get("partition_by") or []), 40) if w.args.get("partition_by") else "(none)" for w in wins}
        cur = node("WindowFunction", f"{len(wins)} window(s), partition by {', '.join(sorted(parts))}", [cur])
    if q.args.get("qualify") is not None:
        cur = node("Filter", "QUALIFY " + snippet(q.args["qualify"].this, 60), [cur])
    if q.args.get("distinct") is not None:
        cur = node("Aggregate", "DISTINCT", [cur])
    order_by, limit = q.args.get("order"), q.args.get("limit")
    if order_by is not None and limit is not None:
        cur = node("SortWithLimit", f"{snippet(order_by, 50)} {snippet(limit, 20)}", [cur])
    elif order_by is not None:
        cur = node("Sort", snippet(order_by, 60), [cur])
    elif limit is not None:
        cur = node("Limit", snippet(limit, 20), [cur])
    return cur


def plan_statement(stmt):
    ctes = ctes_of(stmt)
    body = None
    if isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        body = node("Result", "", [plan_query(stmt, ctes)])
    elif isinstance(stmt, exp.Insert):
        body = node("Insert", table_name(stmt.this) if isinstance(stmt.this, exp.Table) else snippet(stmt.this, 40),
                    [plan_query(stmt.expression, ctes)] if stmt.expression is not None else [])
    elif isinstance(stmt, exp.Create) and isinstance(stmt.expression, (exp.Select, exp.Union, exp.Subquery, exp.Intersect, exp.Except)):
        kind = (stmt.args.get("kind") or "TABLE").upper()
        body = node({"VIEW": "CreateView", "TABLE": "CreateTableAsSelect"}.get(kind, f"Create{kind.title()}"), snippet(stmt.this, 50),
                    [plan_query(stmt.expression, ctes)])
    elif isinstance(stmt, exp.Merge):
        src = stmt.args.get("using")
        src_plan = plan_query(src.this, ctes) if isinstance(src, exp.Subquery) else node("TableScan", snippet(src, 50), table=table_name(src) if isinstance(src, exp.Table) else None, columns="")
        tgt = stmt.this
        body = node("Merge", table_name(tgt) if isinstance(tgt, exp.Table) else snippet(tgt, 40), [
            node("Join", snippet(stmt.args.get("on"), 80), [src_plan, node("TableScan", table_name(tgt) if isinstance(tgt, exp.Table) else "", table=table_name(tgt) if isinstance(tgt, exp.Table) else None, columns="join and updated columns")])])
    elif isinstance(stmt, (exp.Update, exp.Delete)):
        tgt = stmt.this
        scan = node("TableScan", table_name(tgt) if isinstance(tgt, exp.Table) else "", table=table_name(tgt) if isinstance(tgt, exp.Table) else None,
                    columns="", filter=snippet(stmt.args["where"].this, 70) if stmt.args.get("where") is not None else None)
        body = node(type(stmt).__name__, scan["detail"], [scan])
    if body is None:
        return None
    if ctes:
        body = node("WithClause", ", ".join(sorted(ctes)), [body] + [node("CTE " + name, "", [plan_query(c.this, ctes)]) for name, c in sorted(ctes.items())])
    return body


def render_plan(n, prefix="", last=True, depth=0, out=None):
    out = [] if out is None else out
    label = n["op"] + (f" {n['detail']}" if n.get("detail") else "")
    if n["op"] == "TableScan":
        extra = [f"columns: {n['columns']}"] if n.get("columns") else []
        if n.get("filter"):
            extra.append(f"filter: {n['filter']}")
        elif n.get("unknown_filter"):
            extra.append("filters use unqualified columns: see Filter above")
        elif n.get("table"):
            extra.append("no filter: every micro-partition")
        if n.get("size"):
            extra.append(n["size"])
        if extra:
            label += "  [" + "; ".join(extra) + "]"
    out.append(prefix + ("" if depth == 0 else ("└─ " if last else "├─ ")) + label)
    ch = n["children"]
    for k, c in enumerate(ch):
        render_plan(c, prefix + ("" if depth == 0 else ("   " if last else "│  ")), k == len(ch) - 1, depth + 1, out)
    return out


def walk_plan(n):
    yield n
    for c in n["children"]:
        yield from walk_plan(c)


# ---------------------------------------------------------------- rules

class Finding(dict):
    pass


def F(rule, sev, line, title, why, fix, evidence="", category="performance", rewrite=None):
    f = Finding(rule=rule, severity=sev, line=line, title=title, why=why, fix=fix, evidence=evidence, category=category)
    if rewrite:
        f["rewrite"] = rewrite
    return f


DATE_FUNCS = {"TO_DATE", "DATE", "TRY_TO_DATE"}


def rewrite_date_filter(cmp):
    """A range rewrite for common date-wrapping filters, or None."""
    left, right = unparen(cmp.this), unparen(cmp.expression)
    if not isinstance(cmp, exp.EQ):
        return None
    if is_constant(left) and not is_constant(right):
        left, right = right, left
    if not is_constant(right):
        return None
    col = next(iter(cols(left)), None)
    if col is None:
        return None
    c, v = col.sql(dialect="snowflake"), right.sql(dialect="snowflake")
    d = v if not (isinstance(right, exp.Literal) and right.is_string) else f"{v}::DATE"
    name = left.sql_name().upper() if isinstance(left, exp.Func) else ""
    if isinstance(left, exp.Cast) and left.to.is_type("date") or isinstance(left, (exp.TsOrDsToDate, exp.Date)) or name in DATE_FUNCS:
        return f"{c} >= {d} AND {c} < DATEADD(day, 1, {d})"
    if isinstance(left, exp.Year) or name == "YEAR":
        if right.is_int:
            y = int(right.name)
            return f"{c} >= '{y}-01-01'::DATE AND {c} < '{y + 1}-01-01'::DATE"
    if isinstance(left, (exp.DateTrunc, exp.TimestampTrunc)) or name in ("DATE_TRUNC", "TRUNC"):
        unit = left.args.get("unit")
        u = (unit.name if unit is not None else "").lower().strip("'") or "day"
        return f"{c} >= {d} AND {c} < DATEADD({u}, 1, {d})"
    return None


def wrapped_column(e):
    """The single column inside a function/cast/arithmetic, or None if e is a bare column or has 0/2+ columns."""
    e = unparen(e)
    if isinstance(e, exp.Column):
        return None
    cs = cols(e)
    if len({c.sql() for c in cs}) == 1 and not e.find(exp.Select):
        return cs[0]
    return None


def comparisons(pred):
    for e in pred.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Like, exp.ILike, exp.Between, exp.In):
        yield e


def rule_findings(stmt, base, text, tables_info):
    out = []
    selects = list(stmt.find_all(exp.Select))
    root_selects = []
    top = stmt
    if isinstance(stmt, exp.Create) and not isinstance(stmt.expression, (exp.Select, exp.Union, exp.Subquery, exp.Intersect, exp.Except)):
        return []  # a procedure, function or plain DDL: nothing to plan
    if isinstance(stmt, (exp.Insert, exp.Create)) and stmt.expression is not None:
        top = stmt.expression
    q = unparen(top)

    def branches(e):
        e = unparen(e)
        if isinstance(e, (exp.Union, exp.Intersect, exp.Except)):
            return branches(e.this) + branches(e.expression)
        if isinstance(e, exp.Subquery):
            return branches(e.this)
        return [e] if isinstance(e, exp.Select) else []

    root_selects = branches(q)
    dml_kind = type(stmt).__name__

    def big(name):
        info = tables_info.get((name or "").lower().split(".")[-1]) if tables_info else None
        return info

    # R1 SELECT * in the output
    for s in root_selects:
        star = next((e for e in s.expressions if isinstance(e, exp.Star) or (isinstance(e, exp.Column) and isinstance(e.this, exp.Star))), None)
        if star is None:
            continue
        aliases = source_alias_map(s)
        cte_names = set(ctes_of(stmt))
        tabs = [n for k, n, _ in aliases.values() if k == "table" and n.lower() not in cte_names]
        if not tabs:
            continue  # SELECT * FROM a CTE or subquery: the inner query already chose the columns
        info = [big(t) for t in tabs if big(t)]
        sev = "medium"
        if s.args.get("limit") is not None:
            sev = "low"
        if info and max(i["bytes"] for i in info) < GB:
            sev = "low"
        where = "INSERT/CTAS" if dml_kind in ("Insert", "Create") else "the result"
        out.append(F("select-star", sev, line_of(star, base), "SELECT * reads every column",
                     f"Snowflake stores data by column and reads only the columns a query names; * makes {where} carry all of them"
                     + (", from the whole table" if not s.args.get("where") else "") + ".",
                     "List the columns you use. In a pipeline, name them so a new upstream column can't widen the load.",
                     snippet(s, 80), "scan"))
        out[-1]["_select"], out[-1]["_star"] = s, star

    for s in selects:
        sw = s.args.get("where")
        aliases = source_alias_map(s)
        in_exists = s.find_ancestor(exp.Exists) is not None
        # R2 functions on filtered columns (WHERE and JOIN ON with a constant on the other side)
        preds = []
        if sw is not None:
            preds += conjuncts(sw.this)
        for j in s.args.get("joins") or []:
            if j.args.get("on") is not None:
                preds += conjuncts(j.args["on"])
        for p in preds:
            for cmp in comparisons(p):
                if own_select(cmp) is not s:
                    continue
                if isinstance(cmp, exp.Between):
                    subject, others = cmp.this, [cmp.args.get("low"), cmp.args.get("high")]
                elif isinstance(cmp, exp.In):
                    subject, others = cmp.this, cmp.expressions
                else:
                    a, b = cmp.this, cmp.expression
                    subject, others = (a, [b]) if is_constant(b) else (b, [a]) if is_constant(a) else (None, [])
                if subject is None or not all(is_constant(o) for o in others if o is not None):
                    continue
                col = wrapped_column(subject)
                if col is None:
                    continue
                json_path = subject.find(exp.JSONExtract) is not None
                rw = rewrite_date_filter(cmp)
                if json_path:
                    out.append(F("variant-path-filter", "low", line_of(cmp, base), f"Filter on a semi-structured path: {snippet(subject, 50)}",
                                 "Snowflake can prune on some VARIANT paths, but less reliably than on a regular column.",
                                 "If this filter is common, extract the field into its own column at load time and filter on that.",
                                 snippet(cmp, 80), "pruning"))
                    continue
                out.append(F("function-on-filter-column", "medium", line_of(cmp, base),
                             f"{snippet(subject, 50)} wraps the filtered column",
                             "Pruning compares the filter with each micro-partition's min/max for the column. Wrapping the column in a function or cast "
                             "can stop Snowflake from using those ranges, so more partitions are scanned.",
                             "Compare the raw column with a range of constants instead" + (" (this rewrite assumes the column is a DATE or TIMESTAMP):" if rw else "; put any function on the constant side."),
                             snippet(cmp, 80), "pruning", rewrite=rw))
                out[-1]["_col"] = col
            # R3 leading wildcard
            for lk in p.find_all(exp.Like, exp.ILike):
                pat = unparen(lk.expression)
                if isinstance(pat, exp.Literal) and pat.is_string and pat.name.startswith(("%", "_")) and own_select(lk) is s:
                    out.append(F("leading-wildcard", "low", line_of(lk, base), f"LIKE '{pat.name[:20]}' starts with a wildcard",
                                 "Min/max ranges can't rule out any micro-partition for a pattern that can match anywhere, so this predicate prunes nothing.",
                                 "Add a selective filter on another column if you can. For frequent substring lookups on a large table, search optimization "
                                 "(Enterprise edition; costs serverless credits and storage) can help.", snippet(lk, 80), "pruning"))
        # R4 OR across columns at the top of WHERE
        if sw is not None:
            ors = disjuncts(sw.this)
            if len(ors) > 1:
                colsets = [frozenset(c.sql() for c in cols(d)) for d in ors]
                if len(set(colsets)) > 1 and all(colsets):
                    out.append(F("or-across-columns", "low", line_of(sw, base), "WHERE is an OR across different columns",
                                 "Each branch could prune on its own column, but together a micro-partition can be skipped only if it fails every branch.",
                                 "If it's slow, split into a UNION ALL of the branches (deduplicate if a row can match both).", snippet(sw.this, 80), "pruning"))
        # R5 NOT IN (subquery)
        for e in s.find_all(exp.Not, exp.NEQ):
            if own_select(e) is not s:
                continue
            target = unparen(e.this) if isinstance(e, exp.Not) else unparen(e.expression)
            if (isinstance(target, exp.In) and target.args.get("query") is not None) or isinstance(target, exp.All):
                out.append(F("not-in-subquery", "medium", line_of(e, base), "NOT IN (subquery)",
                             "If the subquery returns a NULL, NOT IN returns no rows at all, and the NULL-aware anti-join is harder to optimize.",
                             "Use NOT EXISTS (SELECT 1 FROM ... WHERE inner.key = outer.key), which has the semantics people usually mean.",
                             snippet(e, 80), "correctness"))
        # R6 cartesian joins, R7 non-equi / OR joins, R8 functions in join keys
        order = list(aliases)
        where_preds = conjuncts(sw.this) if sw is not None else []
        for j, a in zip(s.args.get("joins") or [], order[1:]):
            on = j.args.get("on")
            kind = (j.args.get("kind") or "").upper()
            if isinstance(j.this, (exp.Lateral, exp.Unnest, exp.TableFromRows)) or aliases[a][0] == "function":
                continue
            if on is None and not j.args.get("using"):
                linked = join_linked(a, where_preds)
                tiny = one_row(aliases[a][2], ctes_of(stmt)) or one_row(aliases[order[0]][2], ctes_of(stmt))
                if not linked and not tiny:  # a cross join to a one-row aggregate is fine
                    sev = "low" if kind == "CROSS" else "high"
                    who = aliases[a][1] or a
                    who = f"{who} ({a})" if aliases[a][1] and a != (aliases[a][1] or "").lower().split(".")[-1] else who
                    out.append(F("cartesian-join", sev, line_of(j, base), f"{'CROSS JOIN' if kind == 'CROSS' else 'Join'} to {who} with no join condition",
                                 "Every row on one side pairs with every row on the other (a CartesianJoin): rows multiply and so does the work."
                                 + (" An explicit CROSS JOIN is usually deliberate: check that one side is small." if kind == "CROSS" else ""),
                                 "Add the join condition, or confirm the cross product is intended and both sides are small.",
                                 snippet(j, 80), "join"))
                continue
            if on is not None:
                parts = conjuncts(on)
                eqs = [p for p in parts if is_join_equality(p)]
                tiny = one_row(aliases[a][2], ctes_of(stmt)) or one_row(aliases[order[0]][2], ctes_of(stmt))
                if tiny:
                    pass  # comparing one-row aggregates: nothing to optimize
                elif isinstance(unparen(on), exp.Or) and not set.intersection(*[{unparen(c).sql() for c in conjuncts(d) if is_join_equality(c)} for d in disjuncts(on)]):
                    out.append(F("or-in-join", "medium", line_of(on, base), "OR in the join condition",
                                 "An OR across join keys usually can't use a hash join on one key, so far more row pairs are compared.",
                                 "Split into two joins combined with UNION ALL, or join on one key and filter on the other.", snippet(on, 80), "join"))
                elif not eqs:
                    out.append(F("non-equi-join", "medium", line_of(on, base), "Join without an equality between the two sides",
                                 "Range or inequality joins compare many row pairs; on large inputs they behave close to a cartesian join.",
                                 "Add an equality key if one exists (e.g. a bucketed date), or pre-filter both sides hard before the join.",
                                 snippet(on, 80), "join"))
                for p in eqs:
                    p = unparen(p)
                    if wrapped_column(p.this) is not None or wrapped_column(p.expression) is not None:
                        out.append(F("function-in-join-key", "low", line_of(p, base), f"Join key is computed: {snippet(p, 60)}",
                                     "Functions or casts on join keys run for every row and can stop runtime join filtering from pruning the probe side.",
                                     "Store keys with matching types, or compute the key once upstream.", snippet(p, 80), "join"))
        # R10 ORDER BY in a subquery or CTE without LIMIT
        if s.args.get("order") is not None and s.args.get("limit") is None and s not in root_selects and not in_exists \
                and s.find_ancestor(exp.Window) is None and not isinstance(s.parent, (exp.Insert, exp.Create)):
            out.append(F("inner-order-by", "low", line_of(s.args["order"], base), "ORDER BY inside a subquery or CTE",
                         "An inner ORDER BY doesn't decide the final order, but it can still cost a sort.",
                         "Sort once, in the outermost query.", snippet(s.args["order"], 60), "compute"))
        # R11 DISTINCT over joins
        if s.args.get("distinct") is not None and s.args.get("joins"):
            out.append(F("distinct-over-join", "low", line_of(s, base), "SELECT DISTINCT over a join",
                         "DISTINCT after a join often hides a join that multiplies rows; the duplicates are produced and then removed.",
                         "Check the join keys for a one-to-many fan-out; use EXISTS or pre-aggregate the many side instead.", snippet(s, 70), "join"))
        # R14 correlated subqueries
        outer = set(aliases)
        for sub in s.find_all(exp.Subquery):
            inner = sub.this if isinstance(sub.this, exp.Select) else None
            if inner is None or own_select(sub) is not s or sub.find_ancestor(exp.Exists) is not None:
                continue
            inner_aliases = set(source_alias_map(inner))
            refs = {(c.table or "").lower() for c in inner.find_all(exp.Column)} - inner_aliases - {""}
            if refs & outer:
                in_select_list = any(sub is e or sub in list(e.find_all(exp.Subquery)) for e in s.expressions)
                out.append(F("correlated-subquery", "medium" if in_select_list else "low", line_of(sub, base),
                             "Correlated subquery" + (" in the SELECT list" if in_select_list else ""),
                             "It refers to the outer query's " + ", ".join(sorted(refs & outer)) + ". Snowflake rewrites many of these into joins, but not all; "
                             "when it can't, the inner query runs per group of outer rows.",
                             "Rewrite as a join to a pre-aggregated subquery (GROUP BY the correlation key).", snippet(sub, 80), "compute"))
        # R15 window without PARTITION BY
        for w in s.find_all(exp.Window):
            if own_select(w) is s and not w.args.get("partition_by") and (w.args.get("order") is not None or isinstance(w.this, (exp.RowNumber,))):
                out.append(F("window-no-partition", "low", line_of(w, base), f"Window with no PARTITION BY: {snippet(w, 50)}",
                             "Without PARTITION BY the window is one partition, so its sort can't spread across the warehouse's nodes.",
                             "Partition by a key if the logic allows; for a global top-N use ORDER BY ... LIMIT instead.", snippet(w, 80), "compute"))
        # R16 huge IN lists
        for e in s.find_all(exp.In):
            if own_select(e) is s and len(e.expressions) > 200:
                out.append(F("large-in-list", "low", line_of(e, base), f"IN list with {len(e.expressions)} values",
                             "Very long literal lists make compilation slow and can't be cached across different lists.",
                             "Load the values into a temporary table and join to it.", f"{len(e.expressions)} literals", "compute"))
        # R12 COUNT(DISTINCT)
        for e in s.find_all(exp.Count):
            if own_select(e) is s and isinstance(e.this, exp.Distinct):
                out.append(F("count-distinct", "info", line_of(e, base), "COUNT(DISTINCT ...)",
                             "Exact distinct counts hold every distinct value in memory and can spill on high-cardinality columns.",
                             "If a small error is acceptable (dashboards, trends), APPROX_COUNT_DISTINCT is much cheaper.", snippet(e, 60), "compute"))

    # R9 UNION that removes duplicates
    for u in stmt.find_all(exp.Union):
        if u.args.get("distinct"):
            out.append(F("union-distinct", "low", line_of(u, base), "UNION (removes duplicates)",
                         "UNION sorts or hashes the combined rows to drop duplicates.",
                         "Use UNION ALL when the branches can't overlap or duplicates are fine.", "UNION", "compute"))
    # R13 functions that change per run (result cache)
    seen = set()
    for f in stmt.find_all(exp.Func):
        name = f.sql_name().upper()
        if isinstance(f, exp.Anonymous):
            name = str(f.this).upper()
        if isinstance(f, exp.Rand):
            name = "RANDOM"
        if isinstance(f, (exp.CurrentTimestamp, exp.CurrentTime)):
            name = "CURRENT_TIMESTAMP"
        if name in NONDETERMINISTIC and name not in seen:
            seen.add(name)
            out.append(F("no-result-reuse", "info", line_of(f, base), f"{name}() blocks result reuse",
                         "Snowflake doesn't reuse a cached result for queries with functions that return something different on each run.",
                         "Fine if intended. For repeated dashboard queries, move it out so identical runs can come from the result cache.", name, "cache"))
        elif name in TIME_NOW and name not in seen and isinstance(stmt, (exp.Select, exp.Union)):
            seen.add(name)
            out.append(F("current-time-reuse", "info", line_of(f, base), f"{name} changes on every run",
                         "Snowflake's docs don't say whether results of queries using it are reused, so don't count on the result cache here.",
                         "Nothing to change unless repeated runs of this query matter; then measure whether they're served from the cache.", name, "cache"))
    # R17 the same subquery written twice
    by_text = defaultdict(list)
    for sq in stmt.find_all(exp.Subquery):
        if isinstance(sq.this, exp.Select):
            by_text[" ".join(sq.this.sql(dialect="snowflake").split())].append(sq)
    for sq_sql, nodes in by_text.items():
        n = len(nodes)
        if n > 1 and len(sq_sql) > 40:
            out.append(F("repeated-subquery", "low", line_of(nodes[1], base), f"The same subquery appears {n} times",
                         "Each copy may be computed separately.", "Write it once as a CTE and reference it.", sq_sql[:80] + "…", "compute"))
    # R22 DML
    if isinstance(stmt, exp.Update) and stmt.args.get("where") is None:
        out.append(F("update-all-rows", "high", base, "UPDATE without WHERE",
                     "Every micro-partition of the table is rewritten.", "Add the WHERE you mean; for a full rebuild, CREATE OR REPLACE ... AS SELECT is usually cheaper.",
                     snippet(stmt, 60), "dml"))
    if isinstance(stmt, exp.Delete) and stmt.args.get("where") is None:
        out.append(F("delete-all-rows", "info", base, "DELETE without WHERE", "Deletes every row.",
                     "If that's the intent, TRUNCATE TABLE says so clearly.", snippet(stmt, 60), "dml"))
    if isinstance(stmt, exp.Merge):
        on = stmt.args.get("on")
        tgt = stmt.this
        talias = (tgt.alias_or_name if isinstance(tgt, exp.Table) else "").lower()
        tcols = [c for c in cols(on) if (c.table or "").lower() == talias]
        only_keys = all(isinstance(unparen(p), exp.EQ) and all(isinstance(unparen(x), exp.Column) for x in (unparen(p).this, unparen(p).expression)) for p in conjuncts(on))
        if tcols and only_keys:
            out.append(F("merge-full-target-scan", "medium", line_of(on, base), "MERGE matches on keys only",
                         "With only key equality in ON, the target table is usually scanned in full to find matches.",
                         "If the new rows cover a known window, add a target-side range in ON (e.g. AND t.event_date >= DATEADD(day, -3, CURRENT_DATE())) "
                         "so the target scan prunes; make sure no older row can match.", snippet(on, 80), "dml"))
    # LIMIT without ORDER BY at the top (correctness note)
    for s in root_selects:
        if s.args.get("limit") is not None and s.args.get("order") is None and not isinstance(stmt, (exp.Insert, exp.Create)):
            out.append(F("limit-without-order", "info", line_of(s.args["limit"], base), "LIMIT without ORDER BY",
                         "Which rows come back is not defined and can change between runs.", "Add ORDER BY if the rows matter.", snippet(s.args["limit"], 30), "correctness"))
    # dedupe (same rule, same line, same evidence)
    seen_keys, uniq = set(), []
    for f in out:
        k = (f["rule"], f["line"], f["evidence"])
        if k not in seen_keys:
            seen_keys.add(k)
            uniq.append(f)
    return uniq


def text_findings(sql, base):
    """Checks that work even when the statement doesn't parse."""
    out = []
    for m in re.finditer(r"(?i)\b(?:i?like)\s+'%", sql):
        out.append(F("leading-wildcard", "low", base + sql.count("\n", 0, m.start()), "LIKE with a leading wildcard (statement not parsed)",
                     "Prunes nothing.", "Add a selective filter on another column.", m.group(0), "pruning"))
    return out


# ---------------------------------------------------------------- evidence from Snowflake

def explain_findings(plan, base):
    out = []
    for o in plan["ops"]:
        if o["operation"] == "CartesianJoin":
            out.append(F("explain-cartesian", "high", None, "The plan has a CartesianJoin",
                         "Snowflake confirmed a join with no usable condition.", "Add or fix the join condition.", "; ".join(map(str, o["expressions"]))[:90], "join"))
        if o["operation"] in ("TableScan",) and o["pt"]:
            pt, pa, ba = o["pt"], o["pa"] or 0, o["ba"] or 0
            ratio = pa / pt if pt else 0
            name = ", ".join(map(str, o["objects"]))
            if pt >= 50 and ratio >= 0.8 and ba >= GB:
                sev = "high" if ba >= 100 * GB else "medium" if ba >= 10 * GB else "low"
                out.append(F("explain-poor-pruning", sev, None, f"{name}: compile-time pruning keeps {ratio:.0%} of {fmt_int(pt)} partitions ({fmt_bytes(ba)})",
                             "The filters on this table don't rule out micro-partitions at compile time. Runtime join filters may prune more; "
                             "operator stats after a run show the real number.",
                             "Filter on the column the data is ordered by (often a load date). If this table is large, queried far more than it changes, "
                             "and always filtered on the same columns, a clustering key on them can help; automatic clustering costs serverless credits.",
                             f"partitionsAssigned={fmt_int(pa)} partitionsTotal={fmt_int(pt)}", "pruning"))
    return out


def stats_findings(rows, base):
    base = None  # measured findings belong to the whole statement
    out = []
    if not rows:
        return out, []
    ops = []
    for r in rows:
        st = as_obj(r.get("OPERATOR_STATISTICS"))
        tb = as_obj(r.get("EXECUTION_TIME_BREAKDOWN"))
        at = as_obj(r.get("OPERATOR_ATTRIBUTES"))
        parents = r.get("PARENT_OPERATORS", r.get("PARENT_OPERATOR_ID"))
        ops.append({"id": r.get("OPERATOR_ID"), "type": r.get("OPERATOR_TYPE"), "parents": parents, "st": st, "tb": tb, "at": at,
                    "pct": num(tb.get("overall_percentage")) if isinstance(tb, dict) else 0.0})
    ops.sort(key=lambda o: -o["pct"])
    for o in ops:
        st = o["st"] if isinstance(o["st"], dict) else {}
        sp = st.get("spilling") or {}
        rem, loc = num(sp.get("bytes_spilled_remote_storage")), num(sp.get("bytes_spilled_local_storage"))
        name = o["type"] or "operator"
        if rem > 0:
            out.append(F("remote-spill", "high", base, f"{name} spilled {fmt_bytes(rem)} to remote storage",
                         "The operator ran out of memory and local disk, so it wrote to and read from remote storage: the slowest path.",
                         "First shrink its input: filter earlier, select fewer columns, fix any exploding join. Then test the same query one warehouse size up: "
                         "it costs 2x per second, so it pays off only if it runs more than twice as fast.", f"operator {o['id']}", "compute"))
        elif loc > 0:
            out.append(F("local-spill", "medium" if loc > 10 * GB else "low", base, f"{name} spilled {fmt_bytes(loc)} to local disk",
                         "Memory wasn't enough; local spill slows the operator.", "Reduce the rows and columns reaching it; size up only if that's not possible.",
                         f"operator {o['id']}", "compute"))
        pr = st.get("pruning") or {}
        tot, scn = num(pr.get("partitions_total")), num(pr.get("partitions_scanned"))
        if tot >= 50 and scn / tot >= 0.8:
            tname = (o["at"] or {}).get("table_name", "") if isinstance(o["at"], dict) else ""
            out.append(F("poor-pruning", "medium", base, f"{name} {tname}: scanned {fmt_int(scn)} of {fmt_int(tot)} partitions",
                         "Almost every micro-partition was read.", "See the pruning findings above; filter on the column the data is ordered by.",
                         f"operator {o['id']}", "pruning"))
        if name and "Join" in name:
            inp, outp = num(st.get("input_rows")), num(st.get("output_rows"))
            if inp > 0 and outp > 1.5 * inp and outp > 1e5:
                out.append(F("exploding-join", "high", base, f"{name} turns {fmt_int(inp)} input rows into {fmt_int(outp)}",
                             "A join producing more rows than it receives usually means a key isn't unique on the side it should be.",
                             "Check the join keys for duplicates; deduplicate or aggregate that side first.", f"operator {o['id']}", "join"))
        if name == "Filter":
            inp, outp = num(st.get("input_rows")), num(st.get("output_rows"))
            if inp > 1e6 and outp / inp < 0.05:
                out.append(F("late-filter", "medium", base, f"A Filter keeps {outp / inp:.1%} of {fmt_int(inp)} rows",
                             "Many rows were read only to be thrown away; pruning didn't catch this predicate.",
                             "Make the predicate prunable (raw column, constant range) or cluster on that column if it's always used.",
                             f"operator {o['id']}", "pruning"))
    top = [(o["type"], o["pct"]) for o in ops[:3] if o["pct"]]
    return out, top


def history_summary(rows, a):
    """Per-query credits from QUERY_HISTORY: rate x execution time (an estimate: a warehouse is shared)."""
    res = []
    for r in rows:
        size = norm_size(r.get("WAREHOUSE_SIZE")) or norm_size(a.warehouse)
        rate = credits_per_hour(size, a.generation, a.cloud)
        secs = num(r.get("EXECUTION_TIME")) / 1000.0
        cred = rate * secs / 3600.0 if rate is not None else None
        res.append({"query_id": r.get("QUERY_ID"), "size": size, "rate": rate, "exec_s": secs,
                    "compile_s": num(r.get("COMPILATION_TIME")) / 1000.0,
                    "queued_s": (num(r.get("QUEUED_OVERLOAD_TIME")) + num(r.get("QUEUED_PROVISIONING_TIME"))) / 1000.0,
                    "bytes": num(r.get("BYTES_SCANNED")), "pscan": num(r.get("PARTITIONS_SCANNED")), "ptot": num(r.get("PARTITIONS_TOTAL")),
                    "spill_l": num(r.get("BYTES_SPILLED_TO_LOCAL_STORAGE")), "spill_r": num(r.get("BYTES_SPILLED_TO_REMOTE_STORAGE")),
                    "cache_pct": num(r.get("PERCENTAGE_SCANNED_FROM_CACHE")), "credits": cred})
    return res


def history_findings(h, base):
    base = None
    out = []
    for q in h:
        if q["queued_s"] > 5:
            out.append(F("queued", "medium", base, f"Waited {q['queued_s']:.0f} s in the queue",
                         "The warehouse was busy (or starting) when the query arrived.",
                         "For many concurrent users, a multi-cluster warehouse (Enterprise edition) adds clusters for the busy periods; "
                         "or move this workload to its own warehouse.", f"query {q['query_id']}", "compute"))
        if q["compile_s"] > 5:
            out.append(F("slow-compile", "low", base, f"Compilation took {q['compile_s']:.0f} s",
                         "Very long IN lists, deeply nested views or huge UNION chains make compilation slow; it runs in cloud services.",
                         "Simplify the statement, or join to a table of values instead of long literal lists.", f"query {q['query_id']}", "compute"))
        if q["ptot"] >= 50 and q["pscan"] / q["ptot"] >= 0.8:
            out.append(F("history-poor-pruning", "medium", base, f"Scanned {fmt_int(q['pscan'])} of {fmt_int(q['ptot'])} partitions ({fmt_bytes(q['bytes'])})",
                         "Measured on a real run: pruning removed little.", "See the pruning findings; filter on the column the data is ordered by.",
                         f"query {q['query_id']}", "pruning"))
    return out


def load_tables(path):
    info = {}
    if not path:
        return info
    for r in read_rows(path):
        name = (r.get("TABLE_NAME") or r.get("NAME") or "").strip()
        if not name:
            continue
        info[name.lower().split(".")[-1]] = {"rows": num(r.get("ROW_COUNT") or r.get("ROWS")), "bytes": num(r.get("BYTES")),
                                             "clustering_key": (r.get("CLUSTERING_KEY") or "").strip() or None,
                                             "full": ".".join(x for x in (r.get("TABLE_CATALOG"), r.get("TABLE_SCHEMA"), name) if x)}
    return info


def annotate_sizes(plan, tables_info, findings):
    for n in walk_plan(plan):
        if n["op"] == "TableScan" and n.get("table"):
            info = tables_info.get(n["table"].lower().split(".")[-1])
            if not info:
                continue
            n["size"] = f"{fmt_bytes(info['bytes'])}, {fmt_int(info['rows'])} rows" + (f", clustered by {info['clustering_key']}" if info["clustering_key"] else "")
            if not n.get("filter") and not n.get("unknown_filter") and info["bytes"] >= 10 * GB:
                findings.append(F("unfiltered-large-scan", "medium" if info["bytes"] < 1024 * GB else "high", 0,
                                  f"{n['table']} ({fmt_bytes(info['bytes'])}) is read without a filter",
                                  "Every micro-partition is scanned unless a join filter prunes it at runtime.",
                                  "Filter it (a date window is typical), or join it after the small side so runtime join filtering can prune it.",
                                  n["table"], "scan"))
            if n.get("filter") and info["clustering_key"]:
                ck = info["clustering_key"].lower()
                fcols = set(re.findall(r"[a-z_][a-z0-9_$]*", n["filter"].lower()))
                if not any(c in ck for c in fcols if len(c) > 2):
                    findings.append(F("filter-not-on-clustering-key", "low", 0, f"{n['table']} is clustered by {info['clustering_key']}, but filtered on other columns",
                                      "Pruning works best on the columns the table is ordered by.",
                                      "If you can, add a filter on the clustering column too; otherwise expect a wider scan.", n["filter"][:80], "pruning"))


# ---------------------------------------------------------------- cost Snowflake attributed (QUERY_ATTRIBUTION_HISTORY)

def load_attribution(paths, hist_rows=()):
    """Per-query rows (QUERY_ID, ROOT_QUERY_ID, QUERY_PARAMETERIZED_HASH, CREDITS_ATTRIBUTED_COMPUTE,
    CREDITS_USED_QUERY_ACCELERATION) and per-pattern summary rows (RUNS, FIRST_START, LAST_START), as `queries` prints them.
    History rows that already carry CREDITS_ATTRIBUTED_COMPUTE (a join the user did) count as per-query rows."""
    runs, patterns = [], []
    for p in paths or []:
        for r in read_rows(p):
            if str(r.get("RUNS") or "").strip():
                patterns.append(r)
            elif str(r.get("CREDITS_ATTRIBUTED_COMPUTE") or "").strip():
                runs.append(r)
    runs += [r for r in hist_rows if str(r.get("CREDITS_ATTRIBUTED_COMPUTE") or "").strip()]
    return runs, patterns


def parse_ts(v):
    s = str(v or "").strip().replace("T", " ")
    for cut in (19, 16, 10):
        try:
            return datetime.fromisoformat(s[:cut])
        except ValueError:
            continue
    return None


def attributed_credits(query_id, runs):
    """Credits attributed to one query plus its child queries (a stored procedure's statements), or None."""
    if not runs:
        return None
    if query_id:
        mine = [r for r in runs if query_id in (r.get("QUERY_ID"), r.get("ROOT_QUERY_ID"))]
    else:
        roots = {r.get("ROOT_QUERY_ID") or r.get("QUERY_ID") for r in runs}
        mine = runs if len(roots) == 1 else []
    if not mine:
        return None
    comp = sum(num(r.get("CREDITS_ATTRIBUTED_COMPUTE")) for r in mine)
    qas = sum(num(r.get("CREDITS_USED_QUERY_ACCELERATION")) for r in mine)
    top = next((r for r in mine if not r.get("ROOT_QUERY_ID") or r.get("ROOT_QUERY_ID") == r.get("QUERY_ID")), mine[0])
    return {"query_id": top.get("QUERY_ID"), "compute": comp, "qas": qas, "total": comp + qas, "rows": len(mine),
            "hash": top.get("QUERY_PARAMETERIZED_HASH") or None, "warehouse": top.get("WAREHOUSE_NAME") or None}


def pattern_summary(patterns, runs, qhash):
    """Every run of the same query shape (same QUERY_PARAMETERIZED_HASH): runs, credits, credits a day."""
    row = next((p for p in patterns if not qhash or (p.get("QUERY_PARAMETERIZED_HASH") or qhash) == qhash), None)
    if row is not None:
        n = num(row.get("RUNS"))
        credits = num(row.get("CREDITS_ATTRIBUTED_COMPUTE")) + num(row.get("CREDITS_USED_QUERY_ACCELERATION"))
        first, last = parse_ts(row.get("FIRST_START")), parse_ts(row.get("LAST_START"))
        qhash = qhash or row.get("QUERY_PARAMETERIZED_HASH")
    elif qhash:
        by_root = defaultdict(list)
        for r in runs:
            by_root[r.get("ROOT_QUERY_ID") or r.get("QUERY_ID")].append(r)
        mine = [rs for rs in by_root.values() if any(r.get("QUERY_PARAMETERIZED_HASH") == qhash for r in rs)]
        if len(mine) < 2:
            return None
        n = len(mine)
        credits = sum(num(r.get("CREDITS_ATTRIBUTED_COMPUTE")) + num(r.get("CREDITS_USED_QUERY_ACCELERATION")) for rs in mine for r in rs)
        times = [t for rs in mine for t in (parse_ts(r.get("START_TIME")) for r in rs) if t]
        first, last = (min(times), max(times)) if times else (None, None)
    else:
        return None
    days = max(1.0, (last - first).total_seconds() / 86400) if first and last and n >= 2 else None
    return {"hash": qhash, "runs": int(n), "credits": credits, "first": str(first or ""), "last": str(last or ""),
            "days": days, "per_day": credits / days if days else None}


# ---------------------------------------------------------------- schema-aware checks (INFORMATION_SCHEMA.COLUMNS)

def type_family(t):
    t = re.sub(r"\(.*", "", str(t or "")).strip().upper()
    if not t:
        return None
    if t.startswith("TIMESTAMP") or t == "DATETIME":
        return "timestamp"
    for fam, names in (("number", ("NUMBER", "DECIMAL", "NUMERIC", "INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "BYTEINT",
                                   "FLOAT", "FLOAT4", "FLOAT8", "DOUBLE", "DOUBLE PRECISION", "REAL", "FIXED")),
                       ("text", ("TEXT", "VARCHAR", "CHAR", "CHARACTER", "STRING", "NCHAR", "NVARCHAR", "NVARCHAR2", "CHAR VARYING")),
                       ("date", ("DATE",)), ("time", ("TIME",)), ("boolean", ("BOOLEAN",)),
                       ("semi", ("VARIANT", "OBJECT", "ARRAY", "MAP")), ("binary", ("BINARY", "VARBINARY"))):
        if t in names:
            return fam
    return "other"


def load_columns(path):
    """INFORMATION_SCHEMA.COLUMNS rows -> {table_lower: [{"key": (CATALOG, SCHEMA), "name": TABLE, "cols": {col_lower: (NAME, TYPE)}}]}."""
    info = {}
    if not path:
        return info
    rows = read_rows(path)
    rows.sort(key=lambda r: num(r.get("ORDINAL_POSITION"), 0))
    for r in rows:
        t = (r.get("TABLE_NAME") or "").strip()
        c = (r.get("COLUMN_NAME") or "").strip()
        if not t or not c:
            continue
        key = ((r.get("TABLE_CATALOG") or "").strip().upper(), (r.get("TABLE_SCHEMA") or "").strip().upper())
        entries = info.setdefault(t.lower(), [])
        e = next((x for x in entries if x["key"] == key), None)
        if e is None:
            e = {"key": key, "name": ".".join(x for x in (*key, t) if x), "cols": {}}
            entries.append(e)
        e["cols"][c.lower()] = (c, (r.get("DATA_TYPE") or r.get("TYPE") or "").strip())
    return info


def schema_entry(tnode, columns_info):
    entries = columns_info.get(tnode.name.lower()) if columns_info else None
    if not entries:
        return None
    db, cat = (tnode.db or "").upper(), (tnode.catalog or "").upper()
    if db:
        return next((e for e in entries if e["key"][1] in (db, "") and (not cat or e["key"][0] in (cat, ""))), None)
    if len(entries) == 1 or all(e["cols"] == entries[0]["cols"] for e in entries):
        return entries[0]
    return None  # the same table name in several schemas with different columns: don't guess


def resolve_name(sel, name, qualifier, columns_info, stmt, depth=0):
    """(family, TYPE, table) of column `name` as seen from SELECT `sel`, following CTEs and subqueries; None if unknown or ambiguous."""
    if sel is None or depth > 8:
        return None
    srcs = source_alias_map(sel)
    ctes = ctes_of(stmt)
    cand = [srcs.get(qualifier.lower())] if qualifier else list(srcs.values())
    hits = []
    for src in cand:
        if src is None:
            continue
        kind, _, nd = src
        t = None
        if kind == "table":
            cte = ctes.get(nd.name.lower()) if not nd.db else None
            if cte is not None:
                t = projection_type(cte.this, name, columns_info, stmt, depth + 1)
            else:
                e = schema_entry(nd, columns_info)
                if e and name in e["cols"]:
                    typ = e["cols"][name][1]
                    t = (type_family(typ), typ.upper(), e["name"])
        elif kind == "subquery":
            t = projection_type(nd.this, name, columns_info, stmt, depth + 1)
        if t:
            hits.append(t)
    return hits[0] if len(hits) == 1 else None


def projection_type(q, name, columns_info, stmt, depth):
    q = unparen(q)
    while isinstance(q, (exp.Union, exp.Intersect, exp.Except, exp.Subquery)):
        q = unparen(q.this)
    if not isinstance(q, exp.Select):
        return None
    for e in q.expressions:
        if isinstance(e, exp.Star):
            t = resolve_name(q, name, None, columns_info, stmt, depth)
            if t:
                return t
            continue
        if isinstance(e, exp.Column) and isinstance(e.this, exp.Star):
            t = resolve_name(q, name, e.table, columns_info, stmt, depth)
            if t:
                return t
            continue
        if (e.alias_or_name or "").lower() != name:
            continue
        inner = unparen(e.this if isinstance(e, exp.Alias) else e)
        if isinstance(inner, exp.Column):
            return resolve_name(q, inner.name.lower(), inner.table, columns_info, stmt, depth)
        if isinstance(inner, exp.Cast):
            typ = inner.to.sql(dialect="snowflake").upper()
            return (type_family(typ), typ, "a CAST")
        return None
    return None


def column_type(col, columns_info, stmt):
    if not columns_info or not isinstance(col, exp.Column) or isinstance(col.this, exp.Star):
        return None
    return resolve_name(own_select(col), col.name.lower(), col.table, columns_info, stmt)


def literal_family(e):
    e = unparen(e)
    if isinstance(e, exp.Neg):
        e = unparen(e.this)
    if isinstance(e, exp.Literal):
        return "text" if e.is_string else "number"
    if isinstance(e, exp.Cast):
        return type_family(e.to.sql(dialect="snowflake"))
    if isinstance(e, (exp.Date, exp.TsOrDsToDate, exp.CurrentDate)):
        return "date"
    if isinstance(e, (exp.CurrentTimestamp, exp.TimeStrToTime, exp.StrToTime)):
        return "timestamp"
    return None


COMPARABLE = [{"date", "timestamp"}]


def quote_ident(n):
    return n if re.fullmatch(r"[A-Z_][A-Z0-9_$]*", n) else '"' + n.replace('"', '""') + '"'


def schema_findings(stmt, base, columns_info, findings):
    """Checks that need column types, and type-aware updates to findings the rules already made."""
    out = []
    if not columns_info:
        return out
    ctes = ctes_of(stmt)
    # 1. function-on-filter-column: check the date rewrite against the column's real type
    for f in findings:
        col = f.get("_col")
        if f["rule"] != "function-on-filter-column" or col is None:
            continue
        t = column_type(col, columns_info, stmt)
        if t is None:
            if f.get("rewrite"):
                f["rewrite_status"] = "unchecked: the column's type isn't in the --columns export"
            continue
        fam, typ, tab = t
        f["confidence"] = "high"
        if fam in ("date", "timestamp"):
            if f.get("rewrite"):
                f["fix"] = f["fix"].replace("(this rewrite assumes the column is a DATE or TIMESTAMP)", f"({col.name} is {typ} in {tab}, so the range applies)")
                f["rewrite_status"] = f"type checked: {col.name} is {typ}" + (
                    "; TO_DATE uses each value's own time zone, the range uses the session's, so check the zone" if typ.startswith(("TIMESTAMP_TZ", "TIMESTAMP_LTZ")) else "")
        elif fam == "text":
            f.pop("rewrite", None)
            f["fix"] = (f"{col.name} is {typ} in {tab}, so the date is parsed from text on every row. If every value is written as YYYY-MM-DD, "
                        f"compare the text itself ({col.name} = 'YYYY-MM-DD', or a string range), which can prune; otherwise store it as DATE "
                        "(in the load or a staging model) and filter that column.")
            f["rewrite_status"] = "no rewrite: the column is text"
        elif f.get("rewrite"):
            f.pop("rewrite", None)
            f["rewrite_status"] = f"no rewrite: {col.name} is {typ}, not a date"
    # 2. SELECT *: the real column list
    for f in findings:
        s, star = f.get("_select"), f.get("_star")
        if f["rule"] != "select-star" or s is None:
            continue
        srcs = source_alias_map(s)
        if isinstance(star, exp.Column):  # t.*
            pick = {star.table.lower(): srcs.get(star.table.lower())}
        else:
            pick = srcs
        if not pick or any(v is None or v[0] != "table" or (not v[2].db and v[2].name.lower() in ctes) for v in pick.values()):
            continue
        entries = [(a, schema_entry(v[2], columns_info)) for a, v in pick.items()]
        if not all(e for _, e in entries):
            continue
        multi = len(srcs) > 1
        names = [f"{a}.{quote_ident(n)}" if multi else quote_ident(n) for a, e in entries for n, _ in e["cols"].values()]
        shown = ", ".join(names[:30]) + (f", … ({len(names) - 30} more)" if len(names) > 30 else "")
        f["why"] += f" Here that is {len(names)} column{'s' if len(names) != 1 else ''}."
        f["rewrite"] = f"SELECT {shown}"
        f["rewrite_status"] = "columns from the --columns export: keep only the ones you use"
        f["confidence"] = "high"
    # 3. joins and filters that compare different types
    seen = set()
    for s in stmt.find_all(exp.Select):
        preds = []
        for j in s.args.get("joins") or []:
            if j.args.get("on") is not None:
                preds += conjuncts(j.args["on"])
        w = s.args.get("where")
        if w is not None:
            preds += conjuncts(w.this)
        for p in preds:
            for cmp in p.find_all(exp.EQ, exp.NEQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.In):
                if own_select(cmp) is not s:
                    continue
                if isinstance(cmp, exp.In):
                    if cmp.args.get("query") is not None or not cmp.expressions:
                        continue
                    a, b = unparen(cmp.this), unparen(cmp.expressions[0])
                else:
                    a, b = unparen(cmp.this), unparen(cmp.expression)
                if isinstance(a, exp.Column) and isinstance(b, exp.Column) and isinstance(cmp, exp.EQ):
                    ta, tb = column_type(a, columns_info, stmt), column_type(b, columns_info, stmt)
                    if not ta or not tb or ta[0] == tb[0] or "other" in (ta[0], tb[0]) or {ta[0], tb[0]} in COMPARABLE:
                        continue
                    key = ("j", cmp.sql())
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append(F("join-type-mismatch", "medium" if {ta[0], tb[0]} == {"number", "text"} else "low", line_of(cmp, base),
                                 f"{a.sql(dialect='snowflake')} ({ta[1]}) is compared with {b.sql(dialect='snowflake')} ({tb[1]})",
                                 "Snowflake converts one side on every row to compare them. That costs CPU, can stop the join filter from pruning "
                                 "the other table, and for NUMBER against text it can fail, or not match values like '007' and 7.",
                                 "Give both keys the same type in the tables (or cast once in a staging model), then compare the raw columns.",
                                 snippet(cmp, 80), "join"))
                    out[-1]["confidence"] = "high"
                    continue
                col, const = (a, b) if isinstance(a, exp.Column) and is_constant(b) else (b, a) if isinstance(b, exp.Column) and is_constant(a) else (None, None)
                if col is None:
                    continue
                t = column_type(col, columns_info, stmt)
                lf = literal_family(const)
                if t and t[0] == "text" and lf in ("number", "date", "timestamp"):
                    key = ("c", cmp.sql())
                    if key in seen:
                        continue
                    seen.add(key)
                    word = {"number": "number", "date": "date", "timestamp": "timestamp"}[lf]
                    out.append(F("implicit-cast-filter", "medium", line_of(cmp, base), f"{col.sql(dialect='snowflake')} is {t[1]} but compared with a {word}",
                                 f"Snowflake converts the text column to a {word} to compare them, which can stop pruning on its min/max "
                                 "ranges, and one value that doesn't convert makes the whole query fail.",
                                 f"If the column really is text, compare it with a quoted string; if it holds {word}s, store it as "
                                 f"{'NUMBER' if lf == 'number' else lf.upper()}.", snippet(cmp, 80), "pruning"))
                    out[-1]["confidence"] = "high"
    # 4. qualified columns that the table doesn't have
    for c in stmt.find_all(exp.Column):
        if not c.table or isinstance(c.this, exp.Star):
            continue
        s = own_select(c)
        src = source_alias_map(s).get(c.table.lower()) if s is not None else None
        if not src or src[0] != "table" or (not src[2].db and src[2].name.lower() in ctes):
            continue
        e = schema_entry(src[2], columns_info)
        key = ("u", c.table.lower(), c.name.lower())
        if e and c.name.lower() not in e["cols"] and key not in seen:
            seen.add(key)
            out.append(F("unknown-column", "medium", line_of(c, base), f"{c.sql(dialect='snowflake')} isn't a column of {e['name']}",
                         "The --columns export has no such column, so the statement won't compile (or the export is out of date).",
                         "Check the spelling, or export the columns again.", snippet(c, 60), "correctness"))
            out[-1]["confidence"] = "high"
    return out


# ---------------------------------------------------------------- confidence

MEASURED_RULES = {"explain-poor-pruning", "explain-cartesian", "remote-spill", "local-spill", "poor-pruning", "exploding-join", "late-filter",
                  "queued", "slow-compile", "history-poor-pruning"}
SURE_RULES = {"select-star", "leading-wildcard", "not-in-subquery", "union-distinct", "update-all-rows", "delete-all-rows", "large-in-list",
              "no-result-reuse", "current-time-reuse", "limit-without-order", "inner-order-by"}
STEP_DOWN = {"high": "medium", "medium": "low", "low": "low"}


def assign_confidence(r, jinja):
    """high: measured, or certain from the SQL alone. medium: the cost depends on data the SQL doesn't show.
    low: text-level checks on unparsed SQL. One step down inside dbt/Jinja templates (the SQL was reconstructed)."""
    for f in r["findings"]:
        if f["rule"] in MEASURED_RULES:
            f["confidence"] = "high"
            continue
        if "confidence" not in f:
            f["confidence"] = "low" if not r["parsed"] else "high" if f["rule"] in SURE_RULES else "medium"
        if jinja:
            f["confidence"] = STEP_DOWN[f["confidence"]]
        if f.get("rewrite") and "rewrite_status" not in f:
            f["rewrite_status"] = "unchecked: test that it returns the same rows"


# ---------------------------------------------------------------- suppression and project config

DIRECTIVE = re.compile(r"(?:--|//|/\*|\{#)\s*sf-advisor:\s*(disable-next-line|disable-file|disable)\b(?:\s*=\s*([\w\-]+(?:\s*,\s*[\w\-]+)*))?", re.I)
CONFIG_NAMES = (".sf-advisor.toml", ".sf-advisor.json")
CONFIG_KEYS = {"disable", "severity", "exclude", "fail_on", "generation", "cloud", "credit_price", "warehouse"}


def directives(raw):
    """`-- sf-advisor: disable=rule[,rule]` (this line), `disable-next-line=...`, `disable-file=...`; no `=rules` means every rule."""
    by_line, file_rules = defaultdict(set), set()
    for i, ln in enumerate(raw.splitlines(), 1):
        for m in DIRECTIVE.finditer(ln):
            kind = m.group(1).lower()
            rules = {x.strip().lower() for x in (m.group(2) or "").split(",") if x.strip()} or {"*"}
            if kind == "disable-file":
                file_rules |= rules
            elif kind == "disable-next-line":
                by_line[i + 1] |= rules
            else:
                by_line[i] |= rules
    return by_line, file_rules


def is_suppressed(f, r, by_line, file_rules, cfg_disabled):
    rule = f["rule"]

    def hit(s):
        return "*" in s or rule in s
    if rule in cfg_disabled or hit(file_rules):
        return True
    if f["line"]:
        return hit(by_line.get(f["line"], set()))
    return any(hit(by_line.get(n, set())) for n in range(r["line"], r["end"] + 1))  # a finding with no line: anywhere in its statement


def find_config(start):
    p = Path(start).resolve()
    p = p if p.is_dir() else p.parent
    for d in [p, *p.parents]:
        for n in CONFIG_NAMES:
            if (d / n).is_file():
                return d / n
        if (d / ".git").exists():
            break
    return None


def load_config(path):
    """.sf-advisor.toml ([sf-advisor] table or top level) or .sf-advisor.json."""
    text = Path(path).read_text(encoding="utf-8")
    if str(path).endswith(".toml"):
        try:
            import tomllib
        except ImportError:  # pragma: no cover - Python < 3.11
            sys.exit(f"{path}: TOML config needs Python 3.11+; use .sf-advisor.json instead")
        data = tomllib.loads(text)
    else:
        data = json.loads(text)
    data = data.get("sf-advisor", data)
    unknown = set(data) - CONFIG_KEYS
    if unknown:
        sys.exit(f"{path}: unknown setting(s) {', '.join(sorted(unknown))}; known: {', '.join(sorted(CONFIG_KEYS))}")
    for rule, sev in (data.get("severity") or {}).items():
        if sev not in SEV_ORDER:
            sys.exit(f"{path}: severity for {rule} must be one of {', '.join(SEV_ORDER)}")
    data["disable"] = {x.lower() for x in data.get("disable") or []}
    data["_dir"] = Path(path).resolve().parent
    data["_path"] = str(path)
    return data


def excluded(path, cfg):
    pats = cfg.get("exclude") or []
    if not pats:
        return False
    try:
        rel = Path(path).resolve().relative_to(cfg["_dir"]).as_posix()
    except ValueError:
        rel = Path(path).as_posix()
    return any(fnmatch.fnmatch(rel, p) for p in pats)


def changed_files(ref):
    """Files changed against REF's merge base (or HEAD), committed or not, plus untracked files."""
    def git(*args):
        return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout
    try:
        root = git("rev-parse", "--show-toplevel").strip()
        against = git("merge-base", ref, "HEAD").strip() if ref else "HEAD"
        names = set(git("diff", "--name-only", "--diff-filter=ACMR", against).splitlines())
        names |= set(git("ls-files", "--others", "--exclude-standard", "--full-name").splitlines())
    except (OSError, subprocess.CalledProcessError) as e:
        sys.exit(f"--changed-only needs a git checkout with {ref or 'HEAD'} available: {getattr(e, 'stderr', '') or e}".strip())
    return {(Path(root) / n).resolve() for n in names if n}


# ---------------------------------------------------------------- SARIF (GitHub code scanning and other viewers)

SARIF_LEVEL = {"high": "error", "medium": "warning", "low": "note", "info": "note"}


def to_sarif(all_results):
    rules, results = {}, []
    for path, rs, _ in all_results:
        try:
            uri = Path(os.path.relpath(Path(path).resolve(), Path.cwd())).as_posix()
        except ValueError:  # another drive on Windows
            uri = ".."
        if uri.startswith(".."):  # outside the folder it ran from: an absolute file URI
            uri = Path(path).resolve().as_uri()
        for r in rs:
            for f in r["findings"]:
                if f["rule"] not in rules:
                    rules[f["rule"]] = {"id": f["rule"], "name": "".join(w.title() for w in f["rule"].split("-")),
                                        "shortDescription": {"text": f["rule"].replace("-", " ")},
                                        "fullDescription": {"text": f["why"]},
                                        "help": {"text": f["fix"]}, "helpUri": HOME,
                                        "defaultConfiguration": {"level": SARIF_LEVEL[f["severity"]]},
                                        "properties": {"tags": ["snowflake", f["category"]]}}
                msg = f"{f['title']}. {f['why']} Fix: {f['fix']}"
                if f.get("rewrite"):
                    msg += f" Rewrite ({f.get('rewrite_status', 'unchecked')}): {f['rewrite']}"
                fp = hashlib.sha1(f"{f['rule']}|{uri}|{' '.join((f['evidence'] or f['title']).split())}".encode()).hexdigest()
                results.append({"ruleId": f["rule"], "level": SARIF_LEVEL[f["severity"]], "message": {"text": msg},
                                "locations": [{"physicalLocation": {"artifactLocation": {"uri": uri},
                                                                    "region": {"startLine": max(1, f["line"] or r.get("code_line") or r["line"] or 1)}}}],
                                "partialFingerprints": {"sfQueryAdvisor/v1": fp},
                                "properties": {"severity": f["severity"], "confidence": f.get("confidence"), "category": f["category"],
                                               "statement": r["n"]}})
    return {"$schema": "https://json.schemastore.org/sarif-2.1.0.json", "version": "2.1.0",
            "runs": [{"tool": {"driver": {"name": "sf-query-advisor", "version": VERSION, "informationUri": HOME,
                                          "rules": list(rules.values())}},
                      "results": results}]}


def brief_lines(all_results):
    out = []
    for path, rs, _ in all_results:
        for r in rs:
            if r["error"]:
                out.append(f"{path}:{r.get('code_line') or r['line']}: [info] not-parsed: statement {r['n']} couldn't be parsed; only text checks ran")
            for f in r["findings"]:
                out.append(f"{path}:{f['line'] or r.get('code_line') or r['line']}: [{f['severity']}] {f['rule']}: {f['title']} ({f.get('confidence', '?')} confidence)")
    return out


# ---------------------------------------------------------------- report

def first_code_line(sql, base):
    """The first line of a statement that isn't blank or a comment (its text starts at any leading comment)."""
    in_block = False
    for i, ln in enumerate(sql.splitlines()):
        t = ln.strip()
        while t:
            if in_block:
                end = t.find("*/")
                if end == -1:
                    t = ""
                    break
                t, in_block = t[end + 2:].strip(), False
            elif t.startswith("/*"):
                t, in_block = t[2:], True
            elif t.startswith(("--", "//")):
                t = ""
            else:
                return base + i
    return base


def analyze_file(path, a, explains, stats_rows, hist_rows, tables_info, columns_info=None, attribution=None, cfg=None):
    cfg = cfg or {}
    runs, patterns = attribution or ([], [])
    raw = Path(path).read_text(encoding="utf-8", errors="replace")
    by_line, file_rules = directives(raw)
    text, jinja = strip_jinja(raw)
    stmts = split_statements(text)
    results = []
    # files named like <stem>_<k>.explain.json (as `queries` suggests) go to statement k; others in order
    numbered = {p["n"]: p for p in explains if p.get("n")}
    exp_iter = iter([p for p in explains if not p.get("n")])
    for k, (sql, line) in enumerate(stmts, 1):
        r = {"file": str(path), "n": k, "line": line, "end": line + sql.count("\n"), "kind": None, "parsed": False, "plan": None,
             "plan_source": "estimated from the SQL", "findings": [], "error": None, "sql": sql}
        try:
            parsed = sqlglot.parse(sql, read="snowflake")
            stmt = next((p for p in parsed if p is not None), None)
        except Exception as e:  # noqa: BLE001 - any parse failure is reported, not fatal
            stmt, r["error"] = None, str(e).split("\n")[0][:200]
        if stmt is not None and not isinstance(stmt, exp.Command):
            r["parsed"], r["kind"] = True, type(stmt).__name__
            if isinstance(stmt, exp.Create):
                r["kind"] = f"Create {(stmt.args.get('kind') or '').title()}".strip()
            plan = plan_statement(stmt)
            r["findings"] = rule_findings(stmt, line, sql, tables_info)
            r["findings"] += schema_findings(stmt, line, columns_info, r["findings"])
            if plan is not None:
                annotate_sizes(plan, tables_info, r["findings"])
                r["plan"] = "\n".join(render_plan(plan))
                r["tables"] = sorted({n["table"] for n in walk_plan(plan) if n.get("table")})
            else:
                r["tables"] = []
        else:
            r["kind"] = "unparsed" if stmt is None else "command"
            r["findings"] = text_findings(sql, line)
            r["tables"] = []
        if r["parsed"] and r["plan"] and r["kind"] in ("Select", "Union", "Insert", "Create Table", "Create View", "Merge", "Update", "Delete", "Intersect", "Except", "Subquery"):
            ep = numbered.get(k) if numbered else next(exp_iter, None)
            if ep is not None:
                r["plan"] = render_explain(ep)
                g = ep["global"] or {}
                r["plan_source"] = ("from EXPLAIN: " + f"{fmt_int(g.get('partitionsAssigned'))} of {fmt_int(g.get('partitionsTotal'))} partitions, "
                                    f"{fmt_bytes(g.get('bytesAssigned'))} after compile-time pruning")
                r["bytes_assigned"] = g.get("bytesAssigned")
                r["findings"] += explain_findings(ep, line)
        results.append(r)
    if len(results) == 1 or (results and len([r for r in results if r["parsed"]]) == 1):
        target = next(r for r in results if r["parsed"]) if any(r["parsed"] for r in results) else results[0]
        sf, top = stats_findings(stats_rows, target["line"])
        target["findings"] += sf
        target["top_operators"] = top
        h = history_summary(hist_rows, a) if hist_rows else []
        target["history"] = h
        target["findings"] += history_findings(h, target["line"])
        if runs or patterns:
            att = attributed_credits(h[0]["query_id"] if len(h) == 1 else None, runs)
            target["attributed"] = att
            target["pattern"] = pattern_summary(patterns, runs, (att or {}).get("hash"))
    elif stats_rows or hist_rows or runs or patterns:
        print("note: --stats/--history/--attribution are matched to a single statement; this file has several, so they were not used", file=sys.stderr)
    sev_over = cfg.get("severity") or {}
    for r in results:
        rules = {f["rule"] for f in r["findings"]}
        if rules & {"explain-poor-pruning", "poor-pruning"}:
            r["findings"] = [f for f in r["findings"] if f["rule"] != "history-poor-pruning"]
        if "explain-poor-pruning" in rules:
            explained = {f["title"].split(":")[0].upper() for f in r["findings"] if f["rule"] == "explain-poor-pruning"}
            r["findings"] = [f for f in r["findings"] if not (f["rule"] == "poor-pruning" and any(t in f["title"].upper() for t in explained))]
        r["code_line"] = first_code_line(r["sql"], r["line"])
        for f in r["findings"]:
            for k in ("_col", "_select", "_star"):
                f.pop(k, None)
            if f["line"] and f["line"] < r["code_line"]:
                f["line"] = r["code_line"]
            if f["rule"] in sev_over:
                f["severity"] = sev_over[f["rule"]]
        assign_confidence(r, jinja)
        off = [is_suppressed(f, r, by_line, file_rules, cfg.get("disable") or set()) for f in r["findings"]]
        r["suppressed"] = [f["rule"] for f, o in zip(r["findings"], off) if o]
        r["findings"] = [f for f, o in zip(r["findings"], off) if not o]
        r["findings"].sort(key=lambda f: (SEV_ORDER[f["severity"]], f["line"] or 0))
    return results, jinja


def sizing_note(r, a):
    b = r.get("bytes_assigned")
    if not b:
        return None
    gbs = b / GB
    if gbs < 1:
        s = "XS or S"
    elif gbs < 20:
        s = "S to M"
    elif gbs < 200:
        s = "M to L"
    elif gbs < 2000:
        s = "L to XL"
    else:
        s = "XL and up, after making sure pruning can't cut it down"
    return (f"EXPLAIN says up to {fmt_bytes(b)} will be read. As a starting point to test (not a rule), scans of this size usually run on {s}. "
            "Time the query on two adjacent sizes: the bigger one costs 2x per second, so keep it only if it finishes more than twice as fast.")


def attributed_line(att, r, a):
    t = att["total"]
    s = f"Credits Snowflake attributed to this run: {t:.4f} (${t * a.credit_price:.2f})"
    if att["qas"]:
        s += f", of which {att['qas']:.4f} were Query Acceleration"
    if att["rows"] > 1:
        s += f", across {att['rows']} queries (the statement and its child queries)"
    s += ". This is Snowflake's own figure, not an estimate; it leaves out warehouse idle time and cloud services."
    est = next((q["credits"] for q in r.get("history") or [] if q["credits"]), None)
    if est and att["compute"] > 0 and est > 1.25 * att["compute"]:
        s += (f" Rate × run time would have said {est:.4f}. A gap like that usually means the warehouse was shared with other queries "
              "while this one ran (or the size or generation used for the estimate is wrong).")
    if a.runs_per_day:
        s += f" At {a.runs_per_day:g} runs a day: {t * a.runs_per_day:.2f} credits (${t * a.credit_price * a.runs_per_day:.2f}) a day."
    return s


def pattern_line(p, a):
    h = f" (parameterized hash {p['hash'][:12]}…)" if p.get("hash") else ""
    s = f"Every run of this query shape{h}: {p['runs']} runs, {p['credits']:.2f} credits (${p['credits'] * a.credit_price:.2f})"
    if p["first"] and p["last"]:
        s += f" between {p['first'][:10]} and {p['last'][:10]}"
    if p["per_day"]:
        s += f", about {p['per_day']:.2f} credits (${p['per_day'] * a.credit_price:.2f}) a day"
    return s + (". A change that halves this query's cost saves about half of that. For every query shape on the warehouse, and its idle time, "
                "use the snowflake-cost-investigator skill.")


def report_md(all_results, a, inputs):
    lines = []
    total = Counter()
    for _, results, _ in all_results:
        for r in results:
            total.update(f["severity"] for f in r["findings"])
    ev = ["the SQL text"] + [x for x, ok in (("EXPLAIN plan", inputs["explain"]), ("operator stats", inputs["stats"]),
                                            ("query history", inputs["history"]), ("table sizes", inputs["tables"]),
                                            ("column types", inputs.get("columns")), ("attributed credits", inputs.get("attribution"))) if ok]
    lines.append("# Snowflake query review")
    lines.append("")
    lines.append(f"Evidence: {', '.join(ev)}. Findings: " + ", ".join(f"{total[s]} {s}" for s in SEV_ORDER if total[s]) + ("" if total else "none") + ".")
    if not inputs["explain"]:
        lines.append("")
        lines.append("Plans below are **estimated from the SQL**: Snowflake's optimizer may choose a different join order, and pruning numbers need "
                     "`EXPLAIN USING JSON` (it compiles without running; run `sf_query_advisor.py queries <file>` for the statements).")
    for path, results, jinja in all_results:
        lines.append("")
        lines.append(f"## {path}")
        if jinja:
            lines.append("")
            lines.append("dbt/Jinja found: `ref()`/`source()` became table names and other template blocks were blanked, so treat line numbers inside "
                         "macros as approximate.")
        for r in results:
            lines.append("")
            head = f"### Statement {r['n']} (lines {r['line']}–{r['end']}): {r['kind']}"
            lines.append(head)
            if r["error"]:
                lines.append("")
                lines.append(f"Couldn't parse this statement ({r['error']}); only text-level checks ran.")
            if r["plan"]:
                lines.append("")
                lines.append(f"Plan, {r['plan_source']}:")
                lines.append("")
                lines.append("```")
                lines.append(r["plan"])
                lines.append("```")
            if r.get("top_operators"):
                lines.append("")
                lines.append("Most expensive operators (share of execution time): " + ", ".join(f"{t} {p:.0f}%" for t, p in r["top_operators"]) + ".")
            att = r.get("attributed")
            for q in r.get("history") or []:
                lines.append("")
                cost = ""
                if q["credits"] is not None and not att:
                    cost = (f" At {q['size']} ({q['rate']} credits/hour, Gen{a.generation}{'' if a.generation == 1 else ' ' + a.cloud.upper()}) that is about "
                            f"{q['credits']:.4f} credits (${q['credits'] * a.credit_price:.2f}) per run")
                    if a.runs_per_day:
                        cost += f", {q['credits'] * a.runs_per_day:.2f} credits (${q['credits'] * a.credit_price * a.runs_per_day:.2f}) a day at {a.runs_per_day} runs"
                    cost += ". Estimate: a warehouse shared with other queries, its idle time and the 60-second minimum aren't attributed per query."
                lines.append(f"Measured run {q['query_id'] or ''}: {q['exec_s']:.1f} s executing, {q['compile_s']:.1f} s compiling, {q['queued_s']:.1f} s queued, "
                             f"{fmt_bytes(q['bytes'])} scanned ({q['cache_pct'] * 100 if q['cache_pct'] <= 1 else q['cache_pct']:.0f}% from cache), "
                             f"spill {fmt_bytes(q['spill_l'])} local / {fmt_bytes(q['spill_r'])} remote.{cost}")
            if att:
                lines.append("")
                lines.append(attributed_line(att, r, a))
            if r.get("pattern"):
                lines.append("")
                lines.append(pattern_line(r["pattern"], a))
            note = sizing_note(r, a)
            if note:
                lines.append("")
                lines.append(note)
            if r["findings"]:
                lines.append("")
                for f in r["findings"]:
                    loc = f" (line {f['line']})" if f["line"] else ""
                    lines.append(f"- **[{f['severity']}] {f['title']}**{loc} · {f.get('confidence', '?')} confidence. {f['why']} *Fix:* {f['fix']}")
                    if f.get("rewrite"):
                        lines.append(f"  - Rewrite ({f.get('rewrite_status', 'unchecked')}): `{f['rewrite']}`")
                    if f["evidence"]:
                        lines.append(f"  - Seen: `{f['evidence'].replace('`', '')}`")
            elif r["parsed"] and r["plan"] and not r.get("suppressed"):
                lines.append("")
                lines.append("No issues found by the checks.")
            elif r["parsed"] and not r["plan"]:
                lines.append("")
                lines.append("Not a query (DDL, a procedure or a command): nothing to plan.")
            if r.get("suppressed"):
                lines.append("")
                c = Counter(r["suppressed"])
                lines.append(f"Turned off by sf-advisor comments or config: " + ", ".join(f"{k}" + (f" ×{v}" if v > 1 else "") for k, v in sorted(c.items())) + ".")
    lines.append("")
    lines.append("## Before changing anything")
    lines.append("")
    lines.append("- Confirm with Snowflake: `EXPLAIN USING JSON <statement>` for the plan and pruning (no warehouse needed; uses a little cloud services "
                 "compute), and after a run `SELECT * FROM TABLE(GET_QUERY_OPERATOR_STATS('<query_id>'))` for what each operator really did.")
    lines.append("- Structural fixes carry their own running cost: clustering keys (automatic clustering credits and storage churn), search optimization "
                 "(Enterprise edition; serverless credits and storage), materialized views (Enterprise edition; refresh credits), Query Acceleration "
                 "(credits up to its scale factor). Prefer query rewrites first.")
    lines.append("- Measure before and after on the same warehouse size, with the result cache off for the test (`ALTER SESSION SET USE_CACHED_RESULT = FALSE`).")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- commands

def collect(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.rglob("*.sql") if f.is_file()
                            and not ({"target", "dbt_packages", "node_modules", ".git", "macros"} & set(f.relative_to(p).parts[:-1])))
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"not found: {p}")
    return files


def resolve_settings(a):
    """Command line first, then the project config (.sf-advisor.toml / .json), then the defaults."""
    cfg = {}
    if not a.no_config:
        cpath = a.config or find_config(a.paths[0])
        if cpath:
            cfg = load_config(cpath)
    gen = a.generation or cfg.get("generation") or 1
    if int(gen) not in (1, 2):
        sys.exit("generation must be 1 or 2")
    a.generation = int(gen)
    a.cloud = a.cloud or cfg.get("cloud") or "aws"
    if a.cloud not in GEN2_FACTOR:
        sys.exit("cloud must be aws, azure or gcp")
    a.credit_price = a.credit_price if a.credit_price is not None else float(cfg.get("credit_price") or 3.0)
    a.warehouse = a.warehouse or cfg.get("warehouse")
    a.fail_on = a.fail_on or cfg.get("fail_on")
    if a.fail_on and a.fail_on not in SEV_ORDER:
        sys.exit(f"fail_on must be one of {', '.join(SEV_ORDER)}")
    return cfg


def write_sarif(path, all_results):
    Path(path).write_text(json.dumps(to_sarif(all_results), indent=1) + "\n", encoding="utf-8")


def cmd_analyze(a):
    cfg = resolve_settings(a)
    explains = []
    for p in a.explain or []:
        plan = load_explain(p)
        m = re.search(r"_(\d+)\.explain\.(?:json|csv|tsv|txt)$", str(p))
        plan["n"] = int(m.group(1)) if m else None
        explains.append(plan)
    stats = read_rows(a.stats) if a.stats else []
    hist = read_rows(a.history) if a.history else []
    tables = load_tables(a.tables)
    columns = load_columns(a.columns)
    attribution = load_attribution(a.attribution, hist)
    files = [f for f in collect(a.paths) if not excluded(f, cfg)]
    if a.changed_only is not None:
        changed = changed_files(a.changed_only or None)
        files = [f for f in files if Path(f).resolve() in changed]
        if not files:
            print("no changed .sql files to review")
            if a.sarif:
                write_sarif(a.sarif, [])
            return
    if not files:
        sys.exit("no .sql files found")
    all_results = []
    for f in files:
        results, jinja = analyze_file(f, a, explains if len(files) == 1 else [], stats, hist, tables, columns, attribution, cfg)
        all_results.append((str(f), results, jinja))
    md = report_md(all_results, a, {"explain": bool(explains), "stats": bool(stats), "history": bool(hist), "tables": bool(tables),
                                    "columns": bool(columns), "attribution": bool(attribution[0] or attribution[1])})
    if a.sarif:
        write_sarif(a.sarif, all_results)
    if a.brief:
        lines = brief_lines(all_results)
        n = sum(len(r["findings"]) for _, rs, _ in all_results for r in rs)
        sys.stdout.write("\n".join(lines + [f"{len(files)} file(s), {n} finding(s)"]) + "\n")
        if a.md:
            Path(a.md).write_text(md, encoding="utf-8")
    elif a.md:
        Path(a.md).write_text(md, encoding="utf-8")
        n = sum(len(r["findings"]) for _, rs, _ in all_results for r in rs)
        print(f"wrote {a.md}: {sum(len(rs) for _, rs, _ in all_results)} statement(s), {n} finding(s)")
    else:
        sys.stdout.write(md)
    if a.json:
        data = [{"file": p, "jinja": j, "statements": [{k: v for k, v in r.items() if k != "sql"} for r in rs]} for p, rs, j in all_results]
        Path(a.json).write_text(json.dumps(data, indent=1, default=str) + "\n", encoding="utf-8")
    if a.fail_on:
        worst = min((SEV_ORDER[f["severity"]] for _, rs, _ in all_results for r in rs for f in r["findings"]), default=9)
        if worst <= SEV_ORDER[a.fail_on]:
            sys.exit(1)


def cmd_queries(a):
    out = ["-- Read-only statements for the Snowflake query advisor. Nothing here changes data.",
           "-- EXPLAIN compiles without executing (no warehouse needed). Save each result as JSON or CSV.", ""]
    tables = set()
    for f in collect(a.paths):
        text, jinja = strip_jinja(Path(f).read_text(encoding="utf-8", errors="replace"))
        if jinja:
            out.append(f"-- {f}: dbt/Jinja template. Run `dbt compile`, then pass the compiled file from target/compiled/ to `queries`.")
            out.append("")
            continue
        for k, (sql, line) in enumerate(split_statements(text), 1):
            try:
                stmt = sqlglot.parse_one(sql, read="snowflake")
            except Exception:  # noqa: BLE001
                stmt = None
            if stmt is None or isinstance(stmt, exp.Command):
                out.append(f"-- {f} statement {k} (line {line}): not parsed; EXPLAIN it by hand if it's a query")
                continue
            for t in stmt.find_all(exp.Table):
                if isinstance(t.this, exp.Identifier) and t.name.lower() not in ctes_of(stmt):
                    tables.add((t.catalog, t.db, t.name))
            body = sql  # the user's own text, so EXPLAIN sees exactly what will run
            if isinstance(stmt, exp.Create):
                if not isinstance(stmt.expression, (exp.Select, exp.Union, exp.Subquery, exp.Intersect, exp.Except)):
                    continue
                m = re.search(r"(?is)\bAS\s*(?=\(?\s*(?:WITH|SELECT)\b)", sql)
                body = sql[m.end():] if m else stmt.expression.sql(dialect="snowflake", pretty=True)
            elif not isinstance(stmt, (exp.Select, exp.Union, exp.Intersect, exp.Except, exp.Insert, exp.Merge, exp.Update, exp.Delete, exp.Subquery)):
                continue
            out.append(f"-- {f} statement {k} (line {line}); save the result as {Path(f).stem}_{k}.explain.json")
            out.append("EXPLAIN USING JSON")
            out.append(body.strip().rstrip(";") + ";")
            out.append("")
    if tables:
        out.append("-- Table sizes and clustering keys for the tables above; save as tables.csv")
        by_db = defaultdict(set)
        for cat, db, name in sorted(tables):
            by_db[cat or ""].add((db, name))
        for cat, items in sorted(by_db.items()):
            prefix = f"{cat}." if cat else ""
            conds = " OR ".join(f"(table_name = '{n.upper()}'" + (f" AND table_schema = '{d.upper()}')" if d else ")") for d, n in sorted(items, key=lambda x: (x[0] or "", x[1])))
            out.append(f"SELECT table_catalog, table_schema, table_name, row_count, bytes, clustering_key\nFROM {prefix}INFORMATION_SCHEMA.TABLES\nWHERE {conds};")
            out.append("")
            out.append("-- Column names and types for the same tables (save as columns.csv; turns on the type checks)")
            out.append(f"SELECT table_catalog, table_schema, table_name, column_name, ordinal_position, data_type\nFROM {prefix}INFORMATION_SCHEMA.COLUMNS\n"
                       f"WHERE {conds}\nORDER BY table_schema, table_name, ordinal_position;")
            out.append("")
    out.append("-- After running the query once: per-operator statistics (save as stats.csv). Needs OPERATE or MONITOR on the warehouse.")
    out.append("SELECT * FROM TABLE(GET_QUERY_OPERATOR_STATS('<query_id>'));")
    out.append("")
    out.append("-- The run's timing, size, spill and queueing (save as history.csv). ACCOUNT_USAGE views lag behind (up to about 45 minutes);")
    out.append("-- the INFORMATION_SCHEMA.QUERY_HISTORY_BY_SESSION() table function has your own session's queries right away.")
    out.append("SELECT query_id, warehouse_size, execution_time, compilation_time, queued_overload_time, queued_provisioning_time,\n"
               "       bytes_scanned, percentage_scanned_from_cache, partitions_scanned, partitions_total,\n"
               "       bytes_spilled_to_local_storage, bytes_spilled_to_remote_storage\n"
               "FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_HISTORY WHERE query_id = '<query_id>';")
    out.append("")
    out.append("-- Credits Snowflake attributed to the run and its child queries, excluding warehouse idle time (save as attribution.csv).")
    out.append("-- Needs the USAGE_VIEWER or GOVERNANCE_VIEWER database role; the view lags by up to about 8 hours and omits very short queries.")
    out.append("SELECT query_id, parent_query_id, root_query_id, query_parameterized_hash, warehouse_name, start_time,\n"
               "       credits_attributed_compute, credits_used_query_acceleration\n"
               "FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY\n"
               "WHERE query_id = '<query_id>' OR root_query_id = '<query_id>';")
    out.append("")
    out.append("-- Every run of the same query shape over the last 30 days (save as pattern.csv; pass both files with --attribution).")
    out.append("SELECT a.query_parameterized_hash, COUNT(*) AS runs,\n"
               "       SUM(a.credits_attributed_compute) AS credits_attributed_compute,\n"
               "       SUM(COALESCE(a.credits_used_query_acceleration, 0)) AS credits_used_query_acceleration,\n"
               "       MIN(a.start_time) AS first_start, MAX(a.start_time) AS last_start\n"
               "FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY a\n"
               "WHERE a.query_parameterized_hash = (SELECT query_parameterized_hash FROM SNOWFLAKE.ACCOUNT_USAGE.QUERY_ATTRIBUTION_HISTORY\n"
               "                                    WHERE query_id = '<query_id>')\n"
               "  AND a.start_time >= DATEADD(day, -30, CURRENT_TIMESTAMP())\n"
               "GROUP BY a.query_parameterized_hash;")
    sys.stdout.write("\n".join(out) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("analyze")
    p.add_argument("paths", nargs="+")
    p.add_argument("--explain", action="append")
    p.add_argument("--stats")
    p.add_argument("--history")
    p.add_argument("--tables")
    p.add_argument("--warehouse")
    p.add_argument("--columns")
    p.add_argument("--attribution", action="append")
    p.add_argument("--generation", type=int, choices=[1, 2])
    p.add_argument("--cloud", choices=["aws", "azure", "gcp"])
    p.add_argument("--credit-price", type=float)
    p.add_argument("--runs-per-day", type=float)
    p.add_argument("--md")
    p.add_argument("--json")
    p.add_argument("--fail-on", choices=list(SEV_ORDER))
    p.add_argument("--sarif")
    p.add_argument("--brief", action="store_true")
    p.add_argument("--changed-only", nargs="?", const="", metavar="REF")
    p.add_argument("--config")
    p.add_argument("--no-config", action="store_true")
    q = sub.add_parser("queries")
    q.add_argument("paths", nargs="+")
    a = ap.parse_args(argv)
    (cmd_analyze if a.cmd == "analyze" else cmd_queries)(a)


if __name__ == "__main__":
    main()
