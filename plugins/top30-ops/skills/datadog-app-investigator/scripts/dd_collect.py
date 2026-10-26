#!/usr/bin/env python3
"""Collect read-only evidence about one service from the Datadog API.

Keys come from the environment (never pass them as arguments):
  DD_API_KEY, DD_APPLICATION_KEY, and DD_SITE (default datadoghq.com).
Every call is a read: GET, or POST to a search/aggregate endpoint.

Usage:
  python3 dd_collect.py --service orders-api --env prod --window 1h --out ./dd-report

Writes <out>/<section>.json for each section and <out>/summary.md.
Sections that fail are recorded (forbidden, not found, error) and the run continues.
"""
import argparse
import collections
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REDACTIONS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?i)\bbearer\s+\S+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)\b(token|apikey|api_key|password|passwd|secret)\s*[:=]\s*\S+"), r"\1=[REDACTED]"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "[REDACTED]"),
    (re.compile(r"\b\d(?:[ -]?\d){12,18}\b"), "[NUMBER]"),
    (re.compile(r"\b[A-Za-z0-9+/_-]{32,}={0,2}\b"), "[TOKEN]"),
]
UNITS = {"m": 60, "h": 3600, "d": 86400}
# Datadog identifiers and times: needed to open traces and events, and contain no personal data.
KEEP_KEYS = {"id", "trace_id", "span_id", "parent_id", "timestamp", "start_timestamp", "end_timestamp", "time"}


def redact(text, on=True):
    if not on or not isinstance(text, str):
        return text
    for pat, rep in REDACTIONS:
        text = pat.sub(rep, text)
    return text


def deep_redact(obj, on=True):
    """Mask every string in a JSON-like structure (IDs and timestamps are left alone by the patterns)."""
    if not on:
        return obj
    if isinstance(obj, dict):
        return {k: (v if k in KEEP_KEYS else deep_redact(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [deep_redact(v) for v in obj]
    return redact(obj) if isinstance(obj, str) else obj


def window_seconds(w):
    m = re.fullmatch(r"(\d+)([mhd])", w.strip())
    if not m:
        raise SystemExit(f"--window must look like 30m, 1h or 2d (got {w!r})")
    return int(m.group(1)) * UNITS[m.group(2)]


class Datadog:
    def __init__(self, base, api_key, app_key):
        self.base = base.rstrip("/")
        self.headers = {"DD-API-KEY": api_key, "DD-APPLICATION-KEY": app_key,
                        "Content-Type": "application/json", "Accept": "application/json",
                        "User-Agent": "datadog-app-investigator/1.0"}

    def call(self, method, path, params=None, body=None):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        for attempt in range(3):
            req = urllib.request.Request(url, data=data, method=method, headers=self.headers)
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    return {"ok": True, "data": json.loads(r.read() or b"{}")}
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt < 2:
                    wait = min(int(e.headers.get("X-RateLimit-Reset") or 5), 30)
                    time.sleep(wait)
                    continue
                reason = {401: "unauthorized", 403: "forbidden", 404: "not found"}.get(e.code, f"HTTP {e.code}")
                return {"ok": False, "error": reason}
            except (urllib.error.URLError, TimeoutError) as e:
                return {"ok": False, "error": f"network: {getattr(e, 'reason', e)}"}
        return {"ok": False, "error": "rate limited"}


def g(d, *path, default=None):
    for p in path:
        if isinstance(d, dict):
            d = d.get(p)
        elif isinstance(d, list) and isinstance(p, int) and len(d) > p:
            d = d[p]
        else:
            return default
    return default if d is None else d


def pattern(msg):
    """Collapse a log message to a pattern: numbers, ids and quoted values become placeholders."""
    msg = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<id>", msg or "", flags=re.I)
    msg = re.sub(r"\d+", "<n>", msg)
    msg = re.sub(r"'[^']*'|\"[^\"]*\"", "<v>", msg)
    return msg[:160].strip()


def collect(dd, svc, env, secs, limit, redact_on):
    q = f"service:{svc} env:{env}"
    now, prev = f"now-{secs}s", f"now-{2 * secs}s"
    out = {}

    out["validate"] = dd.call("GET", "/api/v1/validate")
    if not out["validate"]["ok"]:
        return out

    out["service_catalog"] = dd.call("GET", "/api/v2/catalog/entity", {"filter[ref]": f"service:{svc}"})
    out["monitors"] = dd.call("GET", "/api/v1/monitor/search", {"query": q, "per_page": 100})
    out["slos"] = dd.call("GET", "/api/v1/slo", {"tags_query": f"service:{svc}", "limit": 50})

    err_q = f"{q} status:(error OR critical)"
    logs = dd.call("POST", "/api/v2/logs/events/search",
                   body={"filter": {"query": err_q, "from": now, "to": "now"}, "sort": "-timestamp", "page": {"limit": limit}})
    if logs["ok"]:
        for item in g(logs, "data", "data", default=[]):
            a = item.get("attributes", {})
            a["message"] = redact(a.get("message"), redact_on)
            if isinstance(a.get("attributes"), dict):
                a["attributes"] = {k: v for k, v in a["attributes"].items() if k in ("error", "http", "status", "logger")}
                err = a["attributes"].get("error")
                if isinstance(err, dict):
                    for k in ("message", "stack"):
                        if k in err:
                            err[k] = redact(str(err[k])[:500], redact_on)
    out["error_logs"] = logs

    def log_count(frm, to):
        r = dd.call("POST", "/api/v2/logs/analytics/aggregate",
                    body={"compute": [{"aggregation": "count"}], "filter": {"query": err_q, "from": frm, "to": to}})
        return r, g(r, "data", "data", "buckets", 0, "computes", "c0")

    out["error_count_now"], _ = log_count(now, "now")
    out["error_count_prev"], _ = log_count(prev, now)
    out["errors_by_kind"] = dd.call("POST", "/api/v2/logs/analytics/aggregate", body={
        "compute": [{"aggregation": "count"}], "filter": {"query": err_q, "from": now, "to": "now"},
        "group_by": [{"facet": "@error.kind", "limit": 10, "sort": {"aggregation": "count", "order": "desc"}}]})
    interval = "5m" if secs <= 3 * 3600 else "1h"
    out["errors_timeseries"] = dd.call("POST", "/api/v2/logs/analytics/aggregate", body={
        "compute": [{"aggregation": "count", "type": "timeseries", "interval": interval}],
        "filter": {"query": err_q, "from": now, "to": "now"}})

    span_filter = {"query": q, "from": now, "to": "now"}
    out["endpoints"] = dd.call("POST", "/api/v2/spans/analytics/aggregate", body={"data": {"type": "aggregate_request", "attributes": {
        "compute": [{"aggregation": "count"}, {"aggregation": "pc95", "metric": "@duration"}, {"aggregation": "pc99", "metric": "@duration"}],
        "filter": span_filter, "group_by": [{"facet": "resource_name", "limit": 15, "sort": {"aggregation": "count", "order": "desc"}}]}}})
    out["endpoint_errors"] = dd.call("POST", "/api/v2/spans/analytics/aggregate", body={"data": {"type": "aggregate_request", "attributes": {
        "compute": [{"aggregation": "count"}], "filter": {**span_filter, "query": q + " status:error"},
        "group_by": [{"facet": "resource_name", "limit": 15, "sort": {"aggregation": "count", "order": "desc"}}]}}})
    out["failing_spans"] = dd.call("POST", "/api/v2/spans/events/search", body={"data": {"type": "search_request", "attributes": {
        "filter": {**span_filter, "query": q + " status:error"}, "sort": "-timestamp", "page": {"limit": 20}}}})

    out["events"] = dd.call("GET", "/api/v2/events", {"filter[query]": f"service:{svc}", "filter[from]": f"now-{secs + 7200}s",
                                                     "filter[to]": "now", "page[limit]": 50, "sort": "-timestamp"})
    out["incidents"] = dd.call("GET", "/api/v2/incidents/search", {"query": f"state:(active OR stable) AND services:{svc}", "page[size]": 20})
    return out


def table(rows, head):
    if not rows:
        return "_None found._\n"
    lines = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    lines += ["| " + " | ".join(str(c).replace("|", "/").replace("\n", " ") for c in r) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def ms(v):
    try:
        return f"{float(v) / 1e6:,.0f} ms"  # span durations are nanoseconds
    except (TypeError, ValueError):
        return "—"


def summarize(res, svc, env, window, site):
    when = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    s = [f"# {svc} ({env}) — Datadog evidence, last {window} (collected {when}, site {site})", ""]
    missing = [k for k, v in res.items() if not v.get("ok")]

    s.append("## Error volume")
    now_c = g(res, "error_count_now", "data", "data", "buckets", 0, "computes", "c0")
    prev_c = g(res, "error_count_prev", "data", "data", "buckets", 0, "computes", "c0")
    s.append(f"- Error/critical logs this window: **{now_c if now_c is not None else '—'}**; previous window: {prev_c if prev_c is not None else '—'}")
    kinds = [(g(b, "by", "@error.kind") or "(none)", g(b, "computes", "c0")) for b in g(res, "errors_by_kind", "data", "data", "buckets", default=[])]
    s += ["", "By error kind:", "", table(kinds, ["Error kind", "Count"])]
    series = g(res, "errors_timeseries", "data", "data", "buckets", 0, "computes", "c0", default=[])
    if isinstance(series, list) and series:
        first = next((p for p in series if (p.get("value") or 0) > 0), None)
        peak = max(series, key=lambda p: p.get("value") or 0)
        s.append(f"- First non-zero interval: {first.get('time') if first else '—'}; peak: {peak.get('value')} at {peak.get('time')}")
    s.append("")

    s.append("## Top error patterns (from up to 100 recent error logs)")
    pats = collections.Counter()
    first_seen, example = {}, {}
    for item in reversed(g(res, "error_logs", "data", "data", default=[])):
        a = item.get("attributes", {})
        p = pattern(a.get("message", ""))
        pats[p] += 1
        first_seen.setdefault(p, a.get("timestamp"))
        example[p] = (a.get("message") or "")[:200]
    s.append(table([(p, n, first_seen[p], example[p]) for p, n in pats.most_common(10)], ["Pattern", "Count", "First seen", "Example (masked)"]))

    s.append("## Endpoints (APM)")
    errs = {g(b, "attributes", "by", "resource_name"): g(b, "attributes", "compute", "c0", default=0)
            for b in g(res, "endpoint_errors", "data", "data", default=[])}
    rows = []
    for b in g(res, "endpoints", "data", "data", default=[]):
        name = g(b, "attributes", "by", "resource_name")
        cnt = g(b, "attributes", "compute", "c0", default=0) or 0
        e = errs.get(name, 0) or 0
        rows.append((name, cnt, f"{100 * e / cnt:.1f}%" if cnt else "—", ms(g(b, "attributes", "compute", "c1")), ms(g(b, "attributes", "compute", "c2"))))
    s.append(table(rows, ["Resource", "Requests", "Error %", "p95", "p99"]))

    s.append("## Failing spans (latest 20)")
    fs = [(g(i, "attributes", "start_timestamp") or g(i, "attributes", "timestamp"), g(i, "attributes", "resource_name"),
           g(i, "attributes", "trace_id"), redact(str(g(i, "attributes", "custom", "error", "message", default="")))[:120])
          for i in g(res, "failing_spans", "data", "data", default=[])]
    s.append(table(fs, ["Time", "Resource", "Trace ID", "Error"]))

    s.append("## Monitors")
    mons = [(m.get("name"), m.get("status"), m.get("id")) for m in g(res, "monitors", "data", "monitors", default=[])]
    mons.sort(key=lambda m: {"Alert": 0, "Warn": 1, "No Data": 2}.get(m[1], 3))
    s.append(table(mons, ["Monitor", "Status", "ID"]))

    s.append("## SLOs")
    s.append(table([(x.get("name"), ", ".join(f"{t.get('timeframe')}: {t.get('target')}%" for t in x.get("thresholds", []))) for x in g(res, "slos", "data", "data", default=[])], ["SLO", "Targets"]))

    s.append("## Deploys, changes and alerts (window + 2h before)")
    ev = [(g(e, "attributes", "timestamp"), g(e, "attributes", "attributes", "title") or g(e, "attributes", "title") or redact(str(g(e, "attributes", "message", default="")))[:120],
           g(e, "attributes", "attributes", "source_type_name") or g(e, "attributes", "attributes", "evt", "source") or "")
          for e in g(res, "events", "data", "data", default=[])]
    s.append(table(ev, ["Time", "Event", "Source"]))

    s.append("## Incidents")
    inc = g(res, "incidents", "data", "data", "attributes", "incidents", default=[])
    s.append(table([(g(i, "data", "attributes", "title"), g(i, "data", "attributes", "state"), g(i, "data", "attributes", "severity")) for i in inc], ["Incident", "State", "Severity"]))

    s.append("## Service catalog")
    ent = g(res, "service_catalog", "data", "data", default=[])
    s.append(table([(g(e, "attributes", "name"), g(e, "attributes", "owner"), g(e, "attributes", "kind")) for e in ent], ["Entity", "Owner", "Kind"]))

    s.append("## Not checked")
    s.append(table([(k, res[k].get("error")) for k in missing], ["Section", "Reason"]))
    return "\n".join(s)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--service", required=True)
    ap.add_argument("--env", default="prod")
    ap.add_argument("--window", default="1h", help="30m, 1h, 6h, 2d ...")
    ap.add_argument("--out", default="./dd-report")
    ap.add_argument("--limit", type=int, default=100, help="max error log lines to sample (<=1000)")
    ap.add_argument("--no-redact", action="store_true", help="keep log text as-is (not recommended)")
    a = ap.parse_args()

    api, app = os.environ.get("DD_API_KEY"), os.environ.get("DD_APPLICATION_KEY") or os.environ.get("DD_APP_KEY")
    if not api or not app:
        sys.exit("Set DD_API_KEY and DD_APPLICATION_KEY in your shell first (see SKILL.md section 6).")
    site = os.environ.get("DD_SITE", "datadoghq.com").removeprefix("https://").removeprefix("app.").strip("/")
    base = os.environ.get("DD_API_BASE") or f"https://api.{site}"
    secs = window_seconds(a.window)

    res = collect(Datadog(base, api, app), a.service, a.env, secs, max(1, min(a.limit, 1000)), not a.no_redact)
    res = deep_redact(res, not a.no_redact)  # nothing unmasked is written to disk
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for k, v in res.items():
        (out / f"{k}.json").write_text(json.dumps(v, indent=1))
    if not res["validate"]["ok"]:
        sys.exit(f"Datadog rejected the keys ({res['validate']['error']}). Check DD_SITE ({site}) and the keys.")
    (out / "summary.md").write_text(summarize(res, a.service, a.env, a.window, site))
    bad = [k for k, v in res.items() if not v.get("ok")]
    print(f"Wrote {out}/summary.md and {len(res)} JSON files." + (f" Not collected: {', '.join(bad)}." if bad else ""))


if __name__ == "__main__":
    main()
