---
name: verifier-data
description: This skill should be used when verifying a change that touches data — SQL queries, joins, aggregations, ETL/pipelines, dataframes, migrations, or any generated table/CSV/dataset. It runs deterministic invariants (row counts, uniqueness, foreign keys, null rates, numeric ranges, distribution drift) because schema-valid data can still be wrong: a bad join, dropped or duplicated rows, a silently-nulled column.
version: 0.1.0
---

# Verifier — data values & invariants

## Overview

Data bugs are invisible where UI bugs are loud. A query returns rows, the schema validates, and
nothing errors — but the join dropped half the rows, a column is silently null, or a backfill
never ran. This verifier proves the *values* are right with deterministic, reusable checks, not
LLM judgment. It is the highest-value surface to mechanize because nothing off-the-shelf encodes
*your* domain invariants.

## When to use

Use when the diff touches anything that produces or transforms data: SQL, ORM queries,
aggregations, pipeline steps, migrations, exports. Pair with the `surface-router` (which routes
here) and `anti-fakery` (which validates the fixtures/baselines you compare against).

## How to run

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verifier-data/scripts/data_invariants.py --spec invariants.json
```

The spec declares one source (CSV or SQLite) and a list of checks:

```json
{
  "source": {"type": "sqlite", "path": "build.sqlite", "table": "orders"},
  "checks": [
    {"type": "row_count", "min": 1},
    {"type": "unique", "columns": ["order_id"]},
    {"type": "not_null", "column": "user_id"},
    {"type": "null_rate", "column": "discount_code", "max": 0.5},
    {"type": "foreign_key", "column": "user_id",
     "ref": {"type": "sqlite", "path": "build.sqlite", "table": "users"}, "ref_column": "id"},
    {"type": "numeric_range", "column": "total", "min": 0, "max": 100000},
    {"type": "distribution", "column": "total", "baseline_mean": 42.0, "tolerance": 0.15}
  ]
}
```

`source` may instead be `{"type": "sqlite", "path": "...", "query": "SELECT ..."}` to verify a
specific query's output, or `{"type": "csv", "path": "..."}`. Quick checks are also available as
CLI flags: `--source data.csv --rows-min 1 --unique id --not-null email`.

The script prints a JSON verdict (`PASS`/`FAIL`) with per-check detail and exits nonzero on
FAIL. Every check names exactly what failed (which column, how many bad rows) so the fix is
obvious.

## What to verify, by change type

- **A new/changed join or aggregation** → `row_count` vs a baseline you trust + `unique` on the
  grain you expect (catches fan-out duplicates) + `not_null` on join keys (catches dropped matches).
- **A migration/backfill** → `null_rate` on the backfilled column should drop to ~0; historical
  rows should now conform (`numeric_range` / `not_null`).
- **A pipeline refresh** → `row_count` within tolerance of the prior run + `distribution` drift on
  key metrics (catches a source that silently changed shape).
- **Referential changes** → `foreign_key` from child to parent (catches orphaned rows).

## Honesty

- The baseline you compare against is itself an oracle — validate it with `anti-fakery`'s
  `validate_fixture.py` before trusting a `row_count`/`distribution` result.
- If you can't reach the real produced data (the build didn't emit it, no DB access), report
  BLOCKED — do not PASS on the schema alone.
