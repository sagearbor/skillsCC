"""Self-tests for the semantic content verifier."""
import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "verifier-semantic" / "scripts" / "semantic_check.py"
PY = sys.executable

DOC = """# Phase III Clinical Trial Protocol

Enrollment began 2023-06-15 at three sites.

## Methods

A randomized, double-blind, placebo-controlled study of the intervention.

## Inclusion Criteria

Adults aged 18 and older with confirmed diagnosis.

## Results

Primary endpoint analysis pending.
"""


def _spec(tmp, source, criteria):
    p = tmp / "spec.json"
    p.write_text(json.dumps({"source": source, "criteria": criteria}))
    return p


def _run(args):
    proc = subprocess.run([PY, str(SCRIPT), *args], capture_output=True, text=True)
    return json.loads(proc.stdout), proc.returncode


def _file(tmp):
    p = tmp / "doc.md"
    p.write_text(DOC)
    return p


def test_valid_protocol_passes_all_criteria(tmp_path):
    spec = _spec(tmp_path, {"type": "file", "path": str(_file(tmp_path))}, {
        "min_words": 20,
        "require_all": ["Phase III", "Inclusion Criteria"],
        "require_any": ["randomized", "open-label"],
        "forbid": ["Lorem ipsum"],
        "sections": ["Methods", "Results"],
        "date_after": "2020-01-01",
    })
    out, code = _run(["--spec", str(spec)])
    assert out["verdict"] == "PASS", out
    assert code == 0


def test_missing_section_fails(tmp_path):
    spec = _spec(tmp_path, {"type": "file", "path": str(_file(tmp_path))},
                 {"sections": ["Discussion"]})
    out, _ = _run(["--spec", str(spec)])
    assert out["verdict"] == "FAIL", out


def test_date_after_cutoff_fails(tmp_path):
    spec = _spec(tmp_path, {"type": "file", "path": str(_file(tmp_path))},
                 {"date_after": "2025-01-01"})
    out, _ = _run(["--spec", str(spec)])
    assert out["verdict"] == "FAIL", out


def test_forbidden_content_fails(tmp_path):
    spec = _spec(tmp_path, {"type": "file", "path": str(_file(tmp_path))},
                 {"forbid": ["Phase III"]})
    out, _ = _run(["--spec", str(spec)])
    assert out["verdict"] == "FAIL", out


def test_missing_required_phrase_fails(tmp_path):
    spec = _spec(tmp_path, {"type": "file", "path": str(_file(tmp_path))},
                 {"require_all": ["Phase IV"]})
    out, _ = _run(["--spec", str(spec)])
    assert out["verdict"] == "FAIL", out


def test_no_criteria_is_usage_error(tmp_path):
    out, code = _run(["--file", str(_file(tmp_path))])
    assert out["verdict"] == "FAIL" and code == 2, out
    assert "vacuous" in out["reason"]


def test_dead_url_fails(tmp_path):
    out, code = _run(["--url", "http://no-such-host.invalid/x", "--require", "anything"])
    assert out["verdict"] == "FAIL" and code == 1, out


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(DOC.encode())

    def log_message(self, *_):
        pass


def test_url_mode_live_content_passes(tmp_path):
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        out, code = _run(["--url", f"http://127.0.0.1:{port}/protocol",
                          "--require", "Phase III", "--section", "Methods",
                          "--date-after", "2020-01-01"])
        assert out["verdict"] == "PASS", out
        assert code == 0
    finally:
        server.shutdown()
