---
name: harness-starter
description: Set up a project so an agent can work on it across many sessions without losing its place or declaring victory early - a locked feature list that defines done, a progress log, an init script, git checkpoints, and a separate evaluator that marks features passing only with evidence. Use when starting a long-running or multi-session build or migration, when an agent keeps saying "done" too soon or forgetting where it was, or when the user asks for a harness, a feature list, or a progress file.
---

# Harness starter

The pattern is Anthropic's, from "Effective harnesses for long-running agents" (Nov 2025) and
"Harness design for long-running application development" (Mar 2026): the first session sets
up the environment; every later session makes one increment and leaves the project clean; a
separate evaluator, not the builder, decides what passes. `scripts/harness_kit.py` creates the
files and adds a lock so the feature list can't be quietly edited to pass.

```bash
H="python3 ${CLAUDE_PLUGIN_ROOT}/skills/harness-starter/scripts/harness_kit.py"   # or this folder's scripts/
```

## First session: set up (the initializer)

1. Read the user's spec. Write the features as a JSON array, each with `category`,
   `description` (a behaviour a user or downstream job would notice) and `steps` (how to verify
   it end to end). Be exhaustive: this list is what stops "done" being declared early. For a
   data project: loads are idempotent, row counts and checksums reconcile, late and duplicate
   data are handled, each model's keys are unique and not null, reruns and backfills work.
2. `$H init --features features.json` creates `feature_list.json` (everything failing),
   `claude-progress.txt` and `init.sh`. Fill in `init.sh`: start what the project needs, then
   one fast smoke check.
3. Show the user the feature list. When they agree, `$H lock`, then commit everything.
   From here only `passes` may change. New scope is the user's call: `$H add ... --relock`.

## Every later session (the builder)

Start, in this order:

1. `pwd`, then `$H status` and read `claude-progress.txt` and `git log --oneline -15`.
2. Run `./init.sh`. If the smoke check fails, fix that first: never build on a broken base.
3. `$H next`: take that one feature. One feature per session.

Finish:

1. Verify the feature the way its `steps` say, as a user would (run the pipeline, query the
   result, drive the UI), not just unit tests.
2. Don't mark it yourself. Hand it to the `harness-evaluator` agent, which runs the steps and
   records `$H mark <id> pass|fail --evidence "..."`.
3. `$H guard` must pass. Never delete or reword a feature to get there.
4. Commit with a descriptive message, then `$H log "<done, verified how, broken, next>"`.
   Leave the tree clean and mergeable.

## Keeping it honest

- `$H guard` fails if a feature was removed, reworded or added without re-locking. Run it in
  CI and before every commit. `$H guard --base main` compares with git instead of the lock
  file, which also catches someone re-locking to hide an edit.
- Pair with the goal gate (`goal-writer` skill): `goal_gate.py on --check "$H guard && ./init.sh"`.
- For an unattended run: `/goal harness_kit.py status shows all features passing and guard
  exits 0. Only the harness-evaluator marks passes. Or stop after 40 turns.`

## When to simplify

Every piece here assumes something the model can't do alone. Anthropic dropped sprints and
context resets as models improved, and kept the planner and evaluator. Re-check after each model
upgrade: if sessions no longer lose their place, the progress ritual can shrink; keep the locked
list and the separate evaluator longest.
