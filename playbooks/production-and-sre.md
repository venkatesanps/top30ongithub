# Playbook: production monitoring for leadership, app developers and SRE / L2 / L3

Each audience needs a different view of the same system. Build them from one telemetry
pipeline so the numbers agree.

## Who needs what

| Audience | Question they ask | View | From this toolkit |
|---|---|---|---|
| **Technology leadership** | Are we up? Are we meeting our promises? Is it getting better? | SLO and error-budget summary per service, incidents and MTTR per month, a status page | **54** Uptime Kuma status page; Grafana SLO dashboard on **50**; DevLake (**46**) for change failure rate and time to restore |
| **Application developers** | Is my release healthy? Where is the time going? | RED metrics (rate, errors, duration) per endpoint, traces, logs for my service, deploy markers | **50** Grafana OTel LGTM (traces, metrics, logs); **51** Grafana MCP to ask questions in Claude |
| **L2 support** | What's firing, what's related, who owns it? | One deduplicated alert queue with service ownership and runbook links | **52** Keep (pulls in Splunk, Dynatrace, Datadog, Prometheus, PagerDuty...); **56** PagerDuty hosted MCP; **44** `operations` runbooks |
| **L3 / SRE** | What's the root cause, and what changed? | Correlated metrics, traces and logs around the alert window, recent deploys and config changes | **53** HolmesGPT; **55** Dynatrace for AI; **51** Grafana MCP; **39** AWS CloudWatch MCP |
| **Data platform** | Did the data land, on time, correct, at what cost? | Freshness, test results, anomaly alerts, Snowflake credits by warehouse | **36** Elementary; **35** dbt-snowflake-monitoring; **34** Airflow agents |

## A one-afternoon trial (laptop or sandbox)

1. `./install.sh 50` — start Grafana OTel LGTM.
2. Instrument one service with OpenTelemetry (auto-instrumentation for Java, Python or Node is
   usually a single agent or package) and point it at `localhost:4318`.
3. In Grafana, build: request rate, error rate, p95 latency, and a deploy annotation.
4. `./install.sh 51` and ask Claude: "Which endpoint's p95 got worse after the last deploy?"
5. `./install.sh 54` and add an HTTP check for the service; publish a status page.

## L2 / L3 incident flow

1. **Alert lands in Keep**, grouped with related alerts; Keep adds owner and runbook link.
2. **L2** follows the runbook. If it doesn't resolve in the agreed window, escalate with the
   Keep incident link.
3. **L3** runs HolmesGPT on the alert: it queries metrics, logs and recent changes and proposes
   a root cause, with the queries it ran so you can check them.
4. **Fix, then review.** `/engineering:incident-response` drafts the timeline;
   `/operations:runbook` updates the runbook; action items go to Jira.

## Leadership dashboard: keep it to one screen

- Availability vs SLO for the top services (green / amber / red).
- Error budget remaining this month.
- Incidents this month by severity, MTTR trend over 6 months.
- Change failure rate and deployment frequency (from DevLake).
- Data freshness for the reports leadership depends on.

## Using what your firm already runs

Most large firms already have Splunk, Dynatrace, Datadog or Grafana. Before standing up new
servers, connect Claude to the existing ones (Dynatrace for AI **55**, Grafana MCP **51**, Datadog's
plugin in the knowledge-work marketplace, Splunk's own MCP app) with read-only tokens. Then
use Keep and HolmesGPT on top.
