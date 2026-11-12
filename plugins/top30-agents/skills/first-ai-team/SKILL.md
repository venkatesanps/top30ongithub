---
name: first-ai-team
description: Design a person's first small team of AI agents - pick one real use case, define 3 to 5 agents with contracts and short prompts, map the handoffs as a checked graph, choose a lean tool stack, set a QA plan and approval gates, and lay out a 7-day launch. Use when the user wants to build an AI team or multi-agent workflow from scratch, asks which agents they need, or shares a "build my AI team" prompt.
---

# First AI team

A blueprint a solo operator can run next week, not a demo. Adapted from a publicly shared
"one-shot AI team setup" prompt, with this kit's checks added: every agent gets a contract and
a check a program can fail, the workflow is verified by `graph_check.py`, and irreversible steps
wait for the person.

## Standing rules

- Keep it narrow: one use case, 3 to 5 agents, one person running it.
- Ask for approval before publishing, sending, deleting, spending money or any other
  irreversible step. Never ask for passwords or secrets in chat.
- The agent that builds never grades its own work.
- Prefer code to a model wherever the step has one right answer (rendering, merging, uploading).

## 1. Ask a few sharp questions

Ask only what you don't already know, at most five, as tappable choices where possible:
the goal for the next 30 days; skills and what already exists (scripts, data, accounts); hours
per week they can spend reviewing; candidate use cases; what must never happen.

## 2. Choose the use case

Compare two or three realistic options on: a repeatable unit of work (one article, one lead, one
ticket, one video); an existing backlog; a check that can fail; cheap mistakes before the final
step; fits the review time they have. Recommend one and say why the others wait.

## 3. Design the team

For each agent give the four-line contract (job, in, out, fails as), whether it's a model or
code, its check, what it must not do, and when it escalates. Typical shape: a maker, an
independent checker, a packager, and a final step behind a human gate. No two agents own the
same output.

## 4. Check the workflow

Write the team as a graph spec (`templates/content-team.json` is a worked example for a story
video channel) and run the kit's checker:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/agent-graph-designer/scripts/graph_check.py" check team.json --out ./team-report --fail-on warn
```

Fix every error and warning: arrows that carry nothing, missing checks, reviewer-only checks,
unbounded repair loops, an irreversible step without a human gate. Use the report's waves to
show what runs in parallel and its diagram in the blueprint.

## 5. Write the prompts

One short prompt per model agent, in this shape, reusable as a subagent file or a system prompt:

```
You are the <role> for <project>. Your one job: <job>.
Input: <fields>. Output: <exact format, e.g. JSON with these keys>.
Rules: <3-6 decision rules specific to this work>.
Never: <what it must not do or touch>.
Done when: <the check>. If <fails-as condition>, stop and return {"escalate": "<reason>"}.
```

## 6. Tool stack, QA and measures

- Tools: only what version one needs: the model, where the backlog and outputs live (files
  or a table), a task list, one channel to reach the person, a scheduler. Say why each is there.
- QA: the check per agent, the review checkpoints, the five likeliest failure modes with how
  each is caught, a dry run on three real items before launch.
- Measures: units finished per week, share passing the checker first time, the person's review
  minutes per unit, and one outcome number for the use case. Decide in advance what result after
  two weeks means "stop" or "simplify".

For work spanning many sessions add the `harness-starter` skill (a locked list of the
backlog, a progress log); for unattended runs add the goal gate (`goal-writer`).

## 7. The 7-day launch and the first step

Day 1 scope and rules; day 2 backlog and checks; day 3 maker and checker on one item; day 4
remaining agents; day 5 dry run on three items, fix what the checker caught; day 6 first real
item with the person approving the last step; day 7 review the numbers, cut what wasn't needed.

End the blueprint with **START HERE FIRST**: the single action for today, small enough to
finish in under an hour.
