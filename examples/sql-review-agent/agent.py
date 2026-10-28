#!/usr/bin/env python3
"""A read-only Snowflake SQL review agent, built on the Claude Agent SDK.

    pip install claude-agent-sdk sqlglot
    python3 agent.py path/to/sql_folder               # writes sql-review.md
    python3 agent.py models/ --model sonnet --budget 0.50 --out review.md

What it shows (the parts of the SDK you'd reuse for any agent):
  * a custom tool: `lint_sql` runs deterministic sqlglot checks (checks.py) so the model reasons
    over real parser output, not guesses
  * a locked-down toolset: only Read, Glob, Grep and lint_sql exist in the session
  * a PreToolUse hook as a second lock: anything else, or any path outside the folder, is denied
  * isolation: setting_sources=[] ignores your personal settings, plugins and CLAUDE.md, so the
    review is the same on every machine
  * a budget cap and turn cap, and the cost printed at the end

It never runs SQL and never connects to Snowflake. Auth is whatever Claude Code uses on this
machine (your login, ANTHROPIC_API_KEY, or CLAUDE_CODE_USE_BEDROCK=1 with AWS credentials).
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from claude_agent_sdk import (AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, HookMatcher,
                              ResultMessage, TextBlock, create_sdk_mcp_server, tool)

sys.path.insert(0, str(Path(__file__).resolve().parent))
from checks import check_sql  # noqa: E402

ALLOWED = {"Read", "Glob", "Grep", "mcp__sql__lint_sql"}

SYSTEM = """You review Snowflake SQL for a data engineering team. You are read-only.

Steps:
1. Glob for **/*.sql under the current folder.
2. Call lint_sql on every file. Its findings come from a real SQL parser: report each one,
   with its line, and do not contradict it.
3. Read each file and add what a parser can't see: wrong join keys or grain, missing
   deduplication, non-idempotent loads (DELETE + INSERT without a transaction, missing MERGE),
   filters on the wrong column, hard-coded dates, unclear names. Only flag what you can point
   to in the code. Never invent table sizes, data or column meanings.
4. Write the report in markdown:
   - "## Summary": files reviewed, counts by severity, the one change to make first.
   - "## Findings": a table | File:line | Severity | Issue | Fix |, errors first.
   - "## Suggested rewrites": corrected SQL only for errors and warnings, shortest form.
   - "## Not checked": anything you could not assess (e.g. needs table stats or data).
Return only the report."""


def make_lint_tool(root: Path):
    @tool("lint_sql", "Parse one .sql file with sqlglot (Snowflake dialect) and return rule-based findings as JSON.",
          {"path": str})
    async def lint_sql(args):
        p = (root / args["path"]).resolve()
        if root not in p.parents and p != root or p.suffix.lower() != ".sql" or not p.is_file():
            return {"content": [{"type": "text", "text": f"Refused: {args['path']} is not a .sql file inside the review folder."}],
                    "is_error": True}
        findings = check_sql(p.read_text(encoding="utf-8", errors="replace"))
        return {"content": [{"type": "text", "text": json.dumps({"file": str(p.relative_to(root)), "findings": findings})}]}
    return lint_sql


def make_guard(root: Path):
    async def guard(input_data, tool_use_id, context):
        name, ti = input_data.get("tool_name", ""), input_data.get("tool_input") or {}
        reason = None
        if name not in ALLOWED:
            reason = f"{name} is not allowed: this agent is read-only."
        else:
            for key in ("file_path", "path"):
                if ti.get(key) and name != "mcp__sql__lint_sql":
                    p = (root / ti[key]).resolve() if not Path(ti[key]).is_absolute() else Path(ti[key]).resolve()
                    if p != root and root not in p.parents:
                        reason = f"{ti[key]} is outside the review folder."
        if reason:
            return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                                           "permissionDecisionReason": reason}}
        return {}
    return guard


async def review(root: Path, model: str | None, budget: float, max_turns: int):
    server = create_sdk_mcp_server(name="sql", version="1.0.0", tools=[make_lint_tool(root)])
    options = ClaudeAgentOptions(
        system_prompt=SYSTEM,
        cwd=str(root),
        tools=["Read", "Glob", "Grep"],
        mcp_servers={"sql": server},
        allowed_tools=sorted(ALLOWED),
        disallowed_tools=["Write", "Edit", "Bash", "NotebookEdit", "WebFetch", "WebSearch"],
        hooks={"PreToolUse": [HookMatcher(matcher=None, hooks=[make_guard(root)])]},
        setting_sources=[],
        permission_mode="default",
        max_turns=max_turns,
        max_budget_usd=budget,
        model=model,
    )
    text, result = [], None
    async with ClaudeSDKClient(options=options) as client:
        await client.query("Review the SQL in this folder and return the report.")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                text = [b.text for b in msg.content if isinstance(b, TextBlock)] or text
            elif isinstance(msg, ResultMessage):
                result = msg
    return (result.result if result and result.result else "\n".join(text)), result


def main():
    ap = argparse.ArgumentParser(description="Read-only Snowflake SQL review agent (Claude Agent SDK).")
    ap.add_argument("folder", help="folder containing .sql files")
    ap.add_argument("--model", help="e.g. sonnet, opus or haiku (default: your Claude Code default)")
    ap.add_argument("--budget", type=float, default=1.0, help="max USD for the whole review (default 1.00)")
    ap.add_argument("--max-turns", type=int, default=40)
    ap.add_argument("--out", default="sql-review.md")
    a = ap.parse_args()
    root = Path(a.folder).expanduser().resolve()
    if not root.is_dir() or not any(root.rglob("*.sql")):
        sys.exit(f"No .sql files under {root}")
    report, res = asyncio.run(review(root, a.model, a.budget, a.max_turns))
    Path(a.out).write_text(report.strip() + "\n", encoding="utf-8")
    cost = f"${res.total_cost_usd:.3f}" if res and res.total_cost_usd is not None else "unknown"
    turns = res.num_turns if res else "?"
    print(f"Wrote {a.out}  (cost {cost}, {turns} turns{', ERROR: ' + str(res.subtype) if res and res.is_error else ''})")
    sys.exit(1 if res is None or res.is_error else 0)


if __name__ == "__main__":
    main()
