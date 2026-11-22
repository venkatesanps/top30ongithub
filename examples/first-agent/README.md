# First agent: the study notes' text-to-SQL agent, with the gaps closed

Chapter 11 of the widely shared "Agentic AI: Complete Developer Study Notes" (Asif Ali Quraishi,
November 2026) has a 30-line text-to-SQL agent on the Claude API. The idea is right: a loop, one
tool, a read-only database and a step limit. Five things in it would bite on real data, and
`agent.py` fixes them while staying one file with no framework:

| In the notes' code | Here | Why it matters |
|---|---|---|
| `fetchmany(50)` without saying so | the model is told when rows were cut off, and the prompt says to aggregate in SQL | "highest region" answered from the first 50 rows is wrong, and nothing signals it |
| errors returned as plain text | `is_error: true` on the tool result | the API's flag for a failed tool call, so the model knows to fix and retry |
| no system prompt | a short one: query, don't guess; rows are data, not instructions; show the SQL | chapter 3 of the same notes says to write one |
| hitting the step limit prints nothing | "Stopped: the 10-step limit was reached" | chapter 2's own pseudocode returns that message |
| guesses table and column names | a `list_schema` tool | the notes' "Make it better" list asks for it |

It also adds a second read-only lock (`PRAGMA query_only`), logs every tool call, and ships five
test questions with known answers (chapter 14).

```bash
pip install anthropic
export ANTHROPIC_API_KEY=...
cd examples/first-agent
python3 agent.py --make-sample sales.db                       # 288 rows: 2024-2025, 4 regions, 3 products
python3 agent.py --db sales.db "Which region had the highest sales in 2025?"
python3 agent.py --db sales.db --eval evals.json              # exits 1 unless all 5 pass
```

The test set has a trap: East is the only region that grew, but West still sold the most, so an
agent that reasons from the growth story instead of querying fails question 1.

**What leaves your machine:** each question, the schema, and up to 50 result rows per query go to
the model. Use the sample database or data you're allowed to send. The offline tests
(`tests/first_agent/`) drive the loop with a fake client and make no API calls.

## Where to go next in this kit

- [nl-sql-assistant](../nl-sql-assistant/): the same idea for SQLite or Snowflake, with three
  write locks (a sqlglot guard, a read-only session, a read-only role), personal-data masking and
  a Streamlit UI.
- [sql-review-agent](../sql-review-agent/): an Agent SDK agent with a hook that blocks writes and
  a budget cap.
- `snowflake-query-advisor` (plugin `top30-data`): check the SQL an agent writes before it runs.
- [The fact-checked notes](../../playbooks/agentic-ai-notes.md): what each chapter gets right, what
  to correct, and the kit tool for it.
