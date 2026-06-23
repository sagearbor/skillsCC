"""Self-tests for the data-invariants verifier."""
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "skills" / "verifier-data" / "scripts" / "data_invariants.py"
PY = sys.executable

USERS = "id,email,age\n1,a@x.com,30\n2,b@x.com,40\n3,c@x.com,50\n"
ORDERS_OK = "order_id,user_id,total\n10,1,5\n11,2,7\n12,3,9\n"


def _spec(tmp, source, checks):
    p = tmp / "spec.json"
    p.write_text(json.dumps({"source": source, "checks": checks}))
    return p


def _run(spec):
    proc = subprocess.run([PY, str(SCRIPT), "--spec", str(spec)], capture_output=True, text=True)
    return json.loads(proc.stdout), proc.returncode


def test_all_checks_pass_on_clean_csv(tmp_path):
    (tmp_path / "users.csv").write_text(USERS)
    spec = _spec(tmp_path, {"type": "csv", "path": str(tmp_path / "users.csv")}, [
        {"type": "row_count", "min": 1, "max": 10},
        {"type": "unique", "columns": ["id"]},
        {"type": "not_null", "column": "email"},
        {"type": "null_rate", "column": "email", "max": 0.0},
        {"type": "numeric_range", "column": "age", "min": 0, "max": 120},
        {"type": "distribution", "column": "age", "baseline_mean": 40, "tolerance": 0.1},
    ])
    out, code = _run(spec)
    assert out["verdict"] == "PASS", out
    assert code == 0


def test_duplicate_key_fails_unique(tmp_path):
    (tmp_path / "d.csv").write_text("id,email\n1,a@x.com\n1,b@x.com\n")
    spec = _spec(tmp_path, {"type": "csv", "path": str(tmp_path / "d.csv")},
                 [{"type": "unique", "columns": ["id"]}])
    out, code = _run(spec)
    assert out["verdict"] == "FAIL" and code == 1, out


def test_null_email_fails_not_null(tmp_path):
    (tmp_path / "n.csv").write_text("id,email\n1,a@x.com\n2,\n")
    spec = _spec(tmp_path, {"type": "csv", "path": str(tmp_path / "n.csv")},
                 [{"type": "not_null", "column": "email"}])
    out, _ = _run(spec)
    assert out["verdict"] == "FAIL", out


def test_foreign_key_violation_fails(tmp_path):
    (tmp_path / "users.csv").write_text(USERS)
    (tmp_path / "orders.csv").write_text("order_id,user_id,total\n10,1,5\n11,999,7\n")
    spec = _spec(tmp_path, {"type": "csv", "path": str(tmp_path / "orders.csv")}, [
        {"type": "foreign_key", "column": "user_id",
         "ref": {"type": "csv", "path": str(tmp_path / "users.csv")}, "ref_column": "id"},
    ])
    out, _ = _run(spec)
    assert out["verdict"] == "FAIL", out
    assert "not in ref" in out["checks"][0]["detail"]


def test_distribution_drift_fails(tmp_path):
    (tmp_path / "s.csv").write_text("id,score\n1,90\n2,95\n3,100\n")
    spec = _spec(tmp_path, {"type": "csv", "path": str(tmp_path / "s.csv")},
                 [{"type": "distribution", "column": "score", "baseline_mean": 50, "tolerance": 0.1}])
    out, _ = _run(spec)
    assert out["verdict"] == "FAIL", out


def test_numeric_range_violation_fails(tmp_path):
    (tmp_path / "a.csv").write_text("id,age\n1,30\n2,200\n")
    spec = _spec(tmp_path, {"type": "csv", "path": str(tmp_path / "a.csv")},
                 [{"type": "numeric_range", "column": "age", "min": 0, "max": 120}])
    out, _ = _run(spec)
    assert out["verdict"] == "FAIL", out


def test_sqlite_source_and_fk_pass(tmp_path):
    db = tmp_path / "d.sqlite"
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE users (id INTEGER, email TEXT)")
    con.executemany("INSERT INTO users VALUES (?,?)", [(1, "a@x.com"), (2, "b@x.com")])
    con.commit()
    con.close()
    spec = _spec(tmp_path, {"type": "sqlite", "path": str(db), "table": "users"}, [
        {"type": "row_count", "equals": 2},
        {"type": "unique", "columns": ["id"]},
        {"type": "not_null", "column": "email"},
    ])
    out, code = _run(spec)
    assert out["verdict"] == "PASS" and code == 0, out
