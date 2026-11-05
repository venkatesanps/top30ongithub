#!/usr/bin/env python3
"""Translate Oracle SQL to Snowflake with SQLGlot and flag what a translator can't know.

Usage:
  python3 ora2sf.py PATH [PATH ...] --out ./ora2sf-out [--fail-on error|warn]

PATH can be .sql, .pks, .pkb, .prc, .fnc, .trg, .vw files or folders of them.
Reads only the files you name and writes only under --out:
  <out>/converted/<file>.sql   plain SQL translated by SQLGlot; PL/SQL blocks kept as comments
  <out>/findings.json          every finding: file, line, severity, rule, message
  <out>/report.md              per-file effort, rule counts, and the full list

Plain SQL statements are translated. PL/SQL (procedures, functions, packages, triggers,
anonymous blocks) is not: it is inventoried for a rewrite in Snowflake Scripting, because
row-by-row logic should usually become set-based SQL rather than be ported line by line.
Needs sqlglot (pip install sqlglot).
"""
import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

try:
    import sqlglot
    from sqlglot.errors import ParseError, TokenError
except ImportError:  # pragma: no cover
    sys.exit("ora2sf needs sqlglot: pip install sqlglot")

EXTS = {".sql", ".pks", ".pkb", ".prc", ".fnc", ".trg", ".vw", ".pls", ".plb"}
I = re.I | re.M

# (rule, severity, pattern, message, scope) scope: all | sql | plsql | ddl
RULES = [
    ("rownum", "error", r"\bROWNUM\b",
     "Snowflake has no ROWNUM. Use LIMIT / FETCH FIRST n ROWS for top-N, or ROW_NUMBER() OVER (...) to number rows.", "all"),
    ("rowid", "error", r"\bROWID\b",
     "Snowflake has no ROWID. Use the table's key, or ROW_NUMBER() over a deterministic order for de-duplication.", "all"),
    ("db-link", "error", r"\b[A-Za-z_][\w$#.]*@[A-Za-z_][\w$#]*",
     "Database link. Snowflake can't query Oracle directly: land the remote table first (or use a share).", "all"),
    ("currval", "error", r"\.\s*CURRVAL\b",
     "Snowflake sequences have no CURRVAL. Keep the NEXTVAL you fetched in a variable, or use a key from the inserted row.", "all"),
    ("trigger", "error", r"^\s*CREATE\s+(OR\s+REPLACE\s+)?(EDITIONABLE\s+|NONEDITIONABLE\s+)?TRIGGER\b",
     "Snowflake has no triggers. Move the logic into the load, or use a stream + task on the table.", "all"),
    ("autonomous-txn", "error", r"PRAGMA\s+AUTONOMOUS_TRANSACTION",
     "No autonomous transactions. Write audit/log rows after the main transaction, or from a separate task.", "all"),
    ("oracle-package-call", "error", r"\b(DBMS_(?!OUTPUT\b)\w+|UTL_\w+|APEX_\w+)\b",
     "Oracle-supplied package. No Snowflake equivalent: replace with Snowflake functions, a task, or an external function.", "all"),
    ("number-no-scale", "warn", r"\bNUMBER\b(?!\s*\()",
     "NUMBER without precision becomes NUMBER(38,0) in Snowflake and silently drops decimals. Declare NUMBER(38,s) or FLOAT.", "all"),
    ("empty-string-null", "warn", r"(=|<>|!=)\s*''|''\s*(=|<>|!=)|\bNVL\s*\([^()]*,\s*''\s*\)",
     "Oracle treats '' as NULL; Snowflake doesn't. Comparisons with '' and NVL(x, '') behave differently: decide which you mean.", "raw"),
    ("sysdate-timezone", "warn", r"\b(SYSDATE|SYSTIMESTAMP)\b",
     "Oracle SYSDATE is the DB server's local time; Snowflake SYSDATE() is UTC. Use CURRENT_TIMESTAMP() with an explicit timezone.", "all"),
    ("date-integer-math", "warn", r"\b(SYSDATE|TRUNC\s*\([^()]*\)|\w*DATE\w*)\s*[-+]\s*\d+(\.\d+)?\b",
     "Date ± number adds days in Oracle (fractions are hours). In Snowflake use DATEADD; TIMESTAMP ± number is an error.", "all"),
    ("outer-join-plus", "warn", r"\(\s*\+\s*\)",
     "Oracle (+) outer join. Snowflake accepts it with restrictions; rewrite as ANSI LEFT/RIGHT JOIN ... ON.", "all"),
    ("order-siblings", "warn", r"ORDER\s+SIBLINGS\s+BY",
     "ORDER SIBLINGS BY isn't supported. Rewrite the hierarchy as a recursive CTE that builds a sort path.", "all"),
    ("connect-by", "info", r"\bCONNECT\s+BY\b",
     "CONNECT BY runs on Snowflake; compare results on real data, or use a recursive CTE.", "all"),
    ("row-by-row", "warn", r"\bBULK\s+COLLECT\b|\bFORALL\b|\bOPEN\s+\w+\s+FOR\b|\bFETCH\s+\w+\s+INTO\b|\bFOR\s+\w+\s+IN\s*\(\s*SELECT\b",
     "Row-by-row processing. Rewrite set-based (INSERT ... SELECT or MERGE): loops are slow and costly on Snowflake.", "plsql"),
    ("type-anchor", "warn", r"%\s*(ROW)?TYPE\b",
     "%TYPE / %ROWTYPE anchors aren't supported in Snowflake Scripting. Declare explicit types.", "plsql"),
    ("named-exception", "warn", r"\bWHEN\s+(NO_DATA_FOUND|TOO_MANY_ROWS|DUP_VAL_ON_INDEX|ZERO_DIVIDE|VALUE_ERROR|INVALID_NUMBER)\b",
     "Oracle named exception. Snowflake Scripting has STATEMENT_ERROR, EXPRESSION_ERROR and OTHER: check SQLCODE/row counts instead.", "plsql"),
    ("raise-app-error", "warn", r"\bRAISE_APPLICATION_ERROR\b",
     "Declare an EXCEPTION (-20xxx, 'message') and RAISE it in Snowflake Scripting.", "plsql"),
    ("package", "warn", r"^\s*CREATE\s+(OR\s+REPLACE\s+)?(EDITIONABLE\s+)?PACKAGE\b",
     "No packages. Make each public routine a schema-level procedure (a schema per package works); package state becomes a table or session variable.", "all"),
    ("commit-in-block", "info", r"\b(COMMIT|ROLLBACK)\b",
     "Transaction control inside a routine. Snowflake procedures can BEGIN/COMMIT, but DDL commits implicitly: re-check the boundaries.", "plsql"),
    ("dbms-output", "info", r"\bDBMS_OUTPUT\b",
     "No console output. Return a value, use SYSTEM$LOG with event tables, or insert into a log table.", "all"),
    ("execute-immediate", "info", r"\bEXECUTE\s+IMMEDIATE\b",
     "Supported in Snowflake Scripting; bind syntax differs (? or :var). Quote identifiers with IDENTIFIER().", "plsql"),
    ("global-temp-table", "info", r"\bGLOBAL\s+TEMPORARY\b",
     "Becomes CREATE TEMPORARY TABLE (session-scoped, created at run time) or a TRANSIENT table.", "all"),
    ("partitioning", "info", r"\bPARTITION\s+BY\s+(RANGE|LIST|HASH)\b",
     "Snowflake partitions automatically. Consider a clustering key on the same column for very large tables.", "ddl"),
    ("date-has-time", "info", r"\bDATE\b(?!\s*')",
     "Oracle DATE holds a time; Snowflake DATE doesn't. Use TIMESTAMP_NTZ for columns that store times.", "ddl"),
    ("hint", "info", r"/\*\+",
     "Optimizer hint removed: Snowflake ignores hints.", "raw"),
]
RULES = [(r, s, re.compile(p, I), m, sc) for r, s, p, m, sc in RULES]
SEV_ORDER = {"error": 0, "warn": 1, "info": 2}

PLSQL_START = re.compile(
    r"^\s*(CREATE\s+(OR\s+REPLACE\s+)?(EDITIONABLE\s+|NONEDITIONABLE\s+)?"
    r"(PROCEDURE|FUNCTION|PACKAGE|TRIGGER|TYPE\s+BODY)\b|DECLARE\b|BEGIN\b)", re.I)
PLSQL_NAME = re.compile(
    r"\b(PROCEDURE|FUNCTION|PACKAGE\s+BODY|PACKAGE|TRIGGER|TYPE\s+BODY)\s+([\w$#.\"]+)", re.I)
DDL = re.compile(r"^\s*(CREATE|ALTER)\s+(GLOBAL\s+TEMPORARY\s+)?TABLE\b", re.I)


def mask(text, strings=True):
    """Blank out comments (and string contents) but keep every newline and offset."""
    out, i, n = list(text), 0, len(text)
    while i < n:
        c, nx = text[i], text[i + 1] if i + 1 < n else ""
        if c == "-" and nx == "-":
            j = text.find("\n", i)
            j = n if j < 0 else j
        elif c == "/" and nx == "*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
        elif c == "'" and strings:
            j = i + 1
            while j < n:
                if text[j] == "'" and j + 1 < n and text[j + 1] == "'":
                    j += 2
                elif text[j] == "'":
                    j += 1
                    break
                else:
                    j += 1
            for k in range(i + 1, j - 1):
                if out[k] != "\n":
                    out[k] = " "
            i = j
            continue
        elif c == "'":
            j = text.find("'", i + 1)
            j = n if j < 0 else j + 1
            i = j
            continue
        else:
            i += 1
            continue
        for k in range(i, j):
            if out[k] != "\n":
                out[k] = " "
        i = j
    return "".join(out)


def split_units(text):
    """Split a file into units: (kind, start_line, text). kind is 'sql' or 'plsql'.

    PL/SQL blocks run to a line holding only '/', the SQL*Plus terminator (or end of file).
    Plain SQL statements end at ';' outside strings and comments.
    """
    m = mask(text)
    lines, mlines = text.split("\n"), m.split("\n")
    units, buf, start, kind = [], [], None, None
    for idx, (ln, ml) in enumerate(zip(lines, mlines), 1):
        if kind is None:
            if not ml.strip() or ml.strip() == "/":
                continue
            kind = "plsql" if PLSQL_START.match(ml) else "sql"
            start, buf = idx, []
        if kind == "plsql":
            if ml.strip() == "/":
                units.append(("plsql", start, "\n".join(buf)))
                kind = None
                continue
            buf.append(ln)
        else:
            if ";" in ml:
                cut = ml.index(";")
                buf.append(ln[:cut])
                units.append(("sql", start, "\n".join(buf)))
                kind, rest = None, ln[cut + 1:]
                if rest.strip() and mask(rest).strip():
                    # another statement starts on the same line: re-split it
                    for k, s, t in split_units(rest):
                        units.append((k, idx + s - 1, t))
                continue
            buf.append(ln)
    if kind is not None and "\n".join(buf).strip():
        units.append((kind, start, "\n".join(buf)))
    return units


def find(unit_kind, start, text):
    found, seen = [], set()
    masked, no_comments = mask(text), mask(text, strings=False)
    is_ddl = bool(DDL.match(masked))
    for rule, sev, rx, msg, scope in RULES:
        if scope == "plsql" and unit_kind != "plsql":
            continue
        if scope == "ddl" and not is_ddl:
            continue
        if scope == "sql" and unit_kind != "sql":
            continue
        hay = text if rule == "hint" else no_comments if scope == "raw" else masked
        for mt in rx.finditer(hay):
            line = start + hay.count("\n", 0, mt.start())
            if (rule, line) in seen:
                continue
            seen.add((rule, line))
            found.append({"line": line, "severity": sev, "rule": rule, "message": msg,
                          "match": " ".join(mt.group(0).split())[:60]})
    return found


PHYSICAL = re.compile(r"\)\s*(PARTITION\s+BY|SUBPARTITION|TABLESPACE|PCTFREE|PCTUSED|INITRANS|STORAGE\s*\(|"
                      r"(NO)?COMPRESS|(NO)?LOGGING|SEGMENT\s+CREATION|ORGANIZATION\s+INDEX|ENABLE\s+ROW\s+MOVEMENT)\b", re.I)


def strip_physical(text):
    """Drop Oracle storage clauses after a CREATE TABLE column list; Snowflake has no use for them."""
    if not DDL.match(mask(text)):
        return text, False
    m = PHYSICAL.search(mask(text))
    return (text[:m.start() + 1], True) if m else (text, False)


def translate(text):
    """Translate one plain SQL statement. Returns (snowflake_sql or None, error or None)."""
    clean = re.sub(r"/\*\+.*?\*/", "", text, flags=re.S)
    clean, _ = strip_physical(clean)
    try:
        out = sqlglot.transpile(clean, read="oracle", write="snowflake", pretty=True)
        return ";\n".join(out), None
    except (ParseError, TokenError, ValueError) as e:
        return None, str(e).split("\n")[0][:200]


def effort(fs):
    c = Counter(f["severity"] for f in fs)
    if c["error"] == 0 and c["warn"] <= 3:
        return "S"
    if c["error"] <= 3 and c["warn"] <= 15:
        return "M"
    return "L"


def convert_file(path):
    text = path.read_text(encoding="utf-8", errors="replace")
    findings, out, stats = [], [f"-- Converted by ora2sf from {path.name}. Review every [ora2sf] note.\n"], Counter()
    for kind, start, body in split_units(text):
        fs = find(kind, start, body)
        if kind == "plsql":
            stats["plsql"] += 1
            nm = PLSQL_NAME.search(mask(body))
            label = f"{nm.group(1).upper()} {nm.group(2)}" if nm else "anonymous block"
            fs.insert(0, {"line": start, "severity": "warn", "rule": "plsql-rewrite", "match": label,
                          "message": f"PL/SQL {label}: rewrite in Snowflake Scripting (or as set-based SQL); not auto-translated."})
            out.append(f"-- [ora2sf] line {start}: PL/SQL {label}. Rewrite needed; original kept below.")
            out.append("/*\n" + body.replace("*/", "* /") + "\n*/\n")
        else:
            stats["sql"] += 1
            if strip_physical(body)[1]:
                fs.append({"line": start, "severity": "info", "rule": "physical-options", "match": "",
                           "message": "Oracle storage/partition clauses dropped from CREATE TABLE (no Snowflake equivalent)."})
            sf, err = translate(body)
            if sf is None:
                stats["failed"] += 1
                fs.insert(0, {"line": start, "severity": "error", "rule": "parse-failed", "match": "",
                              "message": f"SQLGlot couldn't parse this statement: {err}"})
                out.append(f"-- [ora2sf] line {start}: could not translate ({err}). Original kept below.")
                out.append("/*\n" + body.replace("*/", "* /") + "\n*/\n")
            else:
                stats["translated"] += 1
                notes = sorted({f["rule"] for f in fs if f["severity"] != "info"})
                if notes:
                    out.append(f"-- [ora2sf] line {start}: check {', '.join(notes)}")
                out.append(sf + ";\n")
        for f in fs:
            f["file"] = str(path)
        findings += fs
    findings.sort(key=lambda f: (f["line"], SEV_ORDER[f["severity"]]))
    return "\n".join(out), findings, stats


def collect(paths):
    files = []
    for p in map(Path, paths):
        if p.is_dir():
            files += sorted(f for f in p.rglob("*") if f.is_file() and f.suffix.lower() in EXTS)
        elif p.is_file():
            files.append(p)
        else:
            sys.exit(f"not found: {p}")
    return files


def report(results):
    allf = [f for _, fs, _ in results for f in fs]
    sev = Counter(f["severity"] for f in allf)
    md = ["# Oracle → Snowflake conversion report", "",
          f"{len(results)} file(s): **{sev['error']} error(s)**, {sev['warn']} warning(s), {sev['info']} note(s).",
          "Errors won't run or will return different results on Snowflake. Warnings usually need a human decision.", "",
          "## Files", "", "| File | SQL statements | Translated | PL/SQL blocks | Errors | Warnings | Effort |",
          "|---|---|---|---|---|---|---|"]
    for path, fs, st in results:
        c = Counter(f["severity"] for f in fs)
        md.append(f"| {path.name} | {st['sql']} | {st['translated']} | {st['plsql']} | {c['error']} | {c['warn']} | {effort(fs)} |")
    md += ["", "Effort: S = translated SQL with few warnings; M = some manual fixes; L = rewrite (PL/SQL, many errors).",
           "", "## By rule", "", "| Severity | Rule | Count | What to do |", "|---|---|---|---|"]
    by_rule = defaultdict(list)
    for f in allf:
        by_rule[(f["severity"], f["rule"])].append(f)
    for (s, r), fs in sorted(by_rule.items(), key=lambda kv: (SEV_ORDER[kv[0][0]], -len(kv[1]))):
        msg = fs[0]["message"] if r not in ("plsql-rewrite", "parse-failed") else \
            ("Rewrite in Snowflake Scripting or set-based SQL." if r == "plsql-rewrite" else "Fix or translate by hand.")
        md.append(f"| {s} | `{r}` | {len(fs)} | {msg} |")
    md += ["", "## Every finding", ""]
    for path, fs, _ in results:
        if not fs:
            continue
        md += [f"### {path.name}", "", "| Line | Severity | Rule | Found |", "|---|---|---|---|"]
        md += [f"| {f['line']} | {f['severity']} | `{f['rule']}` | `{f['match'].replace('|', '/')}` |" for f in fs]
        md.append("")
    md += ["## Next steps", "",
           "1. Fix every error, then decide each warning (empty string, NUMBER scale, SYSDATE timezone are the usual silent ones).",
           "2. Rewrite PL/SQL blocks set-based where possible; keep loops only where order really matters.",
           "3. Prove equivalence: row counts, checksums and sample diffs on the same input snapshot in both systems."]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("paths", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--fail-on", choices=["error", "warn"], help="exit 1 if any finding at this severity or worse")
    a = ap.parse_args(argv)
    files = collect(a.paths)
    if not files:
        sys.exit("no Oracle source files found (looked for " + ", ".join(sorted(EXTS)) + ")")
    out = Path(a.out)
    (out / "converted").mkdir(parents=True, exist_ok=True)
    results, names = [], Counter()
    for f in files:
        sql, fs, st = convert_file(f)
        names[f.stem] += 1
        stem = f.stem if names[f.stem] == 1 else f"{f.stem}_{names[f.stem]}"
        (out / "converted" / f"{stem}.sql").write_text(sql, encoding="utf-8")
        results.append((f, fs, st))
    allf = [x for _, fs, _ in results for x in fs]
    (out / "findings.json").write_text(json.dumps(allf, indent=1) + "\n", encoding="utf-8")
    (out / "report.md").write_text(report(results), encoding="utf-8")
    sev = Counter(x["severity"] for x in allf)
    print(f"ora2sf: {len(files)} file(s), {sev['error']} error(s), {sev['warn']} warning(s), {sev['info']} note(s) -> {out}/report.md")
    if a.fail_on and any(SEV_ORDER[x["severity"]] <= SEV_ORDER[a.fail_on] for x in allf):
        sys.exit(1)


if __name__ == "__main__":
    main()
