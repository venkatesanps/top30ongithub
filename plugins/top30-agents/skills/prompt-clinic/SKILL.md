---
name: prompt-clinic
description: Write, fix and harden prompts for LLM features. Picks the lightest prompting technique that fits the task (zero-shot, few-shot, chain-of-thought, self-consistency, prompt chaining, ReAct, RAG, PAL, tree-of-thoughts, reflexion, meta-prompting, APE and more), lints a prompt for the four elements, vague sizes, don't-only rules, contradictions, label-skewed examples, secrets and undelimited input slots, and generates prompt-injection, leaking and delimiter-break test cases for each input slot with a grader for your model's outputs. Use when someone says "improve this prompt", "review my system prompt", "which prompting technique", "few-shot or chain-of-thought", "why does the model ignore my instruction", "is this prompt injectable", "red-team my prompt", "/prompt-clinic". Not for designing a whole agent (agent-pattern-picker) or Claude Code session problems (session-doctor).
---

# prompt-clinic

Most prompt bugs are ordinary: the task isn't stated, the format isn't stated, a size is a
feeling ("short"), the rules only say what not to do, the examples all have the same label, or
user text is pasted into the prompt where it can rewrite the instructions. This skill finds
those, picks a technique only when the plain prompt has been measured and falls short, and
tests the input slots the way an attacker would.

Built on the ideas in [dair-ai/Prompt-Engineering-Guide](https://github.com/dair-ai/Prompt-Engineering-Guide)
(MIT). Original text and code.

Script: `python3 ${CLAUDE_PLUGIN_ROOT}/skills/prompt-clinic/scripts/prompt.py` (standard library,
no network, never calls a model).

## 1. Get the prompt and its job

Ask for, or find in the code: the prompt text (system and user parts), which parts are filled in
at runtime and from where (user, retrieved docs, tool output), the model family (reasoning model
or not), and 3-10 real inputs with the output you want. Without real inputs you can lint but not
judge. Save the prompt to a file with slots written as `{name}`, `{{name}}`, `<<name>>`,
`${name}` or `[NAME]`.

## 2. Lint it

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/prompt-clinic/scripts/prompt.py lint prompt.md
```

It reports which of the four elements are present (instruction, context, input data, output
indicator) and the findings below. Errors exit 1. Full list with examples:
[references/lint-rules.md](references/lint-rules.md).

| Rule | Severity | Finds |
|---|---|---|
| P01 | error | no instruction verb |
| P02 | warning | no output format or size |
| P03 | warning | vague size word with no number |
| P04 | warning | "don't" with no "do this instead"; P04b many shouted rules |
| P05 | error | input slot not delimited (tags, quotes, fence, `###`) |
| P06 | warning | input taken but never declared to be data |
| P07 | info | untrusted slot is the last thing the model reads |
| P08 | warning | few-shot labels all the same or skewed |
| P09 | warning | contradictory asks (concise and detailed, JSON only and prose) |
| P10 | info | repeated line |
| P11 / P12 | error | secret in the prompt / hidden Unicode |
| P13 | warning | relies on the prompt staying secret |
| P14 | info | reasoning task with no reasoning guidance |
| P15 | info | over 1,500 words |

The linter is heuristics. Read each finding against the prompt and drop the ones that don't
apply, saying why in one line.

## 3. Pick a technique only if the plain prompt fails

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/prompt-clinic/scripts/prompt.py pick "classify support emails using our refund policy docs" [--reasoning-model]
```

It always returns zero-shot first: fix the lint findings, run the real inputs, and add a
technique only for a failure you saw. `--reasoning-model` drops manual chain-of-thought,
tree-of-thoughts and self-consistency, which these models do internally. When and how to use each
technique, with a skeleton: [references/techniques.md](references/techniques.md). Load the one
section you need.

Rules of thumb:

- Wrong format or label → few-shot (balanced labels, same format as the real input).
- Wrong arithmetic or dates → PAL (code computes), then self-consistency.
- Wrong facts or stale facts → RAG with citations; don't add more instructions.
- Several jobs in one prompt → prompt chaining; test each link alone.
- Needs to act (search, call an API) → ReAct with a step cap and stop condition.

For agent and app prompts, the context around the prompt matters as much as the wording: system
prompt, tool descriptions, retrieved text, memory and state. See
[references/context.md](references/context.md).

## 4. Red-team the input slots

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/prompt-clinic/scripts/prompt.py attack prompt.md --jsonl --out cases.jsonl
```

For every slot it writes ten cases: ignore-instructions, fake system role, prompt leaking,
delimiter break (closes the exact delimiter your prompt uses), format hijack, indirect injection
dressed as a retrieved document, another language, base64, hidden Unicode, and one benign control.
Each attack asks only for a unique marker like `PWNED-1A2B3C`, so a failure is unambiguous and the
cases contain nothing harmful. It also prints a canary to place in the system prompt.

The user runs the cases through their own model and writes `{"id": ..., "output": ...}` lines.
You don't call their model or their API keys. Then:

```bash
python3 ${CLAUDE_PLUGIN_ROOT}/skills/prompt-clinic/scripts/prompt.py grade cases.jsonl outputs.jsonl --canary CANARY-XXXXXXXX
```

A case fails if the output contains its marker or the canary. Fixes, strongest first, are in
[references/defenses.md](references/defenses.md): keep untrusted text out of the instruction
channel, delimit and name it, say it is data, restate the task after it, constrain the output,
check the output in code, and never let a prompt be the only thing guarding a secret or an action.

## 5. Report

Return: the four-element check, the findings you kept (rule, line, fix), the rewritten prompt as a
diff or a full block, the technique you added and the failure that justified it, and the attack
grade if the user ran it. For a prompt that ships to users or reads untrusted text, run the
read-only `prompt-reviewer` agent on the final prompt and fix what it confirms.

## Don'ts

- Don't add chain-of-thought, roles or "you are an expert" by reflex. Measure first.
- Don't claim a prompt is injection-proof. Say which cases passed on which model.
- Don't paste the user's real customer data into example files; write synthetic examples.
- Don't run attack cases against a service the user doesn't own.
