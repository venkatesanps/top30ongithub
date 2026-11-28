# Playbook: Claude Ship, the work after you open a PR

Claude Ship is three agents for what happens after a PR is opened: find issues, fix them, and
decide whether it can merge. This summarizes Anthropic's guide "A practical guide to shipping with
Claude Code" (Claude Code team, November 25, 2026). **Not yet checked against the Claude Code docs:**
Code Review is generally available, but PR Steward and Claude Approvals are in beta, so type `/` in
Claude Code to see what your version has. Starter files are in
[`templates/claude-ship/`](../templates/claude-ship/).

GitHub only (it uses `gh` and the Claude GitHub App). Read
[Before you try this at work](before-you-try-at-work.md) first.

## The three agents

| Agent | What it does | Status | Runs as |
|---|---|---|---|
| Code Review | Reviews the PR through several lenses, checks its own findings adversarially, sorts them and posts them on the PR | Generally available | Cloud service, turned on by an org Owner |
| PR Steward | Keeps the PR green: failing checks, merge conflicts, review comments. Comments after each push with what changed and how to undo it. Never approves or merges | Beta | `claude[bot]` in the cloud, or you locally with `/steward` |
| Claude Approvals | Applies a policy file (`.claude/approvals.yml`) that says when Claude may approve and when people must. Like a smarter CODEOWNERS | Beta | Cloud check |

## The local commands (no admin needed)

| Command | What it does | The catch |
|---|---|---|
| `/code-review [low…max] [PR]` | Reviews your branch's commits and uncommitted changes for correctness bugs. Low effort reports only what it's surest of | Remembers your last effort. Reads `CLAUDE.md`, **not** `REVIEW.md` |
| `/code-review --fix` | Applies the findings to your working tree | Edits from a background review may not come back with `/rewind`: commit first |
| `/code-review --comment 1234` | Posts the findings on PR 1234 | Visible to the whole team |
| `/code-review ultra` | Deeper review in the cloud | Sends code to the cloud, needs a login, can be billed apart from your plan |
| `/ship [effort] [PR] [+bot]` | Commits everything (like `git add -A`), branches if needed, pushes, opens the PR as you, reviews and fixes, then watches the PR for up to 7 days | Run `git status` first. Won't commit secret-looking files or rule files. Commits nothing in public repos |
| `/steward [PR]` | Only the watch: works on checks, conflicts and comments, no review first | Does nothing if the PR already has the Steward label. One watch per session |
| `/ship stop`, `/steward stop` | Ends the watch | Starting a new watch also ends the old one |
| `/ship terms` | Shows the full terms of the watch | Read before your first watch |

**What the watch reads:** comments from you, people with write access and the Claude GitHub App.
`+name` adds a bot, and its comments are treated as claims to check against the code.

**What it escalates:** redesigns or wider scope, a security issue it couldn't resolve, and any
issue still failing after 3 pushes (it reports what it tried).

## Before you run the watch

- **It runs on your machine, as you, on your quota.** Keep the session open and the laptop awake.
  Needs `gh auth login` and only watches PRs you opened. It won't watch in bypass-permissions
  mode, and in most permission modes it stops at prompts and waits for you. On Windows, `/ship`
  opens and reviews the PR but the watch doesn't start.
- **Give it its own checkout.** It needs the branch left checked out: start your next task in a
  separate worktree (`git worktree add ../next-task -b next-task`).
- **Trust the repo.** It merges the base branch and runs your tests, so anyone who can land on the
  base branch can run commands on your machine. Your test script runs with your credentials.
- **The guards have gaps.** Claude can't merge or force-push during unattended turns, and its commits
  leave out `.github/`, `CODEOWNERS`, `CLAUDE.md`, `.claude/` and git hooks. But typing a message
  mid-turn lifts the limits for that turn, and with auto-merge on, a fix of its own can be what lets
  GitHub merge.
- **Git hooks don't run on its commits.** Anything that must hold goes into CI and branch rules.
- **A PreToolUse or PermissionRequest hook on Bash** in the repo's `.claude/settings.json` stops the
  watch from starting (it still reviews).
- **Watch the bill.** It uses model turns while you're away. Stay near your machine the first time.

Good candidates: a PR with red checks, or one stuck in a conflict loop. Bad: a PR in the middle of a
design debate, which is yours to settle.

## Turn repeats into files

Rule of thumb from the guide: a pattern must repeat on at least 2 PRs before it becomes a rule, a
person approves the PR that adds it, and rules get deleted when they stop helping. `/ship` won't
commit these files, so commit them yourself.

| You keep seeing | Write it in | Read by |
|---|---|---|
| The same review comment | `CLAUDE.md` (local review) and root `REVIEW.md` (Code Review) | `/code-review`, `/ship`; Code Review from the default branch |
| Claude working out how to run the app | `.claude/skills/verify/SKILL.md` | Claude Code before committing |
| The same PR upkeep (lockfiles, flaky jobs, pre-push checks) | `.claude/skills/steward/SKILL.md` | Local watch from your working directory; PR Steward from the default branch |

```bash
templates/claude-ship/apply.sh ~/code/my-repo --dry-run   # REVIEW.md, steward and verify, never overwrites
```

Code Review never reads `REVIEW.md` from the PR under review, and it only honors path exclusions
and the Nit cap when the default branch is protected. Anyone who can merge can edit the steward
file: review changes to it like CI changes.

## Across the team (needs admins)

Ask for one repository, a few volunteers and a fixed trial period. Agree the budget first.

The comment commands below are written `@claude …`: the copy of the guide used here lost the
mention handle, so confirm the exact handle in your GitHub App setup.

1. **Protect the default branch.** A repo admin requires a PR with approval on the latest push, and
   keeps the Claude GitHub App off the bypass list.
2. **Turn on Code Review** for that repo (an Owner of your Claude organization).
3. **Turn on PR Steward in Manual mode.** A user with write access comments `@claude steward` to
   start it (or authors opt in); `@claude stop` stops it. It can be fooled by what people write in
   comments: use it only with trusted collaborators, and check what it changes after comments
   from people you don't know.
4. **Add an observe-mode policy.** Copy `templates/claude-ship/approvals.observe.yml` to
   `.claude/approvals.yml` (`apply.sh --with-approvals`). Merging it turns Approvals on, so clear it
   with an Owner. Keep the `advisory: [claude/code_review]` line: once a policy exists, Code Review
   only starts on PRs that match a rule naming it. A policy that names Code Review can start billed
   reviews even where Code Review is off, so tell the budget owner.
5. **Watch it for a week or two.** Go back over merged PRs and compare the Approvals verdicts with what
   your reviewers did. Fix the cases where it would have approved but a person wouldn't, before
   loosening anything.
6. **Optional override, still observing.** Swap the advisory line for the commented override, so that
   a passing Claude review means one seat plus Claude's approval. Text in a PR can sway Claude's
   review, and when it does, the override lowers what that PR needs.
7. **Lock down, in this order:** add a rule with no `if` or `override` for paths that always need a
   non-author (auth, billing, CI; template in the policy file); remove `mode: observe` and merge;
   about five minutes later comment `@claude approvals rerun` on open PRs (reruns can bill
   classifiers again); ask a repo admin to make the Claude Approvals check required, with the
   Claude app as its source.

Two things to settle before enforcing:

- **Claude's approvals are real GitHub approvals.** If a ruleset needs one approval, Claude's can be
  enough. Read the policy and branch rules together.
- **Auto-merge plus author-fillable seats can merge with nobody acting.** Decide per path whether that's
  OK, and write it down. After the watch merges the base branch, the newest commit is a merge commit
  with nobody in the author's seat, so the author comments `@claude approve`.

Custom classifiers (`.claude/classifiers/<name>/def.yml`) are billed per run, even in observe mode.
Start with paths and the Code Review result.

## Try this week

1. **Today:** run `/code-review` on your current branch. Note what it got wrong and what it missed.
2. **Next PR:** in a repo where you trust everyone who can merge, run `/ship` and stay near your
   machine. Try `/steward` on an existing PR from a separate terminal and worktree.
3. **By Friday:** a small PR adding the rule you repeated most, in `CLAUDE.md`, `REVIEW.md` or a skill.
   Commit it yourself and share it with the observe-mode policy.

The person who called the agent owns the change, as if they had typed it. Keep your tests, scanners
and reviewers: Claude Ship can miss bugs and security problems.

## For a data team

- Put SQL rules in both files: e.g. "writes name their target database; nothing points at PROD_*
  from a dev path", "every new model has a uniqueness and not-null test".
- In the steward file: how to rebuild generated artifacts (`dbt deps`, `dbt parse`, lockfiles), which
  jobs are flaky, and "never change a test expectation to make a check pass".
- In the verify file: the smallest real check, e.g. `dbt build --select state:modified+` against a
  dev schema, with the row counts reported.
- On Bitbucket or GitLab none of this runs. The rule-file habit still carries over to whatever review
  tool you use.
