---
name: think-through
description: Deliberate reasoning before answering. Routes a hard prompt to a short chain of thinking modes (frame, widen, diagnose, check, fresh, weigh, commit, taste, pushback, integrate), keeps a visible ledger, and lints it so "I thought about it" is checkable. Use for open-ended design, decisions, debugging, reviews, plans, aesthetic judgment, anything time-sensitive, or when the user's premise might be wrong. Triggers on "think this through", "think harder", "overthink this", "/think-through", "should we...", "what should we do next", "why does this fail", "poke holes", "are you sure". Not for simple lookups, renames or mechanical edits.
---

# think-through

A fast answer fails in predictable ways: it solves the stated problem instead of the real one,
stops at the first idea, trusts a stale fact, agrees with a premise because the user sounded
sure, or hides the tradeoff. This skill makes you spend effort on exactly those failure points,
and leaves a ledger that shows you did.

Inspired by [s0md3v/overthink](https://github.com/s0md3v/overthink). Original text; it adds a
router, a ledger linter, a freshness mode, a pushback mode and an auditor agent.

Script: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/think-through/scripts/think.py` (standard library).

## 1. Decide whether to think at all

Run `think.py route "<prompt>"`. It returns a depth and a suggested chain:

| Depth | When | What you do |
|---|---|---|
| `skip` | lookup, rename, format, one-line fact | Answer. No ledger. |
| `quick` | 1-2 modes | Work the modes in your head; one line per mode in the reply if useful. |
| `standard` | 3-4 modes | Ledger in your reply or a scratch file. |
| `deep` | 5+ modes, or stakes words (prod, security, money, migrate, delete) | Ledger file `.think/<slug>.md`, lint it, then run the `think-auditor` agent. |

The router is keyword heuristics. Override it when it's wrong and say why in one line. The user
saying "think hard" or "overthink" bumps one level; "quick take" drops one.

## 2. Orient (always, before any mode)

Write four lines: **goal** (what the user needs, not what they typed), **likely failure if
answered fast**, **evidence that could change the answer**, **output** (format and length).
If the goal is ambiguous and a wrong guess is expensive, ask one question instead of starting.

## 3. Work the chain

`think.py template frame,widen,weigh,commit --prompt "..."` prints the ledger skeleton. Read one
mode file at a time from `references/` when you reach it; don't load all of them.

| Mode | Use it for | Reference |
|---|---|---|
| frame | the real goal, constraints that are hard vs assumed, a better framing | [frame.md](references/frame.md) |
| widen | 3+ structurally different options before judging | [widen.md](references/widen.md) |
| diagnose | competing causes and the check that separates them | [diagnose.md](references/diagnose.md) |
| check | verify the claims the answer rests on, outside your own head | [check.md](references/check.md) |
| fresh | facts that may have changed since training | [fresh.md](references/fresh.md) |
| weigh | criteria, weights, evidence, critical fails | [weigh.md](references/weigh.md) |
| commit | one choice, its tradeoff, what would flip it | [commit.md](references/commit.md) |
| taste | judging or shaping form: design, copy, tone, naming | [taste.md](references/taste.md) |
| pushback | the premise you're tempted to accept because the user said it | [pushback.md](references/pushback.md) |
| integrate | one through-line from several modes | [integrate.md](references/integrate.md) |

Typical chains (the router suggests these):

- **bug:** diagnose → check
- **decision** ("should we port to Rust?"): frame → check → weigh → commit
- **design / ideas:** frame → widen → weigh → (taste) → integrate
- **review:** frame → weigh → check
- **plan / what next:** frame → check → weigh → commit
- add **fresh** for versions, prices, APIs, "latest", a year; add **pushback** for "obviously",
  "just", "right?"

Each mode ends with a `carry:` line, the one thing the next mode must use. If a mode turns up
nothing new, write that and move on; don't pad.

Research that needs many reads (docs, code search, web) goes to a subagent with a narrow brief,
so its output doesn't flood the ledger.

## 4. Lint, then answer

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/think-through/scripts/think.py lint .think/<slug>.md
```

Errors (exit 1): widen with fewer than 2 options, diagnose with one hypothesis, check with no
tagged claims, fresh with nothing checked, commit with no choice, pushback with no verdict.
Warnings: missing `carry:`, unweighted criteria, no "would change if", hedged choice, untagged
claims. Fix errors before answering. At `deep`, run the `think-auditor` agent on the answer plus
ledger and fix what it confirms.

## 5. Write the answer

- Lead with the answer, not the process. The ledger is the receipt, not the reply.
- Put each caveat next to the claim it limits, not in a closing disclaimer.
- Tag the claims the answer rests on: verified (and how), unverified, assumed.
- If you disagreed with the user's premise, say so plainly in the first lines, with the reason.
- If you changed your answer because the user pushed back, name the new evidence. If there was
  none, hold your position politely.
- Say what would change your mind.

## Don'ts

- Don't run modes for show. A three-line ledger that changed the answer beats a long one that didn't.
- Don't treat re-reading your own draft as verification; check needs something outside you.
- Don't say "you're absolutely right" unless you checked and they are.
- Don't use this for full sparring on the user's idea; that's `sparring-partner` in top30-sparring.
