#!/usr/bin/env python3
"""Loops that can run without you watching: a program decides "done", and every loop has a stop.

  repair  Fix one unit until a check passes.
          agent_loop.py repair --task "..." --check "pytest -q tests/test_x.py" --scope "src/x.py" \
                               [--max-rounds 3] [--budget-usd 2] [--state .agent-loop] [--rules RULES.md]
  hunt    Find things (bugs, flaky tests, sources) round by round until two rounds find nothing new.
          agent_loop.py hunt --task "..." [--verify "cmd"] [--max-rounds 6] [--dry-rounds 2] [--budget-usd 3]

The agent is Claude Code headless (`claude -p ... --output-format json`); set CLAUDE_BIN to use
another binary. Every loop has the five parts: a check that says done (exit code, never "no errors
were thrown"), a round limit, a budget, memory of past attempts (kept in --state, so a re-run
doesn't repeat them), and a clear stop that tells a person what to look at.

Exit codes: 0 done, 2 bad arguments, 3 escalate (round limit or no progress: the plan is wrong),
4 stop (budget spent or the agent itself failed).
"""
import argparse
import fnmatch
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

TAIL = 60


# ---------- plumbing ----------
def sh(cmd, cwd=None, stdin=None, timeout=1800):
    p = subprocess.run(cmd, shell=True, cwd=cwd, input=stdin, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def tail(text, n=TAIL):
    lines = (text or "").strip().splitlines()
    return "\n".join(lines[-n:])


def fingerprint(text):
    """Failure output minus timings and addresses, so 'same failure again' is detectable."""
    t = re.sub(r"\b\d+(\.\d+)?\s*(s|ms|sec|seconds)\b", "", text or "")
    t = re.sub(r"0x[0-9a-f]+|\b\d{4,}\b", "", t, flags=re.I)
    return hashlib.sha1(t.strip().encode()).hexdigest()[:12]


def call_agent(prompt, permission_mode, cwd):
    """Returns (ok, text, cost_usd). One retry on a transient failure (exit code or unparseable output)."""
    claude = os.environ.get("CLAUDE_BIN", "claude")
    cmd = [claude, "-p", prompt, "--output-format", "json", "--permission-mode", permission_mode]
    for attempt in (1, 2):
        try:
            p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=3600)
            d = json.loads(p.stdout)
            if p.returncode == 0 and not d.get("is_error"):
                return True, str(d.get("result", "")), float(d.get("total_cost_usd") or 0)
            err = str(d.get("result") or p.stderr)[:300]
        except (ValueError, OSError, subprocess.TimeoutExpired) as e:
            err = str(e)[:300]
        if attempt == 1:
            time.sleep(2)  # RETRY: tool or network blip
    return False, err, 0.0


class State:
    """Attempt memory on disk: <state>/<loop id>/attempts.jsonl (+ findings.jsonl for hunts)."""

    def __init__(self, root, kind, task):
        self.dir = Path(root) / f"{kind}-{hashlib.sha1(task.encode()).hexdigest()[:10]}"
        self.dir.mkdir(parents=True, exist_ok=True)
        (self.dir / "task.txt").write_text(task)
        self.attempts_p = self.dir / "attempts.jsonl"

    def attempts(self):
        if not self.attempts_p.exists():
            return []
        return [json.loads(l) for l in self.attempts_p.read_text().splitlines() if l.strip()]

    def record(self, **row):
        row["at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(self.attempts_p, "a") as f:
            f.write(json.dumps(row) + "\n")


def git_changed(cwd):
    rc, out = sh("git status --porcelain --untracked-files=all", cwd=cwd)
    if rc:
        return None
    return {l[3:].strip().split(" -> ")[-1] for l in out.splitlines() if l.strip()}


def outside(files, scopes):
    return sorted(f for f in files if not any(fnmatch.fnmatch(f, s) or f.startswith(s.rstrip("/") + "/") for s in scopes))


def read_rules(path):
    p = Path(path) if path else None
    return p.read_text().strip() if p and p.exists() else ""


def add_rule(path, rule, scope, task):
    p = Path(path)
    new = not p.exists()
    with open(p, "a") as f:
        if new:
            f.write("# Rules learned from fixes\n\nRead these before splitting or assigning similar work.\n\n")
        f.write(f"- {rule.strip()}  _(scope: {', '.join(scope)}; {datetime.now().date()}; from: {task[:80]})_\n")


# ---------- repair ----------
REPAIR_PROMPT = """{task}

Scope: change only {scope}. If you notice other problems, don't fix them: list them under "Noticed:".
Done means this command exits 0: `{check}`. Run it yourself before you finish.
{rules}{history}{failure}
End your reply with two lines:
CAUSE: <one line: why it was failing>
RULE: <one line a planner could follow next time so this can't happen again>
"""


def repair(a):
    st = State(a.state, "repair", a.task + a.check + " ".join(a.scope))
    rc, out = sh(a.check, cwd=a.cwd)
    if rc == 0:
        print("Check already passes: nothing to do.")
        return 0
    baseline = git_changed(a.cwd)
    spent, last_fp, same = 0.0, None, 0
    past = st.attempts()
    for rnd in range(1, a.max_rounds + 1):
        if spent >= a.budget_usd:
            return stop(st, f"budget spent (${spent:.2f} of ${a.budget_usd:.2f})", 4)
        hist = ""
        if past:
            hist = "\nAlready tried (don't repeat these):\n" + "\n".join(
                f"- round {p['round']}: {p.get('cause') or p.get('note') or 'no cause given'} -> still failing" for p in past[-5:]) + "\n"
        rules = read_rules(a.rules)
        prompt = REPAIR_PROMPT.format(
            task=a.task, scope=", ".join(a.scope), check=a.check,
            rules=f"\nStanding rules:\n{rules}\n" if rules else "",
            history=hist,
            failure=f"\nThe check currently fails with:\n```\n{tail(out)}\n```\n")
        ok, text, cost = call_agent(prompt, a.permission_mode, a.cwd)
        spent += cost
        if not ok:
            st.record(round=rnd, kind="agent-error", note=text, cost=cost)
            return stop(st, f"the agent failed twice in a row: {text}", 4)
        cause = (re.findall(r"^CAUSE:\s*(.+)$", text, re.M) or [""])[-1]
        rule = (re.findall(r"^RULE:\s*(.+)$", text, re.M) or [""])[-1]
        rc, out = sh(a.check, cwd=a.cwd)
        stray = []
        if baseline is not None:
            now = git_changed(a.cwd) or set()
            own = [str(Path(x).resolve()) for x in (a.state, a.rules) if x]  # the loop's own files aren't the agent's edits
            stray = [f for f in outside(now - baseline, a.scope)
                     if not any(str((Path(a.cwd) / f).resolve()).startswith(o) for o in own)]
        if rc == 0 and not stray:
            st.record(round=rnd, kind="pass", cause=cause, rule=rule, cost=cost)
            if a.rules and rule and rnd + len(past) > 1:  # learned something the hard way: keep it
                add_rule(a.rules, rule, a.scope, a.task)
            print(f"PASS after {rnd} round(s), ${spent:.2f}. Cause: {cause or 'not given'}")
            return 0
        if stray:
            out = (f"Your change touched files outside the scope: {', '.join(stray)}. Revert those; "
                   f"change only {', '.join(a.scope)}.\n" + (out if rc else ""))
        fp = fingerprint(out)
        same = same + 1 if fp == last_fp else 0
        last_fp = fp
        row = dict(round=rnd, kind="fail", cause=cause, cost=cost, check_tail=tail(out, 20), stray=stray)
        st.record(**row)
        past.append(row)
        if same >= 1:
            return escalate(st, a, "two rounds in a row ended with the same failure: no progress", out)
    return escalate(st, a, f"{a.max_rounds} repair rounds failed", out)


def escalate(st, a, why, out):
    body = (f"# Escalation: {why}\n\nTask: {a.task}\nScope: {', '.join(a.scope)}\nCheck: `{a.check}`\n\n"
            f"Repeated repairs didn't converge, so the plan is probably wrong (the split, the scope, or the check).\n\n"
            f"## Attempts\n\n" + "\n".join(f"- round {r['round']}: {r.get('cause') or r.get('note') or '-'}" for r in st.attempts())
            + f"\n\n## Last failure\n\n```\n{tail(out)}\n```\n")
    (st.dir / "ESCALATION.md").write_text(body)
    print(f"ESCALATE: {why}. See {st.dir}/ESCALATION.md")
    return 3


def stop(st, why, code):
    (st.dir / "STOPPED.md").write_text(f"# Stopped: {why}\n")
    print(f"STOP: {why}. A person needs to look: {st.dir}")
    return code


# ---------- hunt ----------
HUNT_PROMPT = """{task}

Report only NEW findings, one JSON object per line, exactly: {{"key": "<short stable id>", "summary": "...", "evidence": "..."}}
Use the same key for the same underlying issue every time. Output nothing else on those lines.
{seen}"""


def hunt(a):
    st = State(a.state, "hunt", a.task)
    fp = st.dir / "findings.jsonl"
    found = [json.loads(l) for l in fp.read_text().splitlines() if l.strip()] if fp.exists() else []
    seen = {f["key"]: f["status"] for f in found}  # accepted AND rejected: never pay to rediscover a dead end
    spent, dry, rounds = 0.0, 0, 0
    while rounds < a.max_rounds:
        if spent >= a.budget_usd:
            return report_hunt(st, found, f"budget spent (${spent:.2f})", 4)
        rounds += 1
        listing = ""
        if seen:
            listing = "Already found (don't report again):\n" + "\n".join(
                f"- {k} ({v})" for k, v in sorted(seen.items())) + "\n"
        ok, text, cost = call_agent(HUNT_PROMPT.format(task=a.task, seen=listing), a.permission_mode, a.cwd)
        spent += cost
        if not ok:
            return report_hunt(st, found, f"the agent failed twice in a row: {text}", 4)
        fresh = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                f = json.loads(line)
            except ValueError:
                continue
            k = str(f.get("key", "")).strip()
            if k and k not in seen and k not in {x["key"] for x in fresh}:
                fresh.append({"key": k, "summary": f.get("summary", ""), "evidence": f.get("evidence", "")})
        for f in fresh:
            if a.verify:
                rc, vout = sh(a.verify, cwd=a.cwd, stdin=json.dumps(f))
                f["status"], f["verify"] = ("accepted" if rc == 0 else "rejected"), tail(vout, 5)
            else:
                f["status"] = "unverified"
            f["round"] = rounds
            seen[f["key"]] = f["status"]
            found.append(f)
            with open(fp, "a") as fh:
                fh.write(json.dumps(f) + "\n")
        dry = dry + 1 if not fresh else 0
        st.record(round=rounds, kind="hunt", fresh=len(fresh), cost=cost)
        print(f"round {rounds}: {len(fresh)} new, {len(seen)} seen")
        if dry >= a.dry_rounds:
            return report_hunt(st, found, f"{a.dry_rounds} rounds in a row found nothing new", 0)
    return report_hunt(st, found, f"round limit ({a.max_rounds}) reached while still finding things", 3)


def report_hunt(st, found, why, code):
    acc = [f for f in found if f["status"] in ("accepted", "unverified")]
    rej = [f for f in found if f["status"] == "rejected"]
    md = [f"# Hunt: {why}", "", f"{len(acc)} kept, {len(rej)} rejected by the check.", "",
          "| Key | Status | Summary |", "|---|---|---|"]
    md += [f"| {f['key']} | {f['status']} | {str(f['summary'])[:120].replace('|', '/')} |" for f in found]
    (st.dir / "REPORT.md").write_text("\n".join(md) + "\n")
    print(f"{'DONE' if code == 0 else 'ESCALATE' if code == 3 else 'STOP'}: {why}. {len(acc)} kept -> {st.dir}/REPORT.md")
    return code


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("repair", "hunt"):
        p = sub.add_parser(name)
        p.add_argument("--task", required=True)
        p.add_argument("--budget-usd", type=float, default=2.0 if name == "repair" else 3.0)
        p.add_argument("--state", default=".agent-loop")
        p.add_argument("--cwd", default=".")
        p.add_argument("--permission-mode", default="acceptEdits" if name == "repair" else "default")
        if name == "repair":
            p.add_argument("--check", required=True, help="command that exits 0 when the work is done")
            p.add_argument("--scope", required=True, nargs="+", help="files or globs the agent may change")
            p.add_argument("--max-rounds", type=int, default=3)
            p.add_argument("--rules", help="markdown file of learned rules (read every round, appended on a hard-won pass)")
        else:
            p.add_argument("--verify", help="command given each finding as JSON on stdin; exit 0 keeps it")
            p.add_argument("--max-rounds", type=int, default=6)
            p.add_argument("--dry-rounds", type=int, default=2)
    a = ap.parse_args(argv)
    if a.cmd == "repair" and not a.check.strip():
        sys.exit("--check must be a real command: silence is not success")
    sys.exit(repair(a) if a.cmd == "repair" else hunt(a))


if __name__ == "__main__":
    main()
