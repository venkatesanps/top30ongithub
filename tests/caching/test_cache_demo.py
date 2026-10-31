"""Runs examples/prompt-caching/cache_demo.py against a fake Messages API: checks the request
marks the document for caching, and the cost math matches the documented multipliers.

python3 tests/caching/test_cache_demo.py   (needs: pip install anthropic; no network, no key)
"""
import json
import os
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
SEEN = []


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        SEEN.append(body)
        first = len(SEEN) == 1
        usage = {"input_tokens": 20, "output_tokens": 10,
                 "cache_creation_input_tokens": 10000 if first else 0,
                 "cache_read_input_tokens": 0 if first else 10000}
        out = {"id": f"msg_{len(SEEN)}", "type": "message", "role": "assistant", "model": body["model"],
               "content": [{"type": "text", "text": f"answer {len(SEEN)}"}], "stop_reason": "end_turn",
               "stop_sequence": None, "usage": usage}
        data = json.dumps(out).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def main():
    fails = []

    def check(c, m):
        print(("PASS " if c else "FAIL ") + m)
        if not c:
            fails.append(m)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    with tempfile.TemporaryDirectory() as tmp:
        doc = Path(tmp) / "doc.md"
        doc.write_text("table fact_trades: one row per trade\n" * 50)
        env = dict(os.environ, ANTHROPIC_API_KEY="test", ANTHROPIC_BASE_URL=f"http://127.0.0.1:{srv.server_port}")
        p = subprocess.run([sys.executable, str(ROOT / "examples/prompt-caching/cache_demo.py"), str(doc),
                            "q1", "q2", "q3"], env=env, capture_output=True, text=True, timeout=60)
        check(p.returncode == 0, f"exits 0 {p.stderr[-300:]}")
        check(len(SEEN) == 3, "one API call per question")
        sysblocks = SEEN[0]["system"]
        check(sysblocks[-1].get("cache_control") == {"type": "ephemeral"} and "fact_trades" in sysblocks[-1]["text"],
              "document block carries cache_control")
        check(all(s["system"] == SEEN[0]["system"] for s in SEEN), "identical cached prefix on every call")
        # call 1: 20 + 1.25*10000 = 12520; calls 2-3: 20 + 0.1*10000 = 1020 each -> 14560 vs 30060 uncached
        check("| 1 | 10,020 | 10,000 | 0 | 12,520 |" in p.stdout, "first call includes the 1.25x write premium")
        check("| 2 | 10,020 | 0 | 10,000 | 1,020 |" in p.stdout, "later calls read at 0.1x")
        check("14,560 units; without: 30,060 units (52% saved over 3 calls)" in p.stdout, "total saving computed")
        SEEN.clear()
        p = subprocess.run([sys.executable, str(ROOT / "examples/prompt-caching/cache_demo.py"), str(doc), "q1", "q2",
                            "--ttl", "1h", "--read-multiplier", "0.05"], env=env, capture_output=True, text=True, timeout=60)
        check(SEEN[0]["system"][-1]["cache_control"] == {"type": "ephemeral", "ttl": "1h"}, "--ttl 1h sends ttl")
        check("| 1 | 10,020 | 10,000 | 0 | 20,020 |" in p.stdout and "| 2 | 10,020 | 0 | 10,000 | 520 |" in p.stdout,
              "1h write at 2x, read multiplier 0.05")
    srv.shutdown()
    print(f"\n{len(fails)} failure(s)")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
