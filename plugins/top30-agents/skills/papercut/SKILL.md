---
name: papercut
description: File a short structured bug report (a "papercut") when a skill, tool, command, MCP server or doc misbehaves - a flag the help lists but the tool rejects, a command that exits 0 on an error, an empty result that should match, wrong units, an out-of-date doc, or the same error twice in a row. Search earlier papercuts for a workaround first, file once per distinct problem, then carry on with the task. Also summarizes papercuts for a skill's owner. Reports stay on this machine.
---

# Papercut

Agents notice when they are fighting a tool, then spend tokens working around it and the lesson is
lost. A papercut turns that moment into a short report that the skill's owner can fix from.
After the papercut loop Uber describes for its skills marketplace ("How Uber Evals 1 Million Agent
Skill Invocations a Month", November 2026), kept local: reports go to
`~/.claude/papercuts/papercuts.jsonl` (or `$PAPERCUT_LOG`), one JSON line each, and nothing is
sent anywhere.

`P` below is `python3 "${CLAUDE_PLUGIN_ROOT}/skills/papercut/scripts/papercut.py"` (use the path inside
this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set).

## When to file

File when something outside your own reasoning is wrong, and you can say what you expected:

- a flag or option the help text lists, which the tool then rejects
- a command that exits 0 but printed an error, or exits non-zero on success
- a query or search that returns nothing where a match clearly exists
- wrong units or formats (seconds where milliseconds are expected), a silent default
- a skill's instructions that are out of date, or point to files or commands that don't exist
- the same error twice in a row after a reasonable fix, or ten turns spent on one obstacle

Don't file your own mistakes, a missing permission the user hasn't granted, or ordinary failing
tests that the task is about.

## Steps

1. **Search first.** Someone may have found a way around it already:
   ```bash
   $P search "words from the error" --skill <skill-name>
   ```
   Check the output: `0 matches` means it's new; otherwise try the listed workaround before
   anything else.
2. **File it once.** Summarise; don't paste prompts, file contents or long logs:
   ```bash
   $P file --skill <skill-name> --tool <command> \
     --tried "ran gh pr checks on a repo with no CI" \
     --expected "a 'no checks' result" --got "404 repeated until timeout" \
     --fix "treat 404 from the checks API as 'no CI configured'" \
     --workaround "skipped the wait step"
   ```
   Confirm it prints `filed <id>`. If it reports earlier copies of the same problem, don't file again.
3. **Carry on with the task,** using the workaround. In your final message, add one line:
   `Filed papercut <id> on <skill>: <what broke>`. Check the details with `$P show <id>` if the
   user asks.
4. **For a skill's owner:** see what to fix first, most-reported first:
   ```bash
   $P summary --skill <skill-name> --days 30
   $P export --skill <skill-name>                       # issue text for the top problem
   $P export --skill <skill-name> --gh owner/repo       # writes a body file, prints the gh command
   ```
   Verify the counts look right before acting on them. `export` never posts: running the printed
   `gh issue create` command sends the report to GitHub, so do that only when the user says to.

## What a report holds

| Field | Contents |
|---|---|
| `skill`, `skill_version`, `tool` | what misbehaved |
| `tried`, `expected`, `got` | one line each, in your own words |
| `fix`, `workaround` | what would fix it for good; what got you past it this time |
| `severity` | low, medium (default) or high |
| `sig` | a signature of skill, tool and the error with numbers removed, used to group repeats |

Every field is collapsed to one line, capped at 300 characters, and scrubbed of keys, tokens,
passwords, emails and your home path. There is no field for prompt text or file contents, and the
script refuses to write its log inside a git repository.

## When it fails

| Failure | Fix |
|---|---|
| `... is inside a git repository` | Set `PAPERCUT_LOG` to a path outside the repo, e.g. `~/.claude/papercuts/team.jsonl` |
| `--tried is required` (or `--expected`, `--got`) | Fill all three; a report without them can't be acted on |
| `search` finds nothing you expected | Search with fewer, rarer words from the error, or drop `--skill` |
| A report shows `[REDACTED]` where it shouldn't | Reword the field without the `key=value` shape that looks like a secret |
| `summary` splits one problem into several groups | Use the same `--skill` and `--tool` names each time; the signature includes both |

## Make it always available

Installing the plugin makes the skill available, but an agent only uses it when it thinks of it.
To make filing a habit, add this line to `~/.claude/CLAUDE.md` or a repo's `CLAUDE.md`:

```markdown
When a skill, tool or doc misbehaves and costs you more than a couple of turns, search and file a papercut (papercut skill), then carry on.
```

Check it took effect by asking in a new session which skill handles a broken tool flag.
