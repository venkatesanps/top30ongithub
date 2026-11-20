#!/usr/bin/env python3
"""Decision log: write down what you chose, how sure you were and what could go wrong,
then check it later and see how good your pre-mortems and confidence really are.

  decisions.py add "<decision>" --chose "<option>" --confidence 70 \
      [--risk "..."]... [--kill "..."] [--review-in 30] [--tag work]
  decisions.py list [--open]
  decisions.py due
  decisions.py show <id>
  decisions.py review <id> --outcome good|mixed|bad [--happened 2 | --happened "new risk"] [--note "..."]
  decisions.py stats [--json]

State lives in ~/.claude/sparring/decisions.json (override with SPARRING_STATE). The script
only reads and writes that file; it sends nothing anywhere.
"""
import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OUTCOME_SCORE = {"good": 1.0, "mixed": 0.5, "bad": 0.0}
BANDS = [(0, 59, "50-59"), (60, 69, "60-69"), (70, 79, "70-79"), (80, 89, "80-89"), (90, 100, "90-100")]


def now():
    override = os.environ.get("SPARRING_NOW")  # for tests
    return datetime.fromisoformat(override) if override else datetime.now(timezone.utc)


def state_path():
    return Path(os.environ.get("SPARRING_STATE") or Path.home() / ".claude" / "sparring" / "decisions.json")


def load():
    p = state_path()
    if not p.exists():
        return {"version": 1, "next_id": 1, "decisions": []}
    try:
        return json.loads(p.read_text())
    except json.JSONDecodeError:
        sys.exit(f"{p} is not valid JSON; fix or move it and try again.")


def save(state):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=1) + "\n")
    tmp.replace(p)


def find(state, ident):
    for d in state["decisions"]:
        if str(d["id"]) == str(ident).lstrip("#"):
            return d
    sys.exit(f"No decision #{ident}. Run: decisions.py list")


def fmt_date(iso):
    return iso[:10]


def cmd_add(a):
    if not 50 <= a.confidence <= 100:
        sys.exit("--confidence is how sure you are the choice turns out well: 50 (coin flip) to 100.")
    if a.review_in < 1:
        sys.exit("--review-in must be at least 1 day.")
    st = load()
    t = now()
    d = {
        "id": st["next_id"],
        "decision": a.decision.strip(),
        "chose": (a.chose or "").strip(),
        "confidence": a.confidence,
        "risks": [r.strip() for r in a.risk if r.strip()],
        "kill": (a.kill or "").strip(),
        "tags": a.tag,
        "created": t.isoformat(),
        "review_on": (t + timedelta(days=a.review_in)).isoformat(),
        "review": None,
    }
    st["decisions"].append(d)
    st["next_id"] += 1
    save(st)
    print(f"Logged #{d['id']}: {d['decision']}")
    if d["chose"]:
        print(f"  chose: {d['chose']} ({d['confidence']}% sure)")
    for i, r in enumerate(d["risks"], 1):
        print(f"  risk {i}: {r}")
    if d["kill"]:
        print(f"  stop if: {d['kill']}")
    print(f"  review on {fmt_date(d['review_on'])}")
    if not d["risks"]:
        print("  note: no risks logged, so this one can't count toward 'predicted by the pre-mortem'.")


def cmd_list(a):
    st = load()
    rows = [d for d in st["decisions"] if not (a.open and d["review"])]
    if not rows:
        print("No decisions logged." if not st["decisions"] else "No open decisions.")
        return
    for d in rows:
        status = d["review"]["outcome"] if d["review"] else f"review {fmt_date(d['review_on'])}"
        print(f"#{d['id']:<3} {fmt_date(d['created'])}  {d['confidence']:>3}%  {status:<17} {d['decision']}")


def cmd_due(a):
    st = load()
    t = now()
    due = [d for d in st["decisions"] if not d["review"] and datetime.fromisoformat(d["review_on"]) <= t]
    if not due:
        print("Nothing due for review.")
        return
    print(f"{len(due)} decision(s) due for review:")
    for d in due:
        days = (t - datetime.fromisoformat(d["review_on"])).days
        late = f", {days} day(s) late" if days else ""
        print(f"#{d['id']}  {d['decision']}  (chose: {d['chose'] or '-'}, {d['confidence']}% sure{late})")
        for i, r in enumerate(d["risks"], 1):
            print(f"     risk {i}: {r}")
    print("Review with: decisions.py review <id> --outcome good|mixed|bad --happened <risk # or text>")


def cmd_show(a):
    d = find(load(), a.id)
    print(json.dumps(d, indent=1))


def cmd_review(a):
    st = load()
    d = find(st, a.id)
    if d["review"] and not a.force:
        sys.exit(f"#{d['id']} was already reviewed ({d['review']['outcome']}). Use --force to redo it.")
    happened, predicted = [], None
    for h in a.happened:
        h = h.strip()
        if h.isdigit():
            n = int(h)
            if not 1 <= n <= len(d["risks"]):
                sys.exit(f"#{d['id']} has {len(d['risks'])} logged risk(s); --happened {n} is out of range.")
            happened.append({"risk": n, "text": d["risks"][n - 1]})
        elif h:
            happened.append({"risk": None, "text": h})
    if happened:
        predicted = any(x["risk"] for x in happened)
    d["review"] = {
        "outcome": a.outcome,
        "happened": happened,
        "predicted": predicted,
        "note": (a.note or "").strip(),
        "reviewed": now().isoformat(),
    }
    save(st)
    print(f"Reviewed #{d['id']}: {a.outcome}")
    if happened:
        for x in happened:
            tag = f"risk {x['risk']} (predicted)" if x["risk"] else "not predicted"
            print(f"  went wrong: {x['text']} [{tag}]")
        if not predicted:
            print("  The pre-mortem missed this. Next time, ask: what would have to be true for this to fail?")


def compute_stats(decisions):
    done = [d for d in decisions if d["review"]]
    out = {"logged": len(decisions), "reviewed": len(done), "open": len(decisions) - len(done)}
    if not done:
        return out
    brier = sum((d["confidence"] / 100 - OUTCOME_SCORE[d["review"]["outcome"]]) ** 2 for d in done) / len(done)
    out["brier"] = round(brier, 3)
    out["outcomes"] = {k: sum(1 for d in done if d["review"]["outcome"] == k) for k in OUTCOME_SCORE}
    bands = []
    for lo, hi, label in BANDS:
        ds = [d for d in done if lo <= d["confidence"] <= hi]
        if ds:
            stated = sum(d["confidence"] for d in ds) / len(ds)
            actual = 100 * sum(OUTCOME_SCORE[d["review"]["outcome"]] for d in ds) / len(ds)
            bands.append({"band": label, "n": len(ds), "stated": round(stated), "actual": round(actual)})
    out["bands"] = bands
    went_wrong = [d for d in done if d["review"]["happened"]]
    out["went_wrong"] = len(went_wrong)
    out["predicted"] = sum(1 for d in went_wrong if d["review"]["predicted"])
    return out


def cmd_stats(a):
    s = compute_stats(load()["decisions"])
    if a.json:
        print(json.dumps(s, indent=1))
        return
    print(f"Decisions: {s['logged']} logged, {s['reviewed']} reviewed, {s['open']} open")
    if not s["reviewed"]:
        print("Review a few (decisions.py due) before the numbers mean anything.")
        return
    o = s["outcomes"]
    print(f"Outcomes: {o['good']} good, {o['mixed']} mixed, {o['bad']} bad")
    print(f"Brier score: {s['brier']} (0 is perfect; always saying 50% scores 0.25)")
    print("Calibration (how often it went well vs how sure you were):")
    for b in s["bands"]:
        gap = b["actual"] - b["stated"]
        verdict = "about right" if abs(gap) < 10 else ("over-confident" if gap < 0 else "under-confident")
        print(f"  {b['band']:>7}%  n={b['n']:<3} said {b['stated']}%, went well {b['actual']}%  {verdict}")
    if s["went_wrong"]:
        pct = round(100 * s["predicted"] / s["went_wrong"])
        print(f"Pre-mortems: {s['predicted']} of {s['went_wrong']} things that went wrong were predicted ({pct}%)")
        if pct < 50:
            print("  Most failures weren't on the list. Spend longer on 'against' before committing.")
    if s["reviewed"] < 5:
        print("Fewer than 5 reviewed: treat these numbers as a hint, not a verdict.")


def main(argv=None):
    p = argparse.ArgumentParser(description="Decision log with pre-mortem risks and calibration.")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("add", help="log a decision")
    s.add_argument("decision")
    s.add_argument("--chose", help="the option you picked")
    s.add_argument("--confidence", type=int, default=70, help="50-100: how sure it turns out well")
    s.add_argument("--risk", action="append", default=[], help="a predicted failure mode (repeat)")
    s.add_argument("--kill", help="signal that means stop or rethink")
    s.add_argument("--review-in", type=int, default=30, help="days until review (default 30)")
    s.add_argument("--tag", action="append", default=[])
    s.set_defaults(fn=cmd_add)

    s = sub.add_parser("list", help="list decisions")
    s.add_argument("--open", action="store_true", help="only ones not yet reviewed")
    s.set_defaults(fn=cmd_list)

    sub.add_parser("due", help="decisions whose review date has passed").set_defaults(fn=cmd_due)

    s = sub.add_parser("show", help="one decision as JSON")
    s.add_argument("id")
    s.set_defaults(fn=cmd_show)

    s = sub.add_parser("review", help="record how it turned out")
    s.add_argument("id")
    s.add_argument("--outcome", required=True, choices=list(OUTCOME_SCORE))
    s.add_argument("--happened", action="append", default=[],
                   help="risk number that occurred, or text for one that wasn't predicted (repeat)")
    s.add_argument("--note")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_review)

    s = sub.add_parser("stats", help="calibration and pre-mortem hit rate")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_stats)

    a = p.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
