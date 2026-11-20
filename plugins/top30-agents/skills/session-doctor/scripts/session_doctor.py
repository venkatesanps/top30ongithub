#!/usr/bin/env python3
"""Session doctor: reads a Claude Code session transcript (.jsonl) and says which layer of the
agent stack failed - prompt, context, loop or harness - and which built-in command fixes it.

Offline and read-only. Reads ~/.claude/projects/<project>/<session>.jsonl, never writes there,
and sends nothing anywhere.

  session_doctor.py list   [--project DIR] [--limit N]
  session_doctor.py diagnose <session.jsonl | session-id | --latest> [--project DIR]
                           [--json] [--no-snippets] [--include-subagents]

Exit code: 0 when the session looks healthy, 1 when any finding is a warning or worse,
2 on bad input. Set SESSION_DOCTOR_PROJECTS to read transcripts from another folder.
"""
import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

LAYERS = ("prompt", "context", "loop", "harness")
SEVERITY = {"info": 0, "warn": 1, "high": 2}

# Thresholds. Kept as constants so tests and readers can see them.
REPEAT_FAILS = 2          # the same failing call this many times = stuck
SAME_ERROR = 3            # the same error text this many times, any input
EDIT_CHURN = 6            # edits to one file in one session
CONTEXT_PEAK = 150_000    # tokens in a single request
SLOW_TOOL_S = 120         # a foreground tool call this long should have been backgrounded
TERSE_PROMPT = 25         # characters in the opening prompt

VERIFY_RE = re.compile(
    r"\b(pytest|unittest|test|tests|jest|vitest|mocha|go test|cargo (test|check|build)|"
    r"npm (run )?(test|build|lint)|pnpm|yarn (test|build)|tsc|mypy|ruff|eslint|flake8|"
    r"make|gradle|mvn|dbt (build|test|run)|validate|py_compile|check|lint|xcodebuild|swift (build|test))\b",
    re.I)
CODE_EXT = re.compile(r"\.(py|js|jsx|ts|tsx|go|rs|java|kt|swift|rb|php|c|cc|cpp|h|cs|sql|sh|scala|vue|svelte)$", re.I)
DENIED_RE = re.compile(
    r"permission .*denied|was denied|denied by|doesn't want to proceed|tool use was rejected|"
    r"not allowed|requires approval|blocked by (a )?hook", re.I)
UNTRUSTED_RE = re.compile(r"Ignoring \d+ permissions?\.allow entr|workspace has not been trusted", re.I)
TIMEOUT_RE = re.compile(r"timed out|timeout after|Command timed out", re.I)
CORRECTION_RE = re.compile(
    r"^(no[,.! ]|nope|wrong|stop\b|don'?t\b|that'?s (not|wrong)|not what i|i said|i told you|"
    r"why did you|you (didn'?t|forgot|ignored)|again[,.!]|undo|revert)", re.I)
INTERRUPT_RE = re.compile(r"\[Request interrupted by user", re.I)
DONE_RE = re.compile(r"\b(done|fixed|all (tests )?pass(es|ing)?|works now|complete[d]?|ready to merge|shipped)\b", re.I)


# ---------- locating transcripts ----------

def projects_root():
    return Path(os.environ.get("SESSION_DOCTOR_PROJECTS") or Path.home() / ".claude" / "projects")


def project_slug(path):
    return re.sub(r"[^A-Za-z0-9]", "-", str(Path(path).resolve()))


def project_dir(project):
    root = projects_root()
    if project:
        p = Path(project).expanduser()
        if p.is_dir() and any(p.glob("*.jsonl")):
            return p
        return root / project_slug(p)
    return root / project_slug(Path.cwd())


def sessions(pdir):
    return sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)


def resolve(target, project, latest):
    if latest:
        pdir = project_dir(project)
        found = sessions(pdir) if pdir.is_dir() else []
        if not found:
            sys.exit(f"No transcripts in {pdir}. Pass --project or a .jsonl path.")
        return found[0]
    p = Path(target).expanduser()
    if p.is_file():
        return p
    hits = list(projects_root().glob(f"*/{target}.jsonl"))
    if len(hits) == 1:
        return hits[0]
    sys.exit(f"Can't find session '{target}'" + (f" ({len(hits)} matches)" if hits else ""))


# ---------- parsing ----------

def load(path, include_subagents=False):
    rows = []
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict):
                continue
            if d.get("isSidechain") and not include_subagents:
                continue
            d["_line"] = n
            rows.append(d)
    return rows


def blocks(d):
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def text_of(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(text_of(x.get("text", x.get("content", ""))) if isinstance(x, dict) else str(x)
                        for x in content)
    return "" if content is None else str(content)


def key_of(name, inp):
    try:
        return name + ":" + json.dumps(inp, sort_keys=True)[:400]
    except (TypeError, ValueError):
        return name + ":" + str(inp)[:400]


def short(s, n=90):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def parse(rows):
    """Turn raw rows into one ordered list of events the checks can read."""
    ev = {"calls": [], "user_prompts": [], "assistant_texts": [], "compactions": [],
          "requests": [], "cwd": None, "title": None, "cost": None, "denied_rules": [],
          "first_ts": None, "last_ts": None, "models": Counter()}
    by_id = {}
    for d in rows:
        t = d.get("type")
        ts = d.get("timestamp")
        if ts:
            ev["first_ts"] = ev["first_ts"] or ts
            ev["last_ts"] = ts
        ev["cwd"] = ev["cwd"] or d.get("cwd")
        if t == "custom-title":
            ev["title"] = d.get("customTitle")
        elif t == "cost-state":
            ev["cost"] = d.get("totalCostUSD")
        elif t == "system" and d.get("subtype") == "compact_boundary":
            meta = d.get("compactMetadata") or {}
            ev["compactions"].append({"line": d["_line"], "trigger": meta.get("trigger", "?"),
                                      "pre": meta.get("preTokens")})
        elif t == "assistant":
            msg = d.get("message") or {}
            if msg.get("model"):
                ev["models"][msg["model"]] += 1
            u = msg.get("usage") or {}
            tok = sum(int(u.get(k) or 0) for k in
                      ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"))
            if tok:
                ev["requests"].append({"line": d["_line"], "tokens": tok})
            for b in blocks(d):
                if b.get("type") == "tool_use":
                    call = {"id": b.get("id"), "name": b.get("name", "?"), "input": b.get("input") or {},
                            "line": d["_line"], "ts": ts, "error": None, "result_ts": None,
                            "interrupted": False, "denied": False}
                    call["key"] = key_of(call["name"], call["input"])
                    ev["calls"].append(call)
                    by_id[call["id"]] = call
                elif b.get("type") == "text" and b.get("text", "").strip():
                    ev["assistant_texts"].append({"line": d["_line"], "text": b["text"]})
        elif t == "user":
            pdec = d.get("permissionDecision") or {}
            tur = d.get("toolUseResult")
            for b in blocks(d):
                if b.get("type") == "tool_result":
                    call = by_id.get(b.get("tool_use_id"))
                    if not call:
                        continue
                    call["result_ts"] = ts
                    body = text_of(b.get("content"))
                    if isinstance(tur, dict) and tur.get("interrupted"):
                        call["interrupted"] = True
                    if pdec.get("decision") == "reject" or DENIED_RE.search(body[:400]):
                        call["denied"] = True
                    if b.get("is_error") in (True, "True", "true"):
                        call["error"] = body
                    if UNTRUSTED_RE.search(body):
                        ev["denied_rules"].append(call["line"])
                elif b.get("type") == "text":
                    txt = b.get("text", "")
                    if txt.startswith("<") and not INTERRUPT_RE.search(txt):
                        continue  # system reminders, command wrappers
                    if d.get("isMeta") or d.get("isCompactSummary"):
                        continue
                    ev["user_prompts"].append({"line": d["_line"], "text": txt})
    return ev


def seconds(a, b):
    from datetime import datetime
    try:
        f = lambda s: datetime.fromisoformat(s.replace("Z", "+00:00"))
        return (f(b) - f(a)).total_seconds()
    except (TypeError, ValueError, AttributeError):
        return None


# ---------- checks ----------

def finding(layer, sev, signal, what, fix, evidence=()):
    return {"layer": layer, "severity": sev, "signal": signal, "what": what, "fix": fix,
            "evidence": list(evidence)[:5]}


def file_of(call):
    i = call["input"]
    return i.get("file_path") or i.get("path") or i.get("notebook_path")


def check(ev, fs=True, snippets=True):
    out = []
    calls = ev["calls"]
    snip = (lambda s: short(s)) if snippets else (lambda s: "")

    # LOOP: the same failing call again and again
    fails = defaultdict(list)
    for c in calls:
        if c["error"] and not c["denied"]:
            fails[c["key"]].append(c)
    stuck = {k: v for k, v in fails.items() if len(v) >= REPEAT_FAILS}
    for k, v in sorted(stuck.items(), key=lambda kv: -len(kv[1]))[:3]:
        out.append(finding(
            "loop", "high" if len(v) >= 3 else "warn", "repeated-failure",
            f"{v[0]['name']} failed {len(v)} times with the same input. Retrying an identical call "
            "never changes the result.",
            "Stop and read the error. If the approach is wrong: /rewind to before it, then /plan. "
            "For a second opinion on why it's stuck: /advisor opus (or fable). If it was thinking "
            "too little: /effort high.",
            [f"line {c['line']}: {snip(c['error'])}" for c in v]))

    errs = Counter(short(c["error"], 120) for c in calls if c["error"] and not c["denied"])
    for msg, n in errs.most_common(2):
        if n >= SAME_ERROR and not any(short(v[0]["error"], 120) == msg for v in stuck.values()):
            out.append(finding(
                "loop", "warn", "same-error",
                f"The same error came back {n} times across different attempts.",
                "Fix the cause the error names before trying variations. /debug turns on debug logs "
                "if the error is from Claude Code itself.",
                [snip(msg)]))

    # LOOP: churn on one file
    edits = Counter(file_of(c) for c in calls if c["name"] in ("Edit", "Write", "MultiEdit", "NotebookEdit")
                    and file_of(c))
    for f, n in edits.most_common(2):
        if n >= EDIT_CHURN:
            out.append(finding(
                "loop", "warn", "edit-churn",
                f"{Path(f).name} was edited {n} times. Many small edits to one file usually means "
                "trial and error rather than a plan.",
                "/plan the change before editing; /rewind if the file drifted. /diff shows where it "
                "ended up.",
                [f]))

    # LOOP: declared done without running a check after the last code edit
    code_edits = [c for c in calls if c["name"] in ("Edit", "Write", "MultiEdit")
                  and CODE_EXT.search(str(file_of(c) or ""))]
    if code_edits:
        last = code_edits[-1]["line"]
        verified = any(c["line"] > last and (
            (c["name"] == "Bash" and VERIFY_RE.search(str(c["input"].get("command", ""))))
            or c["name"] in ("Skill",) and re.search(r"verify|run|test", str(c["input"]), re.I))
            for c in calls)
        claimed = [t for t in ev["assistant_texts"] if t["line"] > last and DONE_RE.search(t["text"])]
        if not verified:
            out.append(finding(
                "loop", "high" if claimed else "warn", "unverified",
                "Code was edited and no test, build or check ran afterwards"
                + (", yet the session said it was done." if claimed else "."),
                "/verify (or /run) to build and drive the app; run the tests; /code-review for bugs "
                "before merging. A /goal with a check command makes this automatic.",
                [f"last code edit line {last}: {file_of(code_edits[-1])}"]
                + [f"line {t['line']}: {snip(t['text'])}" for t in claimed[:2]]))

    # CONTEXT: compactions and peak size
    if ev["compactions"]:
        auto = [c for c in ev["compactions"] if c["trigger"] == "auto"]
        out.append(finding(
            "context", "warn" if auto else "info", "compaction",
            f"Context was compacted {len(ev['compactions'])} time(s)"
            + (f", {len(auto)} automatically" if auto else "")
            + ". Whatever the summary dropped, the model no longer knows.",
            "/context to see what fills the window; /compact <what to keep> yourself before it's "
            "forced; /btw for side questions so they don't land in context; /fork or a subagent for "
            "big reads.",
            [f"line {c['line']}: {c['trigger']}, {c['pre'] or '?'} tokens before" for c in ev["compactions"]]))
    if ev["requests"]:
        peak = max(ev["requests"], key=lambda r: r["tokens"])
        if peak["tokens"] >= CONTEXT_PEAK and not ev["compactions"]:
            out.append(finding(
                "context", "warn", "context-peak",
                f"One request carried {peak['tokens']:,} tokens of context. Quality drops well before "
                "the window is full.",
                "/context to find what's large (tool output, files read whole); /compact with a focus.",
                [f"line {peak['line']}"]))

    # HARNESS: permission denials and untrusted folder
    denied = [c for c in calls if c["denied"]]
    if denied:
        names = Counter(c["name"] for c in denied)
        out.append(finding(
            "harness", "warn", "permission-denied",
            f"{len(denied)} tool call(s) were denied ({', '.join(f'{n} x{k}' for n, k in names.most_common(3))}). "
            "Each denial costs a turn and often a workaround.",
            "If the calls were safe, add exact allow rules in .claude/settings.json (the "
            "fewer-permission-prompts skill finds them); if not, the denial was right and the task "
            "needs a different route.",
            [f"line {c['line']}: {c['name']} {snip(c['error'] or '')}" for c in denied]))
    if ev["denied_rules"]:
        out.append(finding(
            "harness", "high", "untrusted-folder",
            "Claude Code ignored the folder's permissions.allow rules because the folder isn't trusted.",
            "Run `claude` in that folder once and accept the trust dialog; scheduled or headless runs "
            "can't do it for you. (If it was a throwaway test folder, ignore this.)",
            [f"line {n}" for n in ev["denied_rules"]]))

    # HARNESS: slow work in the foreground, timeouts
    slow = []
    for c in calls:
        if c["name"] != "Bash" or c["input"].get("run_in_background"):
            continue
        dur = seconds(c["ts"], c["result_ts"]) if c["ts"] and c["result_ts"] else None
        if (dur and dur >= SLOW_TOOL_S) or (c["error"] and TIMEOUT_RE.search(c["error"][:300])):
            slow.append((c, dur))
    if slow:
        out.append(finding(
            "harness", "warn", "foreground-wait",
            f"{len(slow)} shell command(s) ran {SLOW_TOOL_S}s+ or timed out in the foreground, "
            "blocking the session.",
            "Run long builds and servers in the background (run_in_background) and check them with "
            "/tasks; /background (or /bg) detaches the whole session.",
            [f"line {c['line']}: {snip(c['input'].get('command', ''))}"
             + (f" ({int(d)}s)" if d else " (timed out)") for c, d in slow]))

    # PROMPT: missing CLAUDE.md, terse opening, corrections and interrupts
    cwd = ev["cwd"]
    if fs and cwd and Path(cwd).is_dir():
        has = any((Path(cwd) / p).is_file() for p in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"))
        if not has and (Path(cwd) / ".git").exists():
            out.append(finding(
                "prompt", "warn", "no-claude-md",
                f"The project ({cwd}) has no CLAUDE.md, so every session starts without its build "
                "commands, conventions and no-go areas.",
                "/init writes one from the codebase (CLAUDE_CODE_NEW_INIT=1 for the interactive "
                "version); keep it short and true; /memory to edit it later.",
                [cwd]))
    prompts = [p for p in ev["user_prompts"] if not INTERRUPT_RE.search(p["text"])]
    if prompts and len(prompts[0]["text"].strip()) < TERSE_PROMPT and len(calls) >= 15 \
            and not re.search(r"https?://|/[\w.-]+\.\w+", prompts[0]["text"]):
        out.append(finding(
            "prompt", "info", "terse-start",
            f"The session opened with a {len(prompts[0]['text'].strip())}-character request and "
            f"ran {len(calls)} tool calls. Short asks leave the goal and the finish line to guesswork.",
            "Say what done looks like and how to check it; /plan first for anything multi-step.",
            [f"line {prompts[0]['line']}: {snip(prompts[0]['text'])}"]))
    corr = [p for p in prompts[1:] if CORRECTION_RE.search(p["text"].strip())]
    if len(corr) >= 2:
        out.append(finding(
            "prompt", "warn", "corrections",
            f"You corrected the agent {len(corr)} times. Repeated corrections are usually a rule "
            "that belongs in CLAUDE.md, not in the chat.",
            "Put the rule in CLAUDE.md (/memory); for a wrong turn, /rewind instead of arguing "
            "forward; /btw to ask without derailing.",
            [f"line {p['line']}: {snip(p['text'])}" for p in corr]))
    intr = [p for p in ev["user_prompts"] if INTERRUPT_RE.search(p["text"])]
    intr += [{"line": c["line"]} for c in calls if c["interrupted"]]
    if len(intr) >= 2:
        out.append(finding(
            "prompt", "info", "interrupts",
            f"You interrupted {len(intr)} times. Often the plan wasn't agreed before work started.",
            "/plan to agree the approach first; /rewind to drop a wrong direction cleanly.",
            [f"line {p['line']}" for p in intr]))

    out.sort(key=lambda f: (-SEVERITY[f["severity"]], LAYERS.index(f["layer"])))
    return out


def stats(ev):
    calls = ev["calls"]
    peak = max((r["tokens"] for r in ev["requests"]), default=0)
    return {"title": ev["title"], "cwd": ev["cwd"], "start": ev["first_ts"], "end": ev["last_ts"],
            "user_prompts": len(ev["user_prompts"]), "tool_calls": len(calls),
            "tool_errors": sum(1 for c in calls if c["error"]), "denied": sum(1 for c in calls if c["denied"]),
            "compactions": len(ev["compactions"]), "peak_context": peak,
            "top_tools": dict(Counter(c["name"] for c in calls).most_common(6)),
            "models": dict(ev["models"]), "cost_usd": ev["cost"]}


def verdict(findings):
    if not findings or all(f["severity"] == "info" for f in findings):
        return "healthy"
    worst = Counter()
    for f in findings:
        worst[f["layer"]] += SEVERITY[f["severity"]]
    return "weakest layer: " + worst.most_common(1)[0][0]


# ---------- commands ----------

def cmd_list(a):
    pdir = project_dir(a.project)
    if not pdir.is_dir():
        sys.exit(f"No transcripts folder {pdir}")
    for p in sessions(pdir)[: a.limit]:
        title, first = None, None
        with open(p, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                if '"custom-title"' in line:
                    try:
                        title = json.loads(line).get("customTitle")
                    except ValueError:
                        pass
                if first is None and '"timestamp"' in line:
                    try:
                        first = json.loads(line).get("timestamp")
                    except ValueError:
                        pass
        print(f"{p.stem}  {(first or '')[:16]:16}  {p.stat().st_size // 1024:>6} KB  {title or ''}")
    return 0


def cmd_diagnose(a):
    if not a.target and not a.latest:
        print("Give a session file or id, or --latest.", file=sys.stderr)
        return 2
    path = resolve(a.target, a.project, a.latest)
    ev = parse(load(path, a.include_subagents))
    f = check(ev, fs=not a.no_fs, snippets=not a.no_snippets)
    s = stats(ev)
    rep = {"session": str(path), "verdict": verdict(f), "stats": s, "findings": f}
    if a.json:
        print(json.dumps(rep, indent=2))
    else:
        print(f"# Session doctor: {s['title'] or path.stem}")
        print(f"{path}\n")
        print(f"{s['user_prompts']} prompts, {s['tool_calls']} tool calls ({s['tool_errors']} errors, "
              f"{s['denied']} denied), {s['compactions']} compactions, peak context {s['peak_context']:,} tokens"
              + (f", ${float(s['cost_usd']):.2f}" if s["cost_usd"] else ""))
        print(f"Verdict: {rep['verdict']}\n")
        if not f:
            print("No problems found in the transcript. That doesn't prove the result is right: "
                  "only a check you ran does.")
        for layer in LAYERS:
            lf = [x for x in f if x["layer"] == layer]
            if not lf:
                continue
            print(f"## {layer.upper()}")
            for x in lf:
                print(f"- [{x['severity']}] {x['what']}")
                print(f"  Fix: {x['fix']}")
                for e in x["evidence"]:
                    if e:
                        print(f"    · {e}")
            print()
    return 1 if any(x["severity"] != "info" for x in f) else 0


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("list", help="recent sessions for a project")
    l.add_argument("--project", help="project folder (default: current folder) or its transcripts folder")
    l.add_argument("--limit", type=int, default=15)
    d = sub.add_parser("diagnose", help="diagnose one session")
    d.add_argument("target", nargs="?", help="path to a .jsonl or a session id")
    d.add_argument("--latest", action="store_true", help="the most recent session for --project")
    d.add_argument("--project")
    d.add_argument("--json", action="store_true")
    d.add_argument("--no-snippets", action="store_true", help="don't quote prompt or error text")
    d.add_argument("--no-fs", action="store_true", help="don't look at the project folder (CLAUDE.md check)")
    d.add_argument("--include-subagents", action="store_true")
    a = p.parse_args(argv)
    return cmd_list(a) if a.cmd == "list" else cmd_diagnose(a)


if __name__ == "__main__":
    sys.exit(main())
