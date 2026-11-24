#!/usr/bin/env python3
"""papercut: structured friction reports that an agent files when a skill, tool or doc misbehaves.

After the "papercut" loop Uber describes for its skills marketplace: the agent notices it is
struggling, files what it tried, expected, got and what would fix it, and the skill's owner sees
the reports grouped. This version keeps everything on this machine.

    papercut.py search "exit 0 on error" [--skill pr-create]
    papercut.py file --skill pr-create --tried "..." --expected "..." --got "..." [--fix "..."]
                     [--workaround "..."] [--tool gh] [--skill-version 1.2] [--severity medium]
    papercut.py show <id>
    papercut.py summary [--skill S] [--days 30] [--json]
    papercut.py export --skill S [--sig SIG] [--gh owner/repo]    # prints; never posts

Reports go to one JSON line each in $PAPERCUT_LOG, default ~/.claude/papercuts/papercuts.jsonl,
written with a single append so concurrent sessions don't interleave. Each field is collapsed to
one line, capped at 300 characters and scrubbed of keys, tokens, passwords, emails and your home
path. There is no field for prompt text or file contents. Python standard library only.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shlex
import subprocess
import sys
import uuid
from collections import defaultdict
from pathlib import Path

CAP = 300
FIELDS = ("tried", "expected", "got", "fix", "workaround")
SEVERITIES = ("low", "medium", "high")
SECRET_PATTERNS = [
    (re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?(-----END [A-Z ]*PRIVATE KEY-----|$)", re.S), "[PRIVATE KEY]"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[AWS KEY]"),
    (re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}\b"), "[GITHUB TOKEN]"),
    (re.compile(r"\bxox[abprs]-[A-Za-z0-9-]{10,}\b"), "[SLACK TOKEN]"),
    (re.compile(r"\bsk-(?:ant-)?[A-Za-z0-9_-]{20,}\b"), "[API KEY]"),
    (re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"), "[JWT]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]{12,}"), "Bearer [TOKEN]"),
    (re.compile(r"(?i)\b(api[_-]?key|access[_-]?key|secret|token|password|passwd|pwd)(\s*[=:]\s*)(\"[^\"]*\"|'[^']*'|\S+)"),
     r"\1\2[REDACTED]"),
    (re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@"), r"\1[CREDENTIALS]@"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "[EMAIL]"),
    (re.compile(r"\b[A-Fa-f0-9]{32,}\b"), "[HEX]"),
    (re.compile(r"\b[A-Za-z0-9+/]{40,}={0,2}"), "[BLOB]"),
]


def log_path():
    return Path(os.environ.get("PAPERCUT_LOG") or Path.home() / ".claude" / "papercuts" / "papercuts.jsonl")


def scrub(text):
    if text is None:
        return None
    s = str(text)
    for pat, rep in SECRET_PATTERNS:
        s = pat.sub(rep, s)
    home = str(Path.home())
    if home and home != "/":
        s = s.replace(home, "~")
    s = re.sub(r"\s+", " ", s).strip()
    return s[:CAP - 1] + "…" if len(s) > CAP else s


def signature(skill, tool, got):
    g = (got or "").lower()
    g = re.sub(r"\[[a-z ]+\]", "", g)
    g = re.sub(r"[0-9a-f]{6,}", "#", g)
    g = re.sub(r"\d+", "#", g)
    g = re.sub(r"[\"'`]", "", g)
    g = re.sub(r"\s+", " ", g).strip()
    return hashlib.sha1(f"{skill}|{tool or ''}|{g}".encode()).hexdigest()[:12]


def in_git_repo(path):
    d = path.parent
    while not d.exists() and d != d.parent:
        d = d.parent  # the nearest folder that exists decides, not the current directory
    try:
        out = subprocess.run(["git", "-C", str(d), "rev-parse", "--is-inside-work-tree"],
                             capture_output=True, text=True, timeout=5)
        return out.stdout.strip() == "true"
    except (OSError, subprocess.SubprocessError):
        return False


def read_all():
    p = log_path()
    if not p.exists():
        return []
    rows = []
    for ln in p.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            r = json.loads(ln)
            if isinstance(r, dict) and r.get("id"):
                rows.append(r)
        except json.JSONDecodeError:
            continue  # a torn or foreign line never breaks reading
    return rows


def append(record):
    p = log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    data = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        if p.stat().st_size:
            with open(p, "rb") as f:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    data = b"\n" + data  # a torn last line must not swallow this report
    except FileNotFoundError:
        pass
    fd = os.open(p, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    try:
        os.write(fd, data)  # one write per report: concurrent sessions can't interleave lines
    finally:
        os.close(fd)


def words(s):
    return {w for w in re.findall(r"[a-z0-9_.-]{3,}", (s or "").lower())}


def cmd_file(a):
    for f in ("tried", "expected", "got"):
        if not (getattr(a, f) or "").strip():
            sys.exit(f"--{f} is required: say what you {f if f != 'got' else 'actually got'}")
    p = log_path()
    if in_git_repo(p) and not os.environ.get("PAPERCUT_ALLOW_REPO"):
        sys.exit(f"{p} is inside a git repository; papercuts stay out of repos. Set PAPERCUT_LOG elsewhere "
                 "(or PAPERCUT_ALLOW_REPO=1 if that is deliberate).")
    rec = {"id": uuid.uuid4().hex[:8], "time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
           "skill": scrub(a.skill)[:80], "skill_version": scrub(a.skill_version), "tool": scrub(a.tool),
           "severity": a.severity, "agent": scrub(a.agent), "repo": scrub(a.repo)}
    for f in FIELDS:
        rec[f] = scrub(getattr(a, f))
    rec["sig"] = signature(rec["skill"], rec["tool"], rec["got"])
    same = [r for r in read_all() if r.get("sig") == rec["sig"]]
    append(rec)
    print(f"filed {rec['id']}  skill={rec['skill']}  sig={rec['sig']}  "
          f"({len(same)} earlier report{'s' if len(same) != 1 else ''} of the same problem)")
    if same and any(r.get("workaround") for r in same):
        w = next(r["workaround"] for r in reversed(same) if r.get("workaround"))
        print(f"earlier workaround: {w}")
    return 0


def cmd_search(a):
    q = words(a.query)
    hits = []
    for r in read_all():
        if a.skill and r.get("skill") != a.skill:
            continue
        text = " ".join(str(r.get(k) or "") for k in ("skill", "tool", "tried", "expected", "got", "fix", "workaround"))
        score = len(q & words(text))
        if score:
            hits.append((score, r))
    hits.sort(key=lambda x: (x[0], x[1].get("time", "")), reverse=True)  # best match, then newest
    if not hits:
        print("0 matches")
        return 0
    print(f"{len(hits)} match{'es' if len(hits) != 1 else ''}")
    for _, r in hits[:a.limit]:
        print(f"- {r['id']} [{r.get('skill')}] {r.get('time', '')[:10]} got: {r.get('got')}")
        if r.get("workaround"):
            print(f"    workaround: {r['workaround']}")
        if r.get("fix"):
            print(f"    suggested fix: {r['fix']}")
    return 0


def cmd_show(a):
    for r in read_all():
        if r["id"] == a.id:
            print(json.dumps(r, indent=1, ensure_ascii=False))
            return 0
    print(f"no papercut {a.id}", file=sys.stderr)
    return 1


def groups(rows):
    g = defaultdict(list)
    for r in rows:
        g[(r.get("skill"), r.get("sig"))].append(r)
    return g


def recent(rows, days):
    if not days:
        return rows
    cut = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)
    out = []
    for r in rows:
        try:
            if dt.datetime.fromisoformat(r["time"]) >= cut:
                out.append(r)
        except (KeyError, ValueError):
            continue
    return out


def cmd_summary(a):
    rows = recent([r for r in read_all() if not a.skill or r.get("skill") == a.skill], a.days)
    g = groups(rows)
    items = sorted(g.items(), key=lambda kv: (-len(kv[1]), kv[0][0] or ""))
    if a.json:
        print(json.dumps([{"skill": k[0], "sig": k[1], "count": len(v), "last": max(r["time"] for r in v),
                           "got": v[-1].get("got"), "fix": next((r["fix"] for r in reversed(v) if r.get("fix")), None),
                           "ids": [r["id"] for r in v]} for k, v in items], indent=1))
        return 0
    if not items:
        print("no papercuts" + (f" for {a.skill}" if a.skill else ""))
        return 0
    by_skill = defaultdict(list)
    for (skill, sig), v in items:
        by_skill[skill].append((sig, v))
    for skill in sorted(by_skill, key=lambda s: -sum(len(v) for _, v in by_skill[s])):
        n = sum(len(v) for _, v in by_skill[skill])
        print(f"\n{skill}: {n} report{'s' if n != 1 else ''}, {len(by_skill[skill])} distinct problem{'s' if len(by_skill[skill]) != 1 else ''}")
        for sig, v in by_skill[skill]:
            fix = next((r["fix"] for r in reversed(v) if r.get("fix")), None)
            print(f"  {len(v):>3}× {sig}  last {max(r['time'] for r in v)[:10]}  got: {v[-1].get('got')}")
            if fix:
                print(f"       fix: {fix}")
    return 0


def issue_body(skill, v):
    first, last = v[0], v[-1]
    lines = [f"Papercut on `{skill}`: reported {len(v)} time(s), {first['time'][:10]} to {last['time'][:10]}.", "",
             f"- **Tried:** {last.get('tried')}", f"- **Expected:** {last.get('expected')}", f"- **Got:** {last.get('got')}"]
    for key, label in (("fix", "Suggested fix"), ("workaround", "Workaround used")):
        val = next((r[key] for r in reversed(v) if r.get(key)), None)
        if val:
            lines.append(f"- **{label}:** {val}")
    vers = sorted({r.get("skill_version") for r in v if r.get("skill_version")})
    tools = sorted({r.get("tool") for r in v if r.get("tool")})
    if vers or tools:
        lines.append(f"- **Versions / tools:** {', '.join(vers) or '-'} / {', '.join(tools) or '-'}")
    lines += ["", f"Report ids: {', '.join(r['id'] for r in v)} (signature {last.get('sig')}). "
                  "Filed by an agent with the papercut skill; fields are scrubbed summaries, not transcripts."]
    return "\n".join(lines) + "\n"


def cmd_export(a):
    g = groups([r for r in read_all() if r.get("skill") == a.skill])
    if a.sig:
        g = {k: v for k, v in g.items() if k[1] == a.sig}
    if not g:
        print(f"no papercuts for {a.skill}" + (f" with signature {a.sig}" if a.sig else ""), file=sys.stderr)
        return 1
    (skill, sig), v = max(g.items(), key=lambda kv: len(kv[1]))
    body = issue_body(skill, v)
    title = f"papercut({skill}): {(v[-1].get('got') or '')[:70]}"
    if not a.gh:
        print(f"# {title}\n\n{body}")
        return 0
    out = Path(a.body_file) if a.body_file else log_path().parent / f"papercut-{sig}.md"  # beside the log, not in a repo
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(body, encoding="utf-8")
    # the title carries tool error text: quote everything for the shell, never json-quote
    cmd = shlex.join(["gh", "issue", "create", "--repo", a.gh, "--title", title, "--body-file", str(out)])
    print(f"Wrote {out}. This sends the report to GitHub; run it only if that's allowed for this repo:\n\n  {cmd}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("file", help="file one papercut")
    f.add_argument("--skill", required=True, help="the skill, tool or doc that misbehaved")
    f.add_argument("--tried", required=True)
    f.add_argument("--expected", required=True)
    f.add_argument("--got", required=True)
    f.add_argument("--fix", help="what would fix it for good")
    f.add_argument("--workaround", help="what got you past it this time")
    f.add_argument("--tool", help="the command or MCP tool involved, e.g. gh, snowsql")
    f.add_argument("--skill-version")
    f.add_argument("--severity", choices=SEVERITIES, default="medium")
    f.add_argument("--agent", default=os.environ.get("PAPERCUT_AGENT", "claude-code"))
    f.add_argument("--repo", help="repository name only, not a path")
    s = sub.add_parser("search", help="find earlier papercuts and their workarounds")
    s.add_argument("query")
    s.add_argument("--skill")
    s.add_argument("--limit", type=int, default=5)
    sh = sub.add_parser("show", help="print one papercut")
    sh.add_argument("id")
    su = sub.add_parser("summary", help="papercuts grouped by skill and problem")
    su.add_argument("--skill")
    su.add_argument("--days", type=int)
    su.add_argument("--json", action="store_true")
    ex = sub.add_parser("export", help="an issue for the most-reported problem of a skill (prints; never posts)")
    ex.add_argument("--skill", required=True)
    ex.add_argument("--sig")
    ex.add_argument("--gh", metavar="OWNER/REPO", help="write a body file and print the gh command to run")
    ex.add_argument("--body-file")
    a = ap.parse_args(argv)
    return {"file": cmd_file, "search": cmd_search, "show": cmd_show, "summary": cmd_summary,
            "export": cmd_export}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
