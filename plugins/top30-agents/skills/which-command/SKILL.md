---
name: which-command
description: Pick the right Claude Code built-in command for the situation - /plan, /goal, /loop, /schedule, /batch, /subtask, /fork, /branch, /rewind, /compact, /simplify, /code-review, /deep-research, /design, /remote-control, /mcp, /memory - with the catches each one has. Use when the user asks which command to use, how to make Claude keep going, run things in parallel, undo, save context, review code, or automate something, or when a command they tried did the wrong thing.
---

# Which command

Match the user's situation to one command, say why in a sentence, give the exact line to type,
and name the catch that applies. Facts below were checked against the Claude Code commands
reference (code.claude.com/docs/en/commands) in November 2026; versions change, so if a command
isn't in the user's `/` menu, they need to update Claude Code.

## Before changing code

| Situation | Command | Catch |
|---|---|---|
| Want to see the approach before any edit | `/plan <task>` | Plan mode reads, never edits. Approve the plan to start. |
| Need researched facts with sources | `/deep-research <question>` | A bundled workflow: fans out searches in the background and returns a cited report. |
| Need a UI mockup to react to | `/design <brief>` | Needs v2.1.265+, artifacts on, and isn't available on Bedrock, Google Cloud or Foundry. |

## Keep it going without me

| Situation | Command | Catch |
|---|---|---|
| Work until a condition holds | `/goal <condition>` | The evaluator only reads the chat: state the check command and a bound. Use the `goal-writer` skill. |
| Must not stop until a command exits 0 | goal gate (`goal-writer` skill) | A Stop hook that runs the command itself. |
| Re-check something every N minutes while I'm here | `/loop 5m <prompt>` | Only while the session stays open. |
| Recurring job that runs when I'm away | `/schedule <description>` | Runs in the cloud, not on your machine; it can't see local-only files or VPN resources. |
| Drive this session from my phone | `/remote-control` | Needs a claude.ai subscription; the session keeps running on your computer. |

## Parallel work

| Situation | Command | Catch |
|---|---|---|
| One big mechanical change across many files | `/batch <instruction>` | Splits into 5-30 units with one background agent per unit in its own worktree. Needs git (or v2.1.281+). Units must be independent: use the `batch-scout` agent first. |
| Side task that should report back here | `/subtask <task>` | Inherits the whole conversation. Needs agent view on. |
| A copy of this session working on its own | `/fork <prompt>` | Runs as a separate background session. |
| Try another direction, keep this one | `/branch [name]` | Switches you into the branch; return with `/resume`. |

## Undo and context

| Situation | Command | Catch |
|---|---|---|
| Go back to before a change | `/rewind` (also `/checkpoint`, `/undo`) | Restores Claude's edits and the conversation. Commands Claude ran (DB writes, pushes) aren't undone. |
| Context is full or drifting | `/compact <what to keep>` | Say what must survive, e.g. "keep the schema decisions and open TODOs". |
| Teach the project a standing rule | `/memory` | Edits CLAUDE.md and auto memory; keep rules short and true. |
| Add, fix or re-auth a tool connection | `/mcp` | `/mcp reconnect all` retries failed servers. |

## Before merging

| Situation | Command | Catch |
|---|---|---|
| Tidy the change | `/simplify` | Four parallel reviewers for reuse, simplicity, efficiency, abstraction. It does **not** look for bugs. |
| Find bugs | `/code-review` | Effort levels up to `ultra` (cloud multi-agent review). |
| Security pass | `/security-review` | Reviews your branch against origin's default branch. |

## A good default flow

`/plan` → `/goal` (with a stated check and a bound) → `/simplify` → `/code-review`.
For a large mechanical change: `batch-scout` agent → `/batch` → `/code-review`.
