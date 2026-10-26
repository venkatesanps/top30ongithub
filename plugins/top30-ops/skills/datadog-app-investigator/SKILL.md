---
name: datadog-app-investigator
description: Collect logs, traces, monitors, deploys, incidents and health for one application from Datadog and write an investigation report. Use when the user asks to check, investigate, triage or summarize a service or app in Datadog ("what's wrong with checkout in prod", "pull the last hour of errors for orders-api", "health report for my service").
---

# Datadog app investigator

Builds one evidence-backed report about an application from Datadog: is it healthy, what is
failing, since when, what changed, and where to look next. Read-only: never create, edit or
delete anything in Datadog.

## 1. Connect (login)

Prefer the official Datadog plugin's MCP server, which signs in with OAuth in the browser.

1. Check for the Datadog MCP tools (names like `search_datadog_logs`, `search_datadog_monitors`).
   With Datadog's plugin they appear as `mcp__plugin_datadog_mcp__<tool>`.
2. If they are missing, tell the user to install the official plugin and run its setup, then
   restart Claude Code and come back:
   - `claude plugin marketplace add anthropics/knowledge-work-plugins`
   - `claude plugin install datadog@knowledge-work-plugins`
   - In Claude Code: `/ddsetup` (pick the Datadog site, sign in in the browser).
3. If a tool call fails with an auth error, ask the user to run `/ddconfig` and sign in again.

Never ask the user to paste an API key, application key or token into the chat. If MCP is not
allowed where they work, use the fallback in section 6.

## 2. Pin down the scope

Get these before querying. Ask only for what you can't infer:

| Input | Example | Default |
|---|---|---|
| Service name (Datadog `service` tag) | `orders-api` | none: ask, or offer `search_datadog_entities` to find it |
| Environment (`env` tag) | `prod`, `uat` | `prod` |
| Time window | last 1h, since 09:00 CT | last 1 hour |
| Symptom, if any | "p99 up", "500s on /checkout" | general health |

Always state times with their timezone in the report. Datadog query time strings like
`now-1h` work in every tool.

## 3. Collect, in this order

Use only these read-only tools. Skip a step if its tool isn't available, and note it in the
report under "Not checked".

1. **Service context**: `search_datadog_entities` (owner, team, dependencies, links, runbook),
   and `apm_get_service_health` if available.
2. **Alerting now**: `search_datadog_monitors` with `service:<svc> env:<env>`; keep monitors in
   Alert, Warn or No Data. Then `search_datadog_slos` for the service's SLOs and their status.
3. **Error volume and patterns**: `search_datadog_logs` with
   `service:<svc> env:<env> status:(error OR critical)` over the window, newest first, limit 100.
   Use `analyze_datadog_logs` to count errors by message pattern and by `@error.kind`, with a
   15-minute or 5-minute series to find when it started.
4. **Requests and latency**: `aggregate_spans` for `service:<svc> env:<env>`: request count,
   error rate, p50/p95/p99 duration, grouped by `resource_name`. Then `search_datadog_spans`
   for the slowest and the failing spans (limit 20 each). For the worst one, `get_datadog_trace`,
   and `apm_latency_bottleneck_summary` if latency is the symptom.
5. **What changed**: `search_datadog_events` for deploys, config changes and alerts on the
   service in the window plus 2 hours before it. Line deploy times up with the error series.
6. **Incidents**: `search_datadog_incidents` for active or recent incidents naming the
   service; `get_datadog_incident` for any that are active.
7. **Known issues**: `search_datadog_error_tracking_issues` for the service, newest first.
8. **Infrastructure, only if signs point there**: `search_datadog_hosts`, `get_datadog_metric`
   (CPU, memory, restarts) for the hosts or containers behind the service.

Keep queries scoped with both `service:` and `env:`. Prefer aggregates over pulling thousands of
raw log lines. Use at most 100 log lines and 20 spans as samples.

## 4. Protect sensitive data

Log lines can contain customer data. In the report and in chat:

- Quote at most 5 sample log lines, trimmed to the part that shows the error.
- Mask anything that looks like an email, card or account number, token, password, or personal
  name or address, as `[REDACTED]`.
- Don't copy request or response bodies, headers, or user identifiers into the report.
- If the user asks to save the report, write it to a local file; don't post it anywhere.

## 5. Write the report

Use this structure (see `references/report-template.md`), shortest useful version first:

1. **Verdict**: one line. Healthy, degraded or down, since when, with the main evidence.
2. **What's happening**: error rate, latency and request volume vs. the previous window.
3. **Top error patterns**: table of pattern, count, first seen, example (masked).
4. **Slowest and failing endpoints**: table of resource, requests, error %, p95, p99.
5. **What changed**: deploys and config changes, with times next to when errors started.
6. **Alerts, SLOs, incidents, known issues**: what's firing and what's already tracked.
7. **Likely cause and next steps**: ranked hypotheses, each with the evidence for it and the
   next query or check that would confirm or rule it out.
8. **Links**: Datadog links returned by the tools for logs, traces, monitors and dashboards.
9. **Not checked**: anything you couldn't query and why.

Say plainly when the data is inconclusive. Don't guess a root cause the evidence doesn't
support.

## 6. Fallback without MCP: the collect script

If the Datadog MCP server isn't available or isn't approved, use
`scripts/dd_collect.py` (Python 3 standard library only, read-only calls).

1. The user sets keys in their own shell, never in chat. Recommend read-only scoped
   application keys:
   - `export DD_SITE=datadoghq.com` (or `us3.datadoghq.com`, `us5.datadoghq.com`,
     `datadoghq.eu`, `ap1.datadoghq.com`, `ap2.datadoghq.com`, `uk1.datadoghq.com`)
   - `export DD_API_KEY=...` and `export DD_APPLICATION_KEY=...`
   - On macOS they can keep keys in Keychain:
     `export DD_API_KEY=$(security find-generic-password -s datadog-api-key -w)`
2. Run it:
   `python3 "${CLAUDE_PLUGIN_ROOT}/skills/datadog-app-investigator/scripts/dd_collect.py" --service <svc> --env <env> --window 1h --out ./dd-report`
   (or the script's path inside this skill folder if `CLAUDE_PLUGIN_ROOT` isn't set).
3. Read `./dd-report/summary.md` and the JSON files next to it, then write the report as in
   section 5. The script already masks emails, card-like numbers and tokens in log messages.
4. A section that says `forbidden` means the key lacks that permission (for example incidents
   or APM); list it under "Not checked".
