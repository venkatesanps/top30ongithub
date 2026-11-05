---
name: agent-graph-designer
description: Turn an agent pipeline described in prose into a checked graph - node contracts, arrows that carry a named variable (others deleted so steps run in parallel), model vs code per step, a real check per step, bounded loops, a failure policy, and human gates placed by how hard a mistake is to undo. Use when designing, reviewing or speeding up a multi-step agent workflow, or when someone approves every step by hand.
---

# Agent graph designer

A loop makes one step correct without a person watching. A graph decides which steps exist, in
what order, and where a person signs off. This skill draws the graph, then `scripts/graph_check.py`
checks it. The goal: one human decision per run, at the step a mistake can't be undone.

## 1. List the steps as nodes

From the user's description, write one node per job. Each node gets a four-line contract:

```
NODE       source_researcher
JOB        find one primary source per claim
IN         { topic, source_type }
OUT        { claim, url, quote }
FAILS AS   no_primary_source
```

If a step can't be described this way, split it or ask what it really does.

## 2. Draw only arrows that carry something

For every arrow, name the variable that travels along it. If nobody can, delete the arrow: the
order came from how the instructions were written, not from the work, and both steps can run in
parallel. Wait for a whole set to finish only when the next step needs all of it (de-duplicating
across sources, ranking every candidate).

Use one of four shapes: a **chain** (each step reads the last), **fan-out and join** (research,
reviews, audits), a **router** (a cheap classifier sends easy work down a short path), or a
**bounded cycle** (with `max_rounds`). Parallel workers each get their **own context**; in a
shared one the first answer shapes the rest.

## 3. Model or code, and how each step is checked

- Does the step judge, decide, assess, summarize or write? Model: small for extraction and
  routing, strong for synthesis. Otherwise (merge, de-duplicate, sort, join, count) it's code.
- Every step needs a check a program can fail. Strong: tests exit 0, output matches a schema,
  diff stays inside the plan, row counts and checksums match. Medium: the cited source supports the
  claim, an independent path agrees. Weak: a reviewer agent approves. Not a check: "looks good",
  the model is confident, no errors were thrown.

## 4. Failure policy and gates

Per node, decide in advance: tool or network blip → `retry`; model or source down → `fallback`;
optional branch failed → `skip`; output failed its check → `repair` that unit only, with the
failing evidence and a scope ("this file only"); 3 failed repairs → `escalate` (the plan is wrong);
budget or permission hit → `stop` and wake a person.

Gate by how hard a mistake is to undo (`undo`), never by a confidence score:

| undo | Examples | gate |
|---|---|---|
| `free` / `revert` | copy fix, new test, isolated function, a draft | `auto`: merge on a passing check |
| `hard` | shared utility, schema change, a report sent to leadership | `evidence` (strong checks first) or `human` |
| `irreversible` | migration, delete, production write or MERGE, payment, message to customers | `human`, always |

## 5. Write the spec and run the checker

Write the graph as JSON (`python3 .../graph_check.py init` prints a filled-in example) and run:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/agent-graph-designer/scripts/graph_check.py" check pipeline.json --out ./graph-report
```

(Use the path inside this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set.) Fix every error and
re-run. `report.md` shows the parallel waves, minutes in a line vs. as a graph, who should draw
the graph (generated per run, or fixed in the repo), and a Mermaid diagram.

## 6. Hand it over

Give the user: the diagram, the waves, the time saved, the contract table, the failure policy,
and the single step they still approve. Say which nodes need a loop (use the `agent-loop` skill
for those). If the job runs on a schedule, keep the spec in the repo next to the code and don't
let a model regenerate it each run: it would split the work differently every time and nothing
would carry over.

In Claude Code, a fixed graph can run as a saved dynamic workflow (`.claude/workflows/`), where the
script holds the fan-out and each `agent()` call is one node.
