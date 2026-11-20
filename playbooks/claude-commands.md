# Playbook: Claude Code commands, fact-checked (15 + 20)

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

## 20 more, by layer (second list, checked 2026-11-19)

A second widely shared list (beamnxw on X, Nov 2026) gives 20 commands under one idea:
before you blame the model, check the prompt, the context, the loop and the harness. All 20
are real. Five were already above (`/compact`, `/rewind`, `/plan`, `/simplify`, `/mcp`);
the other fifteen, plus the ones that list shares with "worth knowing":

| Layer | Command | What it does | The catch |
|---|---|---|---|
| Prompt | `/init` | Writes a CLAUDE.md from the codebase | `CLAUDE_CODE_NEW_INIT=1` gives an interactive flow; it offers to import Codex or Gemini config. Review it: it loads every session |
| Prompt | `/model [model]` | Switches model; saved as your default | Press `s` in the picker to change it for this session only |
| Prompt | `/effort [level]` | Sets reasoning effort: `low`, `medium`, `high`, `xhigh`, `max`, `auto` | `max` lasts only this session. Higher effort is slower and costs more; try it on the hard step, not the whole session |
| Prompt | `/advisor [model\|off]` | Consults a second model for advice during the session | `fable` needs access; a second opinion, not a fix for a vague prompt |
| Context | `/context [all]` | A grid of what fills the context window | `all` expands every category. Look before you `/compact` |
| Context | `/btw <question>` | A side question answered without adding to the conversation | Good for "what does this flag do?" mid-task |
| Loop | `/fork [prompt]` | Copies this conversation into a background session in its own worktree | The fork's changes are on its branch until you merge them |
| Loop | `/background` (`/bg`) | Detaches the session so it keeps running and frees the terminal | Use it before a long build, not after it has blocked you |
| Loop | `/tasks` (`/bashes`) | Lists and manages background work: shells, subagents | Includes finished subagents, so check their results here |
| Loop | `/resume [id\|name]` | Reopens an earlier session | Name sessions so you can find them |
| Loop | `/diff` | Shows the working-tree changes in a viewer | Claude's edits and yours alike |
| Loop | `/verify`, `/run` | Skills that build, launch and drive the app to show a change works, not just that tests pass | `/run-skill-generator` teaches them a project that needs special steps |
| Harness | `/code-review [effort] [--fix\|--comment]` | Finds correctness bugs in the diff, a branch or a PR | `ultra` is a billed cloud multi-agent review you start yourself |
| Harness | `/security-review` | Security pass over your branch against origin's default branch | Needs an `origin` remote |
| Harness | `/autofix-pr` | Starts a cloud session that watches the current branch's PR and works on what comes up | Runs in the cloud: push first, and it only sees the pushed branch |
| Harness | `/claude-in-chrome` | Drives your Chrome for web testing and reading signed-in pages | Needs the Chrome extension (`claude --chrome`) |
| Harness | `/claude-api` | Reference and helpers for building on the Claude API (`migrate`, `cost-optimize`, ...) | For code that calls the API, not for Claude Code itself |
| Harness | `/insights` | An HTML report of patterns across your recent sessions | Not available in cloud sessions |
| Harness | `/debug` | Turns on debug logging from that point on | Logs only from when you run it: turn it on, then reproduce |

Three the list leaves out that belong beside these: `/doctor` (checks your setup), `/usage` (aliases `/cost`, `/stats`) and `/workflows` (watch, pause or save running
workflows such as `/deep-research`).

To see which layer failed in a session you already ran, the `session-doctor` skill reads
its transcript and maps what it finds to these commands.

## Tools in this kit that build on them

| Need | Use (plugin `top30-agents`) |
|---|---|
| A `/goal` that finishes | `goal-writer` skill: `goal_lint.py` scores a condition and has recipes for pytest, dbt, sqlfluff, `ora2sf`, reconciliation, mypy |
| A finish line a command decides, not a model | goal gate: a Stop hook that runs your check and keeps Claude working until it exits 0 |
| Safe `/batch` runs | `batch-scout` agent: independent units, shared-file owners, a check per unit, the `/batch` line to paste |
| "Which command do I need?" | `which-command` skill |
| Why did that session go wrong? | `session-doctor` skill and `session-reviewer` agent: which layer failed, and the command that fixes it |
| Loops and graphs in general | [loops-and-graphs.md](loops-and-graphs.md), `agent-loop`, `agent-graph-designer` |

## At work

The same rules as [before you try this at work](before-you-try-at-work.md): `/schedule` and
`/deep-research` run in Anthropic's cloud; `/remote-control` routes the session through
claude.ai. Check your firm's approval for each before using them on work repositories or data.
