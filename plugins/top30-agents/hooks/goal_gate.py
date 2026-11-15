#!/usr/bin/env python3
"""goal_gate: a /goal whose finish line is a command's exit code, not a model's reading of the chat.

/goal asks a small model whether the transcript shows the condition is met. This gate runs the
check itself when Claude tries to stop, and sends Claude back to work (a Stop hook "block") with
the failing output until the command exits 0, the round limit is hit, or two rounds in a row
fail the same way.

Turn it on for a project (run in the project folder, or pass --project):
  goal_gate.py on --check "pytest -q" [--max-rounds 5] [--timeout 600] [--once]
  goal_gate.py status
  goal_gate.py off

As a Stop hook (the top30-agents plugin registers it; it does nothing until turned on):
  goal_gate.py hook      reads the hook JSON on stdin, prints a decision JSON on stdout

Settings live OUTSIDE the repo, in ~/.claude/goal-gate/ (or $GOAL_GATE_HOME), keyed by project
path. A cloned repository can't switch the gate on or choose the command it runs.
Standard library only.
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

TAIL = 40


def home():
    return Path(os.environ.get("GOAL_GATE_HOME") or Path.home() / ".claude" / "goal-gate")


def key(project):
    return hashlib.sha256(str(Path(project).resolve()).encode()).hexdigest()[:16]


def cfg_path(project):
    return home() / f"{key(project)}.json"


def find_config(start):
    """The gate for this folder or its nearest parent that has one."""
    p = Path(start).resolve()
    for d in [p, *p.parents]:
        c = cfg_path(d)
        if c.exists():
            try:
                return d, json.loads(c.read_text())
            except ValueError:
                return d, None
    return None, None


def save(project, cfg):
    home().mkdir(parents=True, exist_ok=True)
    tmp = cfg_path(project).with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, indent=1) + "\n")
    tmp.replace(cfg_path(project))


def tail(text, n=TAIL):
    lines = (text or "").strip().splitlines()
    return "\n".join(lines[-n:])


def fingerprint(text):
    t = re.sub(r"\b\d+(\.\d+)?\s*(s|ms|sec|seconds)\b|0x[0-9a-f]+|\b\d{4,}\b", "", text or "", flags=re.I)
    return hashlib.sha1(t.strip().encode()).hexdigest()[:12]


def emit(obj):
    print(json.dumps(obj))
    return 0


# ---------- the hook ----------
def hook(raw):
    try:
        data = json.loads(raw or "{}")
    except ValueError:
        return 0  # not our input; never block on a parse error
    if data.get("hook_event_name") not in (None, "Stop"):
        return 0
    start = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd") or os.getcwd()
    project, cfg = find_config(start)
    if not cfg or not cfg.get("enabled"):
        return 0
    session = str(data.get("session_id") or "nosession")
    st = cfg.setdefault("sessions", {}).setdefault(session, {"rounds": 0, "last": None, "same": 0})
    t0 = time.time()
    try:
        p = subprocess.run(cfg["check"], shell=True, cwd=str(project), capture_output=True, text=True,
                           timeout=int(cfg.get("timeout", 600)))
        rc, out = p.returncode, (p.stdout + p.stderr)
    except subprocess.TimeoutExpired:
        rc, out = 124, f"check timed out after {cfg.get('timeout', 600)}s"
    secs = time.time() - t0
    if rc == 0:
        cfg["sessions"].pop(session, None)
        cfg["passes"] = cfg.get("passes", 0) + 1
        msg = f"goal gate: `{cfg['check']}` passed ({secs:.0f}s)."
        if cfg.get("once"):
            cfg["enabled"] = False
            msg += " Gate turned off (--once)."
        save(project, cfg)
        return emit({"systemMessage": msg})
    fp = fingerprint(out)
    st["same"] = st["same"] + 1 if fp == st.get("last") else 0
    st["last"] = fp
    st["rounds"] += 1
    limit = int(cfg.get("max_rounds", 5))
    if st["rounds"] > limit or st["same"] >= 2:
        why = (f"{limit} rounds" if st["rounds"] > limit else "three rounds in a row with the same failure")
        cfg["sessions"].pop(session, None)
        save(project, cfg)
        return emit({"systemMessage": f"goal gate: letting Claude stop after {why}; `{cfg['check']}` still fails "
                                      f"(exit {rc}). The plan probably needs a person: check the split, the scope or the check."})
    save(project, cfg)
    return emit({"decision": "block", "reason": (
        f"Not done: the goal gate ran `{cfg['check']}` and it exited {rc} (round {st['rounds']} of {limit}). "
        f"Fix the cause, then run that exact command yourself and show its result before finishing. "
        f"Don't weaken, skip or delete checks to make it pass.\n\nLast {TAIL} lines:\n{tail(out)}")})


# ---------- the CLI ----------
def cmd_on(a):
    project = Path(a.project).resolve()
    if not project.is_dir():
        sys.exit(f"not a folder: {project}")
    cfg = {"enabled": True, "project": str(project), "check": a.check, "max_rounds": a.max_rounds,
           "timeout": a.timeout, "once": a.once, "sessions": {}, "passes": 0}
    save(project, cfg)
    print(f"goal gate ON for {project}\n  check: {a.check}\n  up to {a.max_rounds} rounds per session"
          + (", then turns itself off after the first pass" if a.once else ""))
    print("Needs the top30-agents plugin enabled (it registers the Stop hook), or the hook added to your settings.")


def cmd_off(a):
    project, cfg = find_config(a.project)
    if not cfg:
        print("goal gate: not set for this folder")
        return
    cfg["enabled"] = False
    cfg["sessions"] = {}
    save(project, cfg)
    print(f"goal gate OFF for {project}")


def cmd_status(a):
    project, cfg = find_config(a.project)
    if not cfg:
        print("goal gate: not set for this folder")
        return
    s = cfg.get("sessions", {})
    print(f"goal gate {'ON' if cfg.get('enabled') else 'OFF'} for {project}\n  check: {cfg.get('check')}\n"
          f"  max rounds: {cfg.get('max_rounds')}  once: {cfg.get('once')}  passes so far: {cfg.get('passes', 0)}\n"
          f"  sessions in progress: {len(s)}" + "".join(f"\n    {k[:8]}: round {v['rounds']}" for k, v in s.items()))


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "hook":
        try:
            return hook(sys.stdin.read())
        except Exception as e:  # a broken gate must never trap Claude in a loop
            return emit({"systemMessage": f"goal gate error, not blocking: {e}"})
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("on")
    p.add_argument("--check", required=True, help="command that exits 0 when the work is done")
    p.add_argument("--max-rounds", type=int, default=5)
    p.add_argument("--timeout", type=int, default=600, help="seconds the check may run")
    p.add_argument("--once", action="store_true", help="turn the gate off after the first pass")
    p.add_argument("--project", default=".")
    for name in ("off", "status"):
        sub.add_parser(name).add_argument("--project", default=".")
    a = ap.parse_args(argv)
    {"on": cmd_on, "off": cmd_off, "status": cmd_status}[a.cmd](a)
    return 0


if __name__ == "__main__":
    sys.exit(main())
