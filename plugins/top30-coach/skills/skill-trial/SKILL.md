---
name: skill-trial
description: Coach the user through adopting skills and plugins one at a time - start a one-week trial of a single skill, log each real use with minutes saved, then keep, extend or drop it on evidence, and suggest the next one for their role from the top30ongithub kit. Use when the user asks which skill to try next, wants to start or check a skill trial, asks whether a skill is worth keeping, or has installed too many skills.
---

# Skill trial

The rule this skill enforces: **one skill at a time, on real work, for a week. Keep it only if
it saved time. Three skills you use every day beat thirty you never open.** Every enabled
skill or plugin also adds to every session's context, so unused ones cost something.

All state is in `~/.claude/skill-trials.json`, written by `scripts/trial.py`. The script never
installs or removes anything; give the user the command and let them run it.

```bash
T="python3 ${CLAUDE_PLUGIN_ROOT}/skills/skill-trial/scripts/trial.py"   # or this folder's scripts/trial.py
```

## Pick the next one

1. Ask their role if you don't know it: `data`, `manager`, `sre`, `writer`, `design`, `builder`.
2. `$T suggest --role <role> --catalog <path to top30ongithub/catalog.json>`
   (a clone at `~/top30ongithub` or the current folder is found automatically).
3. Recommend one of the three, matched to a task they do this week. Say what it costs per
   session. If they named a skill outside the kit, that works too: `$T start <name>`.

## Start

`$T start <kit # or name> --goal "<the task it should speed up>"`. Then tell them the install
command it prints (kit items: `./install.sh <n>` from their clone), and to restart Claude Code
if it's a plugin. Only one trial runs at a time; don't start a second without asking whether
to abandon the first (`--force`).

## Log real uses

When a task in this conversation used the trial skill and the task is done, ask once, briefly:
"Did <skill> save you time on that? Roughly how many minutes (negative if it slowed you down)?"
Then `$T log --saved <minutes> --note "<task in a few words>"`. Don't log uses the user didn't
confirm, and don't ask after every message.

`$T status` shows uses, minutes and days left.

## Review

When the week is up (or they ask): `$T review` (add `--now` to judge early).

- **keep**: 3+ uses and time saved overall.
- **extend** one more week: 1–2 uses. A second extension becomes a drop.
- **drop**: never used, or it cost time overall. Give them the disable or uninstall command.

Report the verdict with the numbers, then offer the next suggestion. If they already keep three
or more, ask which one they no longer open before adding another.

`$T history` lists every finished trial.
