"""Runs dd_collect.py against a fake Datadog API and checks the safety properties.

python3 tests/datadog/test_dd_collect.py   (no dependencies, no network)
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.request
from http.server import HTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
SCRIPT = ROOT / "plugins/top30-ops/skills/datadog-app-investigator/scripts/dd_collect.py"
sys.path.insert(0, str(HERE))
import mock_datadog  # noqa: E402

PII = re.compile(r"jane\.doe@|x@y\.com|bob@corp|4111 1111|hunter2|abc\.def\.ghi")


def run(env_extra, out):
    env = {k: v for k, v in os.environ.items() if not k.startswith("DD_")}
    env.update(env_extra)
    return subprocess.run([sys.executable, "-I", str(SCRIPT), "--service", "orders-api", "--env", "prod",
                           "--window", "1h", "--out", str(out)], env=env, capture_output=True, text=True, timeout=60)


def main():
    srv = HTTPServer(("127.0.0.1", 0), mock_datadog.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    failures = []

    def check(cond, msg):
        print(("PASS " if cond else "FAIL ") + msg)
        if not cond:
            failures.append(msg)

    with tempfile.TemporaryDirectory() as tmp:
        tmp = Path(tmp)
        r = run({}, tmp / "nokeys")
        check(r.returncode != 0 and "DD_API_KEY" in r.stderr, "refuses to run without keys")

        r = run({"DD_API_BASE": base, "DD_API_KEY": "wrong", "DD_APPLICATION_KEY": "x"}, tmp / "bad")
        check(r.returncode != 0 and "rejected" in r.stderr, "stops with a clear message on bad keys")

        out = tmp / "good"
        r = run({"DD_API_BASE": base, "DD_API_KEY": "testkey", "DD_APPLICATION_KEY": "appkey"}, out)
        check(r.returncode == 0, f"good run exits 0 ({r.stderr.strip()[:200]})")
        summary = (out / "summary.md").read_text() if (out / "summary.md").exists() else ""
        leaked = [f.name for f in out.glob("*") if PII.search(f.read_text())]
        check(not leaked, f"no raw personal data in any output file {leaked}")
        check("[EMAIL]" in summary and "[NUMBER]" in summary, "summary shows masked values")
        check("1234567890123456789" in summary, "trace IDs are kept for drill-down")
        check(summary.index("Alert") < summary.index("| OK |"), "alerting monitors listed first")
        check("| incidents | forbidden |" in summary, "missing permission reported under Not checked")
        check("Deployed orders-api v2.31.0" in summary, "deploy events included")
        check("9.1%" in summary and "1,900 ms" in summary, "endpoint error rate and p95 computed")
        check("4523" in summary and "88" in summary, "current vs previous window error counts")

        req = urllib.request.Request(base + "/__log", headers={"DD-API-KEY": "testkey"})
        log = [x for x in json.load(urllib.request.urlopen(req)) if x["path"] != "/__log"]
        writes = [x for x in log if x["method"] not in ("GET", "POST")
                  or (x["method"] == "POST" and not re.search(r"/(search|aggregate)$", x["path"]))]
        check(not writes, f"only reads: GET or POST to search/aggregate {writes}")
        check(not any("testkey" in x["query"] or "appkey" in x["query"] for x in log), "keys never in URLs")
        check(sum(1 for x in log if x["path"] == "/api/v1/monitor/search") >= 2, "retries after HTTP 429")
    srv.shutdown()
    print(f"\n{len(failures)} failure(s)")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
