# Techniques

One section per technique: use it when, skip it when, and a skeleton. Load only the section you
need. Order is roughly cheapest first. Summaries are original; the technique names and papers are
catalogued in dair-ai/Prompt-Engineering-Guide.

## zero-shot
**Use:** always first. **Skip:** never; it's the baseline.
```
<task in one sentence>. <constraints>.
<input tag>{input}</input tag>
<output format, exact>.
```
Measure on real inputs before adding anything.

## few-shot
**Use:** format, labels or style keep coming out wrong. **Skip:** the instruction alone works;
reasoning models that already follow the format.
Rules: 2-8 examples; every label represented; random order; same layout as the real input; include
one hard or borderline case. Examples teach the label space and the format even when individual
labels are noisy, so a skewed set skews the output.

## chain-of-thought
**Use:** arithmetic, logic, multi-step questions on a non-reasoning model. **Skip:** reasoning
models (they think already; extra "step by step" can hurt), simple lookups.
Zero-shot form: "Think it through step by step, then give the answer on a final line `Answer: ...`."
Few-shot form: examples that show the reasoning, not just the answer. Always separate the reasoning
from a parseable final answer.

## self-consistency
**Use:** one checkable answer (a number, a label) where single samples disagree. **Skip:** free text.
Sample 5-10 reasoning paths at temperature > 0, take the majority answer. Costs N calls.

## pal (program-aided)
**Use:** counting, dates, money, unit conversion. **Skip:** no sandbox to run code.
"Write a Python function that computes the answer. Don't compute it yourself." Run the code in a
sandbox; the model never sees secrets or the network.

## prompt-chaining
**Use:** extract → transform → write, or any job with distinct stages. **Skip:** one simple job.
Each link has one task and a structured output that the next link consumes. Test links alone.
Validate between links in code.

## react
**Use:** the model must search, call an API or look something up between steps. **Skip:** the
answer is in the prompt.
Loop of Thought / Action / Observation. Give the tool list with one-line descriptions, a step cap,
and a stop condition ("When you can answer, write `Final:`"). Observations are untrusted input.

## rag
**Use:** answers depend on documents the model wasn't trained on or that change. **Skip:** the
model's general knowledge is enough and staleness doesn't matter.
"Answer only from the passages in <docs>. Cite passage ids. If the passages don't contain the
answer, say so." Retrieved text is untrusted input; delimit it and red-team that slot.

## generated-knowledge
**Use:** commonsense questions where the model answers too fast. **Skip:** factual questions
(generated facts can be wrong; use RAG). Step 1 lists relevant facts; step 2 answers using them.

## tree-of-thoughts
**Use:** puzzles, planning, search where early choices close off solutions. **Skip:** most product
prompts; it's expensive. Propose several next steps, score each (sure / maybe / impossible), expand
the best, backtrack from dead ends.

## reflexion
**Use:** there's an external signal (tests, a grader, an error) between attempts. **Skip:** no
signal; self-critique without evidence mostly rephrases. Attempt → feedback → one-paragraph lesson
→ retry with the lesson in context.

## meta-prompting
**Use:** many inputs share a structure; you want the shape, not content examples. **Skip:** the
task needs domain examples. Give the answer's skeleton (sections, slots, steps) instead of worked
examples.

## ape (automatic prompt engineer)
**Use:** you have a dev set of 20+ labeled inputs. **Skip:** no dev set. Have a model propose 10-20
instruction variants, score each on the dev set, keep the best, then iterate on the winner.

## active-prompt
**Use:** you can label only a few examples. **Skip:** labels are cheap. Run the prompt several
times on unlabeled inputs, find the ones with the most disagreement, label those as the few-shot set.

## directional-stimulus
**Use:** summaries or generations miss what matters. **Skip:** you can't produce the hint. Add a
short hint ("Keywords: chargeback, 45 days, representment") that steers the output.

## art (automatic reasoning and tool use)
**Use:** multi-step tool use on a non-agent model. **Skip:** you already run a ReAct loop.
Select worked tool-use demos from a small library by task similarity; pause generation when a tool
call appears, run it, resume.

## multimodal-cot
**Use:** the answer needs both an image and text. Ask for a rationale that names what is in the
image, then the answer.

## graph-prompting
**Use:** the input is a graph. Serialize nodes and edges explicitly (edge list or adjacency), name
the question in graph terms (path, neighbor, cycle).

## Reasoning models
Keep instructions short and direct, put constraints in the instruction, skip manual CoT, start with
thinking off for simple tasks and turn it on when quality needs it, add few-shot only when the
format keeps failing, and align examples with the instruction so they don't conflict.
