# Playbook: set up Claude Code in four folders (checked November 2026)

Prompted by a widely shared post: "building an agent comes down to four folders and a few pasted
prompts". Its order is right. Each piece builds on the last. Five details were wrong or out of
date, and they are fixed below. Each step is something you can do in a few minutes.

**Before any of this at work:** use the account and tools your firm approves, and its rules for
what code and data may leave your machine. Steps 4 and 5 can send data to outside services. See
[Before you try this at work](before-you-try-at-work.md).

| Step | Where it lives | What the post got wrong |
|---|---|---|
| 0. Install | native installer, desktop app or VS Code | `npm i -g` is deprecated |
| 1. Standing rules | `~/.claude/CLAUDE.md` | said `~/CLAUDE.md` |
| 2. Memory | `~/.claude/projects/<project>/memory/` | it's automatic; you don't have to set it up |
| 3. Skills | `~/.claude/skills/<name>/SKILL.md` | right |
| 4. Agents | `~/.claude/agents/<name>.md` | right, but a "95/100 gate" is only a prompt |
| 5. Scheduled runs | claude.ai/code/routines or `/schedule` | right, but your laptop's folders aren't there |

## 0. Install

The npm package is deprecated. Use the native installer: it needs no Node.js and no root, and it
updates itself. On macOS or Linux:

```bash
curl -fsSL https://claude.ai/install.sh | bash      # don't put sudo in front
claude doctor                                        # finds leftover installs
```

On Windows PowerShell, run `irm https://claude.ai/install.ps1 | iex`. If you installed with npm
before, run `npm uninstall -g @anthropic-ai/claude-code` so the old copy doesn't win on your PATH.
Your settings in `~/.claude/` stay as they are. If you'd rather click, the desktop app and the VS
Code extension use the same folders.

## 1. Standing rules: `~/.claude/CLAUDE.md`

Claude Code loads CLAUDE.md files at the start of every session. The one in `~/.claude/` holds
your personal rules for every project. A `CLAUDE.md` at a repo's root holds the team's rules and is
reviewed like code. A `CLAUDE.local.md` at the repo root holds your private rules for that repo;
keep it out of git.

Keep it short and specific. The more concise the rules, the more consistently they're followed.
The post's four headings work well:

```markdown
# Role
Lead data engineer. Snowflake, dbt and Airflow on AWS. I review more SQL than I write.

# Voice
Plain English, short sentences. Lead with the answer, then the reason.

# Banned words
leverage, robust, seamless, delve, game-changer

# Defaults
- SQL: Snowflake dialect, CTEs over nested subqueries, never SELECT *.
- Never run DML or DDL against a shared environment; give me the statement to run.
- Cost estimates: say which warehouse size and rate you assumed.
```

To have Claude draft it, paste this prompt (the post points at Boris Cherny's file as a template;
any good example works, and none is an official template):

> Interview me to write my `~/.claude/CLAUDE.md`. Ask one question at a time about my role, the
> tools I use, how I like answers written, words I never want to see, and the defaults you should
> assume (dialects, test commands, what you must never run). Then write the file under four
> headings (Role, Voice, Banned words, Defaults) in under 60 lines, and show it to me before saving.

## 2. Memory: `~/.claude/projects/<project>/memory/`

You don't need to set this up. Auto memory is on by default. When you correct Claude, it can save
the lesson as a topic file (`user_…`, `feedback_…`, `project_…`, `reference_…`) and list it in
`MEMORY.md`. Next session, that index loads.

What the post leaves out:

- Only the first 200 lines (or 25 KB) of `MEMORY.md` load at the start. Prune it now and then, or
  move rules that must always apply into CLAUDE.md.
- It stays on that machine. It doesn't sync, and cloud sessions (step 5) don't see it.
- To turn it off for a project, set `"autoMemoryEnabled": false` in its settings. To turn it off
  everywhere, set `CLAUDE_CODE_DISABLE_AUTO_MEMORY=1`.

The split that works: CLAUDE.md is how you want things done, and you write it. Memory is what
Claude learned about you and the project, and it writes that.

## 3. Skills: `~/.claude/skills/<name>/SKILL.md`

A skill is a folder with a `SKILL.md`. The description says when it fires, and the body says
what to do. Use `~/.claude/skills/` for skills you want in every project. Use `.claude/skills/`
inside a repo for skills the team shares and that cloud runs can see. Type `/<name>` to run one.

```markdown
---
name: weekly-status
description: Writes my weekly status from the week's merged PRs and closed tickets. Use when I ask for a status update or type /weekly-status.
---
Inputs: the repo, and the date range (default: the last 7 days).
1. List merged PRs and closed tickets in the range.
2. Group them under Shipped, In progress and Blocked. One line each, with links.
3. End with the top risk in one sentence. Keep it under 200 words, in my Voice from CLAUDE.md.
Output: Markdown in the chat. Don't post it anywhere.
```

The connectors the post mentions (Notion, Gmail, Drive) are MCP servers in Claude Code. Add only
the ones the skill needs. Each one is a place your data goes, so at work use only approved ones.
[Skills, plugins and the kit](../README.md) has ready-made skills to start from.

## 4. Agents: `~/.claude/agents/<name>.md`

Each file is one specialist with its own context window, tools and model. The `model` field takes
`opus`, `sonnet`, `haiku`, a full model ID, or `inherit`. The post's split is a good default:
Opus for roles that analyze and judge, Sonnet for roles that execute.

```markdown
---
name: qa-gate
description: Reviews finished work against the brief before it's handed over. Use after the builder finishes.
tools: Read, Grep, Glob
model: opus
---
You did not write this work, and you get no credit for passing it.
Check it against the brief's acceptance list, item by item: pass or fail, with the evidence.
Then score it out of 100. Any failed item, or a score under 95, is a FAIL: list what to fix.
```

Two catches:

- The "95 out of 100" is a number a model gives itself. It isn't a measurement. A pass/fail
  checklist with evidence, plus a test that must run green, is the gate that holds. The score
  just sorts the misses. [Loops and graphs](loops-and-graphs.md) covers checks that can actually
  fail.
- One open bug report says subagents always run on the main session's model, whatever the model
  field says. After setting it up, check your usage page to confirm Sonnet usage moves.

## 5. Run it without you: scheduled tasks (routines)

A routine, now also called a cloud scheduled task, packages a prompt, one or more repos and some
connectors. It runs on Anthropic's cloud, on a schedule, from an API call or on a GitHub event,
so your laptop can be closed. Create one at claude.ai/code/routines, from the desktop app, or with
`/schedule` in the CLI. It needs a paid plan.

What to know before you rely on one:

- **It runs with no approval prompts.** Anything it can reach, it can change. Give it the fewest
  connectors and repos the job needs.
- **It starts fresh each time.** A run sees the repo, not your laptop: `~/.claude/CLAUDE.md`, your
  personal skills and agents, and your memory folder aren't there. Commit what it needs to the
  repo's `CLAUDE.md` and `.claude/skills/` and `.claude/agents/` folders.
- **The schedule uses your time zone.** "8am UK" is 2am in Texas (3am during the few weeks the
  US and UK change clocks on different dates).
- **Output to Notion means a Notion connector.** The routine writes there with that connector's
  permissions.
- **At work:** a routine sends the repo and what its connectors read to the cloud. Only use one
  where your firm allows that code and data to leave its network.

## Order and time

Install, then CLAUDE.md, then a week of normal use so memory fills in, then one skill for the task
you repeat most, then agents, then a routine. The first two steps take about 10 minutes, as the
post says. Budget an afternoon for the rest, because each needs a real run to check it.

## Sources (checked 2026-11-21)

- Install and the npm deprecation: <https://code.claude.com/docs/en/setup>,
  <https://github.com/anthropics/claude-code>
- CLAUDE.md and auto memory: <https://code.claude.com/docs/en/memory>
- Subagents and the `model` field: <https://code.claude.com/docs/en/sub-agents>; model routing
  bug report: <https://github.com/anthropics/claude-code/issues/43869>
- Routines / scheduled tasks: <https://code.claude.com/docs/en/routines>,
  <https://code.claude.com/docs/en/web-scheduled-tasks>
