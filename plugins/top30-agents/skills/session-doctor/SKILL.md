---
name: session-doctor
description: Diagnose a Claude Code session that went badly - stuck retrying, lost the thread after compaction, kept hitting permission prompts, said "done" without testing - by reading its transcript offline and saying which layer failed (prompt, context, loop or harness) and which built-in command fixes it (/init, /context, /compact, /btw, /fork, /effort, /advisor, /rewind, /plan, /verify, /run, /background, /tasks, /debug, /insights). Use when the user asks why a session went wrong, why Claude got stuck or worse over time, before blaming the model, or wants a post-mortem of their last session.
---

# Session doctor

From a post (beamnxw on X, Nov 2026) listing 20 Claude Code commands under one idea: before
you blame the model, check the other layers. An agent is four layers, and most bad sessions
fail in one of the outer three:

| Layer | Fails as | Commands that fix it |
|---|---|---|
| **Prompt** | no CLAUDE.md, a 5-word ask, the same correction three times | `/init`, `/memory`, `/plan` |
| **Context** | auto-compaction, a window full of tool output, side questions in the main thread | `/context`, `/compact <keep>`, `/btw`, `/fork` |
| **Loop** | the same failing call retried, one file edited ten times, "done" with no test | `/rewind`, `/plan`, `/effort`, `/advisor`, `/verify`, `/run`, `/code-review` |
| **Harness** | permission denials, an untrusted folder, a build blocking the session | allow rules, `/background`, `/tasks`, `/debug` |

```bash
D="python3 ${CLAUDE_PLUGIN_ROOT}/skills/session-doctor/scripts/session_doctor.py"   # or this folder's scripts/
```

## Steps

1. Find the session: `$D list --project <folder>` shows recent sessions for that folder,
   newest first, with titles. The current session is usually the first one; the user often
   means the one before it.
2. `$D diagnose <session-id>` (or `--latest --project <folder>`). Add `--no-snippets` when
   the user might paste the output somewhere: it leaves prompt and error text out.
3. Report by layer, worst first. For each finding: what happened (with the transcript line),
   why it hurt, and the exact command to type next time. Then read the 2-3 flagged spots
   in the transcript yourself to confirm before stating a cause: the script finds patterns,
   not intent.
4. Close with the one change that would have helped most, which is usually a line in
   CLAUDE.md or a check command, not a different model.

For a pattern across many sessions rather than one, `/insights` writes an HTML report of
recent sessions; this skill is for one session in depth, offline.

## What it checks

| Signal | Layer | Threshold |
|---|---|---|
| Same tool call with the same input failed again | loop | 2+ (high at 3) |
| Same error text across different attempts | loop | 3+ |
| One file edited over and over | loop | 6+ edits |
| Code edited, no test/build/check after the last edit | loop | high if it then said "done" |
| Compaction | context | auto = warn, manual = info |
| One request carrying a lot of context | context | 150k+ tokens |
| Tool calls denied | harness | any |
| Folder's allow rules ignored (not trusted) | harness | any |
| Shell command blocking the session | harness | 120s+ or a timeout, not backgrounded |
| No CLAUDE.md in a git project | prompt | |
| Short opening prompt followed by a long session | prompt | <25 chars, 15+ calls |
| User corrections ("no,", "I said...") and interrupts | prompt | 2+ |

Exit code 1 when any finding is a warning or worse, so it can run after a headless job:
`claude -p ... ; $D diagnose --latest --project . --no-snippets`.

## Rules

- Read-only. The script never writes under `~/.claude/projects` and sends nothing anywhere.
  Transcripts contain everything the session saw, including secrets it read; don't copy
  them into the reply beyond the short evidence lines.
- Subagent (sidechain) rows are skipped unless `--include-subagents`.
- "No problems found" means the transcript shows none of these patterns, not that the
  result is correct.
- For the deeper read, the `session-reviewer` agent does steps 2-4 in a fresh context.

## The 20 commands from the post, checked

All 20 are real (code.claude.com/docs/en/commands, checked 2026-11-19). The full table with
the catches is in this kit's `playbooks/claude-commands.md`; the `which-command` skill picks
one for a situation.
