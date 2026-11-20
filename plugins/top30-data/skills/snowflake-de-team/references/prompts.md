# Prompt library

The agent files in `agents/sf-*.md` hold each role's full prompt. These are the short prompts
the main session sends, adapted from the post's prompt library.

## Team kickoff (paste into a new Claude Code session)

```
Use the snowflake-de-team skill. Task: <what you need, one paragraph>.
Dev databases: <DEV_DE>. Prod databases: <PROD, RAW>. Connection: <snow CLI connection name>.
Route it, kick off a run folder, ask me what context.md still needs, then run the steps and
verify after each. Don't run anything outside dev. Stop and show me DEPLOY.md at the end.
```

## Per step (main session to each agent)

- **sf-researcher:** "Run folder: `runs/<name>`. Research what the task needs from Snowflake and
  the repo. Only report what you can verify; everything else goes under Unverified."
- **sf-drafter:** "Run folder: `runs/<name>`. Draft the complete change in `02-draft/` from the
  findings. Note at the top anything you had to assume."
- **sf-critic:** "Run folder: `runs/<name>`. Lens: <all|security|correctness|performance|style>.
  Critique `02-draft/`. Never suggest fixes. Rate each problem Critical, Major or Minor. End
  with the strongest parts."
- **sf-refiner:** "Run folder: `runs/<name>`. Fix every Critical and Major problem in
  `03-critique.md`, keep what works, one line per fix in `04-fix-notes.md`."

## Merging a four-lens review

Concatenate `03-critique-<lens>.md` into `03-critique.md`, renumber P1..Pn, and when two lenses
flag the same file:line keep one entry with the higher rating. Merge the "Strongest parts"
sections into one, last.

## Common Snowflake asks and their route

| Ask | Type |
|---|---|
| "Why did last night's ORDERS load fail?" | incident |
| "Credits doubled this month" | cost |
| "This dashboard query takes 4 minutes" | tune |
| "Move these Oracle packages to Snowflake" | migrate |
| "Build an incremental orders fact with SCD2 customers" | build |
| "Review this PR's dbt models" | review |
| "Which tables hold customer emails?" | research |
