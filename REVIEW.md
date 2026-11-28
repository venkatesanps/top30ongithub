# Review instructions

<!-- For Code Review (the managed service), read from the default branch. Local /code-review
     reads CLAUDE.md instead. Add a rule only after the same comment shows up on 2+ PRs.
     The template version for other repos is templates/claude-ship/REVIEW.md. -->

## What Important means here

An install command, verify command or link that no longer works; a claim in a playbook or guide
that its cited source doesn't support; anything that sends data outside without saying so; a
secret or personal detail in the repo.
Wording and style are Nit at most.

## Always check

- Generated files (`install.sh`, `verify.sh`, `guide/index.html`, README status blocks,
  `THIRD_PARTY_NOTICES.md`) changed only through `python3 scripts/kit.py render`, in the same PR
  as the `catalog.json` change behind them.
- New or changed factual claims in `playbooks/` and `guide/` link a source and say when it was
  checked, or are marked as not yet checked.
- Anything that runs in a vendor's cloud or sends code or data outside is said so plainly.
- New skills under `plugins/` pass `scripts/skill_lint.py` without new baseline entries.

## Keep it quiet

- Report at most five Nits.
- Skip `CHANGELOG.md`, `sources/`, `*.zip` and other files the refresh workflow writes.
- Behavior claims need a file and line.
