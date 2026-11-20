#!/usr/bin/env python3
"""Your own "Claude Duet": a chief-of-staff folder for Claude Code, and the checks that keep
it honest.

  cos_kit.py init <dir> [--name "..."] [--role "..."]       # create the folder; never overwrites
  cos_kit.py audit <dir> [--json]                          # do the permissions keep the three levels?
  cos_kit.py promises <dir> [--days 3] [--json]            # overdue and due-soon promises
  cos_kit.py stale <dir> [--days 30] [--json]              # notes not confirmed lately
  cos_kit.py checks <dir>                                  # promises + stale, for briefs/checks.txt
  cos_kit.py schedule <dir> [--os mac|linux|windows] [--brief 07:00] [--review 16:00] [--write]

Standard library only. Reads and writes only inside <dir> (and, with schedule --write, the
launchd plist files inside <dir>/schedule/). It never installs a schedule, connects to mail
or calendar, or sends anything: it prints the command for you to run.
"""
import argparse
import json
import os
import platform
import re
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

HERE = Path(__file__).resolve().parent
TEMPLATES = HERE.parent / "templates"
DIRS = ["memory/people", "memory/projects", "inbox", "briefs", ".claude/commands", ".claude/agents", ".claude/bin"]

PROMISE = re.compile(
    r"^\s*[-*]\s*\[(?P<done>[ xX])\]\s*(?P<what>.+?)\s*[—–-]+\s*due\s+(?P<due>\d{4}-\d{2}-\d{2}|\?)"
    r"(?:\s*\(promised\s+(?P<promised>\d{4}-\d{2}-\d{2})\))?")
LOOSE_PROMISE = re.compile(r"\b(I'?ll send|I will send|I'?ll get back|let'?s do|by (monday|tuesday|wednesday|"
                           r"thursday|friday|saturday|sunday|tomorrow|end of (the )?(day|week|month)))\b", re.I)
CONFIRMED = re.compile(r"^Last confirmed:\s*(\d{4}-\d{2}-\d{2})", re.M)
UNCONFIRMED = re.compile(r"\bUNCONFIRMED\b")

# Tool-name words that mean the agent acts in your name, spends or destroys.
OUTBOUND = re.compile(r"(send|reply|forward|post|publish|draft_and_send|create_event|update_event|"
                      r"delete_event|move_event|respond|rsvp|accept|decline|invite|share)", re.I)
NEVER = re.compile(r"(pay|payment|charge|transfer|purchase|buy|checkout|refund|invoice_send|"
                   r"delete|remove|trash|purge|drop|destroy)", re.I)


def today():
    override = os.environ.get("COS_TODAY")  # for tests
    return date.fromisoformat(override) if override else date.today()


def need_dir(d):
    p = Path(d).expanduser()
    if not p.is_dir():
        sys.exit(f"{p} is not a folder. Create it with: cos_kit.py init {d}")
    return p


# ---------------------------------------------------------------- init

def cmd_init(a):
    root = Path(a.dir).expanduser()
    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)
    created, kept = [], []
    for src in sorted(TEMPLATES.rglob("*")):
        if src.is_dir():
            continue
        rel = src.relative_to(TEMPLATES)
        dst = root / rel
        if dst.exists():
            kept.append(str(rel))
            continue
        text = src.read_text()
        text = text.replace("{{NAME}}", a.name or "[your name]").replace("{{ROLE}}", a.role or "[one line]")
        if rel.name == "cos-checker.md":
            text = text.replace("${CLAUDE_PLUGIN_ROOT}/skills/duet-chief-of-staff/scripts/cos_kit.py",
                                ".claude/bin/cos_kit.py")
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(text)
        created.append(str(rel))
    bin_dst = root / ".claude/bin/cos_kit.py"
    if not bin_dst.exists():
        shutil.copy2(Path(__file__).resolve(), bin_dst)
        created.append(".claude/bin/cos_kit.py")
    gi = root / ".gitignore"
    if not gi.exists():
        gi.write_text(".env\n.env.*\nbriefs/cron.log\n.claude/settings.local.json\n")
        created.append(".gitignore")
    print(f"Chief-of-staff folder: {root}")
    for c in created:
        print(f"  created {c}")
    for k in kept:
        print(f"  kept    {k} (already there)")
    print("\nNext:\n  1. Fill CLAUDE.md (or run claude there and paste the interview prompt from the skill).\n"
          "  2. Run /morning-brief by hand for a week before scheduling it.\n"
          f"  3. cos_kit.py audit {a.dir}  after every change to permissions or connectors.")


# ---------------------------------------------------------------- audit

def load_settings(root):
    out = []
    for name in ("settings.json", "settings.local.json"):
        p = root / ".claude" / name
        if p.exists():
            try:
                out.append((name, json.loads(p.read_text())))
            except json.JSONDecodeError as e:
                out.append((name, {"__error__": str(e)}))
    return out


def folder_trusted(root):
    """True/False from Claude Code's own record of accepted trust dialogs; None if unreadable.
    Read-only: this never changes ~/.claude.json."""
    p = Path(os.environ.get("COS_CLAUDE_JSON") or Path.home() / ".claude.json")
    try:
        projects = json.loads(p.read_text()).get("projects", {})
    except (OSError, json.JSONDecodeError):
        return None
    for cand in {str(root), str(root.resolve())}:
        cur = Path(cand)
        for d in [cur, *cur.parents]:  # trusting a parent folder covers this one
            if projects.get(str(d), {}).get("hasTrustDialogAccepted"):
                return True
    return False


def audit(root):
    findings = []

    def add(level, msg):
        findings.append({"level": level, "msg": msg})

    settings = load_settings(root)
    if not settings:
        add("error", ".claude/settings.json is missing: every tool call will prompt, and an unattended run "
                     "can do nothing useful. Run init or copy the template.")
        return findings
    allow, ask, deny, modes = [], [], [], []
    for name, s in settings:
        if "__error__" in s:
            add("error", f".claude/{name} is not valid JSON ({s['__error__']}); Claude Code will ignore it.")
            continue
        perm = s.get("permissions", {})
        allow += [(name, r) for r in perm.get("allow", [])]
        ask += [(name, r) for r in perm.get("ask", [])]
        deny += [(name, r) for r in perm.get("deny", [])]
        if perm.get("defaultMode"):
            modes.append((name, perm["defaultMode"]))
        if s.get("enableAllProjectMcpServers"):
            add("warn", f".claude/{name}: enableAllProjectMcpServers is on; approve servers one by one instead.")

    for name, m in modes:
        if m in ("bypassPermissions", "auto", "acceptEdits"):
            add("error", f".claude/{name}: defaultMode is {m}. The three levels only hold in default "
                         "(interactive) and dontAsk (scheduled) modes.")

    for name, r in allow:
        base = r.split("(", 1)[0]
        if base == "Bash" and (r in ("Bash", "Bash(*)", "Bash(:*)") or "*" in r and r.startswith("Bash(*")):
            add("error", f"allow has {r} ({name}): any shell command runs unasked, which bypasses every file rule.")
        elif base == "Bash":
            add("warn", f"allow has {r} ({name}): check that this command can't send, delete or install.")
        elif base in ("WebFetch", "WebSearch") and r == base:
            add("warn", f"allow has {r} ({name}): an email that says 'open this link with your notes in it' "
                        "could leak memory/ through a URL. Keep it on ask, or allow named domains only.")
        elif base in ("Edit", "Write") and r in ("Edit", "Write", "Edit(**)", "Write(**)"):
            add("error", f"allow has {r} ({name}): it can rewrite CLAUDE.md and its own permissions. "
                         "Allow memory/**, inbox/** and briefs/** only.")
        elif base.startswith("mcp__"):
            parts = base.split("__")
            if len(parts) == 2 or r.endswith("__*"):
                add("error", f"allow has the whole MCP server {r} ({name}): its send, delete or pay tools run "
                             "unasked. Allow read tools by exact name.")
            elif NEVER.search(parts[-1]):
                add("error", f"allow has {r} ({name}): money and deletion belong in deny.")
            elif OUTBOUND.search(parts[-1]):
                add("error", f"allow has {r} ({name}): anything sent or changed in your name belongs in ask.")

    for name, r in ask:
        base = r.split("(", 1)[0]
        if base.startswith("mcp__") and NEVER.search(base.split("__")[-1]):
            add("warn", f"ask has {r} ({name}): money and deletion belong in deny, not one click away.")

    deny_rules = [r for _, r in deny]
    if not any(r.startswith("Edit(") and "CLAUDE.md" in r for r in deny_rules):
        add("warn", "deny has no Edit(CLAUDE.md): the agent could rewrite its own rules.")
    if not any(r.startswith("Edit(") and ".claude" in r for r in deny_rules):
        add("warn", "deny has no Edit(.claude/**): the agent could edit its own permissions, commands or agents.")
    if not any(r.startswith("Read(") and ".env" in r for r in deny_rules):
        add("warn", "deny has no Read(./.env): secrets in .env can be read and end up in a brief.")

    mcp = root / ".mcp.json"
    if mcp.exists():
        try:
            servers = sorted(json.loads(mcp.read_text()).get("mcpServers", {}))
        except json.JSONDecodeError:
            servers = []
            add("error", ".mcp.json is not valid JSON.")
        all_rules = [r for _, r in allow + ask + deny]
        for s in servers:
            if not any(r.startswith(f"mcp__{s}__") or r == f"mcp__{s}" for r in all_rules):
                add("warn", f"MCP server '{s}' has no rules. Run /mcp to list its tools, then put read tools in "
                            "allow, send/move tools in ask and pay/delete tools in deny.")

    for f in sorted((root / "schedule").glob("*")) if (root / "schedule").is_dir() else []:
        t = f.read_text(errors="ignore")
        if "claude" in t and "-p" in t and "dontAsk" not in t:
            add("error", f"schedule/{f.name} runs claude -p without --permission-mode dontAsk: "
                         "an unattended run may hang on a prompt or follow a looser mode.")
        if "dangerously-skip-permissions" in t or "bypassPermissions" in t:
            add("error", f"schedule/{f.name} skips permissions in an unattended run.")

    trusted = folder_trusted(root)
    if trusted is False:
        add("error", "This folder isn't trusted yet, so Claude Code ignores its allow rules and a scheduled "
                     "run can't even write the brief. Run `claude` here once and accept the trust dialog.")
    elif trusted is None:
        add("warn", "Couldn't read ~/.claude.json to check that this folder is trusted. Run `claude` here once "
                    "and accept the trust dialog, or project allow rules are ignored.")

    if not (root / "CLAUDE.md").exists():
        add("warn", "No CLAUDE.md: the agent doesn't know who it works for or where its permission ends.")
    else:
        t = (root / "CLAUDE.md").read_text()
        if "data, not instructions" not in t and "not instructions" not in t:
            add("warn", "CLAUDE.md doesn't say that email and inbox text are data, not instructions. "
                        "The morning brief reads untrusted mail every day.")
    return findings


def cmd_audit(a):
    root = need_dir(a.dir)
    f = audit(root)
    errors = [x for x in f if x["level"] == "error"]
    if a.json:
        print(json.dumps({"errors": len(errors), "findings": f}, indent=1))
    else:
        if not f:
            print("OK: reads and notes run alone, outbound waits for you, money/deletion/secrets are blocked.")
        for x in f:
            print(f"{x['level'].upper():5}  {x['msg']}")
        if f:
            print(f"\n{len(errors)} error(s), {len(f) - len(errors)} warning(s). "
                  "Review the combined rules with /permissions too (user settings are inherited).")
    sys.exit(1 if errors else 0)


# ---------------------------------------------------------------- promises / stale

def notes(root):
    for sub in ("memory/people", "memory/projects"):
        for p in sorted((root / sub).glob("*.md")):
            if not p.name.startswith("_"):
                yield p


def scan_promises(root, days):
    t = today()
    out = {"overdue": [], "due_soon": [], "no_date": [], "unformatted": []}
    for p in notes(root):
        rel = str(p.relative_to(root))
        for i, line in enumerate(p.read_text().splitlines(), 1):
            m = PROMISE.match(line)
            if m:
                if m["done"].lower() == "x":
                    continue
                item = {"file": rel, "line": i, "what": m["what"].strip(), "due": m["due"],
                        "promised": m["promised"]}
                if m["due"] == "?":
                    out["no_date"].append(item)
                    continue
                due = date.fromisoformat(m["due"])
                item["days"] = (due - t).days
                if due < t:
                    out["overdue"].append(item)
                elif due <= t + timedelta(days=days):
                    out["due_soon"].append(item)
            elif LOOSE_PROMISE.search(line) and not line.lstrip().startswith("#"):
                out["unformatted"].append({"file": rel, "line": i, "what": line.strip()})
    out["overdue"].sort(key=lambda x: x["days"])
    out["due_soon"].sort(key=lambda x: x["days"])
    return out


def scan_stale(root, days):
    t = today()
    out = {"stale": [], "never_confirmed": [], "unconfirmed_marks": []}
    for p in notes(root):
        rel = str(p.relative_to(root))
        text = p.read_text()
        m = CONFIRMED.search(text)
        if not m:
            out["never_confirmed"].append({"file": rel})
        else:
            age = (t - date.fromisoformat(m[1])).days
            if age > days:
                out["stale"].append({"file": rel, "last_confirmed": m[1], "days": age})
        for i, line in enumerate(text.splitlines(), 1):
            if UNCONFIRMED.search(line):
                out["unconfirmed_marks"].append({"file": rel, "line": i, "text": line.strip()})
    out["stale"].sort(key=lambda x: -x["days"])
    return out


def print_promises(r, days):
    if r["overdue"]:
        print("Overdue promises:")
        for x in r["overdue"]:
            print(f"  {-x['days']}d late  {x['what']}  ({x['file']}:{x['line']})")
    if r["due_soon"]:
        print(f"Due in the next {days} days:")
        for x in r["due_soon"]:
            when = "today" if x["days"] == 0 else f"in {x['days']}d"
            print(f"  {when:>7}  {x['what']}  ({x['file']}:{x['line']})")
    if r["no_date"]:
        print("Promises with no date (ask for one):")
        for x in r["no_date"]:
            print(f"  {x['what']}  ({x['file']}:{x['line']})")
    if r["unformatted"]:
        print("Looks like a promise but isn't in the promise format:")
        for x in r["unformatted"]:
            print(f"  {x['what'][:100]}  ({x['file']}:{x['line']})")
    if not any(r.values()):
        print("No open promises overdue or due soon.")


def print_stale(r, days):
    if r["stale"]:
        print(f"Not confirmed in {days}+ days:")
        for x in r["stale"]:
            print(f"  {x['days']}d  {x['file']} (last confirmed {x['last_confirmed']})")
    if r["never_confirmed"]:
        print("No 'Last confirmed:' line:")
        for x in r["never_confirmed"]:
            print(f"  {x['file']}")
    if r["unconfirmed_marks"]:
        print("Marked UNCONFIRMED:")
        for x in r["unconfirmed_marks"]:
            print(f"  {x['text'][:100]}  ({x['file']}:{x['line']})")
    if not any(r.values()):
        print("All notes confirmed recently.")


def cmd_promises(a):
    r = scan_promises(need_dir(a.dir), a.days)
    print(json.dumps(r, indent=1)) if a.json else print_promises(r, a.days)


def cmd_stale(a):
    r = scan_stale(need_dir(a.dir), a.days)
    print(json.dumps(r, indent=1)) if a.json else print_stale(r, a.days)


def cmd_checks(a):
    root = need_dir(a.dir)
    print(f"# Checks for {today().isoformat()} (cos_kit.py, no model involved)\n")
    print_promises(scan_promises(root, 3), 3)
    print()
    print_stale(scan_stale(root, 30), 30)
    errs = [x for x in audit(root) if x["level"] == "error"]
    if errs:
        print("\nPermission errors (fix before trusting unattended runs):")
        for x in errs:
            print(f"  {x['msg']}")


# ---------------------------------------------------------------- schedule

def hhmm(s):
    m = re.fullmatch(r"(\d{1,2}):(\d{2})", s)
    if not m or int(m[1]) > 23 or int(m[2]) > 59:
        sys.exit(f"Time must be HH:MM, got {s!r}")
    return int(m[1]), int(m[2])


def plist(label, root, claude, py, command, weekdays, h, m):
    script = (f"cd {sh_quote(str(root))} && {sh_quote(py)} .claude/bin/cos_kit.py checks . > briefs/checks.txt; "
              f"{sh_quote(claude)} -p {sh_quote(command)} --permission-mode dontAsk >> briefs/cron.log 2>&1")
    cal = "\n".join(f"    <dict><key>Weekday</key><integer>{d}</integer><key>Hour</key><integer>{h}</integer>"
                    f"<key>Minute</key><integer>{m}</integer></dict>" for d in weekdays)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>/bin/zsh</string><string>-lc</string><string>{xml_escape(script)}</string></array>
  <key>StartCalendarInterval</key>
  <array>
{cal}
  </array>
  <key>StandardOutPath</key><string>{xml_escape(str(root / 'briefs/launchd.log'))}</string>
  <key>StandardErrorPath</key><string>{xml_escape(str(root / 'briefs/launchd.log'))}</string>
</dict>
</plist>
"""


def sh_quote(s):
    return s if re.fullmatch(r"[\w@%+=:,./-]+", s) else "'" + s.replace("'", "'\\''") + "'"


def xml_escape(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def cmd_schedule(a):
    root = need_dir(a.dir).resolve()
    osname = a.os or {"Darwin": "mac", "Windows": "windows"}.get(platform.system(), "linux")
    claude = a.claude or shutil.which("claude") or ("claude.exe" if osname == "windows" else None)
    if not claude:
        sys.exit("Couldn't find claude on PATH. Pass --claude /full/path/to/claude (run: command -v claude).")
    py = a.python or shutil.which("python3") or "python3"
    bh, bm = hhmm(a.brief)
    rh, rm = hhmm(a.review)
    print(f"Run each command by hand once first, from {root}, signed in as the same user:\n")
    print(f"  claude -p /morning-brief --permission-mode dontAsk\n")
    print("dontAsk means anything on your ask list is refused, not run; the brief lists it under "
          "'Waiting for you'. The computer must be awake (and on Windows, signed in) at that time.")
    if folder_trusted(root) is not True:
        print("Not trusted yet: run `claude` in this folder once and accept the trust dialog, or the "
              "folder's allow rules are ignored and the run can't write anything.")
    print("If briefs/cron.log shows an expired sign-in, the scheduled user needs to sign in again "
          "(`claude setup-token` makes a long-lived token for unattended use).\n")
    if osname == "mac":
        brief = plist("com.top30.cos.morning-brief", root, claude, py, "/morning-brief", range(1, 6), bh, bm)
        review = plist("com.top30.cos.weekly-review", root, claude, py, "/weekly-review", [5], rh, rm)
        if a.write:
            sd = root / "schedule"
            sd.mkdir(exist_ok=True)
            (sd / "com.top30.cos.morning-brief.plist").write_text(brief)
            (sd / "com.top30.cos.weekly-review.plist").write_text(review)
            print(f"Wrote schedule/com.top30.cos.morning-brief.plist and schedule/com.top30.cos.weekly-review.plist.")
        else:
            print(brief)
            print("(add --write to save both plists into schedule/)\n")
        print("Install them yourself (launchd runs a missed job when the Mac wakes; cron skips it):\n")
        for n in ("morning-brief", "weekly-review"):
            print(f"  cp {sh_quote(str(root / 'schedule' / f'com.top30.cos.{n}.plist'))} ~/Library/LaunchAgents/ && "
                  f"launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.top30.cos.{n}.plist")
        print("\nRemove with: launchctl bootout gui/$(id -u)/com.top30.cos.morning-brief")
    elif osname == "linux":
        pre = f"cd {sh_quote(str(root))} && {sh_quote(py)} .claude/bin/cos_kit.py checks . > briefs/checks.txt;"
        print("Add with crontab -e (full paths, because cron doesn't load your shell's PATH):\n")
        print(f"{bm} {bh} * * 1-5  {pre} {sh_quote(claude)} -p /morning-brief --permission-mode dontAsk >> briefs/cron.log 2>&1")
        print(f"{rm} {rh} * * 5    {pre} {sh_quote(claude)} -p /weekly-review --permission-mode dontAsk >> briefs/cron.log 2>&1")
        print("\nOn a laptop, cron skips runs while asleep; anacron or a systemd timer with Persistent=true catches up.")
    else:
        win = str(root).replace("/", "\\")
        for name, cmd, days, (h, m) in (("MorningBrief", "/morning-brief", "MON,TUE,WED,THU,FRI", (bh, bm)),
                                        ("WeeklyReview", "/weekly-review", "FRI", (rh, rm))):
            tr = (f'cmd /c "cd /d "{win}" && python .claude\\bin\\cos_kit.py checks . > briefs\\checks.txt & '
                  f'"{claude}" -p {cmd} --permission-mode dontAsk >> briefs\\cron.log 2>&1"')
            print(f'schtasks /create /tn "{name}" /sc weekly /d {days} /st {h:02d}:{m:02d} /tr {json.dumps(tr)}\n')
        print("schtasks runs only while you're signed in unless you add /ru and a password; test with "
              'schtasks /run /tn "MorningBrief".')


def main(argv=None):
    p = argparse.ArgumentParser(description="Chief-of-staff folder for Claude Code, with honest checks.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("init")
    s.add_argument("dir")
    s.add_argument("--name")
    s.add_argument("--role")
    s.set_defaults(fn=cmd_init)
    s = sub.add_parser("audit")
    s.add_argument("dir")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_audit)
    s = sub.add_parser("promises")
    s.add_argument("dir")
    s.add_argument("--days", type=int, default=3)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_promises)
    s = sub.add_parser("stale")
    s.add_argument("dir")
    s.add_argument("--days", type=int, default=30)
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_stale)
    s = sub.add_parser("checks")
    s.add_argument("dir")
    s.set_defaults(fn=cmd_checks)
    s = sub.add_parser("schedule")
    s.add_argument("dir")
    s.add_argument("--os", choices=["mac", "linux", "windows"])
    s.add_argument("--brief", default="07:00", help="weekday morning brief time")
    s.add_argument("--review", default="16:00", help="Friday weekly review time")
    s.add_argument("--claude", help="full path to claude")
    s.add_argument("--python", help="full path to python3")
    s.add_argument("--write", action="store_true", help="mac: save plists into <dir>/schedule/")
    s.set_defaults(fn=cmd_schedule)
    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
