#!/usr/bin/env python3
"""Set up and police the files that let an agent work across many sessions without losing its place.

The pattern is from Anthropic's "Effective harnesses for long-running agents" (Nov 2025): a
feature list that defines done, a progress log each session reads first and updates last, an
init script that starts the project, and git commits as checkpoints. This kit adds a lock so
nobody can quietly delete or reword a feature to make the list pass.

  harness_kit.py init [--features features.json] [--root .]   create the files (never overwrites)
  harness_kit.py add --category C --description "..." --step "..." [--step ...]
  harness_kit.py lock            record the agreed feature list (a person or the initializer does this)
  harness_kit.py guard [--base REF]   fail if anything but "passes" changed since lock (or since git REF)
  harness_kit.py status          counts, next feature, last progress entries
  harness_kit.py next            the next unfinished feature, as JSON
  harness_kit.py mark ID pass|fail --evidence "..." [--by evaluator]
  harness_kit.py log "what this session did, what's next"

Files (in --root): feature_list.json, feature_list.lock, claude-progress.txt, init.sh.
Python 3 standard library only.
"""
import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

FEATURES, LOCK, PROGRESS, INIT = "feature_list.json", "feature_list.lock", "claude-progress.txt", "init.sh"
FIELDS = ("id", "category", "description", "steps", "passes")

INIT_SH = """#!/usr/bin/env bash
# Start everything a session needs, then run one fast end-to-end check.
# Every session runs this first: keep it idempotent and under a minute.
set -euo pipefail

# 1. Install or start what the project needs. Examples:
#    uv sync            |  npm ci            |  dbt deps
#    docker compose up -d db

# 2. One basic check that the project still works. Examples:
#    pytest -q -x tests/smoke   |  dbt parse   |  curl -sf localhost:8000/health
echo "init.sh: replace these comments with your project's start and smoke-check commands"
"""

PROGRESS_HEAD = """# Progress log

Each session reads this first and adds an entry last: what was done, what was verified and how,
what's broken or half-finished, and what to do next. Newest entries at the bottom.
"""


def now():
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def load(root):
    p = root / FEATURES
    if not p.exists():
        sys.exit(f"{FEATURES} not found in {root}: run init first")
    try:
        data = json.loads(p.read_text())
    except ValueError as e:
        sys.exit(f"{FEATURES} is not valid JSON: {e}")
    if not isinstance(data, list):
        sys.exit(f"{FEATURES} must be a JSON array of features")
    return data


def save(root, feats):
    (root / FEATURES).write_text(json.dumps(feats, indent=2) + "\n")


def problems(feats):
    out, seen = [], set()
    for i, f in enumerate(feats):
        where = f.get("id", f"#{i + 1}") if isinstance(f, dict) else f"#{i + 1}"
        if not isinstance(f, dict):
            out.append(f"{where}: not an object")
            continue
        for k in FIELDS:
            if k not in f:
                out.append(f"{where}: missing '{k}'")
        if f.get("id") in seen:
            out.append(f"{where}: duplicate id")
        seen.add(f.get("id"))
        if not isinstance(f.get("passes"), bool):
            out.append(f"{where}: 'passes' must be true or false")
        if not isinstance(f.get("steps"), list) or not f.get("steps"):
            out.append(f"{where}: needs at least one step saying how to verify it")
    return out


def digest(f):
    """Hash of everything except 'passes': the part that must never change."""
    body = {k: v for k, v in f.items() if k != "passes"}
    return hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()[:16]


def append_log(root, text):
    p = root / PROGRESS
    if not p.exists():
        p.write_text(PROGRESS_HEAD)
    with open(p, "a") as fh:
        fh.write(f"\n## {now()}\n{text.strip()}\n")


def cmd_init(a):
    root = Path(a.root)
    root.mkdir(parents=True, exist_ok=True)
    made = []
    if not (root / FEATURES).exists():
        feats = []
        if a.features:
            feats = json.loads(Path(a.features).read_text())
            for i, f in enumerate(feats, 1):
                f.setdefault("id", f"F{i:03d}")
                f.setdefault("category", "functional")
                f["passes"] = False  # a new list always starts with everything failing
            bad = problems(feats)
            if bad:
                sys.exit("can't use that feature file:\n  " + "\n  ".join(bad))
        save(root, feats)
        made.append(FEATURES)
    if not (root / PROGRESS).exists():
        (root / PROGRESS).write_text(PROGRESS_HEAD)
        made.append(PROGRESS)
    if not (root / INIT).exists():
        (root / INIT).write_text(INIT_SH)
        (root / INIT).chmod(0o755)
        made.append(INIT)
    print("created: " + (", ".join(made) if made else "nothing (all files already exist)"))
    n = len(load(root))
    print(f"{n} feature(s). " + ("Add features, then run lock." if not (root / LOCK).exists() else "Lock exists."))


def cmd_add(a):
    root = Path(a.root)
    feats = load(root)
    if (root / LOCK).exists() and not a.relock:
        sys.exit("the feature list is locked. Adding scope is a person's decision: re-run with --relock to add and re-lock.")
    nums = [int(f["id"][1:]) for f in feats if str(f.get("id", "")).startswith("F") and f["id"][1:].isdigit()]
    fid = f"F{(max(nums) if nums else 0) + 1:03d}"
    feats.append({"id": fid, "category": a.category, "description": a.description, "steps": a.step, "passes": False})
    save(root, feats)
    print(f"added {fid}: {a.description}")
    if a.relock:
        cmd_lock(a)


def cmd_lock(a):
    root = Path(a.root)
    feats = load(root)
    bad = problems(feats)
    if bad:
        sys.exit("fix the feature list before locking:\n  " + "\n  ".join(bad))
    if not feats:
        sys.exit("nothing to lock: the feature list is empty")
    (root / LOCK).write_text(json.dumps({"locked": now(), "features": {f["id"]: digest(f) for f in feats}}, indent=1) + "\n")
    print(f"locked {len(feats)} feature(s). Commit {FEATURES} and {LOCK}; from here only 'passes' may change.")


def guard(root, base=None):
    feats = load(root)
    errs = problems(feats)
    cur = {f.get("id"): digest(f) for f in feats if isinstance(f, dict)}
    if base:
        r = subprocess.run(["git", "show", f"{base}:./{FEATURES}"], cwd=root, capture_output=True, text=True)
        if r.returncode:
            return errs + [f"can't read {FEATURES} at git ref {base}: {r.stderr.strip()[:120]}"]
        ref = {f["id"]: digest(f) for f in json.loads(r.stdout)}
        src = f"git ref {base}"
    else:
        lp = root / LOCK
        if not lp.exists():
            return errs + [f"no {LOCK}: run lock once the feature list is agreed"]
        ref, src = json.loads(lp.read_text())["features"], LOCK
    for fid, h in ref.items():
        if fid not in cur:
            errs.append(f"{fid}: removed (it was in {src})")
        elif cur[fid] != h:
            errs.append(f"{fid}: description, steps or category were edited (only 'passes' may change)")
    for fid in cur:
        if fid not in ref:
            errs.append(f"{fid}: added without re-locking (new scope needs a person: add --relock)")
    return errs


def cmd_guard(a):
    errs = guard(Path(a.root), a.base)
    for e in errs:
        print("  ERROR:", e)
    print(f"guard: {len(errs)} problem(s)" + ("" if errs else ": feature list intact"))
    sys.exit(1 if errs else 0)


def next_feature(feats):
    return next((f for f in feats if not f.get("passes")), None)


def cmd_status(a):
    root = Path(a.root)
    feats = load(root)
    done = sum(1 for f in feats if f.get("passes"))
    print(f"{done} of {len(feats)} features passing" + (" (all done)" if feats and done == len(feats) else ""))
    by = {}
    for f in feats:
        c = by.setdefault(f.get("category", "?"), [0, 0])
        c[0] += bool(f.get("passes"))
        c[1] += 1
    for cat, (d, n) in sorted(by.items()):
        print(f"  {cat}: {d}/{n}")
    nx = next_feature(feats)
    if nx:
        print(f"next: {nx['id']} {nx['description']}")
    errs = guard(root) if (root / LOCK).exists() else ["not locked yet: run lock"]
    print("list: " + ("intact" if not errs else f"{len(errs)} problem(s), run guard"))
    p = root / PROGRESS
    if p.exists():
        entries = p.read_text().split("\n## ")[1:]
        if entries:
            print("last entry: ## " + entries[-1].strip().replace("\n", "\n  ")[:600])


def cmd_next(a):
    nx = next_feature(load(Path(a.root)))
    print(json.dumps(nx, indent=2) if nx else '{"done": true}')


def cmd_mark(a):
    root = Path(a.root)
    feats = load(root)
    f = next((x for x in feats if x.get("id") == a.id), None)
    if not f:
        sys.exit(f"no feature {a.id}")
    if a.result == "pass" and not a.evidence.strip():
        sys.exit("a pass needs --evidence: the command you ran and what it showed")
    errs = guard(root) if (root / LOCK).exists() else []
    if errs:
        sys.exit("the feature list was tampered with; fix that before marking anything:\n  " + "\n  ".join(errs))
    f["passes"] = a.result == "pass"
    save(root, feats)
    append_log(root, f"{a.by}: {a.id} marked {'PASS' if f['passes'] else 'FAIL'} ({f['description']})\nEvidence: {a.evidence.strip()}")
    done = sum(1 for x in feats if x.get("passes"))
    print(f"{a.id} -> {a.result}. {done} of {len(feats)} passing.")


def cmd_log(a):
    append_log(Path(a.root), a.text)
    print(f"logged to {PROGRESS}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    def mk(name):
        p = sub.add_parser(name)
        p.add_argument("--root", default=".")
        return p

    mk("init").add_argument("--features", help="JSON array of features to start from (all are set to failing)")
    p = mk("add")
    p.add_argument("--category", default="functional")
    p.add_argument("--description", required=True)
    p.add_argument("--step", action="append", required=True, help="one verification step; repeat for more")
    p.add_argument("--relock", action="store_true")
    mk("lock")
    mk("guard").add_argument("--base", help="compare with feature_list.json at this git ref instead of the lock file")
    mk("status")
    mk("next")
    p = mk("mark")
    p.add_argument("id")
    p.add_argument("result", choices=["pass", "fail"])
    p.add_argument("--evidence", default="")
    p.add_argument("--by", default="evaluator")
    mk("log").add_argument("text")
    a = ap.parse_args(argv)
    {"init": cmd_init, "add": cmd_add, "lock": cmd_lock, "guard": cmd_guard, "status": cmd_status,
     "next": cmd_next, "mark": cmd_mark, "log": cmd_log}[a.cmd](a)


if __name__ == "__main__":
    main()
