# Verification surface routing table

The full reasoning lives in `verification-surface-atlas.md` at the repo root. This is the
condensed lookup the router uses: **diff signal → surface → the proof that actually counts.**
A typical change exposes 2–5 surfaces. Name them, demand proof for each, report BLOCKED when a
surface can't be reached. Format-valid is never correctness.

## A — Output correctness

| Signal in the diff | Surface | Proof that counts |
|---|---|---|
| UI components, CSS, templates, anything rendered | visual / browser | drive the real UI by intent (Playwright MCP), screenshot, judge the pixels — not "it builds" |
| event handlers, multi-step flows, forms | interaction | drive the end-to-end flow; assert state at each step |
| queries, joins, aggregations, dataframes, migrations | data values & invariants | row-count delta vs baseline + uniqueness + FK + null-rate + distribution drift |
| scraping/classification/extraction, "is this a valid X" | semantic content validity | assert it *really is* what was asked (phase, date, sections, live URL) — not regex/MIME shape |
| HTTP routes, handlers, serializers | api / contract | assert status AND body schema AND the state that should have changed |
| CLI entrypoints, argparse, stdout formatting | cli / tty | freeze rendered output; assert on text, not exit code |
| audio/media writes | audio / media | duration + RMS (non-silent) + sample rate; optional transcript round-trip |
| file generation (pdf, images, exports) | file integrity | magic-byte type + size floor + `hash != source` + actually open/parse it |
| math, money, stats, rounding | numeric | recompute independently; reconcile totals; check sign + units |

## B — Temporal & performance

| Signal | Surface | Proof |
|---|---|---|
| anything on a hot path, caching, queries | latency | p50/p95/p99 under realistic load vs a stated budget |
| timestamps, scheduling, alignment | timestamp sync / freshness | `event_time ≈ source_time` within tolerance; `max(timestamp)` inside expected window |
| concurrency, locks, async, double-submit | races | do it twice at once with stale state underneath |
| streaming, long-running jobs | drift | measure drift over a long run, not a short clip |

## C — Identity & access (mostly NEGATIVE testing)

| Signal | Surface | Proof |
|---|---|---|
| login, sessions, tokens | authentication | drive real login; assert authenticated state; exercise expiry + refresh |
| roles, permissions, guards | authorization | positive AND negative — a wrong-role user MUST be blocked |
| 2FA/TOTP | multi-factor | drive a real TOTP; confirm the gate actually gates |
| `.env`, secrets, config | secret provisioning | assert required secrets present AND used; fail loud on missing |
| multi-tenant data access | tenancy isolation | cross-tenant negative probe: user B must NOT see user A's data |
| any new entry point | negative security | injection / XSS / path-traversal probes |

## D — Oracle & test apparatus (THE CRUX — always cross-check)

This family verifies the *measuring instrument*. A broken oracle manufactures false PASS at
scale, silently. Run these regardless of the other surfaces — see the `anti-fakery` skill.

| Signal | Check | Proof |
|---|---|---|
| any test offered as evidence | assertion strength | mutate the covered code → the test MUST go red → restore (`mutate_python.py` / `mutate_ts.js`) |
| fixtures / gold sets | fixture validity | validate against real acceptance criteria, not "it's a PDF" (`validate_fixture.py`); quarantine failures |
| spiked / mutated inputs | spike applied | assert `hash(spiked) != hash(original)` and the defect is actually present |
| LLM-as-judge verdicts | judge calibration | agreement vs a human-labeled slice; same input → same verdict; resist distractors |
| the whole verification plan | surface coverage | did a step reach what CHANGED, or just rerun CI? if only build/typecheck/existing-tests → BLOCKED |
| any check | determinism | run suspect checks N times; a flip → quarantine, don't count |

## E — Integration & environment

| Signal | Surface | Proof |
|---|---|---|
| code spanning modules/services | component seams | end-to-end through the real interface |
| Dockerfile, lockfiles, deps | env parity / deps | clean-install from lock; run in prod-like env |
| feature flags, config combos | configuration | matrix the meaningful combinations |
| third-party calls | external contracts | assert the real downstream effect, not the call's 200 |
| re-runnable jobs, checkpoints | idempotency | run twice; kill mid-run and resume; assert identical end state |
| migrations | backfill | assert historical rows conform after migration |

## F — Robustness & edge

| Signal | Surface | Proof |
|---|---|---|
| error handling, try/except | error correctness | assert the error fires AND names the actual problem (see silent-failure-hunter) |
| any input parameter | boundaries + null | empty / zero / max / off-by-one / null explicitly |
| parsers, network input | malformed/adversarial | fuzz the entry points |
| text handling | encoding / i18n | non-ASCII, RTL, locale, TZ boundaries |
| delete / send / publish paths | destructive safety | require dry-run or sandbox before driving |

## G — Cross-cutting reality

| Signal | Surface | Proof |
|---|---|---|
| nondeterministic output | product determinism | same input → same output where expected |
| failure paths | observability | assert the failure path is logged/metered |
| refactors | regression of adjacents | probe the neighbors the refactor touched |
| build/runtime setup | clean-env reproducibility | build and run from a clean checkout |

## SKIP rule

No runtime surface → emit one line and stop, e.g.
`SKIP — no runtime surface: docs-only change` / `type declarations only` / `comments only` /
`test-only with no behavioral diff`. Do not manufacture work.
