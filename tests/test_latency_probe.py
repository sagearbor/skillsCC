"""Self-tests for the latency verifier."""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "verifier-latency" / "scripts" / "latency_probe.py"
PY = sys.executable

SLEEP_50MS = [PY, "-c", "import time; time.sleep(0.05)"]


def _run(extra):
    proc = subprocess.run([PY, str(SCRIPT), *extra], capture_output=True, text=True)
    return json.loads(proc.stdout), proc.returncode


def test_command_within_generous_budget_passes():
    out, code = _run(["--runs", "5", "--warmup", "1", "--budget-p95-ms", "5000", "--", *SLEEP_50MS])
    assert out["verdict"] == "PASS", out
    assert code == 0
    assert out["p95_ms"] >= 40  # actually measured the ~50ms sleep


def test_command_over_tight_budget_fails():
    out, code = _run(["--runs", "5", "--warmup", "1", "--budget-p95-ms", "1", "--", *SLEEP_50MS])
    assert out["verdict"] == "FAIL", out
    assert code == 1
    assert out["breaches"], out


def test_erroring_command_fails():
    out, _ = _run(["--runs", "3", "--warmup", "0", "--budget-p95-ms", "5000",
                   "--", PY, "-c", "import sys; sys.exit(1)"])
    assert out["verdict"] == "FAIL", out
    assert "errored" in out["reason"]


def test_no_budget_is_measurement_only_pass():
    out, code = _run(["--runs", "3", "--warmup", "0", "--", *SLEEP_50MS])
    assert out["verdict"] == "PASS" and code == 0, out
    assert "measurement only" in out["note"]


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def log_message(self, *_):  # silence
        pass


def test_url_mode_against_local_server_passes():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        out, code = _run(["--url", f"http://127.0.0.1:{port}/health",
                          "--runs", "5", "--warmup", "1", "--budget-p95-ms", "5000"])
        assert out["verdict"] == "PASS", out
        assert code == 0
        assert out["runs"] == 5
    finally:
        server.shutdown()
