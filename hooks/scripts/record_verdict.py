#!/usr/bin/env python3
"""Record a proof-of-done verdict tied to the current work signature.

The surface-router / verification run calls this once it has reached every exposed surface and
run the anti-fakery checks. It writes .proof-of-done/verdict.json with the current git work
signature so the Stop gate (gate.py) knows the verdict matches the diff actually on disk.

Usage:
    record_verdict.py <PASS|SKIP|BLOCKED|FAIL> "<one-line evidence>" [--project DIR]

FAIL is accepted so a failing run can be recorded honestly; the gate treats anything other than
PASS/SKIP/BLOCKED as "not done" and keeps blocking.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gate import work_signature  # noqa: E402

VERDICTS = {"PASS", "SKIP", "BLOCKED", "FAIL"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("verdict", choices=sorted(VERDICTS))
    ap.add_argument("evidence")
    ap.add_argument("--project", default=os.getcwd())
    args = ap.parse_args()

    sig, _, _ = work_signature(args.project)
    out_dir = os.path.join(args.project, ".proof-of-done")
    os.makedirs(out_dir, exist_ok=True)
    record = {
        "verdict": args.verdict,
        "evidence": args.evidence,
        "work_signature": sig,
    }
    with open(os.path.join(out_dir, "verdict.json"), "w") as fh:
        json.dump(record, fh, indent=2)
    print(json.dumps({"recorded": record}, indent=2))


if __name__ == "__main__":
    main()
