---
name: evidence
description: This skill should be used when deciding whether verification evidence is strong enough to record a PASS, or whether to record SKIP or BLOCKED instead. It defines what counts as proof per surface and forbids treating "it builds / 200 / no exception / pre-existing tests pass" as evidence.
version: 0.1.0
---

# Evidence — what counts as proof

## Overview

A verdict is only as good as the evidence behind it. This skill sets the bar: PASS requires a
real interaction with the changed surface, captured as an artifact. Absence of errors is not
evidence. Use this together with `surface-router` (which surface) and `anti-fakery` (is the
oracle valid).

## The three verdicts

- **PASS** — every exposed surface was reached and proven, and the Family-D cross-check passed.
  Requires a concrete evidence artifact (see below).
- **SKIP** — no runtime surface. One line, one reason. Docs-only, comments-only,
  type-declarations-only, test-only with no behavioral diff. Nothing else.
- **BLOCKED** — a surface could not be reached. State exactly where it stuck (missing creds, no
  sandbox, environment unavailable). BLOCKED is always better than a false PASS.

Record with:
`python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record_verdict.py <PASS|SKIP|BLOCKED> "<evidence>"`

## Not evidence (these never justify PASS)

- "The build / typecheck succeeded."
- "It returned 200" (without asserting body shape AND the state that should have changed).
- "No exception was thrown."
- "The existing test suite passes" (that is a CI rerun, not verification of what changed).
- "The string matches the regex" (format-valid ≠ correct).
- "I re-read the code and it looks right."

## Evidence that counts, by surface

| Surface | Minimum evidence artifact |
|---|---|
| browser / UI | screenshot or DOM snapshot of the real flow + a stated judgment of what it shows |
| interaction | per-step state assertions through the end-to-end flow |
| data / invariants | row-count delta vs baseline + uniqueness/FK/null-rate results |
| semantic / LLM-doc | content assertions proving it really meets the criteria (live fetch, phase, sections) |
| api / contract | status + schema assertion + the changed downstream state |
| cli / tty | captured rendered output (not just exit code) |
| audio / media | duration + RMS-non-silent + sample-rate probe |
| latency | measured p50/p95/p99 vs the stated budget |
| auth | authenticated-state assertion AND a denied negative probe |
| any test used as proof | a `mutate_*` report showing the test is not WEAK |
| any fixture used as proof | a `validate_fixture` report showing it is not QUARANTINEd |

## Honesty rules

- If you did not reach the surface, you did not verify it — record BLOCKED, not PASS.
- If the oracle is invalid (anti-fakery QUARANTINE / WEAK), the verdict cannot be PASS.
- One line of honest SKIP beats a paragraph of manufactured testing.
- A confirmed escape (a defect that a PASS missed) is a bug in the verification, not just the
  code — capture it so the same gap cannot pass silently again.
