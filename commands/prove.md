---
description: Prove the current work is done — route every changed surface to a real verifier and record a verdict
argument-hint: "[optional: base ref, e.g. main] or a scope note"
allowed-tools: Bash, Read, Grep, Glob, Task
---

# /prove — milestone verification across the integrated diff

Run full proof-of-done verification over everything that changed, not just the last edit. Use
this at a feature/milestone boundary (and the Stop gate will recommend it when a change spans
several files). Do **not** claim done from memory — verify what is on disk.

## Procedure

1. **Get the real diff.** Default to `git diff $ARGUMENTS` if a base ref was given, else
   `git diff main...HEAD` plus uncommitted changes (`git status --porcelain`, `git diff HEAD`).
   List every changed file.

2. **Classify all exposed surfaces.** Invoke the `surface-router` skill against the full diff.
   Name every surface (most milestones hit 4–6): browser, interaction, data, semantic, api, cli,
   audio, latency, auth, integration, edge. If there is genuinely no runtime surface, record SKIP
   and stop.

3. **Verify each surface independently — do not self-certify.** For each named surface, dispatch
   a fresh verifier (Task tool) that did not write the code:
   - the `refute-done` agent (prompted to refute "done"),
   - data → `verifier-data` / `data_invariants.py`,
   - latency → `verifier-latency` / `latency_probe.py`,
   - semantic → `verifier-semantic` / `semantic_check.py`,
   - browser → `verifier-browser` (Playwright MCP),
   - auth → `verifier-auth` (positive AND negative),
   - tests offered as evidence → reuse `pr-review-toolkit:pr-test-analyzer`,
     error handling → `pr-review-toolkit:silent-failure-hunter`.

4. **Run the Family-D anti-fakery cross-check.** Invoke `anti-fakery`: every test offered as
   proof must survive mutation (`mutate_python.py` / `mutate_ts.js` must not report WEAK); every
   fixture/oracle must pass `validate_fixture.py`. A broken oracle voids the PASS.

5. **Collate and record one verdict.** PASS only if every exposed surface was reached and proven
   and the anti-fakery cross-check passed. If any surface is unreachable, record BLOCKED naming
   exactly which and why — never a partial PASS.
   `python3 ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/record_verdict.py <PASS|SKIP|BLOCKED> "<evidence>"`

6. **Report** a per-surface table: surface · reached? · evidence artifact or blocker.

## Rules

- One unreached surface = BLOCKED, not PASS.
- Evidence is a real interaction with the changed surface (see the `evidence` skill), never "it
  builds" or "existing tests pass".
- Run `python3 ${CLAUDE_PLUGIN_ROOT}/evals/run.py` if the change touched the plugin's own scripts.
