# Playbook: 15 Claude Code commands, fact-checked

A widely shared list of "15 official Anthropic commands" for Claude Code. Every one is real.
Checked against the [commands reference](https://code.claude.com/docs/en/commands) and the
[/goal guide](https://code.claude.com/docs/en/goal) on 2026-11-08. Below: what each does, the
catch the list leaves out, and a data-engineering example. Type `/` in Claude Code to see what
your version has.

## The 15

| # | Command | What it does | The catch | Example |
|---|---|---|---|---|
| 1 | `/goal <condition>` | Keeps Claude working, turn after turn, until an evaluator model judges the condition met | The evaluator only reads the chat. State the check command and a bound | `/goal \`dbt build --select fct_orders+\` exits 0. Do not edit tests. Or stop after 20 turns.` |
| 2 | `/batch <instruction>` | Splits a large change into 5-30 units, shows the plan, then runs one background agent per unit in its own worktree | Needs a git repo (or v2.1.281+). Units must not share files | `/batch convert every view in legacy/views to Snowflake SQL, one view per unit` |
| 3 | `/subtask <task>` | A background subagent with the full conversation; its result comes back here | Needs agent view on | `/subtask write row-count recon queries for the tables we just migrated` |
| 4 | `/deep-research <question>` | A bundled workflow: parallel web searches, cross-checked sources, a cited report | Runs in the background; check its sources | `/deep-research Snowflake dynamic tables vs streams and tasks for CDC` |
| 5 | `/design [brief]` | Drafts UI mockups as editable artboards in a Claude Design artifact | Needs v2.1.265+ and artifacts; not on Bedrock, Google Cloud or Foundry | `/design a data-quality dashboard for nightly loads` |
| 6 | `/plan [task]` | Enters plan mode: Claude researches and proposes, then waits for approval before editing | Nothing changes until you approve | `/plan move the refiner scripts from cron to Airflow` |
| 7 | `/memory` | Edits CLAUDE.md files and auto memory | Keep rules short and true; they load every session | Add "never run DML against PROD_* databases" |
| 8 | `/compact [what to keep]` | Summarizes the conversation to free context | Say what must survive | `/compact keep the column mapping decisions and open TODOs` |
| 9 | `/branch [name]` | Branches the conversation; switches you into the branch | Return to the original with `/resume` | Try a MERGE-based load beside the INSERT OVERWRITE one |
| 10 | `/rewind` | Restores code and/or conversation to a checkpoint (aliases `/checkpoint`, `/undo`) | Only Claude's file edits come back. Commands it ran (SQL, pushes) don't | Undo a refactor that broke the tests |
| 11 | `/mcp` | Manages MCP connections and sign-ins | `/mcp reconnect all` retries failed servers | Re-authenticate the Snowflake or Datadog server |
| 12 | `/loop [interval] [prompt]` | Repeats a prompt while the session is open | Stops when you close the session | `/loop 10m check whether the 02:00 load finished and summarize failures` |
| 13 | `/schedule [description]` | Creates scheduled tasks that run in the cloud (alias `/routines`) | Runs in the cloud: no local files or VPN-only systems | Weekly Snowflake cost report from a repo |
| 14 | `/simplify [target]` | Four parallel reviewers: reuse, simplification, efficiency, abstraction. Applies the fixes | Doesn't look for bugs: follow it with `/code-review` | Tidy a refiner script before review |
| 15 | `/remote-control` | Makes this local session reachable from claude.ai, including your phone (alias `/rc`) | Needs a claude.ai subscription; the work still runs on your computer | Approve a long migration's next step from your phone |

The list's "start here: `/plan` → `/goal` → `/simplify`" is good, with one step added:
**`/plan` → `/goal` → `/simplify` → `/code-review`**, because `/simplify` doesn't look for bugs.

## Worth knowing beside the 15

| Command | Use |
|---|---|
| `/fork [prompt]` | Copy this conversation into a separate background session and keep working here |
| `/code-review [effort] [--fix]` | Find correctness bugs in the diff, a branch or a PR; `ultra` runs a cloud multi-agent review |
| `/security-review` | Security pass over your branch against origin's default branch |
| `/workflows` | Watch, pause or save running workflows (`/deep-research` is one) |
| `/tasks` | See background work in this session, including finished subagents |
| `/background` | Detach this session to run in the background and free the terminal |

## Tools in this kit that build on them

| Need | Use (plugin `top30-agents`) |
|---|---|
| A `/goal` that finishes | `goal-writer` skill: `goal_lint.py` scores a condition and has recipes for pytest, dbt, sqlfluff, `ora2sf`, reconciliation, mypy |
| A finish line a command decides, not a model | goal gate: a Stop hook that runs your check and keeps Claude working until it exits 0 |
| Safe `/batch` runs | `batch-scout` agent: independent units, shared-file owners, a check per unit, the `/batch` line to paste |
| "Which command do I need?" | `which-command` skill |
| Loops and graphs in general | [loops-and-graphs.md](loops-and-graphs.md), `agent-loop`, `agent-graph-designer` |

## At work

The same rules as [before you try this at work](before-you-try-at-work.md): `/schedule` and
`/deep-research` run in Anthropic's cloud; `/remote-control` routes the session through
claude.ai. Check your firm's approval for each before using them on work repositories or data.
