"""Deterministic Snowflake SQL checks used by the review agent (and runnable on their own).

    python3 checks.py a.sql b.sql      # prints one JSON array: [{"file", "findings"}, ...]

Each finding: {"line", "severity" (error|warn|info), "rule", "message"}. The agent calls this
as a tool so the model reasons over real parser output instead of guessing. Needs sqlglot.
"""
import json
import sys

import sqlglot
from sqlglot import exp
from sqlglot.errors import ParseError
from sqlglot.tokens import TokenType

DIALECT = "snowflake"


def _statement_lines(sql):
    """Line number of the first token of each statement, in parse order."""
    lines, start = [], None
    for tok in sqlglot.tokenize(sql, read=DIALECT):
        if tok.token_type == TokenType.SEMICOLON:
            if start is not None:
                lines.append(start)
            start = None
        elif start is None:
            start = tok.line
    if start is not None:
        lines.append(start)
    return lines


def _f(line, severity, rule, message):
    return {"line": line, "severity": severity, "rule": rule, "message": message}


def check_statement(stmt, line):
    out = []
    if isinstance(stmt, (exp.Delete, exp.Update)) and not stmt.args.get("where"):
        out.append(_f(line, "error", "no-where", f"{stmt.key.upper()} without WHERE changes every row in the table."))
    for sel in stmt.find_all(exp.Select):
        outer = sel.parent is None or isinstance(sel.parent, (exp.Create, exp.Insert, exp.Union))
        if outer and any(isinstance(e, exp.Star) for e in sel.expressions):
            out.append(_f(line, "warn", "select-star",
                          "SELECT * in a final or persisted query: list the columns so schema changes don't break consumers."))
        if sel.args.get("order") and not sel.args.get("limit") and isinstance(sel.parent, (exp.Subquery, exp.CTE)):
            out.append(_f(line, "info", "order-in-subquery", "ORDER BY inside a CTE or subquery without LIMIT is wasted work."))
        for j in sel.args.get("joins") or []:
            if not j.args.get("on") and not j.args.get("using") and (j.args.get("kind") or "").upper() != "CROSS" \
                    and not isinstance(j.this, (exp.Lateral, exp.Unnest)) and "FLATTEN" not in j.this.sql(DIALECT).upper():
                out.append(_f(line, "warn", "join-no-on", f"{j.this.sql(DIALECT)[:60]} is joined with no ON/USING (a comma join or bare JOIN): "
                                                        "that is an implicit CROSS JOIN. Use JOIN ... ON."))
        where = sel.args.get("where")
        if where:
            for fn in where.find_all(exp.Func):
                if isinstance(fn, (exp.Anonymous, exp.Cast, exp.TsOrDsToDate, exp.Date, exp.DateTrunc, exp.Upper, exp.Lower,
                                   exp.Trim, exp.Substring, exp.Coalesce, exp.ToChar, exp.StrToDate)) \
                        and fn.find(exp.Column) and isinstance(fn.parent, (exp.EQ, exp.GT, exp.GTE, exp.LT, exp.LTE, exp.Between, exp.In)) \
                        and fn.parent.this is fn:
                    out.append(_f(line, "warn", "fn-on-filter-column",
                                  f"{fn.sql(DIALECT)[:60]} in WHERE wraps the column, which can stop Snowflake pruning micro-partitions; "
                                  "compare the raw column to a computed value instead."))
                    break
            # sqlglot rewrites NOT IN (subquery) as <> ALL (subquery)
            nots = [n for n in where.find_all(exp.Not) if isinstance(n.this, exp.In) and n.this.args.get("query")]
            nots += [n for n in where.find_all(exp.NEQ) if isinstance(n.expression, exp.All)]
            if nots:
                out.append(_f(line, "warn", "not-in-subquery",
                                  "NOT IN (subquery) returns no rows if the subquery yields a NULL; use NOT EXISTS."))
    for u in stmt.find_all(exp.Union):
        if u.args.get("distinct"):
            out.append(_f(line, "info", "union-distinct", "UNION removes duplicates (sorts). Use UNION ALL if duplicates are impossible or wanted."))
    return out


def check_sql(sql):
    try:
        stmts = sqlglot.parse(sql, read=DIALECT)
    except ParseError as e:
        errs = e.errors or [{}]
        return [_f(x.get("line"), "error", "parse", (x.get("description") or str(e))[:200]) for x in errs]
    lines = _statement_lines(sql)
    findings = []
    for i, stmt in enumerate(s for s in stmts if s is not None):
        findings += check_statement(stmt, lines[i] if i < len(lines) else None)
    seen, unique = set(), []
    for f in findings:
        k = (f["line"], f["rule"])
        if k not in seen:
            seen.add(k)
            unique.append(f)
    return unique


if __name__ == "__main__":
    print(json.dumps([{"file": p, "findings": check_sql(open(p, encoding="utf-8").read())} for p in sys.argv[1:]], indent=1))
