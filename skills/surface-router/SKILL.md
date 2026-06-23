---
name: surface-router
description: This skill should be used when about to claim a task is done, fixed, working, or complete, or when deciding HOW to verify a change — which surface to test (browser, auth, latency, data invariants, semantic/LLM-doc-ingestion, API, CLI, audio). It classifies what the diff exposes and routes to the proof that actually counts, so "it builds" is never mistaken for "it works".
version: 0.1.0
---

# Surface Router — detect how to test this

## Overview

Before any "done", answer one question: **given what changed, which independent ways could
this be wrong, and what would actually prove it isn't?** This skill turns a diff into a named
verification plan, then drives proof at each surface. It is the antidote to the most common
false "done": running the build, seeing no error, and declaring success without ever reaching
the surface that changed.

Format-valid is not correct. A 200, a passing regex, a clean build, a green pre-existing test —
none of these prove the change works. Route to the real surface and prove it there.

## When to use

Use the moment you are tempted to say done / fixed / working / complete, and whenever you must
decide how to test a change. The Stop gate (`hooks/scripts/gate.py`) will block stopping until a
verdict is recorded, so run this first.

## Procedure

1. **Read the actual diff.** `git diff HEAD` (plus untracked files). Do not verify from memory of
   what you intended to change — verify what is on disk.

2. **Classify the exposed surfaces.** Consult `references/atlas.md` and name every surface the
   diff exposes — most changes hit 2–5. The named list IS the verification plan. Be explicit;
   an unnamed surface is an unverified one.

3. **No runtime surface → SKIP.** Docs-only, comments-only, type-declarations-only, or a
   test-only change with no behavioral diff: record one line and stop.
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record_verdict.py SKIP "no runtime surface: <reason>"`
   Do not manufacture work.

4. **For each surface, demand the proof that counts** (the right-hand column of `atlas.md`).
   Reach the surface for real:
   - browser/UI → drive it with the Playwright MCP (`mcp__plugin_playwright_playwright__*`),
     screenshot, judge the result.
   - data → row-count deltas, uniqueness, FK, null-rate, distribution drift.
   - semantic / LLM-doc-ingestion → assert the content *really* meets the criteria (live URL,
     trial phase, date window, required sections), not just that it is URL-shaped or a PDF.
   - auth → positive AND negative; the wrong principal must be denied.
   - latency → p50/p95/p99 against a stated budget.

5. **Verify independently — do not self-certify.** The failure mode is the agent that wrote the
   code also blessing it. Dispatch a fresh verifier that did not write the code:
   - the `refute-done` agent (prompted to *refute* "this is done"),
   - `pr-review-toolkit:pr-test-analyzer` for test quality,
   - `pr-review-toolkit:silent-failure-hunter` for swallowed errors.

6. **Always run the Family-D cross-check.** Before trusting any result, invoke the `anti-fakery`
   skill: any test offered as evidence must survive mutation (it must be *able* to fail), and any
   fixture/gold must pass validation. A broken oracle manufactures false PASS at scale.

7. **Record the verdict for the current diff.**
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record_verdict.py <PASS|SKIP|BLOCKED> "<evidence>"`
   - PASS only with an evidence artifact pointing at the changed surface.
   - BLOCKED (not PASS) if a surface cannot be reached — say exactly where it stuck.
   - The verdict is tied to the diff's work signature; if you change more code afterwards, the
     gate re-fires and you must re-verify.

## What counts as evidence

See the `evidence` skill for the per-surface bar and the SKIP/BLOCKED rules. The short version:
evidence is a real interaction with the changed surface (screenshot, query result, transcript,
measured latency, mutation-survival report) — never "the build succeeded".

## Reference

- `references/atlas.md` — the full signal → surface → proof routing table (all seven families).
- `verification-surface-atlas.md` (repo root) — the reasoning behind the table.
