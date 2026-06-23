#!/usr/bin/env python3
"""Deterministic data-output verifier — the data values & invariants surface.

Data bugs are invisible where UI bugs are loud: a wrong join, dropped/duplicated rows, a
silently-nulled column, a backfill that never ran. Schema-valid is not correct. This runs a
spec of invariants over a table (CSV or SQLite) and reports PASS/FAIL with per-check detail.

Usage:
    data_invariants.py --spec invariants.json
    data_invariants.py --source data.csv --rows-min 1 --unique id --not-null email

Spec format (JSON):
    {
      "source": {"type": "csv", "path": "data.csv"},
        // or {"type": "sqlite", "path": "db.sqlite", "table": "t"}
        // or {"type": "sqlite", "path": "db.sqlite", "query": "SELECT ..."}
      "checks": [
        {"type": "row_count", "min": 1, "max": 1000},
        {"type": "row_count", "equals": 42},
        {"type": "unique", "columns": ["id"]},
        {"type": "not_null", "column": "email"},
        {"type": "null_rate", "column": "phone", "max": 0.2},
        {"type": "foreign_key", "column": "user_id",
         "ref": {"type": "csv", "path": "users.csv"}, "ref_column": "id"},
        {"type": "numeric_range", "column": "age", "min": 0, "max": 120},
        {"type": "distribution", "column": "score", "baseline_mean": 50, "tolerance": 0.1}
      ]
    }

Output: JSON verdict on stdout. Exit 0 PASS, 1 FAIL, 2 usage/load error.
"""
import argparse
import csv
import json
import sqlite3
import statistics
import sys

NULLISH = {"", "null", "none", "na", "nan"}


def _is_null(v):
    return v is None or (isinstance(v, str) and v.strip().lower() in NULLISH)


def load(source):
    """Return (columns, rows) where rows is a list of dicts."""
    stype = source["type"]
    if stype == "csv":
        with open(source["path"], newline="") as fh:
            reader = csv.DictReader(fh)
            rows = list(reader)
            return (reader.fieldnames or []), rows
    if stype == "sqlite":
        con = sqlite3.connect(source["path"])
        con.row_factory = sqlite3.Row
        try:
            if "query" in source:
                cur = con.execute(source["query"])
            else:
                cur = con.execute(f'SELECT * FROM "{source["table"]}"')
            fetched = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
            return cols, [dict(r) for r in fetched]
        finally:
            con.close()
    raise ValueError(f"unknown source type: {stype}")


def _col(rows, column):
    return [r.get(column) for r in rows]


def check_row_count(rows, cols, c):
    n = len(rows)
    detail = f"{n} rows"
    if "equals" in c:
        return n == c["equals"], detail + f" (expected {c['equals']})"
    ok = True
    if "min" in c:
        ok = ok and n >= c["min"]
    if "max" in c:
        ok = ok and n <= c["max"]
    return ok, detail + f" (min={c.get('min')}, max={c.get('max')})"


def check_unique(rows, cols, c):
    columns = c["columns"]
    seen, dupes = set(), 0
    for r in rows:
        key = tuple(r.get(col) for col in columns)
        if key in seen:
            dupes += 1
        seen.add(key)
    return dupes == 0, f"{dupes} duplicate key(s) on {columns}"


def check_not_null(rows, cols, c):
    nulls = sum(1 for v in _col(rows, c["column"]) if _is_null(v))
    return nulls == 0, f"{nulls} null/missing in {c['column']}"


def check_null_rate(rows, cols, c):
    vals = _col(rows, c["column"])
    rate = (sum(1 for v in vals if _is_null(v)) / len(vals)) if vals else 0.0
    return rate <= c["max"], f"null rate {rate:.3f} (max {c['max']})"


def check_foreign_key(rows, cols, c):
    _, ref_rows = load(c["ref"])
    ref_vals = {str(r.get(c["ref_column"])) for r in ref_rows}
    missing = [v for v in _col(rows, c["column"]) if not _is_null(v) and str(v) not in ref_vals]
    return len(missing) == 0, f"{len(missing)} value(s) of {c['column']} not in ref {c['ref_column']}"


def check_numeric_range(rows, cols, c):
    bad = []
    for v in _col(rows, c["column"]):
        if _is_null(v):
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            bad.append(v)
            continue
        if ("min" in c and x < c["min"]) or ("max" in c and x > c["max"]):
            bad.append(v)
    return len(bad) == 0, f"{len(bad)} value(s) of {c['column']} out of [{c.get('min')},{c.get('max')}]"


def check_distribution(rows, cols, c):
    nums = []
    for v in _col(rows, c["column"]):
        if _is_null(v):
            continue
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            pass
    if not nums:
        return False, f"{c['column']}: no numeric values to compare"
    mean = statistics.fmean(nums)
    base = c["baseline_mean"]
    tol = c["tolerance"]
    denom = abs(base) if base else 1.0
    drift = abs(mean - base) / denom
    return drift <= tol, f"mean {mean:.3f} vs baseline {base} (drift {drift:.3f}, tol {tol})"


HANDLERS = {
    "row_count": check_row_count,
    "unique": check_unique,
    "not_null": check_not_null,
    "null_rate": check_null_rate,
    "foreign_key": check_foreign_key,
    "numeric_range": check_numeric_range,
    "distribution": check_distribution,
}


def build_spec_from_cli(args):
    if not args.source:
        return None
    checks = []
    if args.rows_min is not None:
        checks.append({"type": "row_count", "min": args.rows_min})
    if args.rows_max is not None:
        checks.append({"type": "row_count", "max": args.rows_max})
    for col in args.unique or []:
        checks.append({"type": "unique", "columns": col.split(",")})
    for col in args.not_null or []:
        checks.append({"type": "not_null", "column": col})
    stype = "sqlite" if args.source.endswith((".sqlite", ".db")) else "csv"
    source = {"type": stype, "path": args.source}
    if stype == "sqlite":
        source["table"] = args.table
    return {"source": source, "checks": checks}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec")
    ap.add_argument("--source")
    ap.add_argument("--table")
    ap.add_argument("--rows-min", type=int)
    ap.add_argument("--rows-max", type=int)
    ap.add_argument("--unique", action="append")
    ap.add_argument("--not-null", action="append")
    args = ap.parse_args()

    spec = json.loads(open(args.spec).read()) if args.spec else build_spec_from_cli(args)
    if not spec:
        print(json.dumps({"verdict": "FAIL", "reason": "no --spec or --source given"}))
        return 2
    try:
        cols, rows = load(spec["source"])
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(json.dumps({"verdict": "FAIL", "reason": f"could not load source: {exc}"}))
        return 2

    results = []
    for c in spec.get("checks", []):
        handler = HANDLERS.get(c["type"])
        if handler is None:
            results.append({"check": c["type"], "passed": False, "detail": "unknown check type"})
            continue
        try:
            passed, detail = handler(rows, cols, c)
        except (KeyError, OSError, ValueError, sqlite3.Error) as exc:
            passed, detail = False, f"check error: {exc}"
        results.append({"check": c["type"], "passed": passed, "detail": detail})

    ok = all(r["passed"] for r in results) and bool(results)
    print(json.dumps({
        "verdict": "PASS" if ok else "FAIL",
        "rows": len(rows),
        "columns": cols,
        "checks": results,
    }, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
