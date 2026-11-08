---
name: goal-writer
description: Write a /goal condition that actually finishes - one measurable end state, a stated check command, constraints, and a turn bound - lint it with goal_lint.py, start from data-engineering recipes (pytest, dbt, sqlfluff, Oracle-to-Snowflake, reconciliation), and switch on goal_gate, a Stop hook that runs the real check instead of trusting a model's reading of the chat. Use before running /goal, when a goal never ends or ends too early, or when the user wants Claude to keep working until tests pass.
---

# Goal writer

`/goal <condition>` keeps Claude working turn after turn until a small evaluator model judges
the condition met. That evaluator **reads only the conversation**: it doesn't run commands or open
files. So the condition is only as good as the proof Claude puts in the transcript.

## 1. Write the condition

A condition that finishes has:

1. **One measurable end state**: a test result, an exit code, a count, an empty queue.
2. **A stated check**: the exact command, in backticks, that proves it: "`pytest -q` exits 0".
3. **Constraints**: what must not change on the way ("do not delete or skip tests").
4. **A bound**: "or stop after 20 turns and report what's left".

It must be under 4,000 characters. Keep deploys, production writes, backfills and anything
else you can't undo out of the goal: do those yourself after it's achieved.

## 2. Lint it

```bash
L="python3 ${CLAUDE_PLUGIN_ROOT}/skills/goal-writer/scripts/goal_lint.py"   # or this folder's scripts/
$L "<condition>"            # score, findings, and a stronger shape
$L --recipes                # ready-made conditions
$L --recipes dbt            # one, ready to paste after /goal
```

Fix every error and warning before running it. Recipes cover pytest, dbt, sqlfluff, the
kit's `ora2sf.py`, source-to-target reconciliation, mypy, splitting a large file, and working
through a labelled issue queue. Adapt paths and names; keep the shape.

## 3. Run it

Give the user the final line to paste: `/goal <condition>`. Mention:

- In Manual permission mode Claude still asks before tools; in auto mode goal turns run unattended.
- `/goal` with no argument shows progress; `/goal clear` stops it.
- Headless: `claude -p "/goal ..." --output-format stream-json --verbose` to see each turn.

## 4. When the check must be enforced, not judged: goal gate

The `top30-agents` plugin registers a Stop hook, `hooks/goal_gate.py`, that does nothing until
it's switched on for a project. When it's on, each time Claude tries to finish, the gate runs
the real command and keeps Claude working until it exits 0:

```bash
G="python3 ${CLAUDE_PLUGIN_ROOT}/hooks/goal_gate.py"
$G on --check "dbt build --select state:modified+" --max-rounds 5   # in the project folder
$G status
$G off                                                               # or --once when turning on
```

- Each failure goes back to Claude with the last 40 lines of output and an instruction not to
  weaken the check.
- It stops blocking after `--max-rounds`, or when the same failure repeats three times, and tells
  the person why. Claude Code's own cap (8 consecutive blocks with no tool call in between) is
  a further backstop.
- Settings live in `~/.claude/goal-gate/`, not in the repo, so a cloned project can't switch
  it on or choose its command.
- The check runs every time Claude stops while the gate is on: use a fast, targeted command,
  or `--once`.

Use `/goal` for conditions only a reader can judge ("each acceptance criterion in SPEC.md is
met"); use the gate when a command decides. They combine: the gate enforces the command, the
goal keeps Claude moving between stops.
