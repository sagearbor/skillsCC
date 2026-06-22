---
name: anti-fakery
description: This skill should be used whenever a test, fixture, gold standard, or LLM-judge is offered as proof that something works — to verify the MEASURING INSTRUMENT itself. It mechanically catches vacuous tests that pass but assert nothing (mutation testing) and invalid fixtures/oracles (fixture validation), which are the two ways "the tests pass" becomes a lie.
version: 0.1.0
---

# Anti-Fakery — verify the measuring instrument

## Overview

Most false "done" traces back to a broken oracle, not a broken product. A test that cannot fail,
a fixture that isn't really what it claims, a spike that was never applied, an uncalibrated LLM
judge — each manufactures a green check that means nothing. This skill makes those failures
mechanical to catch. Run it on anything offered as evidence, regardless of which surface changed.

This is Family D of the atlas — the crux. Two deterministic scripts do the heavy lifting.

## 1. Assertion strength — can the test actually fail?

"Tests pass but test nothing" is the headline failure mode. Prove a test suite can go red by
mutating the code it covers: break one thing, rerun, the test MUST fail; restore. A mutation the
suite does not catch (a "survivor") is a defect the tests would miss in production.

Python:
```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/anti-fakery/scripts/mutate_python.py \
    --test-cmd "python3 -m pytest -q path/to/test_file.py" path/to/source.py [more_sources.py]
```
JS/TS:
```
node ${CLAUDE_PLUGIN_ROOT}/skills/anti-fakery/scripts/mutate_ts.js \
    --test-cmd "npx vitest run path/to/file.test.ts" path/to/source.ts
```

Read the JSON verdict:
- `PASS` — survival rate below threshold; the tests catch injected defects. Good evidence.
- `WEAK` — survivors exist; the tests miss real behavior changes. Treat the change as NOT proven;
  strengthen the assertions (or add tests) until the survivors are killed, then re-run.
- `INCONCLUSIVE` — baseline not green or no mutable sites; fix the baseline first.

The `--test-cmd` must run only the tests relevant to the changed code, or the runs will be slow.
Each command is split without a shell, so keep it to a plain argv (no pipes/`&&`); wrap complex
invocations in a small script and point `--test-cmd` at it. The Python checker is AST-precise;
the JS checker is a text heuristic — a JS `WEAK` is a strong signal, a JS `PASS` is supportive.

## 2. Fixture / oracle validity — is the gold really gold?

Validate any fixture, gold artifact, or scraped input against the *real* acceptance criteria —
not "it parses" or "it's URL-shaped". Quarantine anything that fails; never calibrate on it.

```
# A scraped "good URL": is it live and does it contain what was required?
python3 ${CLAUDE_PLUGIN_ROOT}/skills/anti-fakery/scripts/validate_fixture.py url <URL> \
    --must-match "Faculty" --must-match "@university\.edu"

# A gold document: right type, non-trivial, contains required sections?
python3 .../validate_fixture.py file gold.pdf --expect-type pdf --min-size 2000 \
    --must-match "Phase III" --must-match "Inclusion Criteria"

# A spiked/mutated input: did the spike actually change the bytes?
python3 .../validate_fixture.py file spiked.bin --not-identical-to original.bin
```
`QUARANTINE` means the oracle is invalid — any metric computed against it is noise. Fix or drop
the fixture before trusting any verdict that depends on it.

## 3. LLM-judge calibration (when the verdict is a model)

An LLM judge is itself a fallible oracle. Before trusting it: check agreement against a small
human-labeled slice, check consistency (same input → same verdict across repeats), and check it
resists obvious distractors. An uncalibrated judge is the highest-leverage false-positive
generator you have. (Automated tooling for this lands in a later phase; for now do it by hand and
record the agreement rate as evidence.)

## When a check has no power

Every check must be *able* to fail. If you cannot make a check go red on a deliberately broken
input, it is a vacuous oracle (the regex-as-URL-validator problem) — do not count its green.
