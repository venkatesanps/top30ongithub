# Playbook: rolling this out to your team

Goal: every engineer saves real time on daily work within a month, and you can show it.

## Week 1 — leads only

- Two or three volunteers install a small set: **30** I Have ADHD (answers first), **1** Karpathy
  Skills (fewer surprise edits), **5** Superpowers or **4** Agent Skills (plan, test, verify).
- Each keeps a note: task, time before, time with the assistant, what went wrong.
- Before adding a plugin to the team set, run it through `scripts/ab.py` on a real task from
  your backlog (same prompt, plugin off vs on). No better result or lower cost, no place in the set.
- Write the team's `CLAUDE.md`: stack, naming, test commands, "never do" list.

## Week 2 — pick three daily tasks to target

Good first targets for a data team:

1. Writing and reviewing SQL / dbt models (**32**, **42**).
2. Triaging failed jobs and DAG runs (**33**, **34**).
3. Writing ticket updates, runbooks and PR descriptions (**44**).

Run a 30-minute session per task: the lead shows one real example end to end.

## Week 3 — whole team, with guardrails

- Everyone installs the agreed set with `./install.sh <numbers>` and checks it with `./verify.sh`.
- Shared skills live in each repo's `.claude/skills/` and go through code review.
- Read [Before you try this at work](before-you-try-at-work.md) together.

## Week 4 — measure and decide

- Turn on the Claude Code ROI stack (**48**) or collect `ccusage` totals (**49**).
- Compare: PR cycle time, failed-job time-to-fix, and the volunteers' notes from week 1.
- Keep what helped, drop what didn't, and write down why (the next team will ask). Each plugin
  you keep adds to every session's context, so the team set should stay small.

## Habits that make it stick

- **Show, don't mandate.** One good demo at standup beats a policy doc.
- **Office hours.** 30 minutes a week where people bring a stuck task.
- **Share wins and misses** in one channel. Misses teach the team where not to trust it.
- **Refresh monthly.** `git pull` this repo; the daily check flags tools that moved or broke.
