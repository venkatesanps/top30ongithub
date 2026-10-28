# SQL review agent (Claude Agent SDK example)

A small, real agent for a data team: point it at a folder of Snowflake SQL and it writes a
review (`sql-review.md`) with findings by file and line, suggested rewrites, and what it could
not check. It never runs SQL, never connects to Snowflake, and cannot write files.

```bash
./install.sh 69                      # creates ~/claude-learn/agent-venv with the SDK and sqlglot
~/claude-learn/agent-venv/bin/python examples/sql-review-agent/agent.py examples/sql-review-agent/sample
~/claude-learn/agent-venv/bin/python examples/sql-review-agent/agent.py ~/work/dbt/models --model sonnet --budget 0.50
```

On the three sample files it takes about 8 turns and costs about $0.10 with Sonnet. It finds all
seven planted problems, calls out the clean file as clean, and adds two issues a linter can't see
(a result set that is never written, and an insert that isn't idempotent).

## How it's built (the parts you'd reuse for your own agent)

| Piece | Where | Why |
|---|---|---|
| Custom tool `lint_sql` | `agent.py` → `checks.py` | Deterministic sqlglot checks (Snowflake dialect), so the model reasons over real parser output instead of guessing. |
| Locked toolset | `tools=["Read","Glob","Grep"]` | Write, Edit and Bash don't exist in the session at all. |
| Guard hook | `make_guard` (PreToolUse) | A second lock: denies any other tool and any path outside the folder. |
| Isolation | `setting_sources=[]` | Ignores your personal settings, plugins and CLAUDE.md, so every machine gives the same review. |
| Cost control | `max_budget_usd`, `max_turns` | The run stops at the cap, and the cost is printed at the end. |

The rules in `checks.py` cover: parse errors, DELETE/UPDATE without WHERE, `SELECT *` in a
persisted or final query, joins with no condition (comma joins), functions wrapping a filter
column (which can stop micro-partition pruning), `NOT IN (subquery)` and its NULL trap, ORDER BY
in a CTE, and UNION vs UNION ALL. Run them alone with `python3 checks.py file.sql`. Add your
team's rules there; tests are in `tests/sql_agent/`.

## Taking it further

- **Every pull request:** `templates/claude-code-action/sql-review-bedrock.yml` runs the same
  checks plus a Claude review on each PR that touches `.sql` files, through Amazon Bedrock.
- **Your standards:** add your naming rules and banned patterns to `SYSTEM` in `agent.py`, or put
  them in a skill and load it with the SDK's `skills` option.
- **Auth at work:** the SDK uses whatever Claude Code uses: set `CLAUDE_CODE_USE_BEDROCK=1` with
  AWS credentials to keep traffic in your AWS account. Check with your firm before pointing it at
  production code.
