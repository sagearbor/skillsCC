"""Self-tests for the Stop gate — verifies it blocks/allows correctly across the 6 states."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "hooks" / "scripts" / "gate.py"
RECORD = ROOT / "hooks" / "scripts" / "record_verdict.py"
PY = sys.executable


def _git(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, capture_output=True, check=True)


def _repo(tmp_path):
    _git(tmp_path, "init")
    _git(tmp_path, "config", "user.email", "t@t.t")
    _git(tmp_path, "config", "user.name", "t")
    (tmp_path / "app.py").write_text("v1\n")
    _git(tmp_path, "add", "app.py")
    _git(tmp_path, "commit", "-m", "init")
    return tmp_path


def _gate(cwd):
    proc = subprocess.run([PY, str(GATE)], cwd=cwd, capture_output=True, text=True,
                          input=json.dumps({"cwd": str(cwd)}))
    return json.loads(proc.stdout or "{}")


def _decision(cwd):
    return _gate(cwd).get("decision", "allow")


def _record(cwd, verdict):
    subprocess.run([PY, str(RECORD), verdict, "evidence", "--project", str(cwd)],
                   capture_output=True, check=True)


def test_clean_tree_allows(tmp_path):
    repo = _repo(tmp_path)
    assert _decision(repo) == "allow"


def test_change_without_verdict_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("v1\ndef f():\n    return 2\n")
    assert _decision(repo) == "block"


def test_recorded_pass_allows(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("v1\ndef f():\n    return 2\n")
    _record(repo, "PASS")
    assert _decision(repo) == "allow"


def test_stale_verdict_reblocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("v1\ndef f():\n    return 2\n")
    _record(repo, "PASS")
    assert _decision(repo) == "allow"
    (repo / "app.py").write_text("v1\ndef f():\n    return 2\ndef g():\n    return 3\n")
    assert _decision(repo) == "block"  # code changed since verdict


def test_fail_verdict_blocks(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("v1\nx = 1\n")
    _record(repo, "FAIL")
    assert _decision(repo) == "block"


def test_skip_verdict_allows(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("v1\nx = 1\n")
    _record(repo, "SKIP")
    assert _decision(repo) == "allow"


def test_multi_file_change_recommends_prove(tmp_path):
    repo = _repo(tmp_path)
    for i in range(3):
        (repo / f"f{i}.py").write_text(f"x = {i}\n")
    out = _gate(repo)
    assert out.get("decision") == "block"
    assert "/prove" in out.get("reason", ""), "multi-file change should escalate to /prove"


def test_single_file_change_no_prove_escalation(tmp_path):
    repo = _repo(tmp_path)
    (repo / "app.py").write_text("v1\nx = 1\n")
    out = _gate(repo)
    assert out.get("decision") == "block"
    assert "/prove" not in out.get("reason", ""), "single-file change should not escalate"
