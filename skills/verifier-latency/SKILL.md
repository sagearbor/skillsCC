---
name: verifier-latency
description: This skill should be used when verifying a change that could affect performance — anything on a hot path, a new query or endpoint, caching, loops over large inputs, or a stated latency/SLA budget. It measures real p50/p95/p99 latency over many runs against a budget, because "it felt fast once" and a warm-cache single run hide tail-latency regressions.
version: 0.1.0
---

# Verifier — latency & tail performance

## Overview

A result can be correct in value yet wrong in time, and timing regressions are invisible until
measured explicitly. One warm run tells you nothing about p95/p99 — where real users live. This
verifier runs a command or endpoint many times and checks tail percentiles against a budget.

## When to use

Use when the diff touches a hot path, a query/endpoint, caching, batch sizes, or anything with a
stated latency budget. Routed here by `surface-router` for the temporal/performance surface.

## How to run

```
# Time a command (everything after `--`), assert p95 budget
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verifier-latency/scripts/latency_probe.py \
    --runs 30 --warmup 3 --budget-p95-ms 500 -- mycli --do-the-work

# Time an HTTP endpoint
python3 .../latency_probe.py --url http://localhost:8000/api/search \
    --runs 50 --warmup 5 --budget-p95-ms 200 --budget-p99-ms 400
```

Budgets are any subset of `--budget-p50-ms` / `--budget-p95-ms` / `--budget-p99-ms`. The verdict
is `FAIL` if any stated budget is exceeded **or** if any run errors (a broken endpoint has no
meaningful latency). Warmups are excluded from the stats. With no budget, it's a measurement-only
run (reports percentiles, always PASS) — use that to establish a baseline before setting one.

## Evidence that counts

- Measure under **realistic conditions** (production-like data volume, not a 3-row fixture); a
  budget met on toy input is not evidence.
- Quote the actual p95/p99 vs the budget in your verdict, not "seemed fast".
- For throughput/scale concerns, run at production scale and watch p99 and memory, not just p50.

## Honesty

- If you can't run the real workload (no server, no prod-like data), report BLOCKED — do not PASS
  on a localhost toy measurement and call the budget met.
- A single fast run is not a latency verification; require enough runs that p95/p99 are stable.
