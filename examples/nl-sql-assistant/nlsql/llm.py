"""Claude as the SQL writer, through tool calling, and as the explainer of results.

What goes to the model: the question, the schema (names and types, with personal columns
flagged), earlier errors for a retry, and for the explanation either computed facts only or
facts plus a sample of up to 20 rows with personal values masked. Never raw personal values.
"""
import json
import re

DEFAULT_MODEL = "claude-sonnet-5-5"

SYSTEM = """You turn a business question into ONE read-only SQL query for the database described below.
Rules:
- Call the run_sql tool exactly once with the query. Never write INSERT, UPDATE, DELETE, MERGE, DDL,
  CALL, COPY, PUT, GRANT, USE, SET or PRAGMA. One statement, no trailing semicolon needed.
- Use only the tables and columns in the schema. Qualify columns when joining.
- Columns marked [sensitive] hold personal data: select them only when the question asks for them;
  prefer counts or aggregates.
- Add ORDER BY for "top"/"most"/"latest" questions and a LIMIT that fits the question.
- Write the {dialect} dialect."""

TOOL = {
    "name": "run_sql",
    "description": "Run one read-only SQL query against the database and return the rows.",
    "input_schema": {
        "type": "object",
        "properties": {
            "sql": {"type": "string", "description": "One SELECT (or WITH ... SELECT) statement."},
            "intent": {"type": "string", "description": "One sentence: what the query computes."},
        },
        "required": ["sql"],
    },
}

_PII_VALUE = [
    re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}"),
    re.compile(r"(?<!\d)(\+1[ .-]?)?\(?\d{3}\)?[ .-]\d{3}[ .-]\d{4}(?!\d)"),
    re.compile(r"(?<!\d)\d{3}-\d{2}-\d{4}(?!\d)"),
    re.compile(r"(?<!\d)(?:\d[ -]?){13,19}(?!\d)"),
]


def mask_value(v):
    if not isinstance(v, str):
        return v
    for rx in _PII_VALUE:
        v = rx.sub("[masked]", v)
    return v


def mask_rows(columns, rows, sensitive_columns):
    """Mask whole columns whose names are sensitive, and personal data found inside other values."""
    sens = {c.lower() for c in sensitive_columns}
    idx = {i for i, c in enumerate(columns) if c.lower() in sens}
    return [["[masked]" if i in idx else mask_value(v) for i, v in enumerate(row)] for row in rows]


def make_client(provider="anthropic"):
    import anthropic  # pip install anthropic
    if provider == "bedrock":
        return anthropic.AnthropicBedrock()  # AWS credentials; traffic stays in your AWS account
    return anthropic.Anthropic()  # ANTHROPIC_API_KEY


class ClaudeSQL:
    def __init__(self, client=None, model=DEFAULT_MODEL, provider="anthropic", max_tokens=1024):
        self.client = client or make_client(provider)
        self.model, self.max_tokens = model, max_tokens
        self.usage = {"input_tokens": 0, "output_tokens": 0, "cache_read_input_tokens": 0}

    def _count(self, msg):
        u = getattr(msg, "usage", None)
        for k in self.usage:
            self.usage[k] += int(getattr(u, k, 0) or 0)

    def generate(self, question, schema_text, dialect, feedback=None):
        """Return (sql, intent). feedback: list of (previous_sql, error) from earlier attempts."""
        content = f"Question: {question}"
        for prev, err in feedback or []:
            content += f"\n\nYour previous query:\n{prev}\nwas rejected: {err}\nWrite a corrected query."
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=[
                {"type": "text", "text": SYSTEM.format(dialect=dialect)},
                {"type": "text", "text": "Schema:\n" + schema_text, "cache_control": {"type": "ephemeral"}},
            ],
            tools=[TOOL],
            tool_choice={"type": "tool", "name": "run_sql"},
            messages=[{"role": "user", "content": content}],
        )
        self._count(msg)
        for block in msg.content:
            if getattr(block, "type", "") == "tool_use" and block.name == "run_sql":
                return str(block.input.get("sql", "")), str(block.input.get("intent", ""))
        return "", ""

    def explain(self, question, sql, facts, columns=None, sample=None):
        payload = {"question": question, "sql": sql, "facts": facts}
        if sample is not None:
            payload["columns"], payload["sample_rows"] = columns, sample
        msg = self.client.messages.create(
            model=self.model,
            max_tokens=400,
            system="Explain a query result to a business user in 2-4 plain sentences: what it shows and the key "
                   "takeaway. Use only the facts and rows given. Values shown as [masked] are hidden on purpose; "
                   "don't guess them.",
            messages=[{"role": "user", "content": json.dumps(payload, default=str)}],
        )
        self._count(msg)
        return "".join(getattr(b, "text", "") for b in msg.content if getattr(b, "type", "") == "text").strip()
