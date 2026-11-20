---
name: agent-pattern-picker
description: Choose the smallest agent design pattern that fits a task - or decide it needs no agent - from 15 patterns (single agent, sequential, parallel, loop, review and critique, iterative refinement, coordinator, hierarchical decomposition, swarm, ReAct, human-in-the-loop, plan-and-execute, reflexion, custom logic, event-driven), then audit the design against how that pattern breaks and ten production rules (tool contracts, budgets, traces, gates on irreversible actions, failure-case evals). Says how to build each pattern in Claude Code. Use when the user is designing an agent or multi-agent system, asks which pattern or architecture to use, whether something needs an agent at all, or wants an agent design reviewed.
---

# Agent pattern picker

From Rahul's "15 AI Agent Design Patterns Every Engineer Must Know" (X, Jun 2026). Its
core idea: match the pattern to the *kind of uncertainty* in the task, and use the smallest
one that works. This skill turns that into a questionnaire, a design file and an audit a
program can fail.

```bash
K="python3 ${CLAUDE_PLUGIN_ROOT}/skills/agent-pattern-picker/scripts/pattern_kit.py"   # or this folder's scripts/
```

## 1. Does it need an agent?

Ask first. Summaries, classification, simple extraction and templated text are a single
model call or plain code. An agent is justified only when one call can't do it reliably,
the model must choose tools or sources at runtime, the work needs planning, checking or
refinement, or the uncertainty can't be hard-coded.

## 2. Pick

Ask the user which of these are true, then pass them as flags:

| Flag | True when |
|---|---|
| `--predictable` | the input-to-output path is fixed |
| `--tool-choice` | it must choose tools or data sources at runtime |
| `--path-unknown` | the next step depends on what the last one found |
| `--approve-plan` / `--fast-changing` | a plan must be approved first / the world changes mid-run |
| `--route` | requests are of genuinely different kinds |
| `--quality` / `--measurable` | quality varies and matters / "good enough" is a number a program computes |
| `--repeat` / `--self-correct` | it needs attempts until a check passes / failures say what to fix |
| `--stages` / `--independent` | fixed stages feeding each other / subtasks that don't depend on each other |
| `--broad` / `--no-right-answer` | too broad for one pass / competing views, no single answer |
| `--event` | it must act when something happens, not when asked |
| `--risk` | money, legal or reputation is at stake |

`$K pick <flags>` prints the pattern to start with, why, how it breaks, how to build it in
Claude Code, the next pattern up if that isn't enough, and wrappers (`--risk` adds custom
logic and a human step around whatever was picked). When scores are close it picks the
simpler pattern: a swarm is not an upgrade from one agent that needs one tool call.

## 3. Write the design and audit it

`$K scaffold <pattern> > design.json`, fill it in with the user (tools with real
descriptions, budget, exit check, gates), then `$K audit design.json`. Exit 1 on errors
(`--fail-on warn` for stricter). Use `"patterns": [...]` for combinations such as ReAct
inside human-in-the-loop.

The audit checks the post's ten rules where a program can: system prompt past ~700 words
or "but don't X when Y" clauses (split it), tool descriptions under 40 characters (write
them as contracts), no step, tool-call or spend cap, no action trace, irreversible tools
(refund, send, delete, deploy... found by name too) gated by anything but code or a
person, no failure-case evals, multi-agent with no timeout, judges with no deterministic
check. And each pattern's breaking point: loops with no cap or check, ReAct with no step
cap, critics sharing the writer's context or model, self-scored refinement, "parallel"
branches that need each other's output, coordinators with no fallback route, swarms with
no round limit, human steps with no reviewer, timeout or durable state, plans run without
review or re-checks, reflexion with no lessons file, event triggers with no condition,
dedupe or rate limit.

## 4. Build it

`$K list` shows how to build each pattern with Claude Code and this kit. Then hand the
design to `agent-graph-designer` to wire the steps, or `first-ai-team` for a standing
team. The `pattern-reviewer` agent reads existing agent code or a design doc and says which
pattern it really is.

## Corrections to the post

| Post | Here |
|---|---|
| Refinement example: the generator scores its own draft | The post's own warning applies: that score is gameable. The audit makes self-scoring an error; score with code or a separate agent. |
| Critic "with the same blind spots" | Concrete fix: its own context, a rubric, ideally another model, plus a deterministic check (rule 9). |
| Reflexion "carries memory" | Only if lessons are written to a file with a cap; in-context lessons vanish next run. |
| Loop, refinement, reflexion as three patterns | One skeleton (attempt, check, cap); they differ only in what carries over: nothing, a score, or lessons. |
| Human-in-the-loop needs durable state | In Claude Code, `ask` tools are refused in unattended `dontAsk` runs: queue the decision to a file and stop. |
| Parallel: "combined into one view" | Decide what the merge does when one branch fails or times out (rule 8). |
| Event-driven: "poorly defined triggers" | Add dedupe, a rate limit and a week of dry run that only logs. |

Full table of the 15 with examples and Claude Code builds: `references/patterns.md`.
