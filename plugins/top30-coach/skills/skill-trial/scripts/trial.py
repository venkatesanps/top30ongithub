#!/usr/bin/env python3
"""One skill at a time: try it for a week on real work, keep it only if it saved time.

  trial.py start <skill or kit #> [--goal "..."] [--days 7]
  trial.py log --saved 15 [--note "..."]     # minutes saved this use (negative if it cost time)
  trial.py status
  trial.py review [--now]                    # keep / drop / extend, once the trial is over
  trial.py suggest --role data|manager|sre|writer|design|builder [--catalog catalog.json]
  trial.py history

State lives in ~/.claude/skill-trials.json (override with SKILL_TRIAL_STATE). Nothing is
installed, uninstalled or sent anywhere: the script only reads and writes that file and
reads the kit's catalog.json for suggestions.
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROLES = {  # kit rows, most relevant first
    "data": [6, 7, 1], "manager": [8, 10, 2], "sre": [9, 7, 11], "writer": [5, 2, 12],
    "design": [4, 12], "builder": [1, 10, 11, 13],
}
DAILY_CAP = 3  # "3 skills you use every day beat 27 you never open"


def now():
    override = os.environ.get("SKILL_TRIAL_NOW")  # for tests
    return datetime.fromisoformat(override) if override else datetime.now(timezone.utc)


def state_path():
    return Path(os.environ.get("SKILL_TRIAL_STATE") or Path.home() / ".claude" / "skill-trials.json")


def load():
    p = state_path()
    if p.exists():
        return json.loads(p.read_text())
    return {"active": None, "history": []}


def save(s):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(s, indent=1) + "\n")
    tmp.replace(p)


def find_catalog(arg):
    for c in [arg, os.environ.get("TOP30_CATALOG"), Path(__file__).resolve().parents[5] / "catalog.json",
              Path.cwd() / "catalog.json", Path.home() / "top30ongithub" / "catalog.json"]:
        if c and Path(c).is_file():
            return json.loads(Path(c).read_text())
    return None


def tokens(it):
    m = re.search(r"[\d,]+", str(it.get("always_on", "")))
    return int(m.group(0).replace(",", "")) if m else 0


def resolve(skill, catalog):
    if catalog and skill.isdigit():
        it = next((i for i in catalog["items"] if i["n"] == int(skill)), None)
        if not it:
            sys.exit(f"no kit item #{skill}")
        return {"skill": it["name"], "kit": it["n"], "install": f"./install.sh {it['n']}", "use": it.get("use", ""),
                "tokens": it.get("always_on", "")}
    return {"skill": skill}


def tally(t):
    uses = t.get("uses", [])
    return len(uses), sum(u["saved"] for u in uses)


def cmd_start(a):
    s = load()
    if s["active"] and not a.force:
        t = s["active"]
        sys.exit(f"Already trying {t['skill']} until {t['ends'][:10]}. Review it first (trial.py review), "
                 "or pass --force to abandon it.")
    if s["active"]:
        s["active"].update(verdict="abandoned", reviewed=now().isoformat())
        s["history"].append(s["active"])
    kept = [h for h in s["history"] if h.get("verdict") == "keep"]
    t = resolve(a.skill, find_catalog(a.catalog))
    if any(h["skill"].lower() == t["skill"].lower() for h in kept):
        sys.exit(f"{t['skill']} is already kept. Pick the next one: trial.py suggest")
    t.update(goal=a.goal or "", started=now().isoformat(), ends=(now() + timedelta(days=a.days)).isoformat(), uses=[])
    s["active"] = t
    save(s)
    print(f"Trial started: {t['skill']} for {a.days} days (until {t['ends'][:10]}).")
    if t.get("install"):
        print(f"Install: {t['install']}   Always-on cost: {t.get('tokens') or 'n/a'} tokens/session")
    if t.get("use"):
        print(f"Try: {t['use']}")
    if len(kept) >= DAILY_CAP:
        print(f"Note: you already keep {len(kept)} skills. Consider dropping one you no longer open.")


def cmd_log(a):
    s = load()
    if not s["active"]:
        sys.exit("No active trial. Start one: trial.py start <skill>")
    s["active"]["uses"].append({"at": now().isoformat(), "saved": a.saved, "note": a.note or ""})
    save(s)
    n, saved = tally(s["active"])
    print(f"Logged. {s['active']['skill']}: {n} use(s), {saved:+d} min so far.")


def cmd_status(a):
    s = load()
    t = s["active"]
    kept = [h["skill"] for h in s["history"] if h.get("verdict") == "keep"]
    if not t:
        print("No active trial." + (f" Kept: {', '.join(kept)}." if kept else "") + " Start one: trial.py start <skill>")
        return
    n, saved = tally(t)
    left = (datetime.fromisoformat(t["ends"]) - now()).days
    print(f"Trying {t['skill']}: {n} use(s), {saved:+d} min, "
          + (f"{left} day(s) left." if left >= 0 else "trial over: run trial.py review."))
    if t.get("goal"):
        print(f"Goal: {t['goal']}")
    if kept:
        print(f"Kept so far: {', '.join(kept)}")


def verdict(n, saved):
    if n == 0:
        return "drop", "never used in real work: it isn't solving a problem you have."
    if saved <= 0:
        return "drop", f"used {n} time(s) but saved no time overall ({saved:+d} min)."
    if n < 3:
        return "extend", f"only {n} use(s): not enough to judge. One more week."
    return "keep", f"{n} uses, {saved:+d} min saved."


def cmd_review(a):
    s = load()
    t = s["active"]
    if not t:
        sys.exit("No active trial to review.")
    if now() < datetime.fromisoformat(t["ends"]) and not a.now:
        sys.exit(f"Trial runs until {t['ends'][:10]}. Keep using it, or pass --now to review early.")
    n, saved = tally(t)
    v, why = verdict(n, saved)
    if v == "extend" and t.get("extended"):
        v, why = "drop", f"still only {n} use(s) after an extra week."
    if v == "extend":
        t["ends"] = (now() + timedelta(days=7)).isoformat()
        t["extended"] = True
        save(s)
        print(f"EXTEND {t['skill']}: {why} New end: {t['ends'][:10]}.")
        return
    t.update(verdict=v, reviewed=now().isoformat(), minutes_saved=saved)
    s["history"].append(t)
    s["active"] = None
    save(s)
    print(f"{v.upper()} {t['skill']}: {why}")
    if v == "drop":
        print("Uninstall or disable it so it stops loading into every session (claude plugin disable <name>).")
    kept = [h["skill"] for h in s["history"] if h.get("verdict") == "keep"]
    print(f"Kept: {', '.join(kept) or 'none yet'}. Next: trial.py suggest --role <your role>")


def cmd_suggest(a):
    c = find_catalog(a.catalog)
    if not c:
        sys.exit("catalog.json not found: pass --catalog path/to/top30ongithub/catalog.json")
    s = load()
    tried = {h["skill"].lower() for h in s["history"]} | ({s["active"]["skill"].lower()} if s["active"] else set())
    rows = ROLES[a.role]
    pick = [i for i in c["items"] if i["row"] in rows and i["name"].lower() not in tried and i.get("status") == "ok"]
    pick.sort(key=lambda i: (rows.index(i["row"]), tokens(i)))
    print(f"Next to try as {a.role} (one at a time, cheapest per session first within each row):")
    for i in pick[:a.top]:
        print(f"  #{i['n']:<3} {i['name']}  ({c['rows'][str(i['row'])]}; {i.get('always_on') or 'n/a'} tokens/session)")
        print(f"       {i['what'][:150]}")
    if pick:
        print(f"Start one: trial.py start {pick[0]['n']}")


def cmd_history(a):
    s = load()
    if not s["history"]:
        print("No finished trials yet.")
    for h in s["history"]:
        print(f"{h['reviewed'][:10]}  {h.get('verdict', '?'):9} {h['skill']}  ({len(h.get('uses', []))} uses, "
              f"{h.get('minutes_saved', 0):+d} min)")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("start")
    p.add_argument("skill")
    p.add_argument("--goal")
    p.add_argument("--days", type=int, default=7)
    p.add_argument("--force", action="store_true")
    p.add_argument("--catalog")
    p = sub.add_parser("log")
    p.add_argument("--saved", type=int, required=True, help="minutes saved (negative if it cost time)")
    p.add_argument("--note")
    sub.add_parser("status")
    p = sub.add_parser("review")
    p.add_argument("--now", action="store_true")
    p = sub.add_parser("suggest")
    p.add_argument("--role", choices=sorted(ROLES), required=True)
    p.add_argument("--catalog")
    p.add_argument("--top", type=int, default=3)
    sub.add_parser("history")
    a = ap.parse_args(argv)
    {"start": cmd_start, "log": cmd_log, "status": cmd_status, "review": cmd_review,
     "suggest": cmd_suggest, "history": cmd_history}[a.cmd](a)


if __name__ == "__main__":
    main()
