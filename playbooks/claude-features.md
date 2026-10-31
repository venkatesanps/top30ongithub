# Playbook: Claude features worth setting up (checked October 2026)

Prompted by a widely shared "hidden features in Claude" post (by Anatoli Kopadze). Each feature
below was checked against Anthropic's current help and API docs, rewritten for a manager and
lead data engineer, and given a setup you can use at work. Where the post was wrong or out of
date, the correction is at the end.

**Before any of this at work:** use the Claude account your firm provides (Team or Enterprise)
and its rules for what data may go in. On those plans an admin decides which features are on,
so some items below may be missing or switched off for you. See
[Before you try this at work](before-you-try-at-work.md).

## Set up once, benefit every day

### 1. Projects: standing context per piece of work
A project holds instructions and reference files, and every chat inside it starts with them. All
plans have Projects (free accounts are limited to five). On paid plans, large project knowledge
switches to retrieval automatically, so it can hold far more than one chat.

One project per stream of work beats one giant project. For example:

```text
Project: Snowflake refiner pipeline
Instructions:
You help me maintain our Snowflake transformation ("refiner") scripts. Stack: AWS, Snowflake,
dbt, Airflow. Assume senior-engineer knowledge; don't explain basics.
When I share SQL: check grain, join keys, idempotency and pruning before style.
When I ask for a change: give the diff, then a 3-line test plan.
Say when you're unsure or need a table definition; never invent column names.
Knowledge: data dictionary export, naming standards, the last two incident write-ups.
```

### 2. Memory: so you stop re-introducing yourself
Claude saves useful facts about you as you chat, and you can say "remember that..." to add one
or "forget..." to remove one. Everything it remembers is listed (and editable) in Settings, under
Your Claude → Manage memory. Each project keeps its own memory, and you can stop a project from
using your account-wide memory.

- **Default:** on for Free, Pro, Max and Ultra. On Team and Enterprise, the owner decides
  whether memory is available, and then each member turns it on for themselves.
- **Privacy:** incognito chats are never remembered. Sensitive topics (health, politics,
  religion) aren't stored unless you turn that on. Admins can't read your memories.

### 3. Standing rules for code: `CLAUDE.md`
Claude Code reads `CLAUDE.md` at the start of every session: put one in the repo root with the
team's conventions, and keep personal ones in `~/.claude/CLAUDE.md`. Review it like code. For the
Claude app, use project instructions (1) instead.

```markdown
# Refiner repo: rules for Claude
- Snowflake SQL, lowercase keywords, CTEs over nested subqueries, no SELECT * in models.
- Every model change needs a dbt test; run `dbt build -s <model>+` before saying it's done.
- Never touch prod connections or `profiles.yml`. Never run DELETE/TRUNCATE without asking.
- Commit messages: imperative, reference the Jira key (DATA-123).
```

### 4. Skills: package a workflow once
A skill is a folder of instructions (and optionally scripts) that Claude loads when a task
matches. Skills are available on every plan. They need "Code execution and file creation"
turned on, and they're managed under Customize → Skills, where you can also upload your own as a
ZIP. Install skills only from sources you trust, and read anything a colleague sends before
enabling it: a skill can carry scripts and instructions.

In this kit: the [Datadog investigator](../plugins/top30-ops/skills/datadog-app-investigator/)
and the upload-ready zips in [`claude-ai-skills/`](../claude-ai-skills/).

## Make it think harder when it matters

### 5. Thinking and effort
In the model menu next to the send button, newer models (Opus 5.5, Sonnet 5.5, Opus 4.7) have an
**Effort** level with a **Thinking** toggle under it. Other models have an **Extended** toggle.
Leave thinking off for quick questions. Turn it on, at high effort, for decisions, designs and
debugging, where you want Claude to work through the problem before answering. The post called
this "Adaptive Thinking"; the apps label it Thinking or Extended.

Use it with a decision prompt:

```text
Think this through before answering. I'm choosing between:
A: migrate the nightly Oracle extracts to Snowflake tasks + streams now
B: keep Informatica for another two quarters and migrate by domain
Context: 4 engineers, a Q1 audit, 140 mappings, two of them business-critical.
Work out second-order effects, what I'm likely over- or under-weighting, the facts that would
flip the answer, and which option fails more gracefully. Then recommend one and say why.
```

## Build things, not just text

### 6. Artifacts: working pages in the chat
Claude can build a working page (a calculator, tracker, chart or dashboard) that you use in the
side panel and can share by link. Good first builds for a team lead:

- an on-call handover checklist the team fills in
- a Snowflake credit estimator (warehouse size × hours × credit price)
- a sprint capacity planner for leave and holidays

Say how saved data should behave. Data kept only in your own browser can vanish; for shared or
lasting data, ask Claude to store it with the artifact.

### 7. Claude Design: visual work
Claude Design is an Anthropic Labs research preview at claude.ai/design. It makes slide decks,
one-pagers and prototypes, and exports to PDF, PPTX, HTML or Canva. It's on Pro, Max, Team and
Enterprise; Enterprise organizations must switch it on. Use it for the quarterly platform update
or a roadmap one-pager.

## Let it act for you

### 8. Claude in Chrome
A browser extension that reads the page you're on and can click, fill in and navigate. It's on
paid plans (Pro, Max, Team, Enterprise) and works in Google Chrome only, not other Chromium
browsers. It's powerful and still risky: keep it away from banking, HR and production consoles,
and let your admin's allowlist decide where it can go. A safe first task is reading
public vendor docs or release notes into a comparison table.

### 9. The Claude desktop app: your files, and tasks on a schedule
The desktop app can work directly with folders you connect: it reads, creates and edits files
there, so you don't have to paste them in. The post calls this "Cowork"; it is now simply part of
Claude. Desktop **scheduled tasks** run a saved prompt hourly, daily, on weekdays or weekly, on
paid plans. They run only while your computer is awake and the app is open; a missed run happens
when the app next opens.

A scheduled task worth having:

```text
Every weekday at 7:45: read the files in ~/Reports/airflow-failures/ added since yesterday,
group failures by DAG and likely cause, flag anything that failed 3+ days running, and write
standup-YYYY-MM-DD.md in ~/Reports/standup/ with a 5-line summary at the top.
```

### 10. Claude Code (and Claude Code in GitHub)
These are covered in this kit as items **70** (Claude Code) and **71** (Claude Code Action, with a
SQL-review workflow for Amazon Bedrock). Item **69** and
[examples/sql-review-agent](../examples/sql-review-agent/) show how to build your own agent.

## For developers: prompt caching, with real numbers

When many calls share a large prefix (a long system prompt, a data dictionary, tool
definitions), mark it with `cache_control` and later calls read it from cache instead of
reprocessing it.

| | Cost vs normal input |
|---|---|
| Cache write, 5-minute TTL (default) | 1.25× |
| Cache write, 1-hour TTL (`"ttl": "1h"`) | 2× |
| Cache read, most models | 0.1× (90% off) |
| Cache read, Opus 5.5 and Sonnet 5.5 | 0.05× (95% off) |

- **Minimum size:** prompts below the model's minimum aren't cached at all, even when marked.
  The minimum is 512 tokens on the 5.x models, 1,024 on Sonnet 5 and 4.6, 2,048 on Opus 4.7,
  and 4,096 on Haiku 4.5.
- **Automatic mode:** a single top-level `"cache_control": {"type": "ephemeral"}` caches the
  conversation as it grows. The older Bedrock integration (Opus 4.6 and earlier) rejects this;
  use block-level markers there.
- **What you'll actually save:** the first call costs more than an uncached one, so savings
  build up over calls. [examples/prompt-caching](../examples/prompt-caching/cache_demo.py)
  measures it from the API's own usage fields: with three questions on a 10k-token document,
  input cost falls by about half; with many questions, it approaches the 90% figure.

## Role prompts that help a manager

Paste one at the start of a chat. They work best with thinking on.

**Stress-test a plan before you present it**

```text
Act as a skeptical engineering director who has seen many platform migrations fail. I'll share
a plan. Find the weakest assumptions, the risks I'm downplaying, and the question my VP will ask
that I can't answer yet. No reassurance. End with the one thing to fix before Thursday.
```

**Case against a decision you've already made**

```text
I've decided: [decision]. My reasons: [reasons]. Objections I've already handled: [list].
Make the strongest case against it: the assumptions most likely to be wrong, the three most
realistic ways it backfires, and what I'd have to believe for it to be a mistake. Don't balance it.
```

**Rehearse a hard conversation**

```text
Play [person: e.g. a senior engineer whose last two releases caused incidents; proud, defensive,
well-liked]. I need to [goal: agree a recovery plan without losing them]. Stay in character and
react as they would, pushing back when I'm vague. After each exchange, step out for one line on
what landed and what didn't. Finish with a debrief and three phrases to use in the real meeting.
Wait for me to open.
```

The post also suggests playing a therapist and a personal trainer. Claude can be a good sounding
board for working through a decision, but it isn't therapy, and a training plan should account
for injuries a professional has assessed.

## Corrections to the original post

| Post says | Current docs (Oct 2026) |
|---|---|
| Memory is off by default | On by default for Free, Pro, Max and Ultra. On Team and Enterprise, the owner enables it and each member opts in. |
| "Adaptive Thinking" toggle | The apps label it Thinking (under Effort, on newer models) or Extended. |
| Cowork is a separate desktop app | Its capabilities are now part of Claude. Desktop scheduled tasks need the computer awake and the app open. |
| Prompt caching gives 90% off | 90% off reads on most models, 95% on Opus 5.5 and Sonnet 5.5. Writes cost 1.25× (or 2× for 1 hour), and prompts below the model's minimum aren't cached. |
| Caching example uses `claude-opus-4-6` | That model still works; current models are the 5.x family, and automatic (top-level) caching now exists. |
| Claude Design for everyone | A research preview on paid plans; off by default for Enterprise. |
| Claude in Chrome on any page | Paid plans and Google Chrome only; admins can restrict sites. |

Sources: Anthropic help center articles on memory, projects, skills, model and thinking
settings, Claude in Chrome and scheduled tasks (support.claude.com); the prompt caching guide
(platform.claude.com/docs/en/build-with-claude/prompt-caching); Unite.AI on the Claude Design launch.
