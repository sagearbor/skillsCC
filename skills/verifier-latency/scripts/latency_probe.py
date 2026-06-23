#!/usr/bin/env python3
"""Latency verifier — the temporal/performance surface.

"Works on a warm cache" hides p95/p99 blowups. This measures real latency over N runs and
checks tail percentiles against a stated budget, so a change that's correct in value but wrong
in time fails loudly instead of passing.

Two modes:
  command:  latency_probe.py --runs 20 --warmup 2 --budget-p95-ms 500 -- mycmd --arg
            Runs the command (argv after `--`) N times; measures wall time of each run.
  url:      latency_probe.py --url http://localhost:8000/health --runs 50 --budget-p95-ms 200
            Issues N HTTP GETs; measures response time.

Budgets: any subset of --budget-p50-ms / --budget-p95-ms / --budget-p99-ms. The verdict is
FAIL if any stated budget is exceeded, or if any run errors (you can't measure the latency of a
broken endpoint). Warmup runs are excluded from the stats.

Output: JSON on stdout. Exit 0 PASS, 1 FAIL, 2 usage error.
"""
import argparse
import json
import math
import subprocess
import sys
import time
import urllib.error
import urllib.request


def percentile(sorted_vals, p):
    if not sorted_vals:
        return None
    k = max(0, math.ceil(p / 100 * len(sorted_vals)) - 1)
    return sorted_vals[k]


def time_command(argv, timeout):
    start = time.perf_counter()
    try:
        proc = subprocess.run(argv, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, "timeout"
    except (OSError, ValueError) as exc:
        return None, f"launch error: {exc}"
    elapsed_ms = (time.perf_counter() - start) * 1000
    if proc.returncode != 0:
        return None, f"exit {proc.returncode}"
    return elapsed_ms, None


def time_url(url, timeout):
    req = urllib.request.Request(url, headers={"User-Agent": "proof-of-done/0.1"})
    start = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            resp.read()
            status = resp.status
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        return None, f"request failed: {exc}"
    elapsed_ms = (time.perf_counter() - start) * 1000
    if status != 200:
        return None, f"status {status}"
    return elapsed_ms, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=20)
    ap.add_argument("--warmup", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=30)
    ap.add_argument("--url")
    ap.add_argument("--budget-p50-ms", type=float)
    ap.add_argument("--budget-p95-ms", type=float)
    ap.add_argument("--budget-p99-ms", type=float)
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="command to time, after `--` (command mode)")
    args = ap.parse_args()

    argv = args.command[1:] if args.command and args.command[0] == "--" else args.command
    if not args.url and not argv:
        print(json.dumps({"verdict": "FAIL", "reason": "give --url or a command after --"}))
        return 2

    samples, errors = [], []
    total = args.warmup + args.runs
    for i in range(total):
        if args.url:
            ms, err = time_url(args.url, args.timeout)
        else:
            ms, err = time_command(argv, args.timeout)
        if i < args.warmup:
            continue  # discard warmups
        if err:
            errors.append(err)
        else:
            samples.append(ms)

    if errors:
        print(json.dumps({
            "verdict": "FAIL",
            "reason": f"{len(errors)} of {args.runs} runs errored — cannot trust latency",
            "errors": errors[:5],
            "measured": len(samples),
        }, indent=2))
        return 1

    samples.sort()
    stats = {
        "runs": len(samples),
        "min_ms": round(samples[0], 2),
        "p50_ms": round(percentile(samples, 50), 2),
        "p95_ms": round(percentile(samples, 95), 2),
        "p99_ms": round(percentile(samples, 99), 2),
        "max_ms": round(samples[-1], 2),
        "mean_ms": round(sum(samples) / len(samples), 2),
    }

    breaches = []
    for label, key, budget in [("p50", "p50_ms", args.budget_p50_ms),
                               ("p95", "p95_ms", args.budget_p95_ms),
                               ("p99", "p99_ms", args.budget_p99_ms)]:
        if budget is not None and stats[key] > budget:
            breaches.append(f"{label} {stats[key]}ms > budget {budget}ms")

    if args.budget_p50_ms is None and args.budget_p95_ms is None and args.budget_p99_ms is None:
        verdict = "PASS"  # measurement-only run, no budget asserted
        note = "no budget given — measurement only, not a pass/fail check"
    else:
        verdict = "FAIL" if breaches else "PASS"
        note = "within budget" if not breaches else "budget exceeded"

    print(json.dumps({"verdict": verdict, **stats, "breaches": breaches, "note": note}, indent=2))
    return 1 if verdict == "FAIL" else 0


if __name__ == "__main__":
    sys.exit(main())
