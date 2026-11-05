#!/usr/bin/env python3
"""Check an agent pipeline drawn as a graph: arrows that carry nothing, missing contracts,
models doing code's job, checks too weak to trust, unbounded loops, and gates on the wrong steps.

  python3 graph_check.py init > pipeline.json      # a commented starting point
  python3 graph_check.py check pipeline.json [--out ./graph-report] [--fail-on error|warn]

Spec (JSON; YAML too if PyYAML is installed):
  name, runs ("once" | "recurring"), inputs: [variables the run starts with]
  nodes: { id: { job, in: [...], out: [...], fails_as, kind: model|code, size: small|strong,
                 check, minutes, undo: free|revert|hard|irreversible, gate: auto|evidence|human,
                 on_fail: retry|fallback|skip|repair|escalate|stop, max_rounds, context: own|shared } }
  edges: [ {from, to, carries} ] or [ "a -> b : variable" ]
  drawn_order: [node ids in the order the process was first written down]  (optional)

Writes <out>/report.md and <out>/graph.mmd (Mermaid). Reads only the spec; no model calls.
"""
import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

CONTRACT = ("job", "in", "out", "fails_as")
STRENGTH = [  # (pattern, strength) first match wins; mirrors the evidence ranking
    (r"\b(tests?|pytest|unit|dbt test|exit 0|exit code|schema|json ?schema|diff[- ]in[- ]plan|diff stays|row ?counts?|checksums?|compiles?|type ?check|lint)\b", "strong"),
    (r"\b(cited source|source supports|independent|second path|cross[- ]?check|reconcile|sample diff)\b", "medium"),
    (r"\b(review(er)?( agent)?|llm judge|model review|critic)\b", "weak"),
    (r"\b(lgtm|looks good|confiden(t|ce)|no errors?|none|manual glance)\b", "noise"),
]
DETERMINISTIC = re.compile(r"\b(merge|dedupe|de-?duplicate|sort|join|union|filter|count|concatenate|rename|format|reformat|"
                           r"diff|split|batch|parse json|validate schema|lookup|deduplicat\w*)\b", re.I)
JUDGEMENT = re.compile(r"\b(judge|decide|assess|summari[sz]e|rank|write|draft|explain|classify|extract|review|"
                       r"recommend|plan|triage|critique|evaluate|research|find)\w*", re.I)
SEV = {"error": 0, "warn": 1, "info": 2}

TEMPLATE = {
    "name": "weekly-vendor-brief",
    "runs": "recurring",
    "inputs": ["topic", "repo_path", "vendor_list"],
    "nodes": {
        "research": {"job": "find one primary source per claim about the topic", "in": ["topic"], "out": ["claims"],
                     "fails_as": "no_primary_source", "kind": "model", "size": "strong", "check": "cited source supports the claim",
                     "minutes": 12, "undo": "free", "gate": "auto", "on_fail": "repair", "max_rounds": 3, "context": "own"},
        "repo_scan": {"job": "list where our code depends on the topic", "in": ["repo_path"], "out": ["usages"],
                      "fails_as": "repo_unreadable", "kind": "model", "size": "small", "check": "schema",
                      "minutes": 6, "undo": "free", "gate": "auto", "on_fail": "retry"},
        "pricing": {"job": "pull current list prices for each vendor", "in": ["vendor_list"], "out": ["prices"],
                    "fails_as": "price_page_changed", "kind": "code", "check": "schema",
                    "minutes": 4, "undo": "free", "gate": "auto", "on_fail": "fallback"},
        "write": {"job": "write the brief from claims, usages and prices", "in": ["claims", "usages", "prices"],
                  "out": ["brief"], "fails_as": "unsupported_claim", "kind": "model", "size": "strong",
                  "check": "schema, and each claim's cited source supports it", "minutes": 5, "undo": "hard",
                  "gate": "human", "on_fail": "repair", "max_rounds": 3},
    },
    "edges": ["research -> write : claims", "repo_scan -> write : usages", "pricing -> write : prices"],
    "drawn_order": ["research", "repo_scan", "pricing", "write"],
}


def load_spec(path):
    text = Path(path).read_text()
    if path.endswith((".yml", ".yaml")):
        try:
            import yaml
        except ImportError:
            sys.exit("YAML spec needs PyYAML (pip install pyyaml), or save it as JSON")
        return yaml.safe_load(text)
    return json.loads(text)


def edges_of(spec):
    out = []
    for e in spec.get("edges", []):
        if isinstance(e, str):
            m = re.match(r"\s*([\w.-]+)\s*->\s*([\w.-]+)\s*(?::\s*(.*))?$", e)
            if not m:
                sys.exit(f"can't read edge {e!r}: write 'a -> b : variable'")
            out.append({"from": m.group(1), "to": m.group(2), "carries": (m.group(3) or "").strip()})
        else:
            out.append({"from": e["from"], "to": e["to"], "carries": str(e.get("carries") or "").strip()})
    return out


def strength(check):
    if not check:
        return "missing"
    for pat, s in STRENGTH:
        if re.search(pat, check, re.I):
            return s
    return "unknown"


def cycles(nodes, edges):
    """Nodes that sit on a cycle (Tarjan's SCC; self-loops count)."""
    adj = defaultdict(list)
    for e in edges:
        adj[e["from"]].append(e["to"])
    idx, low, on, stack, out, n = {}, {}, set(), [], [], [0]

    def visit(v):
        idx[v] = low[v] = n[0]
        n[0] += 1
        stack.append(v)
        on.add(v)
        for w in adj[v]:
            if w not in idx:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], idx[w])
        if low[v] == idx[v]:
            comp = []
            while True:
                w = stack.pop()
                on.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 or v in adj[v]:
                out.append(comp)

    for v in nodes:
        if v not in idx:
            visit(v)
    return out


def waves(nodes, edges, cyc):
    """Topological levels ignoring back-edges inside cycles; each wave can run in parallel."""
    in_cycle = {v for c in cyc for v in c}
    deps = defaultdict(set)
    for e in edges:
        if not (e["from"] in in_cycle and e["to"] in in_cycle):
            deps[e["to"]].add(e["from"])
    level, done = {}, set()
    remaining = list(nodes)
    while remaining:
        ready = [v for v in remaining if deps[v] <= done]
        if not ready:  # unresolved cycle across components: break it deterministically
            ready = [remaining[0]]
        for v in ready:
            level[v] = 1 + max((level[d] for d in deps[v] if d in level), default=-1)
        done |= set(ready)
        remaining = [v for v in remaining if v not in done]
    out = defaultdict(list)
    for v, l in level.items():
        out[l].append(v)
    return [sorted(out[k]) for k in sorted(out)], deps


def critical_path(nodes, deps, order):
    finish = {}
    for wave in order:
        for v in wave:
            m = float(nodes[v].get("minutes") or 0)
            finish[v] = m + max((finish[d] for d in deps[v] if d in finish), default=0)
    return max(finish.values(), default=0)


def who_draws(runs, worst):
    recurring = str(runs).lower() not in ("once", "one-off", "oneoff")
    risky = worst in ("hard", "irreversible")
    if not recurring and not risky:
        return "One-off, cheap to undo: let the model generate the workflow and throw it away afterwards."
    if not recurring:
        return "One-off but hard to undo: let the model draft the plan, and read only the plan before it runs."
    if not risky:
        return "Recurring and low-risk: keep this graph fixed in the repo and let it ship. Don't regenerate it each run."
    return "Recurring and hard to undo: fixed graph in the repo, and a person signs the last irreversible step."


def check(spec):
    nodes, edges, inputs = spec.get("nodes") or {}, edges_of(spec), set(spec.get("inputs") or [])
    fs = []

    def add(sev, rule, where, msg):
        fs.append({"severity": sev, "rule": rule, "where": where, "message": msg})

    if not nodes:
        add("error", "no-nodes", "-", "The spec has no nodes.")
        return fs, {}
    for e in edges:
        for end in ("from", "to"):
            if e[end] not in nodes:
                add("error", "unknown-node", f"{e['from']} -> {e['to']}", f"'{e[end]}' isn't a node.")
    edges = [e for e in edges if e["from"] in nodes and e["to"] in nodes]

    # contracts
    for nid, n in nodes.items():
        miss = [k for k in CONTRACT if not n.get(k)]
        if miss:
            add("error", "contract", nid, f"Missing {', '.join(miss)}. A node you can't describe in four lines can't be tested or swapped.")

    # the arrow test
    for e in edges:
        w = f"{e['from']} -> {e['to']}"
        if not e["carries"]:
            add("error", "arrow-carries-nothing", w,
                "Name the variable this arrow carries, or delete it so both steps run in parallel.")
            continue
        outs, ins = set(nodes[e["from"]].get("out") or []), set(nodes[e["to"]].get("in") or [])
        if e["carries"] not in outs:
            add("error", "arrow-not-produced", w, f"'{e['carries']}' isn't in {e['from']}'s outputs {sorted(outs)}.")
        if e["carries"] not in ins:
            add("warn", "arrow-not-read", w,
                f"{e['to']} doesn't list '{e['carries']}' as an input: the order may come from the sentence, not the work.")

    # every input has a source
    fed = defaultdict(set)
    for e in edges:
        fed[e["to"]].add(e["carries"])
    for nid, n in nodes.items():
        for v in n.get("in") or []:
            if v not in inputs and v not in fed[nid]:
                add("error", "input-without-source", nid, f"Input '{v}' isn't a run input and no arrow brings it.")

    # model or code
    for nid, n in nodes.items():
        job, kind = str(n.get("job", "")), str(n.get("kind", "")).lower()
        if kind == "model" and DETERMINISTIC.search(job) and not JUDGEMENT.search(job):
            add("warn", "model-doing-code", nid,
                "Merging, de-duplicating, sorting and joining have one right answer: make this code. A model is slower, costlier and sometimes wrong.")
        if kind == "code" and JUDGEMENT.search(job) and not DETERMINISTIC.search(job):
            add("info", "code-doing-judgement", nid, "This job judges or writes: it probably needs a model.")
        if kind == "model" and not n.get("size"):
            add("info", "model-size", nid, "Pick a size: small for extraction and routing, strong for synthesis and judgement.")
        if not kind:
            add("warn", "kind", nid, "Say whether this is a model or code.")

    # checks
    for nid, n in nodes.items():
        s = strength(n.get("check"))
        if s in ("missing", "noise"):
            add("error", "no-real-check", nid,
                f"Check is {'missing' if s == 'missing' else repr(n.get('check'))}. A loop needs a check a program can fail: tests, a schema, a diff inside the plan.")
        elif s == "weak":
            add("warn", "weak-check", nid, "A reviewer agent is one more opinion. Put a program check (tests, schema) in front of it.")
        elif s == "unknown":
            add("info", "check-unclear", nid, f"Can't tell how strong '{n.get('check')}' is. Prefer something that exits non-zero on failure.")

    # loops
    cyc = cycles(nodes, edges)
    for comp in cyc:
        unbounded = [v for v in comp if not nodes[v].get("max_rounds")]
        if unbounded:
            add("error", "unbounded-cycle", " -> ".join(sorted(comp)),
                f"Cycle with no round limit on {', '.join(sorted(unbounded))}. Set max_rounds (and a budget).")
    for nid, n in nodes.items():
        if str(n.get("on_fail", "")).lower() == "repair" and not n.get("max_rounds"):
            add("warn", "repair-without-limit", nid, "Repairs need a limit: after 3 failed repairs, escalate (the plan is wrong).")

    # fan-out contexts
    children = defaultdict(list)
    for e in edges:
        children[e["from"]].append(e["to"])
    roots = [v for v in nodes if not any(e["to"] == v for e in edges)]
    groups = list(children.values()) + [roots]
    for grp in groups:
        sib = [v for v in set(grp) if str(nodes[v].get("kind")).lower() == "model"]
        shared = [v for v in sib if str(nodes[v].get("context", "")).lower() == "shared"]
        if len(sib) > 1 and shared:
            add("warn", "shared-context", ", ".join(sorted(shared)),
                "Parallel workers in one shared context copy each other's first answer. Give each its own context.")

    # gates
    for nid, n in nodes.items():
        undo, gate = str(n.get("undo", "")).lower(), str(n.get("gate", "")).lower()
        if "confiden" in gate or "threshold" in gate or "score" in gate:
            add("warn", "confidence-gate", nid, "Confidence is the model's opinion of itself. Gate on how hard a mistake is to undo.")
        if undo == "irreversible" and gate != "human":
            add("error", "open-irreversible", nid, "Migrations, deletions, production writes and payments stay closed: gate must be 'human'.")
        elif undo == "hard" and gate == "auto":
            add("warn", "hard-undo-auto", nid, "Hard to undo but auto-approved: require strong evidence ('evidence') first.")
        elif undo in ("free", "revert") and gate == "human":
            add("info", "human-on-cheap-step", nid, "A person approves a step that costs one revert: let it merge on a passing check.")
        if not undo:
            add("warn", "undo", nid, "Say how hard a mistake here is to undo (free, revert, hard, irreversible).")
        if not n.get("on_fail"):
            add("info", "on-fail", nid, "Decide failure handling now: retry blips, fall back on outages, repair this unit only, escalate after 3.")

    # timing after the arrow test: arrows that carry nothing (or carry what the target never reads) are dropped
    real = [e for e in edges if e["carries"] and e["carries"] in (nodes[e["to"]].get("in") or [])]
    order, deps = waves(nodes, real, [c for c in cyc if all(v in nodes for v in c)])
    timed = all(n.get("minutes") is not None for n in nodes.values())
    drawn = spec.get("drawn_order") or [v for w in order for v in w]
    stats = {"waves": order, "cycles": cyc, "timed": timed,
             "serial_minutes": sum(float(nodes[v].get("minutes") or 0) for v in drawn) if timed else None,
             "critical_minutes": critical_path(nodes, deps, order) if timed else None,
             "worst_undo": max((str(n.get("undo", "free")).lower() for n in nodes.values()),
                               key=lambda u: ["free", "revert", "hard", "irreversible"].index(u)
                               if u in ["free", "revert", "hard", "irreversible"] else 0)}
    uniq = {(f["rule"], f["where"]): f for f in fs}
    fs = sorted(uniq.values(), key=lambda f: (SEV[f["severity"]], f["rule"], f["where"]))
    return fs, stats


def mermaid(spec):
    nodes, lines = spec.get("nodes") or {}, ["flowchart LR"]
    for nid, n in nodes.items():
        shape = ("[[", "]]") if str(n.get("gate", "")).lower() == "human" else (("(", ")") if n.get("kind") == "code" else ("[", "]"))
        label = f"{nid}<br/>{n.get('kind', '?')}{'/' + n['size'] if n.get('size') else ''} · {n.get('minutes', '?')}m"
        lines.append(f'  {nid}{shape[0]}"{label}"{shape[1]}')
    for e in edges_of(spec):
        lines.append(f"  {e['from']} -->|{e['carries'] or '??'}| {e['to']}" if e["carries"] else f"  {e['from']} -.-> {e['to']}")
    return "\n".join(lines) + "\n"


def report(spec, fs, st):
    c = {s: sum(1 for f in fs if f["severity"] == s) for s in SEV}
    md = [f"# Graph check: {spec.get('name', 'pipeline')}", "",
          f"{len(spec.get('nodes') or {})} nodes: **{c['error']} error(s)**, {c['warn']} warning(s), {c['info']} note(s).", ""]
    if st.get("waves"):
        md += ["## Run order", "", "Each wave can run in parallel; a wave waits only for what it reads "
               "(arrows that carry nothing are left out).", ""]
        md += [f"{i}. {', '.join(w)}" for i, w in enumerate(st["waves"], 1)]
        md.append("")
        if st["timed"]:
            md.append(f"As drawn in a line: **{st['serial_minutes']:g} min**. As a graph: **{st['critical_minutes']:g} min** "
                      f"(critical path). Same work, fewer waits.")
            md.append("")
        md += ["## Who should draw this graph", "", who_draws(spec.get("runs", "recurring"), st["worst_undo"]), ""]
    md += ["## Findings", ""]
    if not fs:
        md.append("No problems found.")
    md += [f"- **[{f['severity']}] {f['where']}** `{f['rule']}`: {f['message']}" for f in fs]
    md += ["", "## Diagram", "", "```mermaid", mermaid(spec).rstrip(), "```", "",
           "Square-bracket nodes are models, round ones code, double-bordered ones wait for a person. A dotted arrow carries nothing."]
    return "\n".join(md) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    p = sub.add_parser("check")
    p.add_argument("spec")
    p.add_argument("--out", default="./graph-report")
    p.add_argument("--fail-on", choices=["error", "warn"])
    a = ap.parse_args(argv)
    if a.cmd == "init":
        print(json.dumps(TEMPLATE, indent=2))
        return
    spec = load_spec(a.spec)
    fs, st = check(spec)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.md").write_text(report(spec, fs, st))
    (out / "graph.mmd").write_text(mermaid(spec))
    (out / "findings.json").write_text(json.dumps({"findings": fs, "stats": st}, indent=1) + "\n")
    c = {s: sum(1 for f in fs if f["severity"] == s) for s in SEV}
    timing = f", {st['serial_minutes']:g} -> {st['critical_minutes']:g} min" if st.get("timed") else ""
    print(f"graph_check: {c['error']} error(s), {c['warn']} warning(s){timing} -> {out}/report.md")
    if a.fail_on and any(SEV[f["severity"]] <= SEV[a.fail_on] for f in fs):
        sys.exit(1)


if __name__ == "__main__":
    main()
