---
name: agent-loop
description: Run an agent in a loop that can be trusted unattended - repair one unit until a program check passes (scoped, with a round limit, budget, memory of past attempts and escalation), or hunt for findings round by round until two rounds find nothing new. Use when the user wants Claude to "keep fixing until tests pass", sweep for bugs, flaky tests or sources, or stop babysitting an agent.
---

# Agent loop

A loop makes one unit of work correct without a person reading every attempt. It's only as good as
its check, and it needs a way to stop. `scripts/agent_loop.py` runs Claude Code headless inside
both, so the user approves the outcome, not each step.

## Before starting: write the check

The check is a command that exits 0 when the work is done, written **before** the task. Rank what
counts as evidence:

| Strength | Evidence |
|---|---|
| strong | tests exit 0, output matches a schema, the diff stays inside the plan, row counts/checksums match |
| medium | the cited source supports the claim, an independent path reaches the same answer |
| weak | a reviewer agent approves |
| not evidence | "looks good", the model says it's confident, no errors were thrown |

An empty error log means nothing was reported, not that nothing went wrong. If no strong or
medium check exists, help the user write one first (a pytest, a dbt test, a schema, a row-count
query) instead of looping.

## Repair: fix one unit

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/agent-loop/scripts/agent_loop.py" repair \
  --task "Make test_orders pass without changing its assertions" \
  --check "pytest -q tests/test_orders.py" --scope "src/orders.py" \
  --max-rounds 3 --budget-usd 2 --rules RULES.md
```

(Use the path inside this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set.) Each round sends
the agent the task, the scope line ("change only src/orders.py; list anything else under
Noticed"), the failing output, what earlier rounds already tried, and the standing rules. It then
runs the check itself, and in a git repo treats edits outside `--scope` as a failure.

- **exit 0:** the check passed. If it took more than one round, the agent's `RULE:` line is
  appended to `RULES.md` so the next planner avoids the same bug.
- **exit 3, escalate:** the round limit was hit, or two rounds in a row ended with the same
  failure. Read `.agent-loop/<id>/ESCALATION.md`: repeated repairs not converging means the plan is
  wrong (the split, the scope or the check), not that it needs more rounds.
- **exit 4, stop:** the budget is spent or the agent failed twice. A person looks.

When several units fail, repair **each unit separately**, never the whole batch: rewriting
slices that already pass produces new versions that can fail for new reasons.

## Hunt: find until the list stops growing

```bash
python3 .../agent_loop.py hunt --task "Find flaky tests: run the suite repeatedly, report tests that fail intermittently" \
  --verify "python3 scripts/confirm_flaky.py" --max-rounds 6 --dry-rounds 2 --budget-usd 3
```

The agent reports findings as JSON lines with a stable `key`. New keys are checked by `--verify`
(finding on stdin, exit 0 keeps it). Rejected findings stay in memory too, so later rounds don't
pay to rediscover dead ends. It stops after two rounds with nothing new.

## Report back

Tell the user: the outcome and exit status, rounds and dollars spent, the cause and any new rule,
and for escalations, what the attempts suggest is wrong with the plan. Memory lives in
`--state` (default `.agent-loop/`): add it to `.gitignore`, and keep `RULES.md` in the repo.

In Claude Code you can also ask a dynamic workflow for the same shape ("keep fixing until the type
check passes or two rounds in a row make no progress"). Use this script when you want the loop,
its memory and its rules as files in the repo, or in CI.
