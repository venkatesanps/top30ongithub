# Claude Ship starter files

Drop-in files for Claude Ship's three agents (Code Review, PR Steward, Claude Approvals) and the
local `/code-review`, `/ship` and `/steward` commands. The how and why is in
[playbooks/claude-ship.md](../../playbooks/claude-ship.md).

The files here are stored under flat names on purpose: a `.claude/` folder or `approvals.yml`
inside this repo could be picked up by Claude Code or Claude Approvals as if it were live.
`apply.sh` puts each one where it belongs in your repo.

| File here | Goes to | Read by | When |
|---|---|---|---|
| `REVIEW.md` | `REVIEW.md` (root) | Code Review (cloud) | From the default branch, never from the PR under review |
| `steward.SKILL.md` | `.claude/skills/steward/SKILL.md` | `/ship`, `/steward` (local watch) and PR Steward (cloud) | Local: your working directory. Cloud: the default branch |
| `verify.SKILL.md` | `.claude/skills/verify/SKILL.md` | Claude Code, before committing | Any session in that folder |
| `approvals.observe.yml` | `.claude/approvals.yml` | Claude Approvals | From the default branch; merging it turns Approvals on |

Local `/code-review` (and so `/ship`) reads `CLAUDE.md`, not `REVIEW.md`. Keep your "Always
check" rules in both if you use both.

```bash
templates/claude-ship/apply.sh ~/code/my-repo --dry-run
templates/claude-ship/apply.sh ~/code/my-repo                    # REVIEW.md, steward, verify
templates/claude-ship/apply.sh ~/code/my-repo --with-approvals   # after an Owner agrees
```

It never overwrites and never commits. Edit the examples, commit them yourself and get the PR
approved by someone else.

This repository uses the same pattern for itself: see the root `REVIEW.md` and
`.claude/skills/steward/` and `.claude/skills/verify/`.
