# Playbook: harness engineering, a fact-checked reading path

A harness is everything around the model that makes its work reliable: the loop, the tools,
the files it reads first, the checks that say no, and where a person signs off. This page takes
a widely shared reading list, marks what was checked on 2026-11-11, and maps each idea to a
tool in this kit.

**Checked** means the page or repo was opened or its key claim confirmed that day. **Exists**
means the page or repo was found but its content wasn't read. **Unconfirmed** means only
second-hand reports were found.

## Read in this order

| # | Read | Status | Take from it |
|---|---|---|---|
| 1 | [OpenAI: Harness engineering](https://www.openai.com/index/harness-engineering) | Exists; the "3 engineers, about 1M lines, no hand-written code" framing is widely reported, not re-read here | Humans steer, agents execute; the repo is the system of record |
| 2 | [LangChain: The anatomy of an agent harness](https://www.langchain.com/blog/the-anatomy-of-an-agent-harness) | Exists | The parts: loop, tools, context, memory, sandbox |
| 3 | [Anthropic: Effective harnesses for long-running agents](https://anthropic.com/engineering/effective-harnesses-for-long-running-agents) (Nov 26, 2025) | Checked | Initializer session, then one feature per session; `feature_list.json` where only `passes` may change; `claude-progress.txt`; `init.sh`; git commits as checkpoints; test as a user would |
| 4 | [Anthropic: Harness design for long-running application development](https://anthropic.com/engineering/harness-design-long-running-apps) (Mar 24, 2026) | Checked | Planner, generator, evaluator. Agents grade their own work too kindly, so a separate skeptical evaluator with hard thresholds decides. Sprints and context resets were dropped as models improved; planner and evaluator stayed |
| 5 | [Martin Fowler site: Harness engineering for coding agent users](https://martinfowler.com/articles/harness-engineering.html) (Böckeler) | Exists | The user's side: guides and sensors you add around an off-the-shelf agent |
| 6 | [Mitchell Hashimoto: My AI adoption journey](https://mitchellh.com/writing/my-ai-adoption-journey) | Exists | One engineer's six steps; "engineer the harness" each time the agent makes a mistake |
| 7 | [Anthropic: Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents) | Known, not re-opened | What goes in the window and what stays in files |
| 8 | [The Ralph loop](https://ghuntley.com/ralph/) (Huntley) | Known, not re-opened | The simplest harness: the same prompt in a loop over a spec |
| 9 | [Thoughtworks podcast: What is harness engineering?](https://www.thoughtworks.com/insights/podcasts/technology-podcasts/what-harness-engineering) | Exists | A spoken overview |

## Claims in the list, checked

| Claim | Verdict |
|---|---|
| "Meta-Harness: the same model gets up to a 6x gap from the harness alone" | **Not in the abstract.** [arXiv 2603.28052](https://arxiv.org/abs/2603.28052) reports +7.7 points on text classification with 4x fewer context tokens, +4.7 points on 200 IMO-level problems, and beating hand-built harnesses on TerminalBench-2. Don't quote "6x" without finding it in the paper |
| "RHO: one pass lifts SWE-Bench Pro from 59% to 78%" | **Accurate.** [arXiv 2606.05922](https://arxiv.org/abs/2606.05922): "a single optimization round improves the pass rate on SWE-Bench Pro from 59% to 78% without any external grading" |
| "Code as Agent Harness" | A survey ([arXiv 2605.18747](https://arxiv.org/abs/2605.18747)) |
| "Dive into Claude Code" | A design-space study of Claude Code beside two open-source agents ([arXiv 2604.14228](https://arxiv.org/abs/2604.14228)) |
| "Fable 5.2: 1,000 agents coordinating through one shared database" | **Unconfirmed.** Only third-party summaries were found; the original post and the `claude.dev` address weren't verified |
| "Learn Harness Engineering: 14 lectures" | The repo exists; the lecture count wasn't checked |

## Repos (all found on GitHub on 2026-11-11; contents not reviewed)

[walkinglabs/learn-harness-engineering](https://github.com/walkinglabs/learn-harness-engineering) ·
[ai-boost/awesome-harness-engineering](https://github.com/ai-boost/awesome-harness-engineering) ·
[Picrew/awesome-agent-harness](https://github.com/Picrew/awesome-agent-harness) ·
[YennNing/Awesome-Code-as-Agent-Harness-Papers](https://github.com/YennNing/Awesome-Code-as-Agent-Harness-Papers) ·
[langchain-ai/deepagents](https://github.com/langchain-ai/deepagents) (`pip install deepagents`, 0.7.35 on PyPI) ·
[openai/codex](https://github.com/openai/codex) ·
[stanford-iris-lab/meta-harness](https://github.com/stanford-iris-lab/meta-harness) and its
[TerminalBench-2 artifact](https://github.com/stanford-iris-lab/meta-harness-tbench2-artifact) ·
[VILA-Lab/Dive-into-Claude-Code](https://github.com/VILA-Lab/Dive-into-Claude-Code) ·
[harbor-framework/terminal-bench](https://github.com/harbor-framework/terminal-bench) ·
[wbopan/retro-harness](https://github.com/wbopan/retro-harness)

## The same path with this kit

The list's learning order, and what already exists here (plugin `top30-agents` unless noted):

| Step | Idea | In this kit |
|---|---|---|
| 1 | One loop with a real check | `agent-loop` (`agent_loop.py repair`), `/goal` via `goal-writer` |
| 2 | A feature list and a progress file | `harness-starter` (`harness_kit.py init`, `lock`, `guard`, `log`) |
| 3 | A separate evaluator | `harness-evaluator` agent; goal gate when a command can decide |
| 4 | Parallel work that doesn't collide | `batch-scout` agent, then `/batch`; `agent-graph-designer` |
| 5 | Shared memory across agents | item **81** Busabase, item **15** Claude-Mem |
| 6 | Measure the harness | `scripts/ab.py` (same task, with and without); Terminal-Bench for a public benchmark |
| 7 | Learn from each failure | `agent_loop.py --rules RULES.md`; CLAUDE.md via `/memory` |

Two habits from the Anthropic posts worth keeping whatever tools you use: **the builder never
marks its own work as passing**, and **every part of a harness is an assumption about what the
model can't do alone, so re-test those assumptions after each model upgrade and delete what's no
longer needed.**
