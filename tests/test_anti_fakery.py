"""Self-tests for the anti-fakery scripts — proof-of-done dogfooding itself.

Each test drives a script the way the skill does (subprocess, temp dir) and asserts the
verdict on a known-good or known-bad input. These are the mechanical eval cases from
evals/cases.json, made executable.
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "skills" / "anti-fakery" / "scripts"
PY = sys.executable

CALC = "def add(a, b):\n    return a + b\n\n\ndef is_adult(age):\n    return age >= 18\n"
VACUOUS = "import calc\n\n\ndef test_runs():\n    calc.add(2, 3)\n    calc.is_adult(20)\n    assert True\n"
STRONG = (
    "import calc\n\n\ndef test_add():\n    assert calc.add(2, 3) == 5\n\n\n"
    "def test_adult():\n    assert calc.is_adult(18) is True\n    assert calc.is_adult(17) is False\n"
)


def _run(args, cwd):
    return subprocess.run([PY, *args], cwd=cwd, capture_output=True, text=True)


def _verdict(proc):
    return json.loads(proc.stdout)["verdict"]


def test_mutate_python_flags_vacuous_as_weak(tmp_path):
    (tmp_path / "calc.py").write_text(CALC)
    (tmp_path / "test_v.py").write_text(VACUOUS)
    proc = _run([str(SCRIPTS / "mutate_python.py"), "--test-cmd",
                 f"{PY} -m pytest -q test_v.py", "calc.py"], tmp_path)
    assert _verdict(proc) == "WEAK", proc.stdout
    # source must be restored exactly
    assert (tmp_path / "calc.py").read_text() == CALC


def test_mutate_python_passes_strong_suite(tmp_path):
    (tmp_path / "calc.py").write_text(CALC)
    (tmp_path / "test_s.py").write_text(STRONG)
    proc = _run([str(SCRIPTS / "mutate_python.py"), "--test-cmd",
                 f"{PY} -m pytest -q test_s.py", "calc.py"], tmp_path)
    assert _verdict(proc) == "PASS", proc.stdout


def test_mutate_python_inconclusive_on_red_baseline(tmp_path):
    (tmp_path / "calc.py").write_text(CALC)
    (tmp_path / "test_r.py").write_text("import calc\n\n\ndef test_bad():\n    assert calc.add(1, 1) == 99\n")
    proc = _run([str(SCRIPTS / "mutate_python.py"), "--test-cmd",
                 f"{PY} -m pytest -q test_r.py", "calc.py"], tmp_path)
    assert _verdict(proc) == "INCONCLUSIVE", proc.stdout


def test_validate_fixture_quarantines_unapplied_spike(tmp_path):
    (tmp_path / "src.txt").write_text("original\n")
    (tmp_path / "spiked.txt").write_text("original\n")
    proc = _run([str(SCRIPTS / "validate_fixture.py"), "file", "spiked.txt",
                 "--not-identical-to", "src.txt"], tmp_path)
    assert _verdict(proc) == "QUARANTINE", proc.stdout


def test_validate_fixture_quarantines_wrong_type(tmp_path):
    (tmp_path / "fake.pdf").write_text("not a pdf\n")
    proc = _run([str(SCRIPTS / "validate_fixture.py"), "file", "fake.pdf",
                 "--expect-type", "pdf"], tmp_path)
    assert _verdict(proc) == "QUARANTINE", proc.stdout


def test_validate_fixture_passes_valid_gold(tmp_path):
    (tmp_path / "good.txt").write_text("Phase III trial, enrolled 2024-01-01, Methods present.\n")
    proc = _run([str(SCRIPTS / "validate_fixture.py"), "file", "good.txt",
                 "--min-size", "10", "--must-match", "Phase III",
                 "--must-not-match", "Phase I trial"], tmp_path)
    assert _verdict(proc) == "PASS", proc.stdout


def test_validate_fixture_quarantines_dead_url(tmp_path):
    proc = _run([str(SCRIPTS / "validate_fixture.py"), "url",
                 "http://no-such-host.invalid/x", "--timeout", "5"], tmp_path)
    assert _verdict(proc) == "QUARANTINE", proc.stdout
