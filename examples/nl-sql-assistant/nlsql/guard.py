"""Read-only SQL guard (lock 1 of 3). Parses the SQL with sqlglot and allows one read query only.

Why not `sql.strip().upper().startswith("SELECT")`? It passes `SELECT 1; DROP TABLE x`, and it
refuses legitimate `WITH ... SELECT`. A parser sees the whole statement tree.
"""
import logging
import re
from dataclasses import dataclass, field

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError, TokenError

READ_ROOTS = (exp.Select, exp.Union, exp.Intersect, exp.Except)
WRITE_NODES = tuple(t for t in (
    getattr(exp, n, None) for n in (
        "Insert", "Update", "Delete", "Merge", "Create", "Drop", "Alter", "AlterTable", "TruncateTable",
        "Command", "Pragma", "Attach", "Detach", "Copy", "Put", "Get", "Grant", "Revoke", "Use", "Set",
        "Transaction", "Commit", "Rollback", "Into", "LoadData", "Analyze", "Cache", "Uncache", "Refresh",
        "Kill", "Declare",
    )) if isinstance(t, type))
SIDE_EFFECT_FUNCS = re.compile(
    r"^(system\$.*|load_extension|writefile|readfile|fts3_tokenizer|edit|fsdir|sqlar_.*|zipfile|"
    r"pg_.*|dblink.*|lo_.*|xp_.*|sp_.*|external_.*)$", re.I)
DEFAULT_MAX_ROWS = 1000
logging.getLogger("sqlglot").setLevel(logging.ERROR)  # its "falling back to Command" notice is our refusal


@dataclass
class Verdict:
    ok: bool
    sql: str = ""
    problems: list = field(default_factory=list)
    warnings: list = field(default_factory=list)


def _table_name(t):
    parts = [p for p in (t.catalog, t.db, t.name) if p]
    return ".".join(parts).lower()


def _known(name, known):
    if not known:
        return True
    if name in known:
        return True
    bare = name.split(".")[-1]
    return any(k == bare or k.endswith("." + bare) for k in known) and (
        "." not in name or any(k.endswith(name) or name.endswith(k) for k in known))


def validate(sql, dialect="sqlite", known_tables=None, max_rows=DEFAULT_MAX_ROWS):
    """Return a Verdict. On ok, Verdict.sql is the query to run (re-rendered, with a row LIMIT)."""
    known = {k.lower() for k in (known_tables or ())}
    text = (sql or "").strip()
    if not text or not text.strip(";").strip():
        return Verdict(False, problems=["empty query"])
    try:
        stmts = [s for s in sqlglot.parse(text, read=dialect) if s is not None]
    except (ParseError, TokenError) as e:
        return Verdict(False, problems=[f"parse error: {str(e).splitlines()[0][:200]}"])
    if len(stmts) != 1:
        return Verdict(False, problems=[f"only one statement allowed (got {len(stmts)})"])
    stmt = stmts[0]
    problems, warnings = [], []

    if not isinstance(stmt, READ_ROOTS):
        kind = type(stmt).__name__.upper()
        if isinstance(stmt, exp.Command):
            kind = (stmt.this or "COMMAND").upper()
        problems.append(f"not a read query ({kind})")
    for node in stmt.walk():
        node = node[0] if isinstance(node, tuple) else node
        if node is not stmt and isinstance(node, WRITE_NODES):
            problems.append(f"not a read query (contains {type(node).__name__.upper()})")
            break
    for f in stmt.find_all(exp.Func):
        name = f.name if isinstance(f, exp.Anonymous) else (f.sql_name() if hasattr(f, "sql_name") else "")
        if name and SIDE_EFFECT_FUNCS.match(name):
            problems.append(f"side effect function not allowed: {name}")

    cte_names = {c.alias_or_name.lower() for c in stmt.find_all(exp.CTE)}
    for t in stmt.find_all(exp.Table):
        if not t.name:
            continue
        name = _table_name(t)
        if name.split(".")[-1] in cte_names and "." not in name:
            continue
        if not _known(name, known):
            problems.append(f"unknown table: {name} (only tables in the schema may be read)")
    if problems:
        return Verdict(False, problems=list(dict.fromkeys(problems)))

    if max_rows and isinstance(stmt, READ_ROOTS):
        lim = stmt.args.get("limit")
        current = None
        if lim is not None:
            val = lim.args.get("expression") or lim.this
            try:
                current = int(val.this) if isinstance(val, exp.Literal) else None
            except (TypeError, ValueError):
                current = None
        if lim is None:
            stmt = stmt.limit(max_rows)
        elif current is None or current > max_rows:
            stmt = stmt.limit(max_rows)
            warnings.append(f"row limit capped at {max_rows}" + (f" (asked for {current})" if current else ""))
    return Verdict(True, sql=stmt.sql(dialect=dialect), warnings=warnings)
