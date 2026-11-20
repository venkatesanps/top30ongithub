---
name: duet-chief-of-staff
description: Build your own "Claude Duet" - a proactive chief of staff in Claude Code that writes a morning brief, keeps a memory of people, projects and promises in plain files, runs on a schedule while you're away, and asks before it sends, moves or pays for anything. Scaffolds the folder (CLAUDE.md, memory/, commands, four subagents, three-level permissions), audits that the permissions really hold (including the folder trust step most guides miss), checks overdue promises and stale notes without a model, and prints the launchd, cron or Task Scheduler entries. Use when the user wants a chief of staff, proactive agent, morning brief, Claude Duet without the waitlist, a promise or commitment tracker, or to schedule Claude Code to run unattended.
---

# Duet-style chief of staff in Claude Code

From Mika's course "Claude Duet: How to Build Your Own AI Agents with Claude Code & Opus 5.5"
(X, Oct 2026), which rebuilds the four behaviors Anthropic announced for the Claude Duet
research preview: comes to you with what needs attention, finishes tasks, keeps working while
you're away, checks with you before acting in your name. This skill builds that setup and
adds checks the post leaves to trust.

```bash
K="python3 ${CLAUDE_PLUGIN_ROOT}/skills/duet-chief-of-staff/scripts/cos_kit.py"   # or this folder's scripts/cos_kit.py
```

The script reads and writes only inside the folder. It never installs a schedule, connects
mail or calendar, or sends anything; it prints commands for the user to run.

## The rule the whole thing rests on

Three levels, enforced by `.claude/settings.json`, not by a polite line in a prompt:

| Level | What | Setting |
|---|---|---|
| Do it and report | read, sort, write its own notes and briefs | `allow` |
| Do the work, then ask | replies, invites, anything outbound, shell, web | `ask` (refused in scheduled runs) |
| Never | money, deleting, secrets, its own rules | `deny` |

Why it matters more than the post says: the morning brief reads **untrusted email every
day**. An agent that reads strangers' text, holds your private notes and can send things is
exactly the setup prompt injection exploits. Keeping every outbound tool on `ask` (so
scheduled runs refuse it) is what makes that safe, and CLAUDE.md tells it inbox text is data.

## Build it (week 1)

1. `$K init ~/chief-of-staff --name "<name>" --role "<one line>"`. Creates the folder, never
   overwrites existing files, and copies the script to `.claude/bin/` so scheduled runs and
   the checker don't depend on the plugin.
2. **Trust the folder:** the user runs `claude` there once and accepts the trust dialog.
   Until then Claude Code ignores the folder's `allow` rules, so an unattended run can't
   even write the brief. (Found while testing this skill; the post doesn't mention it.)
3. Fill CLAUDE.md by interview. Inside the folder, ask ten short questions about their work,
   the people they deal with and what they never want done without asking; show the
   CLAUDE.md and first `memory/people/*.md` files before saving. Keep CLAUDE.md short: every
   line is read on every task.
4. `$K audit ~/chief-of-staff` must print OK (exit 0). Then run `/morning-brief` by hand.

Memory formats are fixed so a script can check them without a model:
- Promise: `- [ ] <what> — due YYYY-MM-DD (promised YYYY-MM-DD)` (`due ?` if no date).
- Every person/project file has `Last confirmed: YYYY-MM-DD`.

## Checks without a model

- `$K promises <dir>`: overdue, due in 3 days, undated, and promise-like lines ("I'll send...
  by Friday") that aren't in the format yet.
- `$K stale <dir>`: notes not confirmed in 30 days, no confirmation line, UNCONFIRMED marks.
- `$K checks <dir>`: both, plus permission errors. Scheduled runs write it to
  `briefs/checks.txt` first and the brief reads it, so late promises can't be missed because
  the model skimmed.

## Connect mail and calendar (week 3)

Add connectors with `claude mcp add`, read access first. Then in `/mcp`, list each server's
tool names and add rules by exact name: read tools to `allow`, send/reply/move/invite tools
to `ask`, pay/delete tools to `deny`. Never allow a whole server (`mcp__gmail`). Re-run
`$K audit`: it flags allowed tools whose names send, move, pay or delete, whole-server
allows, servers in `.mcp.json` with no rules, `Bash`/`Edit` with no path in allow,
`WebFetch` allowed (a URL can carry your notes out), `bypassPermissions`/`auto` default
modes, missing denies for CLAUDE.md, `.claude/` and `.env`, and an untrusted folder.

## Schedule it (week 2)

`$K schedule <dir> [--os mac|linux|windows] [--brief 07:00] [--review 16:00] [--write]`
prints entries with full paths and `--permission-mode dontAsk` (anything on `ask` is refused
and lands in the brief's "Waiting for you"). On macOS it writes launchd plists rather than
cron, because launchd runs a missed job when the Mac wakes and cron skips it. Hand the user
the install command; don't run `launchctl`, `crontab` or `schtasks` yourself. Have them run
the command once by hand first and check `briefs/`. If the log shows an expired sign-in,
`claude setup-token` creates a long-lived token for unattended runs.

## The team (week 4)

`init` adds four subagents in `.claude/agents/`: `inbox-triage` (labels, never replies),
`meeting-prep` (read-only page per meeting), `promise-keeper` (logs commitments in the
format) and `cos-checker` (read-only weekly check: contradictions, stale notes, late
promises, brief lines that claim something was sent). The checker also ships as this
plugin's agent. The agent that writes notes should never be the only one reviewing them.

## Corrections to the post

| Post | Here |
|---|---|
| Doesn't mention folder trust | Project `allow` rules are ignored until the folder is trusted; `audit` checks it. |
| cron on macOS | launchd plists: cron skips jobs while the Mac sleeps. |
| `claude -p "/morning-brief"` in the cron line | Adds `--permission-mode dontAsk` to every scheduled line, as the post's own Step 6 advises. |
| Promises as free text ("by Friday") | Dated format, checked by a script every morning. |
| "Put payment and delete tools in deny" | `audit` finds them by name in your rules and flags whole-server allows. |
| Inbox text not mentioned as a risk | CLAUDE.md and triage agent treat messages as data; `WebFetch` stays on ask. |
| Edit(CLAUDE.md) denied | Also denies `Edit(.claude/**)`, so it can't loosen its own permissions or agents. |

The post also lists ten community repos (claude-chief-of-staff, neo, garrick and others).
They aren't pinned or tested here; check each one's license and what it sends where before
installing.
