# <service> (<env>) — Datadog investigation, <window with timezone>

**Verdict:** Degraded since 09:40 CT. Error rate 4.8% (normal 0.2%), all on `POST /orders`,
starting 6 minutes after deploy v2.31.0.

## What's happening

| Signal | This window | Previous window | Change |
|---|---|---|---|
| Requests | 182k | 176k | +3% |
| Error rate | 4.8% | 0.2% | +4.6 pts |
| p95 latency | 840 ms | 310 ms | +171% |
| p99 latency | 2.4 s | 620 ms | +287% |

## Top error patterns

| Pattern | Count | First seen | Example (masked) |
|---|---|---|---|
| `TimeoutException: orders-db pool exhausted` | 3,912 | 09:41 | `... acquiring connection after 5000ms ...` |
| `HTTP 503 from inventory-svc` | 611 | 09:44 | `... GET /stock/[REDACTED] 503 ...` |

## Slowest and failing endpoints

| Resource | Requests | Error % | p95 | p99 |
|---|---|---|---|---|
| POST /orders | 41k | 9.1% | 1.9 s | 4.8 s |

## What changed

- 09:34 CT — deploy `orders-api` v2.31.0 (event link)
- 09:41 CT — first pool-exhausted error

## Alerts, SLOs, incidents, known issues

- Monitor "orders-api p99 latency" — Alert since 09:47
- SLO "Orders availability 99.9%" — 38% of monthly error budget left
- No open incident; error-tracking issue #123 "pool exhausted" reopened 09:42

## Likely cause and next steps

1. **Connection pool too small after v2.31.0** (strongest). Evidence: errors begin 6 min after
   deploy, all are pool timeouts. Next: compare pool settings between v2.30 and v2.31; check
   DB connection count metric.
2. **inventory-svc slowness** (weaker). Evidence: 503s start 3 min later than pool errors, so
   more likely a knock-on effect. Next: check inventory-svc's own error rate.

## Links

- Logs, traces, monitor, dashboard (from tool results)

## Not checked

- Incidents: the key lacks incident read permission.
