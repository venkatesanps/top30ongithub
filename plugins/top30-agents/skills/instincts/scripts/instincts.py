#!/usr/bin/env python3
"""Learn small, evidence-backed habits ("instincts") from your own Claude Code sessions,
offline and on request. No hooks, no background model, nothing leaves the machine.

  instincts.py mine [SESSION.jsonl ...] [--project DIR] [--latest N] [--no-snippets] [--json]
  instincts.py new ID --trigger "when ..." --action "..." --domain workflow --evidence "correction: ..."
  instincts.py observe ID confirm|repeat|correction|contradict|correct --note "..."
  instincts.py status [--write] [--json]        # effective confidence after decay
  instincts.py lint                              # atomic, evidenced, no secrets or injected text
  instincts.py evolve [-o DIR]                   # CLAUDE.md rules, hook ideas, skill drafts (files only)
  instincts.py promote --stores A B [--dry-run]  # same instinct strong in 2+ projects -> global
  instincts.py export [-o FILE] [--min 0.5]      # ECC-compatible, evidence reduced to counts
  instincts.py import FILE [--min 0.3]           # untrusted: linted, capped at 0.5 until confirmed
  instincts.py prune [--dry-run]                 # move dormant instincts to archive/

Store: one Markdown file per instinct in --store (default .claude/instincts), or --global
(~/.local/share/top30-instincts, or $TOP30_INSTINCTS_GLOBAL). Standard library only.
Format is compatible with ECC's continuous-learning-v2 instinct files.
"""
import argparse
import datetime as dt
import json
import os
import re
import shutil
import sys
from collections import Counter, defaultdict
from pathlib import Path

TODAY = dt.date.today()
if os.environ.get("TOP30_INSTINCTS_TODAY"):
    TODAY = dt.date.fromisoformat(os.environ["TOP30_INSTINCTS_TODAY"])

# confidence model: start at BASE, each evidence kind moves it, clamp, then decay by age
BASE = 0.3
WEIGHT = {"correction": 0.15, "confirm": 0.10, "repeat": 0.05, "fix": 0.10, "imported": 0.0,
          "contradict": -0.20, "correct": -0.25}
CAP, FLOOR = 0.9, 0.1
IMPORT_CAP = 0.5
DECAY_PER_30D = 0.05
BANDS = [(0.8, "core"), (0.7, "strong"), (0.5, "apply when relevant"), (0.3, "tentative"), (0.0, "dormant")]
PROMOTE_MIN, PROMOTE_STORES = 0.8, 2
DOMAINS = {"workflow", "code-style", "testing", "git", "debugging", "security", "data", "docs",
           "tooling", "communication", "review", "performance", "other"}

SECRET_RE = re.compile(
    r"(sk-[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|xox[abpr]-[A-Za-z0-9-]{10,}"
    r"|-----BEGIN [A-Z ]*PRIVATE KEY|eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{10,}"
    r"|(?:password|passwd|secret|token|api[_-]?key)\s*[:=]\s*\S{6,})", re.I)
EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
INJECT_RE = re.compile(
    r"(ignore (all |any )?(previous|prior|above) (instructions|rules)|disregard (the|your|all)"
    r"|you are now|system prompt|curl[^\n|]*\|\s*(ba|z)?sh|wget[^\n|]*\|\s*(ba|z)?sh|base64 -d[^\n|]*\|"
    r"|exfiltrat|send (it|this|the \w+) to https?://|bypassPermissions|--dangerously|rm -rf (~|/|\$HOME))", re.I)
HIDDEN_RE = re.compile("[​-‏‪-‮⁠-⁤﻿]")


def redact(s):
    s = SECRET_RE.sub("[secret]", s)
    return EMAIL_RE.sub("[email]", s)


def short(s, n=110):
    s = re.sub(r"\s+", " ", str(s)).strip()
    return s if len(s) <= n else s[: n - 1] + "…"


# ---------------------------------------------------------------- transcripts

def projects_root():
    return Path(os.environ.get("SESSION_DOCTOR_PROJECTS") or Path.home() / ".claude" / "projects")


def project_dir(project):
    p = Path(project or Path.cwd()).expanduser()
    if p.is_dir() and any(p.glob("*.jsonl")):
        return p
    return projects_root() / re.sub(r"[^A-Za-z0-9]", "-", str(p.resolve()))


def blocks(d):
    c = (d.get("message") or {}).get("content")
    if isinstance(c, str):
        return [{"type": "text", "text": c}]
    return [b for b in c if isinstance(b, dict)] if isinstance(c, list) else []


def text_of(c):
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return " ".join(text_of(x.get("text", x.get("content", ""))) if isinstance(x, dict) else str(x) for x in c)
    return "" if c is None else str(c)


def read_session(path):
    """Ordered events: ('user', text, line) and ('call', {name, cmd, error}, line)."""
    ev, calls = [], {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for n, line in enumerate(fh, 1):
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if not isinstance(d, dict) or d.get("isSidechain"):
                continue
            t = d.get("type")
            if t == "assistant":
                for b in blocks(d):
                    if b.get("type") == "tool_use":
                        inp = b.get("input") or {}
                        c = {"name": b.get("name", "?"), "cmd": str(inp.get("command", "")) if isinstance(inp, dict) else "",
                             "file": str(inp.get("file_path", "")) if isinstance(inp, dict) else "", "error": None}
                        calls[b.get("id")] = c
                        ev.append(("call", c, n))
            elif t == "user":
                if d.get("isMeta") or d.get("isCompactSummary"):
                    continue
                for b in blocks(d):
                    if b.get("type") == "tool_result":
                        c = calls.get(b.get("tool_use_id"))
                        if c is not None and b.get("is_error") in (True, "true", "True"):
                            c["error"] = text_of(b.get("content"))
                    elif b.get("type") == "text":
                        txt = b.get("text", "")
                        if txt.lstrip().startswith(("<", "Caveat:", "[Request interrupted")):
                            continue
                        ev.append(("user", txt, n))
    return ev


CORRECTION_START = re.compile(r"^\s*(no\b|nope|don'?t|do not|stop|instead|actually|wrong|that'?s (not|wrong)|not like that|undo|revert)", re.I)
RULE_WORDS = re.compile(r"\b(always|never|from now on|going forward|next time|in future|prefer|instead of|rather than|"
                        r"make sure (to|you)|remember to|please don'?t|you should|you forgot|don'?t ever|each time|every time)\b", re.I)
TRIVIAL_HEADS = {"ls", "cd", "cat", "echo", "pwd", "grep", "rg", "find", "head", "tail", "sed", "awk", "wc", "sort",
                 "git status", "git diff", "git log", "git show", "mkdir", "rm", "cp", "mv", "true", "sleep", "which", "open",
                 "for", "while", "if", "python", "python3", "node", "bash", "sh", "zsh", "export", "source", "set", "test",
                 "printf", "xargs", "tee", "date", "touch", "chmod", "file", "stat", "du", "df", "ps", "kill", "jq", "uv",
                 "npx", "poetry", "git add", "git rev-parse", "git branch", "git remote", "git config", "gh api", "diff", "cmp"}
SCRIPT_TOKEN = re.compile(r"^[\w./:-]+$")


def trivial(h):
    return not h or h in TRIVIAL_HEADS


def cmd_head(cmd):
    cmd = re.sub(r"^\s*(cd [^&;]+(&&|;)\s*)+", "", cmd.strip())
    cmd = re.sub(r"^([A-Z_]+=\S+\s+)+", "", cmd)
    toks = [t for t in re.split(r"\s+", cmd) if t]
    if not toks:
        return ""
    first = Path(toks[0]).name
    if not re.match(r"^[A-Za-z][\w.+-]*$", first):
        return ""
    if first in ("python", "python3", "node", "npx", "uv", "poetry", "bash", "sh") and len(toks) > 1:
        second = toks[1] if not toks[1].startswith("-") else (toks[2] if len(toks) > 2 else "")
        if first in ("python", "python3") and toks[1] == "-m" and len(toks) > 2:
            second = toks[2]
        if not SCRIPT_TOKEN.match(second) or second.startswith("-"):
            return first
        return f"{first} {Path(second).name}".strip()
    if first in ("git", "npm", "pnpm", "yarn", "bun", "cargo", "go", "make", "dbt", "gh", "docker", "kubectl", "terraform", "snow", "claude") and len(toks) > 1:
        return f"{first} {toks[1]}"
    return first


def sentences_with_rules(txt):
    out = []
    for s in re.split(r"(?<=[.!?])\s+|\n+", txt):
        s = s.strip()
        if 6 <= len(s) <= 300 and (RULE_WORDS.search(s) or CORRECTION_START.search(s)):
            out.append(s)
    return out


def norm_key(s):
    w = re.findall(r"[a-z0-9_.-]+", s.lower())
    stop = {"the", "a", "an", "to", "and", "or", "please", "you", "it", "this", "that", "of", "for", "in", "on", "is", "be", "i"}
    return " ".join(x for x in w if x not in stop)[:120]


def mine(paths, snippets=True, min_sessions=3):
    corrections = defaultdict(lambda: {"count": 0, "where": [], "text": "", "after": Counter()})
    fixes, heads, pairs = [], defaultdict(set), defaultdict(set)
    for p in paths:
        sid = p.stem[:8]
        ev = read_session(p)
        last_call, first_user = None, True
        for i, (kind, x, line) in enumerate(ev):
            if kind == "call":
                last_call = x
                if x["name"] == "Bash" and x["cmd"]:
                    h = cmd_head(x["cmd"])
                    if not trivial(h):
                        heads[h].add(sid)
                        # edit -> check pairs
                        prev = [e for e in ev[max(0, i - 4):i] if e[0] == "call"]
                        if any(e[1]["name"] in ("Edit", "Write", "MultiEdit") for e in prev):
                            pairs[f"after editing, run `{h}`"].add(sid)
                    if x["error"]:
                        for kind2, y, line2 in ev[i + 1:i + 7]:
                            if kind2 == "call" and y["name"] == "Bash" and not y["error"] and y["cmd"] != x["cmd"] \
                                    and cmd_head(y["cmd"]) == cmd_head(x["cmd"]):
                                if trivial(cmd_head(x["cmd"])):
                                    break
                                err = next((l for l in x["error"].splitlines()
                                            if l.strip() and not re.match(r"^\s*exit code \d+\s*$", l, re.I)), "")[:140]
                                fixes.append({"session": sid, "line": line, "head": cmd_head(x["cmd"]),
                                              "failed": redact(short(x["cmd"], 140)), "error": redact(short(err, 140)),
                                              "worked": redact(short(y["cmd"], 140)), "worked_line": line2})
                                break
                continue
            # user text
            is_reaction = last_call is not None and not first_user
            first_user = False
            for s in sentences_with_rules(x):
                if not (RULE_WORDS.search(s) or is_reaction):
                    continue
                k = norm_key(s)
                if not k:
                    continue
                c = corrections[k]
                c["count"] += 1
                c["text"] = c["text"] or redact(short(s, 200))
                c["where"].append(f"{sid}:{line}")
                if last_call:
                    c["after"][last_call["name"] + (":" + cmd_head(last_call["cmd"]) if last_call["cmd"] else "")] += 1
    cands = []
    for k, c in sorted(corrections.items(), key=lambda kv: -kv[1]["count"]):
        cands.append({"kind": "correction", "signal": c["text"] if snippets else f"(correction, {len(c['text'])} chars)",
                      "count": c["count"], "where": c["where"][:6],
                      "context": [a for a, _ in c["after"].most_common(2)]})
    for f in fixes:
        if not snippets:
            f = {k: v for k, v in f.items() if k in ("session", "line", "head", "worked_line")}
        cands.append(dict(kind="fix", count=1, **f))
    for h, ss in sorted(heads.items(), key=lambda kv: -len(kv[1])):
        if len(ss) >= min_sessions:
            cands.append({"kind": "repeat", "signal": f"`{h}` run in {len(ss)} sessions", "count": len(ss), "where": sorted(ss)[:6]})
    for h, ss in sorted(pairs.items(), key=lambda kv: -len(kv[1])):
        if len(ss) >= min_sessions:
            cands.append({"kind": "repeat", "signal": f"{h} ({len(ss)} sessions)", "count": len(ss), "where": sorted(ss)[:6]})
    return cands


# ---------------------------------------------------------------- instinct files

def store_dir(a):
    if getattr(a, "global_", False):
        return Path(os.environ.get("TOP30_INSTINCTS_GLOBAL") or Path.home() / ".local/share/top30-instincts")
    return Path(a.store)


EVID_RE = re.compile(r"^\s*-\s*(\d{4}-\d{2}-\d{2})\s+([a-z]+):\s*(.*)$")


def parse_blocks(text):
    """Parse one or more instincts: frontmatter + '# title' + '## Action' + '## Evidence'."""
    out, lines, i = [], text.splitlines(), 0
    while i < len(lines):
        if lines[i].strip() != "---":
            i += 1
            continue
        j = i + 1
        fm = {}
        while j < len(lines) and lines[j].strip() != "---":
            m = re.match(r"^([A-Za-z_]+):\s*(.*)$", lines[j])
            if m:
                v = m.group(2).strip()
                if len(v) >= 2 and v[0] == v[-1] == '"':
                    try:
                        v = json.loads(v)
                    except ValueError:
                        v = v[1:-1]
                elif len(v) >= 2 and v[0] == v[-1] == "'":
                    v = v[1:-1].replace("''", "'")
                fm[m.group(1)] = v
            j += 1
        k = j + 1
        while k < len(lines) and not (lines[k].strip() == "---" and k + 1 < len(lines) and re.match(r"^[a-z_]+:", lines[k + 1])):
            k += 1
        body = "\n".join(lines[j + 1:k])
        if "id" in fm:
            out.append(build(fm, body))
        i = k
    return out


def build(fm, body):
    sec, cur = defaultdict(list), "pre"
    for ln in body.splitlines():
        m = re.match(r"^##\s+(\w+)", ln)
        if m:
            cur = m.group(1).lower()
            continue
        if ln.startswith("# ") and cur == "pre":
            sec["title"] = [ln[2:].strip()]
            continue
        sec[cur].append(ln)
    ev = []
    for ln in sec.get("evidence", []):
        m = EVID_RE.match(ln)
        if m:
            ev.append({"date": m.group(1), "kind": m.group(2), "note": m.group(3)})
        elif ln.strip().startswith("-"):
            ev.append({"date": None, "kind": "note", "note": ln.strip()[1:].strip()})
    try:
        conf = float(fm.get("confidence", BASE))
    except ValueError:
        conf = -1.0
    return {"id": fm.get("id", ""), "trigger": fm.get("trigger", ""), "confidence": conf,
            "domain": fm.get("domain", "other"), "source": fm.get("source", "session-observation"),
            "scope": fm.get("scope", "project"), "project_name": fm.get("project_name", ""),
            "last_seen": fm.get("last_seen", ""), "title": (sec.get("title") or [""])[0],
            "action": "\n".join(sec.get("action", [])).strip(), "evidence": ev, "raw_fm": fm}


def render(ins, evidence=True):
    q = lambda v: json.dumps(str(v), ensure_ascii=False)
    fm = ["---", f"id: {ins['id']}", f"trigger: {q(ins['trigger'])}", f"confidence: {ins['confidence']:.2f}",
          f"domain: {q(ins['domain'])}", f"source: {q(ins['source'])}", f"scope: {ins['scope']}"]
    if ins.get("project_name"):
        fm.append(f"project_name: {q(ins['project_name'])}")
    if ins.get("last_seen"):
        fm.append(f"last_seen: {ins['last_seen']}")
    fm.append("---")
    title = ins.get("title") or ins["id"].replace("-", " ").capitalize()
    out = fm + ["", f"# {title}", "", "## Action", ins["action"], "", "## Evidence"]
    if evidence:
        out += [f"- {e['date']} {e['kind']}: {e['note']}" if e.get("date") else f"- {e['note']}" for e in ins["evidence"]]
    else:
        c = Counter(e["kind"] for e in ins["evidence"])
        out.append(f"- {sum(c.values())} observations (" + ", ".join(f"{v} {k}" for k, v in sorted(c.items())) + ")")
    return "\n".join(out) + "\n"


def load_store(d):
    d = Path(d)
    items = []
    if d.is_dir():
        for p in sorted(d.glob("*.md")):
            for ins in parse_blocks(p.read_text(encoding="utf-8", errors="replace")):
                ins["_path"] = p
                items.append(ins)
    return items


def stored_confidence(ins):
    c = BASE
    for e in ins["evidence"]:  # clamp as we go, so evidence past the cap isn't banked
        c = max(FLOOR, min(CAP, c + WEIGHT.get(e["kind"], 0.0)))
    if ins.get("source") == "inherited" and not any(e["kind"] == "confirm" for e in ins["evidence"]):
        c = min(c, IMPORT_CAP)
    return round(c, 2)


def last_seen(ins):
    ds = [e["date"] for e in ins["evidence"] if e.get("date")] + ([ins["last_seen"]] if ins.get("last_seen") else [])
    try:
        return max(dt.date.fromisoformat(x) for x in ds) if ds else None
    except ValueError:
        return None


def effective(ins):
    c = stored_confidence(ins)
    ls = last_seen(ins)
    if ls:
        c -= DECAY_PER_30D * max(0, (TODAY - ls).days // 30)
    return round(max(FLOOR, c), 2)


def band(c):
    return next(name for lo, name in BANDS if c >= lo)


def words(s):
    return set(re.findall(r"[a-z0-9]{3,}", s.lower())) - {"when", "the", "and", "with", "for", "you", "your", "before", "after", "run"}


def jacc(a, b):
    a, b = words(a), words(b)
    return len(a & b) / len(a | b) if a and b else 0.0


NEG_RE = re.compile(r"\b(never|don'?t|do not|avoid|no longer|stop)\b", re.I)


def lint_items(items):
    fs = []

    def add(sev, iid, msg):
        fs.append({"severity": sev, "id": iid, "msg": msg})
    seen = {}
    for ins in items:
        iid = ins["id"] or "?"
        raw = render(ins)
        if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", ins["id"]):
            add("error", iid, "id must be kebab-case")
        if ins.get("_path") and ins["_path"].stem != ins["id"]:
            add("warn", iid, f"file name {ins['_path'].name} doesn't match id")
        if iid in seen:
            add("error", iid, "duplicate id")
        seen[iid] = ins
        if not ins["trigger"]:
            add("error", iid, "no trigger")
        elif not ins["trigger"].lower().startswith(("when ", "before ", "after ", "if ", "while ")):
            add("warn", iid, "trigger should start with when/before/after/if: name the situation")
        if not ins["action"]:
            add("error", iid, "no action")
        else:
            nsent = len([s for s in re.split(r"(?<=[.!?])\s+", ins["action"]) if s.strip()])
            if nsent > 2 or len(ins["action"].split()) > 40:
                add("warn", iid, "action is not atomic (over 2 sentences or 40 words); split it")
            if re.search(r"\b(also|additionally)\b", ins["action"], re.I):
                add("warn", iid, "action says 'also': probably two instincts")
        if not ins["evidence"]:
            add("error", iid, "no evidence: an instinct must come from something observed")
        if not 0.0 <= ins["confidence"] <= 1.0:
            add("error", iid, "confidence must be between 0 and 1")
        elif abs(ins["confidence"] - stored_confidence(ins)) > 0.011:
            add("warn", iid, f"confidence {ins['confidence']:.2f} doesn't match evidence ({stored_confidence(ins):.2f}); run status --write")
        if ins["scope"] not in ("project", "global"):
            add("error", iid, "scope must be project or global")
        if ins["domain"] not in DOMAINS:
            add("info", iid, f"domain '{ins['domain']}' not in the usual set")
        if SECRET_RE.search(raw):
            add("error", iid, "looks like a secret in the file; remove it")
        if EMAIL_RE.search(raw):
            add("warn", iid, "email address in the file; instincts should hold patterns, not personal data")
        if INJECT_RE.search(raw):
            add("error", iid, "text reads like an instruction injection or a dangerous command")
        if HIDDEN_RE.search(raw):
            add("error", iid, "hidden or bidi Unicode characters")
    ids = list(seen.values())
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            t = jacc(a["trigger"], b["trigger"])
            if t >= 0.5:
                if bool(NEG_RE.search(a["action"])) != bool(NEG_RE.search(b["action"])) and jacc(a["action"], b["action"]) >= 0.3:
                    add("warn", a["id"], f"may conflict with {b['id']} (same situation, opposite action)")
                elif jacc(a["action"], b["action"]) >= 0.6:
                    add("warn", a["id"], f"near-duplicate of {b['id']}; merge them")
    return fs


# ---------------------------------------------------------------- commands

def find_sessions(a):
    if a.sessions:
        return [Path(s).expanduser() for s in a.sessions]
    pdir = project_dir(a.project)
    found = sorted(pdir.glob("*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True) if pdir.is_dir() else []
    if not found:
        sys.exit(f"No transcripts in {pdir}. Pass .jsonl paths or --project.")
    return found[: a.latest]


def cmd_mine(a):
    paths = find_sessions(a)
    cands = mine(paths, snippets=not a.no_snippets, min_sessions=a.min_sessions)
    have = load_store(store_dir(a))
    for c in cands:
        sig = c.get("signal") or f"{c.get('failed', '')} {c.get('worked', '')}"
        best = max(have, key=lambda i: jacc(sig, i["trigger"] + " " + i["action"]), default=None)
        if best and jacc(sig, best["trigger"] + " " + best["action"]) >= 0.35:
            c["matches"] = best["id"]
    if a.json:
        print(json.dumps({"sessions": len(paths), "candidates": cands}, indent=2))
        return 0
    print(f"{len(paths)} session(s), {len(cands)} candidate(s). Candidates are leads, not instincts: "
          "keep the ones that are a real, reusable preference.\n")
    for n, c in enumerate(cands, 1):
        m = f"  [matches {c['matches']}: observe it instead]" if c.get("matches") else ""
        if c["kind"] == "fix":
            print(f"{n:>3}. fix      {c['session']}:{c['line']}  `{c.get('failed', '?')}`" + (f" -> {c.get('error')}" if c.get("error") else ""))
            print(f"               then worked: `{c.get('worked', '?')}`{m}")
        else:
            ctx = f"  (after {', '.join(c['context'])})" if c.get("context") else ""
            print(f"{n:>3}. {c['kind']:<10} x{c['count']}  {c['signal']}{ctx}{m}")
            print(f"               at {', '.join(c['where'])}")
    return 0


def write(ins, d):
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{ins['id']}.md"
    ins["confidence"] = stored_confidence(ins)
    ls = last_seen(ins)
    ins["last_seen"] = ls.isoformat() if ls else ""
    p.write_text(render(ins), encoding="utf-8")
    return p


def get(d, iid):
    for ins in load_store(d):
        if ins["id"] == iid:
            return ins
    sys.exit(f"no instinct '{iid}' in {d}")


def cmd_new(a):
    d = store_dir(a)
    if (d / f"{a.id}.md").exists():
        sys.exit(f"{a.id} exists; use `observe {a.id} ...` to add evidence")
    ev = []
    for e in a.evidence:
        m = re.match(r"^\s*([a-z]+):\s*(.*)$", e)
        kind, note = (m.group(1), m.group(2)) if m and m.group(1) in WEIGHT else ("correction", e)
        ev.append({"date": TODAY.isoformat(), "kind": kind, "note": redact(note)})
    ins = {"id": a.id, "trigger": a.trigger, "action": a.action, "domain": a.domain, "source": "session-observation",
           "scope": "global" if a.global_ else a.scope, "project_name": a.project_name or ("" if a.global_ else Path.cwd().name),
           "title": a.title or "", "evidence": ev, "last_seen": "", "confidence": BASE}
    fs = [f for f in lint_items([ins]) if f["severity"] == "error"]
    if fs:
        for f in fs:
            print(f"ERROR {f['id']}: {f['msg']}", file=sys.stderr)
        return 1
    p = write(ins, d)
    print(f"wrote {p} (confidence {ins['confidence']:.2f}, {band(effective(ins))})")
    return 0


def cmd_observe(a):
    d = store_dir(a)
    ins = get(d, a.id)
    before = effective(ins)
    ins["evidence"].append({"date": TODAY.isoformat(), "kind": a.kind, "note": redact(a.note or "")})
    p = write(ins, d)
    print(f"{a.id}: {before:.2f} -> {effective(ins):.2f} ({band(effective(ins))})  [{p}]")
    return 0


def cmd_status(a):
    d = store_dir(a)
    items = load_store(d)
    rows = []
    for ins in items:
        e = effective(ins)
        rows.append({"id": ins["id"], "effective": e, "stored": ins["confidence"], "band": band(e), "scope": ins["scope"],
                     "domain": ins["domain"], "last_seen": (last_seen(ins) or "").__str__(), "trigger": ins["trigger"],
                     "evidence": len(ins["evidence"])})
        if a.write and abs(ins["confidence"] - stored_confidence(ins)) > 0.001:
            write(ins, d)
    rows.sort(key=lambda r: -r["effective"])
    if a.json:
        print(json.dumps(rows, indent=2))
        return 0
    if not rows:
        print(f"no instincts in {d}")
        return 0
    print(f"{len(rows)} instinct(s) in {d}")
    for r in rows:
        bar = "#" * int(round(r["effective"] * 10))
        print(f"  {r['effective']:.2f} {bar:<9} {r['band']:<19} {r['id']:<34} {short(r['trigger'], 50)}")
    return 0


def cmd_lint(a):
    items = load_store(store_dir(a)) if not a.file else parse_blocks(Path(a.file).read_text(encoding="utf-8", errors="replace"))
    fs = lint_items(items)
    errs = sum(f["severity"] == "error" for f in fs)
    if a.json:
        print(json.dumps({"instincts": len(items), "findings": fs}, indent=2))
    else:
        for f in fs:
            print(f"{f['severity'].upper():5} {f['id']}: {f['msg']}")
        print(f"{len(items)} instinct(s), {errs} error(s), {sum(f['severity'] == 'warn' for f in fs)} warning(s)")
    return 1 if errs else 0


HOOK_HINTS = [
    (re.compile(r"\bbefore (a |each |every )?(git )?commit", re.I), "PreToolUse", "Bash", r"git commit"),
    (re.compile(r"\bbefore (a |each |every )?(git )?push", re.I), "PreToolUse", "Bash", r"git push"),
    (re.compile(r"\bafter (editing|each edit|changing|writing)", re.I), "PostToolUse", "Edit|Write|MultiEdit", None),
]


def cmd_evolve(a):
    d = store_dir(a)
    items = [i for i in load_store(d) if not [f for f in lint_items([i]) if f["severity"] == "error"]]
    out = Path(a.out or d / "evolved")
    out.mkdir(parents=True, exist_ok=True)
    rules = [i for i in items if effective(i) >= 0.8]
    lines = ["# Learned instincts", "", f"<!-- generated by instincts.py evolve on {TODAY}; review before importing into CLAUDE.md -->", ""]
    lines += [f"- {i['trigger'][0].upper() + i['trigger'][1:]}: {i['action']} <!-- {i['id']} {effective(i):.2f} -->" for i in rules]
    (out / "CLAUDE.instincts.md").write_text("\n".join(lines) + "\n")
    hooks = []
    for i in items:
        if effective(i) < 0.7:
            continue
        cmd = re.search(r"`([^`]+)`", i["action"])
        for rx, event, matcher, gate in HOOK_HINTS:
            if rx.search(i["trigger"]) and cmd:
                hooks.append({"instinct": i["id"], "event": event, "matcher": matcher, "only_when_command_matches": gate,
                              "run": cmd.group(1), "note": "suggestion only; nothing installed"})
    (out / "hook-suggestions.json").write_text(json.dumps(hooks, indent=2) + "\n")
    by = defaultdict(list)
    for i in items:
        if effective(i) >= 0.5:
            by[i["domain"]].append(i)
    drafts = []
    for dom, group in sorted(by.items()):
        avg = sum(effective(i) for i in group) / len(group)
        if len(group) >= 3 and avg >= 0.7:
            name = f"{dom}-habits"
            sd = out / "skills" / name
            sd.mkdir(parents=True, exist_ok=True)
            body = [f"---", f"name: {name}", f"description: Learned {dom} habits for this project ({len(group)} instincts, "
                    f"avg confidence {avg:.2f}). Use when doing {dom} work here.", "---", "", f"# {dom} habits", "",
                    "Generated from instincts; edit before installing.", ""]
            body += [f"- **{i['trigger']}**: {i['action']}" for i in sorted(group, key=lambda i: -effective(i))]
            (sd / "SKILL.md").write_text("\n".join(body) + "\n")
            drafts.append(str(sd / "SKILL.md"))
    print(f"{len(rules)} rule(s) -> {out / 'CLAUDE.instincts.md'}")
    print(f"{len(hooks)} hook suggestion(s) -> {out / 'hook-suggestions.json'}")
    print(f"{len(drafts)} skill draft(s)" + ("".join(f"\n  {x}" for x in drafts)))
    print("Nothing was installed. Review the files, then add `@.claude/instincts/evolved/CLAUDE.instincts.md` "
          "to CLAUDE.md or copy the lines you want.")
    return 0


def cmd_promote(a):
    stores = [Path(s) for s in a.stores]
    by = defaultdict(list)
    for s in stores:
        for i in load_store(s):
            if i["scope"] == "project":
                by[i["id"]].append((s, i))
    g = Path(os.environ.get("TOP30_INSTINCTS_GLOBAL") or a.to or Path.home() / ".local/share/top30-instincts")
    done = 0
    for iid, entries in sorted(by.items()):
        if len({s for s, _ in entries}) < PROMOTE_STORES:
            continue
        avg = sum(effective(i) for _, i in entries) / len(entries)
        if avg < PROMOTE_MIN:
            continue
        base = max((i for _, i in entries), key=effective)
        merged = dict(base, scope="global", project_name="", evidence=[e for _, i in entries for e in i["evidence"]])
        merged["evidence"].append({"date": TODAY.isoformat(), "kind": "note",
                                   "note": f"promoted from {len(entries)} projects (avg {avg:.2f})"})
        print(f"{'would promote' if a.dry_run else 'promoted'} {iid}  ({len(entries)} projects, avg {avg:.2f})")
        if not a.dry_run:
            write(merged, g)
        done += 1
    if not done:
        print(f"nothing qualifies (needs the same id in {PROMOTE_STORES}+ stores, avg >= {PROMOTE_MIN})")
    return 0


def cmd_export(a):
    items = [i for i in load_store(store_dir(a)) if effective(i) >= a.min]
    items = [i for i in items if not [f for f in lint_items([i]) if f["severity"] == "error"]]
    text = "".join(render(dict(i, confidence=effective(i)), evidence=False) + "\n" for i in items)
    if a.out:
        Path(a.out).write_text(text)
        print(f"exported {len(items)} instinct(s) to {a.out} (evidence reduced to counts)")
    else:
        sys.stdout.write(text)
    return 0


def cmd_import(a):
    d = store_dir(a)
    items = parse_blocks(Path(a.file).read_text(encoding="utf-8", errors="replace"))
    have = {i["id"] for i in load_store(d)}
    added = skipped = 0
    for i in items:
        bad = [f for f in lint_items([dict(i, evidence=i["evidence"] or [{"date": None, "kind": "note", "note": "x"}])])
               if f["severity"] == "error" and "confidence" not in f["msg"]]
        try:
            claimed = float(i["raw_fm"].get("confidence", BASE))
        except ValueError:
            claimed = BASE
        if bad or claimed < a.min or i["id"] in have:
            why = bad[0]["msg"] if bad else ("already in store" if i["id"] in have else f"confidence {claimed:.2f} < {a.min}")
            print(f"skip {i['id'] or '?'}: {why}")
            skipped += 1
            continue
        i.update(source="inherited", scope="global" if a.global_ else "project",
                 evidence=[{"date": TODAY.isoformat(), "kind": "imported", "note": f"from {Path(a.file).name}, claimed {claimed:.2f}"}])
        write(i, d)
        added += 1
    print(f"imported {added}, skipped {skipped}. Imported instincts start at {BASE:.2f} and stay at or "
          f"below {IMPORT_CAP:.2f} until you `observe <id> confirm`.")
    return 0


def cmd_prune(a):
    d = store_dir(a)
    moved = 0
    for i in load_store(d):
        if effective(i) < 0.3:
            print(f"{'would archive' if a.dry_run else 'archived'} {i['id']} ({effective(i):.2f})")
            if not a.dry_run:
                (d / "archive").mkdir(exist_ok=True)
                shutil.move(str(i["_path"]), str(d / "archive" / i["_path"].name))
            moved += 1
    if not moved:
        print("nothing dormant")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", default=".claude/instincts")
    common.add_argument("--global", dest="global_", action="store_true", help="use the global store")
    sub = ap.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("mine", parents=[common])
    m.add_argument("sessions", nargs="*")
    m.add_argument("--project")
    m.add_argument("--latest", type=int, default=10)
    m.add_argument("--min-sessions", type=int, default=3)
    m.add_argument("--no-snippets", action="store_true")
    m.add_argument("--json", action="store_true")
    n = sub.add_parser("new", parents=[common])
    n.add_argument("id")
    n.add_argument("--trigger", required=True)
    n.add_argument("--action", required=True)
    n.add_argument("--domain", default="workflow")
    n.add_argument("--scope", default="project", choices=["project", "global"])
    n.add_argument("--title")
    n.add_argument("--project-name")
    n.add_argument("--evidence", action="append", required=True, help="'kind: note', kind in correction|repeat|fix|confirm")
    o = sub.add_parser("observe", parents=[common])
    o.add_argument("id")
    o.add_argument("kind", choices=sorted(k for k in WEIGHT if k != "imported"))
    o.add_argument("--note", default="")
    s = sub.add_parser("status", parents=[common])
    s.add_argument("--write", action="store_true")
    s.add_argument("--json", action="store_true")
    li = sub.add_parser("lint", parents=[common])
    li.add_argument("file", nargs="?")
    li.add_argument("--json", action="store_true")
    e = sub.add_parser("evolve", parents=[common])
    e.add_argument("-o", "--out")
    p = sub.add_parser("promote", parents=[common])
    p.add_argument("--stores", nargs="+", required=True)
    p.add_argument("--to")
    p.add_argument("--dry-run", action="store_true")
    x = sub.add_parser("export", parents=[common])
    x.add_argument("-o", "--out")
    x.add_argument("--min", type=float, default=0.5)
    im = sub.add_parser("import", parents=[common])
    im.add_argument("file")
    im.add_argument("--min", type=float, default=0.3)
    pr = sub.add_parser("prune", parents=[common])
    pr.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    return {"mine": cmd_mine, "new": cmd_new, "observe": cmd_observe, "status": cmd_status, "lint": cmd_lint,
            "evolve": cmd_evolve, "promote": cmd_promote, "export": cmd_export, "import": cmd_import,
            "prune": cmd_prune}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
