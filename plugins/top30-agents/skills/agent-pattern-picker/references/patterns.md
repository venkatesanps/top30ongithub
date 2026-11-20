# The 15 patterns, by the uncertainty they handle

Summarized from Rahul's post (X, Jun 2026), with how to build each in Claude Code and the
tool in this kit that helps. Complexity runs from 1 (least autonomy) to 6.

| Uncertainty | Pattern | Cx | Use when | Breaks when | In Claude Code |
|---|---|---|---|---|---|
| None | *no agent* | 0 | summarize, classify, extract, template | | One model call, or a skill that runs a script |
| Which tool | Single agent | 1 | small tool set, one job | tools keep growing, prompt past a page | One session or skill; `--allowedTools` headless |
| Which tool, which step | ReAct | 3 | the path depends on what each step finds | it doesn't converge | Claude Code's own loop; a turn bound in `/goal` or `agent_loop.py`; state an evidence bar |
| Where to route | Coordinator | 4 | genuinely different request types | requests fit no category, or several | Main agent routes to subagents by description; an "unclear: ask" route |
| Quality | Review and critique | 3 | quality over speed | the critic shares the writer's blind spots | A subagent with its own context and `model:` (like `harness-evaluator`); `/code-review` |
| Quality, measurable | Iterative refinement | 3 | "good enough" is a number | the score is vague or gameable | `agent_loop.py` with a scoring script as the check |
| Execution path, reviewable | Plan-and-execute | 4 | the plan must be approved before acting | the plan goes stale mid-run | `/plan`, then re-check preconditions before each step |
| How to self-correct | Loop | 2 | attempts until a check passes | no reliable exit condition | `/goal`, the goal gate Stop hook, `agent_loop.py repair` |
| How to self-correct | Reflexion | 4 | failures say what to fix | failures are random | `agent_loop.py` rules file; lasting lessons to CLAUDE.md |
| Business risk | Human-in-the-loop | 3 | money, legal or reputation at stake | it's a pause button, not durable state | `ask` permissions, plan approval, PreToolUse hooks, state in files (`harness-starter`) |
| Business risk | Custom logic | 2 | rules that must never be wrong | the model ends up deciding eligibility or money | Rules in scripts and hooks; `deny` the dangerous tools |
| Fixed stages | Multi-agent sequential | 2 | each stage feeds the next, order never changes | the order depends on findings | Chained subagents or `claude -p` steps; `agent-graph-designer` |
| Independent parts | Multi-agent parallel | 3 | independent subtasks, speed matters | branches need each other's results | Several subagents in one message; `/batch` for code |
| Problem structure | Hierarchical decomposition | 5 | broad goal, separable expertise | subgoals need each other while running | Plan, one subagent per subgoal, synthesis; `first-ai-team` |
| Problem structure, no right answer | Swarm | 6 | decisions shaped by competing views | you need fast, deterministic answers | Role subagents for N rounds plus a facilitator; `sparring-partner` decide mode |
| Can't wait to be asked | Event-driven | 4 | timing matters most | vague triggers | `/schedule`, launchd/cron with `claude -p --permission-mode dontAsk`, GitHub Actions, `/autofix-pr` |

## The ten production rules, and which the audit checks

| # | Rule | Audit |
|---|---|---|
| 1 | Start with the smallest pattern that works | `pick` prefers the simplest; info when a 5-6 pattern has 1-2 tools |
| 2 | Write tool descriptions like contracts | warn under 40 characters |
| 3 | Cap iterations, tool calls and spend | error with no budget, warn per missing cap |
| 4 | Log the full action trace | error without `logging.trace` |
| 5 | Irreversible actions behind code checks or a person | error when gate isn't `code` or `human`; names like refund/send/delete flagged |
| 6 | Evaluate with real failure cases | error/warn without `evals.failure_cases` |
| 7 | Separate prompts by responsibility | warn past ~700 words or "but don't X when Y" |
| 8 | Multi-agent is a distributed system | warn with no timeout |
| 9 | Model review isn't validation | warn when a judge has no deterministic check |
| 10 | Prefer the simpler pattern | see rule 1 |

The audit can only check what the design file declares. A design that says
`"trace": true` and doesn't log is the reviewer's job (`pattern-reviewer` agent).
