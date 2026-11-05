# Playbook: loops and graphs (approve one step, not every step)

Goal: agent work that runs without someone watching it, with one human decision per run, at the
step where a mistake can't be undone. Two parts make that possible:

- A **loop** makes one unit of work correct without you: a check a program can fail, a round
  limit, a budget, memory of past attempts, and a person paged when it stalls.
- A **graph** decides which units exist, which run in parallel, and where a person signs off.

Build the check first, then the graph, then the step that writes down what each fix taught you.
Every layer you skip comes back as manual work: without a loop you read every output, without a
graph you approve every step.

The reference case: in May 2026 Bun's runtime was rewritten from Zig to Rust (reported at around a
million lines) with heavy use of AI tools, and merged within days once it passed Bun's existing
test suite ([Wikipedia](https://en.wikipedia.org/wiki/Bun_(software))). The suite existed years
before any agent touched the code. That's what made the volume trustworthy.

## Tools in this kit

| Need | Use |
|---|---|
| Design or review a pipeline as a graph | `agent-graph-designer` skill + `graph_check.py` (plugin `top30-agents`) |
| Fix one unit until a check passes; hunt until nothing new | `agent-loop` skill + `agent_loop.py` (plugin `top30-agents`) |
| Run a fan-out at scale inside Claude Code | Dynamic workflows: Claude writes a script that runs subagents, up to 16 at a time by default and 1,000 per run, and you can save it to `.claude/workflows/` ([docs](https://code.claude.com/docs/en/workflows)) |
| Checks to loop against | **42** SQLFluff, **32** dbt tests, `ora2sf.py --fail-on error`, row-count and checksum queries |
| Compare a setup before and after | `scripts/ab.py` (same task, plugin off and on) |
| Memory every agent shares, with writes that wait for review | **81** Busabase: agents propose change requests (author, diff, history); a credential limited to proposing keeps the lane closed until a person approves |

## 1. The check decides everything

| Strength | Evidence | Data-engineering example |
|---|---|---|
| strong | tests exit 0 | `dbt build --select model+` passes; pytest on a refiner |
| strong | output matches a schema | JSON schema on an extract; `DESCRIBE` matches the contract |
| strong | diff stays inside the plan | only the files in scope changed (`agent_loop.py` enforces this) |
| strong | numbers reconcile | row counts and per-key checksums match source and target |
| medium | the cited source supports the claim | the doc page really says the function behaves that way |
| medium | an independent path agrees | a second query written differently gets the same total |
| weak | a reviewer agent approves | one more opinion |
| not evidence | "looks good", confidence, no errors | a job that logged nothing can still have loaded nothing |

Write the check before the task. For a migration, that means the equivalence queries exist before
the first translated model.

## 2. Every loop stops on a count

- **Repair:** stop on pass, after N rounds (escalate), when two rounds end in the same failure
  (escalate: the plan is wrong), or when the budget is spent (stop, page a person).
- **Hunt** (bugs, flaky tests, sources, data issues): track new findings per round, de-duplicated
  against everything seen, *including what was rejected*, and stop after two rounds with nothing new.

## 3. Draw the graph from the work, not the sentence

Pipelines get drawn as a line because instructions are written as a line. Test every arrow: name
the variable that travels on it. If you can't, delete it and let both steps run at once.

| Shape | Use it for | Example |
|---|---|---|
| Chain | each step reads the last | extract → validate → load |
| Fan-out and join | research, reviews, audits | one reviewer per changed model, then one ranked summary |
| Router | cheap classifier, short path for easy work | trivial SQL style fixes auto-merge; anything touching MERGE goes the long way |
| Bounded cycle | repair until green | translate → test → repair, `max_rounds: 3` |

Parallel workers get **separate contexts**; in one shared window the first answer shapes the rest.
Don't use a model where code will do: merging lists, de-duplicating, sorting and joining records
have one right answer.

## 4. Decide failure handling in advance

| Failure | Action |
|---|---|
| tool or network blip | retry |
| model or source down | fall back |
| optional branch failed | skip |
| output failed its check | repair **that unit only**, with the failing evidence and a scope line |
| 3 repairs failed | escalate: the plan is wrong |
| budget or permission hit | stop, wake a person |

Never send back the whole batch: three good slices rewritten into new versions can each fail for
new reasons, and the run stops converging. After a fix passes, write its cause as a rule for
whoever splits the work next time (`agent_loop.py --rules RULES.md` does this).

## 5. Gate on what a mistake would cost

| Lane | Data-engineering examples | Gate |
|---|---|---|
| Open | new dbt test, doc fix, a refactor inside one model, a draft report | merge on a passing check |
| Evidence | shared macro or utility, schema change in staging, new incremental logic | strong checks first, then merge |
| Closed | MERGE or DELETE in production, backfills over published data, dropping objects, anything that moves money or messages users | a person signs, always |

A confidence threshold is a number someone can lower on a busy Friday. A closed lane has no number.

## 6. Who draws the graph

| Job | Who draws it |
|---|---|
| One-off, cheap to undo (an audit, a refactor) | let Claude generate the workflow and throw it away |
| One-off, hard to undo (a production migration) | Claude drafts the plan; you read the plan, not every diff |
| Recurring, low risk (weekly cost report) | fixed graph in the repo; it ships on green |
| Recurring, touches production or people | fixed graph in the repo; you sign the last step |

Don't let a model regenerate a recurring workflow from scratch each run: it splits the work
differently every time and nothing it learned carries over. Save it (`.claude/workflows/` or a
graph spec in the repo) and change it deliberately.

## Prompts that work

- "Here's our nightly load described in prose. Draw it as a graph with a contract per node, name
  what each arrow carries, and run graph_check.py on it."
- "Repair `models/fct_positions.sql` until `dbt build --select fct_positions+` passes. Scope: that
  file only. Three rounds, $2."
- "Hunt for models with no tests on their primary key. Verify each finding with the manifest; stop
  after two rounds with nothing new."
