"""Question -> SQL -> guard -> read-only run -> explanation, with self-correction and an audit log."""
import json
import time
from dataclasses import dataclass, field
from numbers import Number
from pathlib import Path

import sqlglot
from sqlglot import exp

from . import guard
from .db import QueryError, ReadOnlyError
from .llm import mask_rows

SAMPLE_ROWS = 20


@dataclass
class Result:
    ok: bool
    question: str
    sql: str = ""
    intent: str = ""
    columns: list = field(default_factory=list)
    rows: list = field(default_factory=list)
    explanation: str = ""
    warnings: list = field(default_factory=list)
    problems: list = field(default_factory=list)
    attempts: int = 0
    seconds: float = 0.0


def local_facts(columns, rows):
    """Facts computed here, never values from text columns."""
    facts = f"{len(rows)} row{'s' if len(rows) != 1 else ''} x {len(columns)} column{'s' if len(columns) != 1 else ''}."
    for i, c in enumerate(columns):
        nums = [r[i] for r in rows if isinstance(r[i], Number) and not isinstance(r[i], bool)]
        if nums and len(nums) == len(rows):
            facts += f" {c}: total {sum(nums):,.2f}, max {max(nums):,.2f}, min {min(nums):,.2f}."
    return facts


def sensitive_output_columns(sql, dialect, columns, sensitive_names):
    """Output columns that carry a sensitive source column (by name, alias or inside an expression)."""
    sens = {s.lower() for s in sensitive_names}
    out = {c for c in columns if c.lower() in sens}
    try:
        stmt = sqlglot.parse_one(sql, read=dialect)
        selects = [stmt] if isinstance(stmt, exp.Select) else list(stmt.find_all(exp.Select))[:1]
        for sel in selects:
            for proj, col in zip(sel.expressions, columns):
                inner = proj.this if isinstance(proj, exp.Alias) else proj
                if isinstance(inner, exp.Count):
                    continue
                if any(c.name.lower() in sens for c in proj.find_all(exp.Column)):
                    out.add(col)
    except Exception:
        pass
    return out


class Assistant:
    def __init__(self, runner, schema, llm, explain="sample", max_rows=1000, max_attempts=3, audit_path=None):
        if explain not in ("sample", "facts", "none"):
            raise ValueError("explain must be sample, facts or none")
        self.runner, self.schema, self.llm = runner, schema, llm
        self.explain, self.max_rows, self.max_attempts = explain, max_rows, max_attempts
        self.audit_path = Path(audit_path).expanduser() if audit_path else None

    def run_sql(self, sql, question="(your SQL)"):
        """Guard and run SQL you wrote yourself. No model call."""
        t0 = time.monotonic()
        res = Result(False, question, attempts=1)
        v = guard.validate(sql, self.runner.dialect, self.schema.known_tables(), self.max_rows)
        res.sql, res.warnings = v.sql or sql, list(v.warnings)
        if not v.ok:
            res.problems = v.problems
        else:
            try:
                res.columns, rows = self.runner.run(v.sql, self.max_rows)
                res.rows, res.ok = [list(r) for r in rows], True
                res.explanation = local_facts(res.columns, res.rows)
            except (QueryError, ReadOnlyError) as e:
                res.problems = [str(e)]
        res.seconds = time.monotonic() - t0
        self._audit(res)
        return res

    def ask(self, question):
        t0 = time.monotonic()
        res = Result(False, question)
        feedback = []
        for attempt in range(1, self.max_attempts + 1):
            res.attempts = attempt
            sql, intent = self.llm.generate(question, self.schema.text(), self.runner.dialect, feedback)
            res.sql, res.intent = sql, intent
            v = guard.validate(sql, self.runner.dialect, self.schema.known_tables(), self.max_rows)
            if not v.ok:
                res.problems = v.problems
                feedback.append((sql, "; ".join(v.problems)))
                continue
            try:
                cols, rows = self.runner.run(v.sql, self.max_rows)
            except (QueryError, ReadOnlyError) as e:
                res.problems = [str(e)]
                feedback.append((v.sql, str(e)))
                continue
            res.ok, res.sql, res.problems = True, v.sql, []
            res.warnings += v.warnings
            res.columns, res.rows = cols, [list(r) for r in rows]
            break
        if res.ok:
            self._explain(res)
        res.seconds = time.monotonic() - t0
        self._audit(res)
        return res

    def _explain(self, res):
        facts = local_facts(res.columns, res.rows)
        hidden = sensitive_output_columns(res.sql, self.runner.dialect, res.columns, self.schema.sensitive_columns())
        if hidden:
            res.warnings.append(f"selected sensitive columns ({', '.join(sorted(hidden))}): shown to you here, "
                                f"masked in anything sent to the model")
        if self.explain == "none":
            res.explanation = facts
            return
        sample = None
        if self.explain == "sample":
            sample = mask_rows(res.columns, res.rows[:SAMPLE_ROWS], hidden)
        try:
            res.explanation = self.llm.explain(res.question, res.sql, facts, res.columns, sample) or facts
        except Exception as e:  # the answer still stands without the prose
            res.explanation = facts
            res.warnings.append(f"explanation unavailable: {type(e).__name__}")

    def _audit(self, res):
        if not self.audit_path:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        with self.audit_path.open("a") as f:
            f.write(json.dumps({"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "question": res.question, "sql": res.sql,
                                "ok": res.ok, "rows": len(res.rows), "attempts": res.attempts,
                                "problems": res.problems[:3], "seconds": round(res.seconds, 3)}) + "\n")
