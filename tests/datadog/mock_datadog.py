"""Minimal fake Datadog API for testing dd_collect.py. Records every request."""
import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = []  # requests seen, for assertions
STATE = {"monitor_calls": 0}
NS = 1_000_000


def logs_search(body):
    q = body["filter"]["query"]
    msgs = [
        "TimeoutException: orders-db pool exhausted after 5000ms (order 123456)",
        "TimeoutException: orders-db pool exhausted after 5001ms (order 123999)",
        "Payment failed for jane.doe@example.com card 4111 1111 1111 1111 Bearer abc.def.ghi password=hunter2",
        "HTTP 503 from inventory-svc for sku 'ABC-1'",
    ]
    return {"data": [{"id": str(i), "attributes": {"timestamp": f"2026-10-26T12:{10+i:02d}:00Z", "status": "error", "service": "orders-api",
             "message": m, "attributes": {"error": {"kind": "TimeoutException", "message": m, "stack": "at x"}, "usr": {"email": "x@y.com"}}}}
            for i, m in enumerate(msgs)], "meta": {"q": q}}


def logs_agg(body):
    if "group_by" in body:
        return {"data": {"buckets": [{"by": {"@error.kind": "TimeoutException"}, "computes": {"c0": 3912}}, {"by": {"@error.kind": "HttpError"}, "computes": {"c0": 611}}]}}
    if body["compute"][0].get("type") == "timeseries":
        return {"data": {"buckets": [{"by": {}, "computes": {"c0": [{"time": "2026-10-26T11:35:00Z", "value": 0}, {"time": "2026-10-26T11:40:00Z", "value": 120}, {"time": "2026-10-26T11:45:00Z", "value": 900}]}}]}}
    n = 4523 if body["filter"]["from"].endswith("3600s") else 88
    return {"data": {"buckets": [{"by": {}, "computes": {"c0": n}}]}}


def spans_agg(body):
    a = body["data"]["attributes"]
    if "status:error" in a["filter"]["query"]:
        return {"data": [{"attributes": {"by": {"resource_name": "POST /orders"}, "compute": {"c0": 3731}}}]}
    return {"data": [{"attributes": {"by": {"resource_name": "POST /orders"}, "compute": {"c0": 41000, "c1": 1.9e9, "c2": 4.8e9}}},
                     {"attributes": {"by": {"resource_name": "GET /orders/{id}"}, "compute": {"c0": 120000, "c1": 120 * NS, "c2": 300 * NS}}}]}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def reply(self, code, obj=None, headers=None):
        self.send_response(code)
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(obj or {}).encode())

    def handle_any(self, method):
        path = self.path.split("?")[0]
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n)) if n else None
        LOG.append({"method": method, "path": path, "query": self.path.partition("?")[2], "has_keys": bool(self.headers.get("DD-API-KEY") and self.headers.get("DD-APPLICATION-KEY"))})
        if self.headers.get("DD-API-KEY") != "testkey":
            return self.reply(403, {"errors": ["Forbidden"]})
        if path == "/__log":
            return self.reply(200, LOG)
        if path == "/api/v1/validate":
            return self.reply(200, {"valid": True})
        if path == "/api/v1/monitor/search":
            STATE["monitor_calls"] += 1
            if STATE["monitor_calls"] == 1:
                return self.reply(429, {"errors": ["rate limited"]}, {"X-RateLimit-Reset": "1"})
            return self.reply(200, {"monitors": [{"id": 1, "name": "orders-api p99 latency", "status": "OK"}, {"id": 2, "name": "orders-api error rate", "status": "Alert"}]})
        if path == "/api/v1/slo":
            return self.reply(200, {"data": [{"name": "Orders availability", "thresholds": [{"timeframe": "30d", "target": 99.9}]}]})
        if path == "/api/v2/logs/events/search":
            return self.reply(200, logs_search(body))
        if path == "/api/v2/logs/analytics/aggregate":
            return self.reply(200, logs_agg(body))
        if path == "/api/v2/spans/analytics/aggregate":
            return self.reply(200, spans_agg(body))
        if path == "/api/v2/spans/events/search":
            return self.reply(200, {"data": [{"attributes": {"start_timestamp": "2026-10-26T12:11:00Z", "resource_name": "POST /orders", "trace_id": "1234567890123456789",
                                                             "custom": {"error": {"message": "pool exhausted for bob@corp.com"}}}}]})
        if path == "/api/v2/events":
            return self.reply(200, {"data": [{"attributes": {"timestamp": "2026-10-26T11:34:00Z", "attributes": {"title": "Deployed orders-api v2.31.0", "source_type_name": "deployment"}}}]})
        if path == "/api/v2/incidents/search":
            return self.reply(403, {"errors": ["Forbidden"]})
        if path == "/api/v2/catalog/entity":
            return self.reply(200, {"data": [{"attributes": {"name": "orders-api", "owner": "team-orders", "kind": "service"}}]})
        return self.reply(404, {"errors": ["not found"]})

    def do_GET(self):
        self.handle_any("GET")

    def do_POST(self):
        self.handle_any("POST")


if __name__ == "__main__":
    srv = HTTPServer(("127.0.0.1", int(sys.argv[1])), H)
    srv.serve_forever()
