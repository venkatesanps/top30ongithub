#!/usr/bin/env python3
"""Deterministic parts of a Snowflake data-engineering agent team.

The agents (sf-researcher, sf-drafter, sf-critic, sf-refiner) do the thinking. This script does
what has one right answer, so no model has to be trusted with it:

  route    "<task>"            which agents run, in what order, on which models
  kickoff  --task ... --out D  shared context, team.json and the run folder layout
  gate     file.sql            is this SQL safe to run here? (read-only, dev writes, prod = human)
  hook                         the same gate as a Claude Code PreToolUse hook (exit 2 blocks)
  check-findings  file.md      researcher output: Finding -> Source -> Confidence
  check-critique  file.md      critic output: rated problems, no fixes, strongest parts last
  check-refine    critique.md notes.md   every Critical and Major problem has a fix note
  verify   D                   runs every check on a run folder and says what's next

Standard library only. Never connects to Snowflake.
Exit codes: 0 ok, 1 findings at or above --fail-on, 2 bad input.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SEV_ORDER = {"info": 0, "warn": 1, "error": 2}

# ---------------------------------------------------------------- routing

PRIORITY = ["incident", "review", "migrate", "tune", "cost", "build", "research"]
MODELS = {"sonnet": "opus", "opus": "sonnet", "haiku": "sonnet"}

TASK_TYPES = {
    # type: (keywords, steps, what done looks like)
    "incident": (
        ["fail", "failed", "failing", "error", "broke", "broken", "stuck", "didn't run", "did not run",
         "late", "missing rows", "why did", "ran long", "timed out", "timeout", "alert"],
        ["pipeline-failure-triage"],
        "a triage note with the first real error, root cause, smallest safe fix and re-run plan",
    ),
    "cost": (
        ["credit", "credits", "cost", "spend", "bill", "expensive", "finops", "budget", "warehouse size"],
        ["sf-researcher:cost", "sf-critic", "sf-refiner"],
        "a cost report where every finding has the ACCOUNT_USAGE query behind it and a fix statement",
    ),
    "tune": (
        ["slow", "tune", "tuning", "optimize", "optimise", "speed up", "explain plan", "query profile",
         "spill", "pruning", "performance"],
        ["sf-researcher:tune", "sf-drafter", "sf-critic", "sf-refiner"],
        "a rewritten query with the plan before and after and the advisor findings resolved",
    ),
    "migrate": (
        ["oracle", "pl/sql", "plsql", "migrate", "migration", "teradata", "port to snowflake", "convert"],
        ["sf-researcher", "sf-drafter:migrate", "sf-critic", "sf-refiner"],
        "translated SQL with ora2sf findings resolved and a row-count/checksum test per object",
    ),
    "build": (
        ["build", "create", "new model", "dbt", "pipeline", "ingest", "load", "snowpipe", "stream",
         "task", "dynamic table", "merge", "scd", "incremental", "elt", "etl", "stage", "copy into"],
        ["sf-researcher", "sf-drafter", "sf-critic", "sf-refiner"],
        "SQL/dbt files that pass the gate and the critic, with tests and a deploy note for a human",
    ),
    "review": (
        ["review", "pull request", " pr ", "check my sql", "code review", "audit this sql", "look over"],
        ["sf-critic:security", "sf-critic:correctness", "sf-critic:performance", "sf-critic:style"],
        "one merged critique, problems rated Critical/Major/Minor, strongest parts last",
    ),
    "research": (
        ["what tables", "which tables", "lineage", "where is", "who uses", "document", "find", "explore",
         "inventory", "data dictionary", "how is", "column"],
        ["sf-researcher"],
        "sourced findings, each with the query or file it came from and a confidence",
    ),
}
STEP_INFO = {
    "pipeline-failure-triage": ("agent", "existing read-only triage agent in this plugin"),
    "sf-researcher": ("agent", "read-only metadata and profiling"),
    "sf-researcher:cost": ("agent", "uses snowflake-cost-investigator (sf_cost.py)"),
    "sf-researcher:tune": ("agent", "uses snowflake-query-advisor (sf_query_advisor.py)"),
    "sf-drafter": ("agent", "writes files only; never runs DDL/DML"),
    "sf-drafter:migrate": ("agent", "uses oracle-to-snowflake (ora2sf.py)"),
    "sf-critic": ("agent", "own context, the other model, rates problems, suggests no fixes"),
    "sf-refiner": ("agent", "fixes every Critical and Major, one note per fix"),
}


def route(task, drafter_model="sonnet"):
    t = " " + task.lower() + " "
    scores = {}
    for name, (kws, _, _) in TASK_TYPES.items():
        hits = [k for k in kws if k in t]
        if hits:
            scores[name] = hits
    if not scores:
        return {"type": "unclear", "ask": "Is this a failure to triage, a cost question, a slow query, a "
                "migration, something to build, a review, or a question about the data?", "steps": []}
    # incident first: fixing forward before knowing why is the classic mistake. Then review (the
    # user has the code already), then the specific kinds, with build and research as catch-alls.
    if "incident" in scores:
        best = "incident"
    else:
        top = max(len(v) for v in scores.values())
        best = next(k for k in PRIORITY if len(scores.get(k, [])) == top)
        if best in ("build", "research") and "review" in scores:
            best = "review"
    hits = scores[best]
    also = [k for k in PRIORITY if k in scores and k != best]
    critic_model = MODELS.get(drafter_model, "opus")
    steps = []
    for s in TASK_TYPES[best][1]:
        base, _, mode = s.partition(":")
        model = critic_model if base == "sf-critic" else (drafter_model if base in ("sf-drafter", "sf-refiner")
                                                          else "sonnet")
        steps.append({"agent": base, "mode": mode or None, "model": model, "note": STEP_INFO.get(s, STEP_INFO.get(base, ("", "")))[1]
                      + (f"; lens: {mode}" if base == "sf-critic" and mode else "")})
    out = {"type": best, "matched": hits, "also": also, "steps": steps, "done_when": TASK_TYPES[best][2],
           "parallel": best == "review",
           "gates": ["de_team.py gate on every .sql before anything runs",
                     "a person approves any DDL/DML outside the dev databases"]}
    if best == "review":
        out["merge"] = "concatenate the four critiques; keep the highest rating when two lenses flag the same line"
    return out


# ---------------------------------------------------------------- SQL gate

READ_VERBS = {"SELECT", "WITH", "SHOW", "DESCRIBE", "DESC", "EXPLAIN", "LIST", "LS", "USE", "VALUES", "GET"}
KINDS = (r"(?:SECURE\s+)?(?:(?:TRANSIENT|TEMPORARY|TEMP|VOLATILE|LOCAL|GLOBAL)\s+)*"
         r"(?:DYNAMIC\s+TABLE|MATERIALIZED\s+VIEW|EXTERNAL\s+TABLE|ICEBERG\s+TABLE|HYBRID\s+TABLE|FILE\s+FORMAT|"
         r"TABLE|VIEW|SCHEMA|DATABASE|STAGE|TASK|STREAM|PIPE|PROCEDURE|FUNCTION|SEQUENCE|WAREHOUSE|ROLE|USER|"
         r"TAG|MASKING\s+POLICY|ROW\s+ACCESS\s+POLICY|INTEGRATION|SHARE|ALERT)")
NAME = r'((?:"[^"]+"|[\w$@~]+)(?:\.(?:"[^"]+"|[\w$]+)){0,2})'
TARGETS = [
    re.compile(r"^INSERT\s+(?:OVERWRITE\s+)?(?:ALL\s+|FIRST\s+)?INTO\s+" + NAME, re.I),
    re.compile(r"^UPDATE\s+" + NAME, re.I),
    re.compile(r"^DELETE\s+FROM\s+" + NAME, re.I),
    re.compile(r"^MERGE\s+INTO\s+" + NAME, re.I),
    re.compile(r"^TRUNCATE\s+(?:TABLE\s+)?(?:IF\s+EXISTS\s+)?" + NAME, re.I),
    re.compile(r"^COPY\s+INTO\s+" + NAME, re.I),
    re.compile(r"^(?:DROP|UNDROP)\s+" + KINDS + r"\s+(?:IF\s+EXISTS\s+)?" + NAME, re.I),
    re.compile(r"^CREATE\s+(?:OR\s+REPLACE\s+)?" + KINDS + r"\s+(?:IF\s+NOT\s+EXISTS\s+)?" + NAME, re.I),
    re.compile(r"^ALTER\s+" + KINDS + r"\s+(?:IF\s+EXISTS\s+)?" + NAME, re.I),
]
ADMIN_ROLES = {"ACCOUNTADMIN", "SECURITYADMIN", "ORGADMIN", "USERADMIN"}


def strip_sql(text):
    """Blank out comments and string literals (keeping line breaks) and pull out $$ bodies."""
    out, bodies, i, n = [], [], 0, len(text)
    while i < n:
        c, nxt = text[i], text[i:i + 2]
        if nxt == "--" or nxt == "//":
            j = text.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif nxt == "/*":
            j = text.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append(re.sub(r"[^\n]", " ", text[i:j]))
            i = j
        elif nxt == "$$":
            j = text.find("$$", i + 2)
            j = n if j < 0 else j + 2
            bodies.append(text[i + 2:j - 2])
            out.append("$BODY" + "\n" * text.count("\n", i, j))
            i = j
        elif c == "'":
            j = i + 1
            while j < n:
                if text[j] == "\\":
                    j += 2
                    continue
                if text[j] == "'":
                    if text[j + 1:j + 2] == "'":
                        j += 2
                        continue
                    break
                j += 1
            out.append("''" + "\n" * text.count("\n", i, j + 1))
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out), bodies


def statements(text):
    clean, bodies = strip_sql(text)
    res, line, start = [], 1, 0
    for part in clean.split(";"):
        s = part.strip()
        if s:
            lead = part[:len(part) - len(part.lstrip())]
            res.append((line + lead.count("\n"), s))
        line += part.count("\n")
    return res, bodies


def db_of(name, kind, current_db):
    parts = [p.strip('"').upper() for p in re.findall(r'"[^"]+"|[^.]+', name)]
    if kind == "DATABASE":
        return parts[0]
    if kind == "SCHEMA":
        return parts[0] if len(parts) == 2 else current_db
    if name.startswith("@"):
        parts[0] = parts[0].lstrip("@~")
        if parts[0] == "" or name.startswith("@~") or name.startswith("@%"):
            return current_db
    return parts[0] if len(parts) == 3 else current_db


def classify(stmt):
    first = re.match(r"\(?\s*([A-Za-z]+)", stmt)
    verb = first.group(1).upper() if first else ""
    if verb in READ_VERBS:
        if verb == "WITH" and re.search(r"\)\s*(INSERT|UPDATE|DELETE|MERGE)\b", stmt, re.I):
            return "write", verb
        return "read", verb
    return "write", verb


def gate(text, cfg, fname="<sql>"):
    dev = {d.upper() for d in cfg.get("dev_databases", [])}
    prod = {d.upper() for d in cfg.get("prod_databases", [])}
    current_db = (cfg.get("current_database") or "").upper() or None
    findings = []

    def add(sev, line, rule, msg):
        findings.append({"severity": sev, "file": fname, "line": line, "rule": rule, "msg": msg})

    stmts, bodies = statements(text)
    for b in bodies:
        if re.search(r"\b(INSERT|UPDATE|DELETE|MERGE|DROP|TRUNCATE|EXECUTE\s+IMMEDIATE)\b", b, re.I):
            add("warn", None, "body", "a $$ procedure/function body writes data; the gate can't see its targets, "
                "so a person reads it before the CALL")
    for line, s in stmts:
        flat = re.sub(r"\s+", " ", s)
        kind, verb = classify(flat)
        if verb == "USE":
            m = re.match(r"USE\s+(ROLE|DATABASE|SCHEMA|WAREHOUSE|SECONDARY\s+ROLES)?\s*" + NAME, flat, re.I)
            if m:
                what, val = (m.group(1) or "DATABASE").upper(), m.group(2).strip('"').upper()
                if what == "ROLE" and val in ADMIN_ROLES:
                    add("error", line, "admin-role", f"USE ROLE {val}: the team works with a scoped role, never {val}")
                elif what == "DATABASE":
                    current_db = val
                elif what == "SCHEMA" and "." in val:
                    current_db = val.split(".")[0]
            continue
        if kind == "read":
            continue
        if verb in ("GRANT", "REVOKE"):
            add("error", line, "grants", f"{verb} changes access; a person runs it")
            continue
        if verb in ("CALL", "EXECUTE"):
            add("warn", line, "opaque", f"{verb}: what it does isn't visible here; review the procedure first")
            continue
        if verb in ("PUT", "REMOVE", "RM"):
            add("warn", line, "stage-files", f"{verb} changes files on a stage")
            continue
        target, tkind = None, "TABLE"
        for rx in TARGETS:
            m = rx.match(flat)
            if m:
                target = m.group(1)
                km = re.match(r"^(?:CREATE\s+(?:OR\s+REPLACE\s+)?|DROP\s+|UNDROP\s+|ALTER\s+)" + "(" + KINDS + ")", flat, re.I)
                if km:
                    tkind = re.sub(r"\s+", " ", km.group(1).upper()).split()[-1]
                break
        if re.match(r"ALTER\s+ACCOUNT\b", flat, re.I) or tkind in ("WAREHOUSE", "ROLE", "USER", "INTEGRATION", "SHARE") \
                and verb in ("CREATE", "ALTER", "DROP"):
            add("error", line, "account-object", f"{verb} {tkind if target else 'ACCOUNT'} changes the account, not a "
                "pipeline; a person runs it")
            continue
        temp = bool(re.match(r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:LOCAL\s+|GLOBAL\s+)?(TEMPORARY|TEMP|VOLATILE)\b", flat, re.I))
        if temp:
            add("info", line, "temp", "temporary object: session-scoped, allowed")
            continue
        db = db_of(target, tkind, current_db) if target else current_db
        where = f"{target} " if target else ""
        if verb in ("DELETE", "UPDATE") and not re.search(r"\bWHERE\b", flat, re.I):
            add("error", line, "no-where", f"{verb} {where}has no WHERE: it touches every row")
        if verb in ("DROP", "TRUNCATE") or (verb == "CREATE" and re.match(r"CREATE\s+OR\s+REPLACE\s+(?:TRANSIENT\s+)?TABLE\b", flat, re.I)):
            what = "CREATE OR REPLACE TABLE drops the existing table and its rows" if verb == "CREATE" else f"{verb} removes data"
            sev = "warn" if db in dev else "error"
            add(sev, line, "destructive", f"{what} ({where.strip() or 'unknown target'}); "
                + ("allowed in dev, check it's intended" if sev == "warn" else "a person approves it"))
            if sev == "error":
                continue
        if db is None:
            add("error", line, "unqualified", f"{verb} {where}has no database and no USE DATABASE before it; "
                "qualify it as DB.SCHEMA.OBJECT so the gate can tell dev from prod")
        elif db in prod or (dev and db not in dev):
            add("error", line, "prod-write", f"{verb} {where}writes to {db}, which isn't a dev database; "
                "the drafter writes the file, a person deploys it")
        elif db in dev:
            add("info", line, "dev-write", f"{verb} {where}in dev database {db}")
        else:
            add("warn", line, "unknown-db", f"{verb} {where}in {db}: set dev_databases in team.json so writes can be judged")
    reads = sum(1 for _, s in stmts if classify(re.sub(r"\s+", " ", s))[0] == "read")
    return {"file": fname, "statements": len(stmts), "read_only": reads == len(stmts) and not bodies,
            "findings": findings}


def command_sql(cmd):
    """Pull SQL out of a `snow sql` / `snowsql` shell command, or None if it isn't one."""
    if not re.search(r"\b(snow\s+sql|snowsql)\b", cmd):
        return None
    m = re.search(r"""(?:-q|--query)[\s=]+(?:"((?:[^"\\]|\\.)*)"|'([^']*)'|(\S+))""", cmd)
    if m:
        return next(g for g in m.groups() if g is not None).replace('\\"', '"')
    f = re.search(r"(?:-f|--filename)[\s=]+(\S+)", cmd)
    if f:
        p = Path(f.group(1).strip("'\""))
        return p.read_text(errors="replace") if p.exists() else ""
    return ""


# ---------------------------------------------------------------- output checks

ARROW = r"\s*(?:→|->|=>)\s*"
FINDING = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*(?P<finding>.+?)" + ARROW + r"(?P<source>.+?)" + ARROW +
                     r"\[?\s*Confidence\s*:\s*(?P<conf>\w+)\s*\]?\s*$", re.I)
WEAK_SOURCE = re.compile(r"^\s*(none|n/a|assumed?|assumption|i think|probably|likely|memory|general knowledge|"
                         r"common practice|best practice|unknown)\b", re.I)
SOURCE_SHAPE = re.compile(r"(\w+\.\w+|\.sql\b|\.ya?ml\b|\.py\b|:\d+|\bquery\b|\bquery_id\b|SELECT|SHOW|DESCRIBE|"
                          r"INFORMATION_SCHEMA|ACCOUNT_USAGE|GET_DDL|EXPLAIN|log\b|commit\b|https?://)", re.I)
RECENT = re.compile(r"\b(last|past)\s+(hour|\d+\s*min|30\s*minutes)|\btoday\b|\bjust now\b|\bright now\b|\bin the last hour\b", re.I)


def check_findings(text):
    fs, items = [], []
    for i, raw in enumerate(text.splitlines(), 1):
        if not re.search(r"→|->|=>", raw) or raw.strip().startswith(("#", "```", "|")):
            continue
        m = FINDING.match(raw)
        if not m:
            fs.append({"severity": "error", "line": i, "rule": "format",
                       "msg": "a finding needs '[Finding] → [Source] → [Confidence: High/Medium/Low]'"})
            continue
        conf = m.group("conf").capitalize()
        src = m.group("source").strip(" []")
        items.append({"line": i, "finding": m.group("finding").strip(" []"), "source": src, "confidence": conf})
        if conf not in ("High", "Medium", "Low"):
            fs.append({"severity": "error", "line": i, "rule": "confidence", "msg": f"confidence '{conf}' isn't High/Medium/Low"})
        if not src or WEAK_SOURCE.match(src):
            fs.append({"severity": "error", "line": i, "rule": "source", "msg": f"'{src or 'empty'}' isn't a source; "
                       "move it to Unverified or name the query, view or file"})
        elif conf == "High" and not SOURCE_SHAPE.search(src):
            fs.append({"severity": "warn", "line": i, "rule": "source",
                       "msg": f"High confidence from '{src}': name the query, view, file:line or log it came from"})
        if "ACCOUNT_USAGE" in src.upper() and RECENT.search(raw):
            fs.append({"severity": "warn", "line": i, "rule": "latency",
                       "msg": "ACCOUNT_USAGE lags (45 min to 3 h by view); for the last hour use INFORMATION_SCHEMA table functions"})
    if not items:
        fs.append({"severity": "error", "line": None, "rule": "empty", "msg": "no findings in the expected format"})
    return {"findings_count": len(items), "items": items, "findings": fs}


PROBLEM = re.compile(r"^\s*(?:[-*•]|\d+[.)])?\s*(?:\*\*)?(?P<id>[A-Z]\d+)?\s*:?\s*(?:\*\*)?\s*"
                     r"\[(?P<sev>Critical|Major|Minor)\]\s*(?P<rest>.*)$", re.I)
FIX_WORDS = re.compile(r"\b(instead|replace (?:it |this )?with|change (?:it |this )?to|rewrite (?:it |this )?as|"
                       r"fix(?:ed)? by|you (?:should|could|can) (?:use|add|change)|consider (?:using|adding)|"
                       r"recommend|suggest(?:ion)?|try (?:using|adding))\b", re.I)
LOCATION = re.compile(r"(\S+\.(sql|ya?ml|py|md):\d+|\bline\s+\d+|\bstatement\s+\d+|\bL\d+\b|`[^`]+`)", re.I)


def check_critique(text):
    lines = text.splitlines()
    fs, problems = [], []
    strongest = None
    for i, raw in enumerate(lines, 1):
        if re.search(r"strongest", raw, re.I) and (raw.lstrip().startswith("#") or raw.strip().endswith(":")
                                                   or raw.strip().startswith("**")):
            strongest = i
        m = PROBLEM.match(raw)
        if not m:
            continue
        sev, pid, rest = m.group("sev").capitalize(), m.group("id"), m.group("rest")
        problems.append({"line": i, "id": pid, "severity": sev, "text": rest.strip()})
        if not pid:
            fs.append({"severity": "error", "line": i, "rule": "id", "msg": "give each problem an id (P1, P2...) so the refiner can answer it"})
        if FIX_WORDS.search(rest):
            fs.append({"severity": "error", "line": i, "rule": "no-fixes",
                       "msg": "the critic names problems and why they matter; fixes are the refiner's job"})
        if not LOCATION.search(rest):
            fs.append({"severity": "warn", "line": i, "rule": "location", "msg": "say where: file:line, statement N or the `code`"})
    ids = [p["id"] for p in problems if p["id"]]
    for d in sorted({x for x in ids if ids.count(x) > 1}):
        fs.append({"severity": "error", "line": None, "rule": "id", "msg": f"id {d} is used twice"})
    clean = re.search(r"\bno (critical|major|real)? ?problems\b|\bnothing (critical|major) found\b", text, re.I)
    if not problems and not clean:
        fs.append({"severity": "error", "line": None, "rule": "empty",
                   "msg": "no rated problems; if there are none, say 'No problems found' and why"})
    if strongest is None:
        fs.append({"severity": "error", "line": None, "rule": "strongest", "msg": "end with a 'Strongest parts' section"})
    elif problems and strongest < max(p["line"] for p in problems):
        fs.append({"severity": "warn", "line": strongest, "rule": "strongest", "msg": "'Strongest parts' goes last, after the problems"})
    counts = {s: sum(1 for p in problems if p["severity"] == s) for s in ("Critical", "Major", "Minor")}
    return {"problems": problems, "counts": counts, "findings": fs}


def check_refine(critique, notes):
    c = check_critique(critique)
    must = [p for p in c["problems"] if p["severity"] in ("Critical", "Major") and p["id"]]
    fs, answered = [], {}
    for i, raw in enumerate(notes.splitlines(), 1):
        m = re.match(r"^\s*(?:[-*•]\s*)?(?:\*\*)?([A-Z]\d+)(?:\*\*)?\s*[:\-–—]\s*(.*)$", raw)
        if m:
            answered.setdefault(m.group(1).upper(), []).append((i, m.group(2).strip()))
    for p in must:
        got = answered.get(p["id"].upper())
        if not got:
            fs.append({"severity": "error", "line": None, "rule": "unanswered",
                       "msg": f"{p['id']} [{p['severity']}] has no fix note"})
            continue
        ln, txt = got[0]
        if re.match(r"(?i)(won't fix|wontfix|skipped|not fixed|ignored|disagree)", txt) and len(txt.split()) < 6:
            fs.append({"severity": "error", "line": ln, "rule": "reason", "msg": f"{p['id']} not fixed without a reason"})
        if len(got) > 1:
            fs.append({"severity": "warn", "line": got[1][0], "rule": "one-line", "msg": f"{p['id']} has more than one note"})
    known = {p["id"].upper() for p in c["problems"] if p["id"]}
    for k, v in answered.items():
        if k not in known:
            fs.append({"severity": "warn", "line": v[0][0], "rule": "unknown-id", "msg": f"{k} isn't in the critique"})
    return {"must_fix": [p["id"] for p in must], "answered": sorted(answered), "findings": fs}


# ---------------------------------------------------------------- kickoff and verify

CONTEXT = """# Shared context: {title}

Every agent reads this first. Edit it; don't repeat it in prompts.

## Task
{task}

Route: **{type}** ({steps})
Done when: {done}

## Environment
- Snowflake account / connection name: <fill in; never a password or key>
- Role the team uses (read-only for research): <e.g. DE_READONLY>
- Dev databases (the only place writes are allowed): {dev}
- Prod databases (no agent writes here, ever): {prod}
- Warehouse for research queries (XS is enough): <e.g. DE_RESEARCH_WH>
- dbt project path, if any: <path>

## Conventions
- Names: <e.g. STG_/INT_/FCT_/DIM_ prefixes, snake_case columns, UTC timestamps as TIMESTAMP_NTZ>
- Every model has a primary key test and a freshness or row-count check.
- Incremental loads are idempotent: MERGE on a declared key, never blind INSERT on re-run.

## Constraints
- Research is SELECT / SHOW / DESCRIBE only.
- Drafts are files. Nothing runs outside dev; a person deploys.
- No customer data in prompts, findings or commits: counts and column names, not values.
"""


def kickoff(task, out, dev, prod, drafter_model):
    r = route(task, drafter_model)
    out.mkdir(parents=True, exist_ok=True)
    if r["type"] == "unclear":
        return r
    team = {"task": task, "route": r, "dev_databases": dev, "prod_databases": prod,
            "files": {"findings": "01-findings.md", "draft": "02-draft/", "critique": "03-critique.md",
                      "refined": "04-refined/", "notes": "04-fix-notes.md"}}
    (out / "team.json").write_text(json.dumps(team, indent=2) + "\n")
    ctx = out / "context.md"
    if not ctx.exists():
        ctx.write_text(CONTEXT.format(title=task[:60], task=task, type=r["type"],
                                      steps=" → ".join(s["agent"] + (f":{s['mode']}" if s["mode"] else "") for s in r["steps"]),
                                      done=r["done_when"], dev=", ".join(dev) or "<none set: every write is blocked>",
                                      prod=", ".join(prod) or "<fill in>"))
    for d in ("02-draft", "04-refined"):
        (out / d).mkdir(exist_ok=True)
    return dict(r, folder=str(out))


def verify(run):
    tj = run / "team.json"
    if not tj.exists():
        raise SystemExit(f"{tj} not found; run kickoff first")
    team = json.loads(tj.read_text())
    agents = [s["agent"] for s in team["route"]["steps"]]
    f = team["files"]
    stages, nxt = [], None

    def stage(name, path, result):
        bad = [x for x in result["findings"] if x["severity"] == "error"]
        stages.append({"stage": name, "path": str(path), "ok": not bad, "errors": len(bad),
                       "warnings": sum(1 for x in result["findings"] if x["severity"] == "warn"),
                       "findings": result["findings"]})
        return not bad

    def sql_stage(name, folder):
        files = sorted(p for p in (run / folder).rglob("*.sql"))
        if not files:
            return None
        allf = []
        for p in files:
            allf += gate(p.read_text(errors="replace"), team, str(p.relative_to(run)))["findings"]
        return stage(name, run / folder, {"findings": allf})

    if "sf-researcher" in agents:
        p = run / f["findings"]
        if not p.exists():
            nxt = nxt or "sf-researcher writes 01-findings.md"
        elif not stage("findings", p, check_findings(p.read_text())):
            nxt = nxt or "sf-researcher fixes 01-findings.md"
    if "sf-drafter" in agents:
        ok = sql_stage("draft gate", f["draft"])
        if ok is None:
            nxt = nxt or "sf-drafter writes SQL into 02-draft/"
        elif not ok:
            nxt = nxt or "sf-drafter fixes gate errors (or a person approves them) in 02-draft/"
    if "sf-critic" in agents:
        p = run / f["critique"]
        if not p.exists():
            nxt = nxt or "sf-critic writes 03-critique.md"
        elif not stage("critique", p, check_critique(p.read_text())):
            nxt = nxt or "sf-critic fixes the format of 03-critique.md"
    if "sf-refiner" in agents and (run / f["critique"]).exists():
        p = run / f["notes"]
        if not p.exists():
            nxt = nxt or "sf-refiner writes 04-refined/ and 04-fix-notes.md"
        else:
            stage("fix notes", p, check_refine((run / f["critique"]).read_text(), p.read_text()))
            if "sf-drafter" in agents:
                if sql_stage("refined gate", f["refined"]) is None:
                    stages.append({"stage": "refined gate", "path": str(run / f["refined"]), "ok": False, "errors": 1,
                                   "warnings": 0, "findings": [{"severity": "error", "line": None, "rule": "missing",
                                                                "msg": "no refined .sql files"}]})
            if not all(s["ok"] for s in stages):
                nxt = nxt or "sf-refiner answers every Critical and Major in 04-fix-notes.md and keeps 04-refined/ gate-clean"
    done = nxt is None and all(s["ok"] for s in stages)
    return {"run": str(run), "type": team["route"]["type"], "stages": stages,
            "next": "a person reviews 04-refined/ and deploys it" if done and "sf-drafter" in agents
            else ("done" if done else nxt), "done": done}


# ---------------------------------------------------------------- CLI

def load_cfg(path):
    if not path:
        return {}
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as e:
        raise SystemExit(f"can't read config {path}: {e}")


def emit(result, as_json, fail_on, render):
    if as_json:
        print(json.dumps(result, indent=2))
    else:
        render(result)
    worst = max((SEV_ORDER[f["severity"]] for f in result.get("findings", [])), default=-1)
    return 1 if worst >= SEV_ORDER[fail_on] else 0


def show_findings(fs, label=""):
    for f in fs:
        loc = ":".join(str(x) for x in (f.get("file") or label, f.get("line")) if x)
        print(f"  [{f['severity']}] {loc} {f['rule']}: {f['msg']}")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("route"); p.add_argument("task"); p.add_argument("--drafter-model", default="sonnet")
    p.add_argument("--json", action="store_true")
    p = sub.add_parser("kickoff"); p.add_argument("--task", required=True); p.add_argument("--out", required=True)
    p.add_argument("--dev", action="append", default=[]); p.add_argument("--prod", action="append", default=[])
    p.add_argument("--drafter-model", default="sonnet"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("gate"); p.add_argument("paths", nargs="+"); p.add_argument("--config")
    p.add_argument("--dev", action="append", default=[]); p.add_argument("--prod", action="append", default=[])
    p.add_argument("--json", action="store_true"); p.add_argument("--fail-on", default="error", choices=SEV_ORDER)
    p = sub.add_parser("hook"); p.add_argument("--config")
    p.add_argument("--dev", action="append", default=[]); p.add_argument("--prod", action="append", default=[])
    for name in ("check-findings", "check-critique"):
        p = sub.add_parser(name); p.add_argument("path"); p.add_argument("--json", action="store_true")
        p.add_argument("--fail-on", default="error", choices=SEV_ORDER)
    p = sub.add_parser("check-refine"); p.add_argument("critique"); p.add_argument("notes")
    p.add_argument("--json", action="store_true"); p.add_argument("--fail-on", default="error", choices=SEV_ORDER)
    p = sub.add_parser("verify"); p.add_argument("run"); p.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    def read(path):
        try:
            return Path(path).read_text(errors="replace")
        except OSError as e:
            print(f"can't read {path}: {e}", file=sys.stderr)
            sys.exit(2)

    if a.cmd == "route":
        r = route(a.task, a.drafter_model)
        if a.json:
            print(json.dumps(r, indent=2))
        elif r["type"] == "unclear":
            print(f"Unclear. Ask: {r['ask']}")
        else:
            print(f"Type: {r['type']}  (matched: {', '.join(r['matched'])})")
            for i, s in enumerate(r["steps"], 1):
                print(f"  {i}. {s['agent']}{':' + s['mode'] if s['mode'] else ''}  [{s['model']}]  {s['note']}")
            if r.get("parallel"):
                print(f"  run in parallel; merge: {r['merge']}")
            print(f"Done when: {r['done_when']}")
        return 0 if r["type"] != "unclear" else 3

    if a.cmd == "kickoff":
        r = kickoff(a.task, Path(a.out), a.dev, a.prod, a.drafter_model)
        if a.json:
            print(json.dumps(r, indent=2))
        elif r["type"] == "unclear":
            print(f"Unclear. Ask: {r['ask']}")
        else:
            print(f"Kicked off '{r['type']}' in {r['folder']}: fill in context.md, then run the steps; "
                  f"`verify {r['folder']}` says what's next.")
        return 0 if r["type"] != "unclear" else 3

    if a.cmd in ("gate", "hook"):
        cfg = load_cfg(a.config)
        cfg["dev_databases"] = cfg.get("dev_databases", []) + a.dev
        cfg["prod_databases"] = cfg.get("prod_databases", []) + a.prod

    if a.cmd == "gate":
        results = [gate(read(p), cfg, p) for p in a.paths]
        allf = [f for r in results for f in r["findings"]]

        def render(_):
            for r in results:
                print(f"{r['file']}: {r['statements']} statement(s), {'read-only' if r['read_only'] else 'writes'}")
                show_findings(r["findings"])
        return emit({"files": results, "findings": allf}, a.json, a.fail_on, render)

    if a.cmd == "hook":
        try:
            ev = json.load(sys.stdin)
        except json.JSONDecodeError:
            return 0
        tool, inp = ev.get("tool_name", ""), ev.get("tool_input") or {}
        if tool == "Bash":
            sql = command_sql(inp.get("command", ""))
        elif "snowflake" in tool.lower():
            sql = next((inp[k] for k in ("query", "sql", "statement", "statements") if isinstance(inp.get(k), str)), None)
        else:
            sql = None
        if not sql:
            return 0
        bad = [f for f in gate(sql, cfg, "<tool call>")["findings"] if f["severity"] == "error"]
        if bad:
            print("Blocked by snowflake-de-team gate:\n" + "\n".join(f"- {f['rule']}: {f['msg']}" for f in bad) +
                  "\nWrite the SQL to a file for a person to review and run instead.", file=sys.stderr)
            return 2
        return 0

    if a.cmd == "check-findings":
        r = check_findings(read(a.path))
        return emit(r, a.json, a.fail_on, lambda r: (print(f"{a.path}: {r['findings_count']} finding(s)"),
                                                     show_findings(r["findings"], a.path)))
    if a.cmd == "check-critique":
        r = check_critique(read(a.path))
        c = r["counts"]
        return emit(r, a.json, a.fail_on, lambda r: (
            print(f"{a.path}: {c['Critical']} critical, {c['Major']} major, {c['Minor']} minor"),
            show_findings(r["findings"], a.path)))
    if a.cmd == "check-refine":
        r = check_refine(read(a.critique), read(a.notes))
        return emit(r, a.json, a.fail_on, lambda r: (
            print(f"must fix: {', '.join(r['must_fix']) or 'none'}; answered: {', '.join(r['answered']) or 'none'}"),
            show_findings(r["findings"], a.notes)))
    if a.cmd == "verify":
        r = verify(Path(a.run))
        if a.json:
            print(json.dumps(r, indent=2))
        else:
            for s in r["stages"]:
                print(f"{'ok  ' if s['ok'] else 'FAIL'} {s['stage']}: {s['errors']} error(s), {s['warnings']} warning(s)")
                show_findings([f for f in s["findings"] if f["severity"] != "info"], s["path"])
            print(f"Next: {r['next']}")
        return 0 if r["done"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
