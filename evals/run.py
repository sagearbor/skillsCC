#!/usr/bin/env python3
"""proof-of-done eval runner.

Single command to validate the plugin's mechanical guarantees: runs the self-test suite
(pytest + node:test), which executes the must-catch cases from evals/cases.json, and prints
a pass/fail summary. Exit code is nonzero if anything fails — wire this into CI.

Usage: python3 evals/run.py
"""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def run(label, args, cwd=ROOT):
    print(f"\n=== {label} ===")
    proc = subprocess.run(args, cwd=cwd)
    return proc.returncode == 0


def main():
    cases = json.loads((ROOT / "evals" / "cases.json").read_text())
    mech = cases.get("mechanical", [])
    print(f"proof-of-done evals — {len(mech)} mechanical cases, "
          f"{len(cases.get('trigger', []))} trigger cases (trigger cases are doc-only).")

    results = {
        "pytest (anti-fakery + gate)": run(
            "pytest", [PY, "-m", "pytest", "-q", "tests/test_anti_fakery.py", "tests/test_gate.py"]),
        "node:test (mutate_ts)": run(
            "node --test", ["node", "--test", "tests/test_mutate_ts.mjs"]),
    }

    print("\n=== summary ===")
    ok = True
    for name, passed in results.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
        ok = ok and passed
    print("\nALL GREEN" if ok else "\nFAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
