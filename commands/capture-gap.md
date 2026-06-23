---
description: Turn a defect that slipped past a PASS into a permanent regression check + a new Gotcha
argument-hint: "describe the escaped defect (what was wrong that verification missed)"
allowed-tools: Bash, Read, Edit, Write, Grep, Glob, Task
---

# /capture-gap — make an escape impossible to repeat

A defect that a PASS missed is a bug in the *verification*, not just the code. This command turns
that escape into a permanent, structural check so the same gap can never pass silently twice — the
compounding moat.

The escaped defect: **$ARGUMENTS**

## Procedure

1. **Reproduce the miss against current code.** Use `systematic-debugging` discipline: write the
   minimal input and the assertion that *should* have failed. Confirm it actually reproduces now
   (red). If it doesn't reproduce, say so — don't fabricate a fixture.

2. **Identify the surface and the weak oracle.** Which verifier should have caught this, and why
   didn't it? Name the axis from the `surface-router` atlas (often a Family-D gap: a vacuous
   assertion, an invalid fixture, an unreached surface).

3. **Write a regression fixture.**
   - Add an executable regression test under `tests/` (so `evals/run.py` enforces it forever) that
     fails on the buggy behavior and passes once fixed.
   - Record the escape in `regressions/` (a short note: input, expected vs actual, the surface,
     the date) for the human-readable moat.

4. **Patch the relevant verifier's Gotchas.** Append to the responsible skill's SKILL.md (or its
   reference) a short "Gotcha" describing the failure point, so routing/checks now cover this
   surface or edge. This accumulated list is the highest-signal content in the plugin.

5. **Re-run red-then-green.** Confirm the new regression test fails on the old behavior and passes
   after the fix. Then run `python3 ${CLAUDE_PLUGIN_ROOT}/evals/run.py` — it must be ALL GREEN.

6. **Open a PR** with the fixture + the Gotcha diff + the fix. Title it `capture-gap: <one line>`.

## Rules

- The regression test must be *able to fail* — verify it goes red on the old behavior before
  trusting its green (assertion-strength applies to your own fixture too).
- Prefer one reproduced, enforced regression over a vague note.
- If the gap was an uncalibrated oracle (judge/fixture), the Gotcha must address the oracle, not
  just the one input.
