#!/usr/bin/env python3
"""Pick the smallest agent design pattern for a task, then audit a design against the way
that pattern breaks and against ten production rules. No model calls, no network.

  pattern_kit.py pick [--predictable] [--tool-choice] [--route] [--quality] [--measurable]
                      [--path-unknown] [--approve-plan] [--fast-changing] [--self-correct]
                      [--risk] [--broad] [--no-right-answer] [--event] [--stages]
                      [--independent] [--repeat] [--json]
  pattern_kit.py scaffold <pattern>            # a design.json to fill in
  pattern_kit.py audit <design.json> [--json] [--fail-on error|warn]
  pattern_kit.py list                          # the 15 patterns and how to build each in Claude Code

Exit codes: audit returns 1 when a finding at --fail-on level (default error) exists, 2 on bad input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

PATTERNS = {
    "single": ("Single agent", "One model, one system prompt, a few tools; it picks tools until it can answer.",
               "you keep adding tools and the prompt passes a page",
               "One session or skill with a short CLAUDE.md and a small tool list (`--allowedTools` for headless runs)."),
    "sequential": ("Multi-agent sequential", "Specialists in a fixed order; each output is the next input.",
                   "the order really depends on what's found midway",
                   "Chained subagents or `claude -p` steps; draw it with `agent-graph-designer` so each arrow carries a named variable."),
    "parallel": ("Multi-agent parallel", "Independent subtasks at the same time, merged into one view.",
                 "the branches depend on each other's results",
                 "Several subagents started in one message, `/batch` for code units in separate worktrees, then one merge step."),
    "loop": ("Loop", "Repeat steps until a checkable exit condition holds, with a round cap.",
             "there's no reliable exit condition",
             "`/goal <check> ... or stop after N turns`, the goal gate Stop hook, or `agent_loop.py repair`."),
    "review": ("Review and critique", "A separate judge critiques output with specific feedback.",
               "the critic shares the generator's blind spots",
               "A subagent with its own context and a different `model:` in its frontmatter (like `harness-evaluator`), plus `/code-review` for code."),
    "refine": ("Iterative refinement", "Regenerate until a quality score crosses a threshold.",
               "the score is vague or the generator can game it",
               "`agent_loop.py` with a scoring script as the check; the scorer is code or a different agent, never the writer."),
    "coordinator": ("Coordinator", "A router sends each request to the specialist that fits.",
                    "requests don't fall cleanly into one category",
                    "A main agent that routes to subagents by their descriptions, with an explicit 'unclear: ask' route."),
    "hierarchical": ("Hierarchical decomposition", "A root splits a broad goal into subgoals for workers, then synthesizes.",
                     "the subgoals need each other's results while running",
                     "Plan, then one subagent per subgoal, then a synthesis step; `first-ai-team` for a standing team."),
    "swarm": ("Swarm", "Specialists argue across rounds; a facilitator weighs the trade-offs.",
              "you need a fast, deterministic answer",
              "Role subagents (research, finance, engineering...) for a fixed number of rounds, then a facilitator; `sparring-partner` decide mode for one person."),
    "react": ("ReAct", "Reason, act, observe, repeat until there's enough evidence; the path emerges.",
              "it runs long without converging",
              "Claude Code's own loop; cap it with a turn bound (`/goal ... or stop after N turns`, or `agent_loop.py` rounds) and a stated evidence bar."),
    "hitl": ("Human-in-the-loop", "The agent recommends; a person decides anything risky or ambiguous.",
             "it's a pause button, not durable state with a reviewer, timeout and escalation",
             "Permission rules on `ask`, plan-mode approval, PreToolUse hooks; durable state in files (`harness-starter`)."),
    "plan-execute": ("Plan-and-execute", "A reviewable plan first, then an executor runs the steps.",
                     "the world changes faster than the plan runs",
                     "`/plan` (plan mode) to approve, then execute with a re-check of preconditions before each step."),
    "reflexion": ("Reflexion", "After a failure the agent writes what went wrong and carries it into the next try.",
                  "failures are random, so there's nothing to learn",
                  "`agent_loop.py` keeps a rules file of lessons; promote lasting ones to CLAUDE.md with `/memory`."),
    "custom-logic": ("Custom logic", "Code enforces the rules that must never be wrong; the model drafts and judges.",
                     "the model ends up deciding eligibility, permissions or money",
                     "Rules in scripts and PreToolUse hooks, `deny` permissions for the dangerous tools; the model calls them, never replaces them."),
    "event-driven": ("Event-driven", "Subscribes to events and acts when a condition fires, without being asked.",
                     "triggers are vague, so it cries wolf or misses the signal",
                     "`/schedule` (cloud), launchd/cron with `claude -p --permission-mode dontAsk`, GitHub Actions, or `/autofix-pr` for PRs."),
}
ORDER = list(PATTERNS)
# The smaller the number, the less autonomy. pick() prefers the smallest that fits.
COMPLEXITY = {"single": 1, "sequential": 2, "loop": 2, "custom-logic": 2, "react": 3, "review": 3, "refine": 3,
              "parallel": 3, "coordinator": 4, "plan-execute": 4, "reflexion": 4, "hitl": 3, "event-driven": 4,
              "hierarchical": 5, "swarm": 6}
IRREVERSIBLE = re.compile(r"(?:^|[_\W])(pay|payment|refund|transfer|charge|wire|send|email|post|publish|delete|drop|"
                          r"truncate|deploy|merge|push|resize|scale|terminate|cancel|approve|grant|revoke)\w*", re.I)


# ---------- pick ----------

def pick(a):
    if a.predictable and not any([a.tool_choice, a.route, a.path_unknown, a.self_correct, a.broad,
                                  a.no_right_answer, a.event, a.repeat]):
        return {"verdict": "no-agent", "primary": None, "also": [],
                "why": ["The input-to-output path is predictable: a direct model call (or plain code) is "
                        "faster, cheaper and more reliable than an agent."],
                "wrap": wrappers(a)}
    score = {}
    why = {}

    def add(p, pts, reason):
        score[p] = score.get(p, 0) + pts
        why.setdefault(p, []).append(reason)

    if a.tool_choice:
        add("single", 3, "it must choose tools at runtime")
        add("react", 2, "it must choose tools at runtime")
    if a.path_unknown:
        add("react", 3, "the path depends on what each step reveals")
        if a.approve_plan:
            add("plan-execute", 1, "you also want to review a plan")
    if a.approve_plan:
        add("plan-execute", 4 if not a.fast_changing else 1, "the plan must be reviewable before anything runs")
        if a.fast_changing:
            add("react", 2, "the environment changes faster than a plan stays valid")
    if a.route:
        add("coordinator", 4, "requests are of genuinely different kinds")
    if a.quality:
        if a.measurable:
            add("refine", 3, "quality varies and 'good enough' is measurable")
            add("loop", 1, "a checkable stop condition exists")
        else:
            add("review", 3, "quality matters more than speed, judged by a separate critic")
    if a.repeat:
        add("loop", 3, "it needs several attempts with a checkable stop")
    if a.self_correct:
        add("reflexion", 3, "failures are informative, so lessons should carry over")
        add("loop", 1, "retries need a cap")
    if a.stages:
        add("sequential", 3, "the stages are fixed and each feeds the next")
    if a.independent:
        add("parallel", 3, "the subtasks are independent and speed matters")
    if a.broad:
        add("hierarchical", 3 if a.independent or not a.no_right_answer else 1,
            "the problem splits into separate areas of expertise")
    if a.no_right_answer:
        add("swarm", 3, "there's no single right answer; competing views should be argued")
    if a.event:
        add("event-driven", 4, "it must act when something happens, not when asked")
    if not score:
        add("single", 1, "nothing points past the simplest pattern")

    ranked = sorted(score, key=lambda p: (-score[p], COMPLEXITY[p], ORDER.index(p)))
    top = score[ranked[0]]
    # Among patterns within one point of the best, prefer the simplest.
    near = [p for p in ranked if score[p] >= top - 1]
    primary = min(near, key=lambda p: (COMPLEXITY[p], -score[p], ORDER.index(p)))
    also = [p for p in ranked if p != primary and COMPLEXITY[p] >= COMPLEXITY[primary]][:2]
    return {"verdict": "agent", "primary": primary, "also": also,
            "why": why[primary], "why_also": {p: why[p] for p in also}, "wrap": wrappers(a)}


def wrappers(a):
    w = []
    if a.risk:
        w.append(("custom-logic", "rules with legal or money consequences stay in code"))
        w.append(("hitl", "risky or ambiguous cases wait for a person"))
    return w


def print_pick(r):
    if r["verdict"] == "no-agent":
        print("Verdict: no agent needed.")
        for y in r["why"]:
            print(f"  {y}")
    else:
        p = r["primary"]
        name, what, breaks, build = PATTERNS[p]
        print(f"Start with: {name} ({p})")
        print(f"  {what}")
        for y in r["why"]:
            print(f"  because {y}")
        print(f"  Breaks when {breaks}.")
        print(f"  In Claude Code: {build}")
        for q in r["also"]:
            print(f"\nIf that isn't enough: {PATTERNS[q][0]} ({q}), because {'; '.join(r['why_also'][q])}.")
    for p, reason in r["wrap"]:
        print(f"\nWrap it in: {PATTERNS[p][0]} ({p}): {reason}. {PATTERNS[p][3]}")
    print("\nNext: `pattern_kit.py scaffold <pattern>` and `audit` the design.")


# ---------- scaffold ----------

BASE = {
    "name": "my-agent",
    "pattern": "single",
    "goal": "one sentence: what done looks like",
    "system_prompt_words": 300,
    "tools": [{"name": "lookup_order", "description": "Returns status, carrier and ETA for one order id. "
               "Read-only. Errors with NOT_FOUND for unknown ids.", "irreversible": False}],
    "budget": {"max_steps": 20, "max_tool_calls": 40, "max_usd": 2.0, "timeout_s": 600},
    "logging": {"trace": True},
    "evals": {"happy_cases": 20, "failure_cases": 10},
    "rules_in_code": [],
}
EXTRA = {
    "sequential": {"stages": [{"name": "extract", "out": ["obligations"]},
                              {"name": "risks", "in": ["obligations"], "out": ["risks"]},
                              {"name": "summary", "in": ["risks"], "out": ["summary"]}]},
    "parallel": {"stages": [{"name": "logs", "out": ["log_findings"]}, {"name": "metrics", "out": ["metric_findings"]},
                            {"name": "deploys", "out": ["deploy_findings"]}],
                 "merge": "one step combines the three findings", "branch_timeout_s": 300},
    "loop": {"exit": {"check": "python -m pytest tests/ exits 0", "max_rounds": 5}},
    "review": {"generator": {"model": "opus"}, "critic": {"model": "sonnet", "context": "own",
                                                          "rubric": "claims without evidence, missing sections"},
               "rules_in_code": ["report has every required section (schema check)"]},
    "refine": {"score": {"by": "code", "threshold": 0.8, "how": "script counts guideline violations"},
               "exit": {"max_rounds": 4}},
    "coordinator": {"routes": ["billing", "technical", "account"], "fallback_route": "ask the user"},
    "hierarchical": {"subgoals": [{"name": "competition"}, {"name": "regulation"}, {"name": "market_size"}],
                     "synthesis": "one step weighs the subgoal results"},
    "swarm": {"roles": ["research", "finance", "engineering"], "rounds": 2, "facilitator": "separate agent"},
    "react": {"budget": {"max_steps": 15, "max_tool_calls": 30, "max_usd": 2.0, "timeout_s": 600},
              "evidence_bar": "two independent signals agree"},
    "hitl": {"human": {"when": "amount > 500 or fraud signal", "reviewer": "support lead", "timeout": "24h",
                       "on_timeout": "escalate", "state": "durable"}},
    "plan-execute": {"plan": {"reviewed": True, "recheck_before_each_step": True}},
    "reflexion": {"memory": {"lessons_file": "lessons.md", "max_lessons": 20}, "exit": {"max_rounds": 4}},
    "custom-logic": {"rules_in_code": ["purchase verified", "fraud check"],
                     "tools": [{"name": "issue_refund", "description": "Refunds one verified order in full. Irreversible. Fails with NOT_VERIFIED if the purchase check failed.",
                                "irreversible": True, "gate": "code"}]},
    "event-driven": {"trigger": {"event": "transaction.created", "condition": "score > 0.9 and amount > 1000",
                                 "dedupe": True, "rate_limit": "10/min", "dry_run_days": 7}},
}


def scaffold(p):
    d = json.loads(json.dumps(BASE))
    d["pattern"] = p
    for k, v in EXTRA.get(p, {}).items():
        d[k] = v if not isinstance(v, dict) or k not in d else {**d[k], **v}
    return d


# ---------- audit ----------

def audit(d):
    out = []

    def f(sev, rule, msg):
        out.append({"severity": sev, "rule": rule, "msg": msg})

    pats = d.get("patterns") or [d.get("pattern")]
    pats = [p for p in pats if p]
    for p in pats:
        if p not in PATTERNS:
            f("error", "pattern", f"unknown pattern '{p}' (see `list`)")
    pats = [p for p in pats if p in PATTERNS]
    if not pats:
        f("error", "pattern", "no pattern named")
    tools = d.get("tools") or []
    budget = d.get("budget") or {}
    words = d.get("system_prompt_words")
    if d.get("system_prompt_file") and Path(d["system_prompt_file"]).is_file():
        text = Path(d["system_prompt_file"]).read_text(errors="replace")
        words = len(text.split())
        if re.search(r"\bbut (don'?t|do not|never)\b.*\bwhen\b", text, re.I):
            f("warn", "rule 7: separate prompts", "the prompt has 'but don't X when Y' clauses: it may be doing two jobs")

    # rule 1 and single-agent break condition
    if words and words > 700:
        f("warn", "rule 7: separate prompts", f"system prompt is {words} words; past a page, split by responsibility "
          "(coordinator or sequential) instead of growing it")
    if "single" in pats and len(tools) > 8:
        f("warn", "single agent", f"{len(tools)} tools for one agent; past a handful it starts picking the wrong one")
    # rule 2: tool descriptions as contracts
    for t in tools:
        desc = (t.get("description") or "").strip()
        if len(desc) < 40:
            f("warn", "rule 2: tool contracts", f"tool '{t.get('name')}' has a {len(desc)}-char description; say what "
              "it returns, what it changes and how it fails")
    # rule 3: budgets
    if not budget:
        f("error", "rule 3: budgets", "no budget: cap steps, tool calls and spend per request")
    else:
        for k in ("max_steps", "max_tool_calls", "max_usd"):
            if k not in budget:
                f("warn", "rule 3: budgets", f"budget has no {k}")
    # rule 4: trace
    if not (d.get("logging") or {}).get("trace"):
        f("error", "rule 4: trace", "no action trace: log tool calls, arguments, outputs and the final decision")
    # rule 5: irreversible actions gated by code or a person
    for t in tools:
        irr = t.get("irreversible")
        if irr is None and IRREVERSIBLE.search(t.get("name", "")):
            f("warn", "rule 5: irreversible", f"tool '{t['name']}' sounds irreversible but isn't marked; set irreversible")
            irr = True
        if irr and t.get("gate") not in ("code", "human"):
            f("error", "rule 5: irreversible", f"tool '{t.get('name')}' is irreversible with gate "
              f"'{t.get('gate', 'none')}': it needs a code check or a person, never the model alone")
    # rule 6: failure-case evals
    ev = d.get("evals") or {}
    if not ev.get("failure_cases"):
        f("error" if ev.get("happy_cases") else "warn", "rule 6: evals",
          "no failure-case evals: happy-path correctness is a prototype")
    # rule 8: distributed systems
    multi = {"sequential", "parallel", "coordinator", "hierarchical", "swarm", "review", "refine"} & set(pats)
    if multi and not (d.get("branch_timeout_s") or budget.get("timeout_s")):
        f("warn", "rule 8: distributed", "multi-agent with no timeout: decide what happens when one agent hangs or fails")
    # rule 9: model review is not validation
    if ("review" in pats or "refine" in pats) and not d.get("rules_in_code") and not (d.get("exit") or {}).get("check") \
            and (d.get("score") or {}).get("by") != "code":
        f("warn", "rule 9: validation", "a judge improves quality but enforces nothing; add a deterministic check too")

    # pattern break conditions
    ex = d.get("exit") or {}
    if {"loop", "refine", "reflexion"} & set(pats):
        if not ex.get("max_rounds"):
            f("error", "loop", "no max_rounds: without a cap a loop can run up costs forever")
        if "loop" in pats and not ex.get("check"):
            f("error", "loop", "no exit check: say which command or test decides 'done'")
    if "react" in pats and not budget.get("max_steps"):
        f("error", "react", "no max_steps: cap reason-act cycles or it explores forever")
    if "review" in pats:
        g, c = d.get("generator") or {}, d.get("critic") or {}
        if not c:
            f("error", "review", "no critic described")
        else:
            if c.get("context") != "own":
                f("warn", "review", "critic shares the generator's context: it inherits its framing; give it its own")
            if g.get("model") and g.get("model") == c.get("model") and not c.get("rubric"):
                f("warn", "review", "same model as the generator and no rubric: same blind spots")
    if "refine" in pats:
        s = d.get("score") or {}
        if s.get("by") in (None, "same-model", "self", "generator"):
            f("error", "refine", "the generator scores itself: it can inflate the score without improving; "
              "score with code or a separate agent")
        if s.get("threshold") is None:
            f("error", "refine", "no score threshold")
    if "parallel" in pats or "hierarchical" in pats:
        parts = d.get("stages") or d.get("subgoals") or []
        names = {s.get("name") for s in parts}
        outs = {o for s in parts for o in (s.get("out") or [])}
        for s in parts:
            dep = [x for x in (s.get("in") or []) if x in outs] + [x for x in (s.get("depends_on") or []) if x in names]
            if dep:
                f("error", "parallel" if "parallel" in pats else "hierarchical",
                  f"'{s.get('name')}' needs {', '.join(dep)} from another branch: that's sequential, not parallel")
        if not (d.get("merge") or d.get("synthesis")):
            f("warn", "parallel", "no merge or synthesis step named")
    if "sequential" in pats:
        st = d.get("stages") or []
        for prev, nxt in zip(st, st[1:]):
            need = set(nxt.get("in") or [])
            if need and not need & set(prev.get("out") or []):
                f("warn", "sequential", f"'{nxt.get('name')}' takes {sorted(need)} but '{prev.get('name')}' doesn't produce it")
    if "coordinator" in pats:
        if len(d.get("routes") or []) < 2:
            f("error", "coordinator", "fewer than two routes: a coordinator with one destination is a single agent")
        if not d.get("fallback_route"):
            f("error", "coordinator", "no fallback route for requests that fit no category (or several)")
    if "swarm" in pats:
        if not d.get("rounds"):
            f("error", "swarm", "no round limit")
        if not d.get("facilitator"):
            f("warn", "swarm", "no facilitator to weigh the views")
        if len(d.get("roles") or []) < 3:
            f("warn", "swarm", "fewer than three roles: use review-and-critique instead")
    if "hitl" in pats:
        h = d.get("human") or {}
        for k, why in (("reviewer", "who decides"), ("timeout", "how long it waits"),
                       ("on_timeout", "what happens if nobody answers"), ("when", "which cases pause")):
            if not h.get(k):
                f("error", "hitl", f"human step has no {k} ({why})")
        if h.get("state") != "durable":
            f("error", "hitl", "pending decisions aren't in durable state: a restart loses them")
    if "plan-execute" in pats:
        pl = d.get("plan") or {}
        if not pl.get("reviewed"):
            f("warn", "plan-execute", "the plan isn't reviewed before running: then it's just ReAct with extra steps")
        if not pl.get("recheck_before_each_step"):
            f("warn", "plan-execute", "no precondition re-check before each step: a stale plan run blindly is worse than none")
    if "reflexion" in pats:
        m = d.get("memory") or {}
        if not m.get("lessons_file"):
            f("error", "reflexion", "no lessons file: lessons that live only in the context vanish next run")
        if not m.get("max_lessons"):
            f("warn", "reflexion", "no cap on lessons: the list grows until it's noise")
    if "custom-logic" in pats and not d.get("rules_in_code"):
        f("error", "custom-logic", "no rules listed as code: name what the model must never decide")
    if "event-driven" in pats:
        t = d.get("trigger") or {}
        if not t.get("condition"):
            f("error", "event-driven", "no trigger condition: vague triggers cry wolf")
        if not t.get("dedupe"):
            f("warn", "event-driven", "no dedupe: the same event can fire the agent twice")
        if not t.get("rate_limit"):
            f("warn", "event-driven", "no rate limit: an event storm becomes an agent storm")
        if not t.get("dry_run_days"):
            f("info", "event-driven", "no dry run: log what it would do for a week before it acts")

    # rule 10: prefer the simpler pattern
    if len(pats) == 1 and COMPLEXITY[pats[0]] >= 5 and len(tools) <= 2 and not d.get("roles") and not d.get("subgoals"):
        f("info", "rule 10: simpler", f"{PATTERNS[pats[0]][0]} with {len(tools)} tool(s): check a single agent doesn't do")
    order = {"error": 0, "warn": 1, "info": 2}
    out.sort(key=lambda x: order[x["severity"]])
    return out


# ---------- main ----------

def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("pick")
    for flag, h in (("predictable", "input-to-output path is predictable"), ("tool-choice", "must choose tools at runtime"),
                    ("route", "requests are of different kinds"), ("quality", "output quality varies and matters"),
                    ("measurable", "'good enough' has a measurable threshold"),
                    ("path-unknown", "path depends on what each step finds"),
                    ("approve-plan", "the plan must be approved first"), ("fast-changing", "environment changes quickly"),
                    ("self-correct", "failures are informative"), ("risk", "financial, legal or reputational risk"),
                    ("broad", "too broad for one pass"), ("no-right-answer", "competing views, no single answer"),
                    ("event", "must act on events, not requests"), ("stages", "fixed stages, each feeds the next"),
                    ("independent", "subtasks are independent"), ("repeat", "needs several attempts with a stop check")):
        p.add_argument("--" + flag, action="store_true", help=h)
    p.add_argument("--json", action="store_true")
    s = sub.add_parser("scaffold")
    s.add_argument("pattern", choices=ORDER)
    au = sub.add_parser("audit")
    au.add_argument("design")
    au.add_argument("--json", action="store_true")
    au.add_argument("--fail-on", choices=("error", "warn"), default="error")
    sub.add_parser("list")
    a = ap.parse_args(argv)

    if a.cmd == "list":
        for k in ORDER:
            name, what, breaks, build = PATTERNS[k]
            print(f"{k:13} {name}: {what}\n{'':13} breaks when {breaks}.\n{'':13} Claude Code: {build}\n")
        return 0
    if a.cmd == "pick":
        r = pick(a)
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            print_pick(r)
        return 0
    if a.cmd == "scaffold":
        print(json.dumps(scaffold(a.pattern), indent=2))
        return 0
    try:
        d = json.loads(Path(a.design).read_text())
    except (OSError, ValueError) as e:
        print(f"Can't read {a.design}: {e}", file=sys.stderr)
        return 2
    res = audit(d)
    if a.json:
        print(json.dumps({"design": d.get("name"), "findings": res}, indent=2))
    else:
        errs = sum(1 for r in res if r["severity"] == "error")
        print(("OK" if not errs else f"{errs} error(s)") + f": {d.get('name', a.design)} "
              f"({', '.join(d.get('patterns') or [str(d.get('pattern'))])})")
        for r in res:
            print(f"  [{r['severity']}] {r['rule']}: {r['msg']}")
    bad = {"error"} if a.fail_on == "error" else {"error", "warn"}
    return 1 if any(r["severity"] in bad for r in res) else 0


if __name__ == "__main__":
    sys.exit(main())
