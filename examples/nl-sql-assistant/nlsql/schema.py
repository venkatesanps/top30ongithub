"""Schema grounding: table and column names and types, with personal columns flagged.

Only names and types are ever sent to the model, never values.
"""
import re
from dataclasses import dataclass, field

SENSITIVE = re.compile(
    r"(e_?mail|phone|mobile|cell|fax|ssn|social_?sec|tax_?id|\btin\b|national_?id|passport|licen[cs]e|"
    r"first_?name|last_?name|full_?name|middle_?name|surname|given_?name|customer_?name|employee_?name|^name$|"
    r"address|street|postal|zip_?code|^zip$|birth|\bdob\b|^dob$|gender|"
    r"card_?(no|num)|^card$|iban|account_?(no|num)|routing|sort_?code|salary|"
    r"ip_?addr|^ip$|device_?id|lat(itude)?$|lon(gitude)?$|password|secret|token)",
    re.I,
)


@dataclass
class Schema:
    dialect: str
    tables: dict = field(default_factory=dict)  # name -> [(column, type)]
    sensitive: set = field(default_factory=set)  # {"table.column"}, lowercase

    def known_tables(self):
        return set(self.tables)

    def sensitive_columns(self):
        return {s.split(".")[-1] for s in self.sensitive}

    def text(self):
        lines = [f"-- dialect: {self.dialect}. Columns marked [sensitive] hold personal data:"
                 " don't select them unless the question asks for them."]
        for t, cols in sorted(self.tables.items()):
            parts = [f"{c} {ty}" + (" [sensitive]" if f"{t}.{c}".lower() in self.sensitive else "") for c, ty in cols]
            lines.append(f"{t}({', '.join(parts)})")
        return "\n".join(lines)


def _finish(sch, extra_sensitive, not_sensitive):
    for t, cols in sch.tables.items():
        for c, _ in cols:
            if SENSITIVE.search(c):
                sch.sensitive.add(f"{t}.{c}".lower())
    sch.sensitive |= {s.lower() for s in (extra_sensitive or ())}
    sch.sensitive -= {s.lower() for s in (not_sensitive or ())}
    return sch


def describe_sqlite(runner, extra_sensitive=None, not_sensitive=None):
    sch = Schema("sqlite")
    _, rows = runner._raw("SELECT name FROM sqlite_master WHERE type IN ('table','view') AND name NOT LIKE 'sqlite_%' ORDER BY name")
    for (t,) in rows:
        _, cols = runner._raw("SELECT name, type FROM pragma_table_info(?)", (t,))
        sch.tables[t.lower()] = [(c, ty or "ANY") for c, ty in cols]
    return _finish(sch, extra_sensitive, not_sensitive)


def describe_snowflake(runner, database, schema_name, extra_sensitive=None, not_sensitive=None):
    for v in (database, schema_name):
        if not re.match(r"^[A-Za-z_][A-Za-z0-9_$]*$", v or ""):
            raise ValueError(f"not a valid identifier: {v}")
    sch = Schema("snowflake")
    _, rows = runner._raw(
        f"SELECT table_name, column_name, data_type FROM {database}.INFORMATION_SCHEMA.COLUMNS "
        f"WHERE table_schema = %s ORDER BY table_name, ordinal_position", (schema_name.upper(),))
    for t, c, ty in rows:
        sch.tables.setdefault(f"{database}.{schema_name}.{t}".lower(), []).append((c.lower(), ty))
    return _finish(sch, extra_sensitive, not_sensitive)
