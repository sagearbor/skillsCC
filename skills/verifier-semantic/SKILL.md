---
name: verifier-semantic
description: This skill should be used when verifying scraped, fetched, extracted, classified, or generated content is genuinely what was asked for — not just format-valid. Use for "is this really a Phase-III protocol / a live faculty page / the right document type / after date X with sections Y". It demands multiple independent content criteria because a single regex is a vacuous oracle for semantic correctness.
version: 0.1.0
---

# Verifier — semantic content validity

## Overview

The classic false PASS: a value matches a regex, returns 200, or is a PDF — and is still the
wrong thing. A faculty URL is live and URL-shaped but points at a dead profile; a "clinical-trial
protocol" is a valid PDF but isn't Phase III and lacks the required sections. The fix is to assert
*multiple independent* criteria over the real content. One regex answers "is this shaped like X";
that is not "is this X".

## When to use

Routed here by `surface-router` when the diff scrapes/ingests/classifies/extracts content, or
when a fixture's validity depends on what it *says*, not its format. Pair with `anti-fakery`'s
`validate_fixture.py` for liveness/type and with this for content meaning.

## How to run

```
python3 ${CLAUDE_PLUGIN_ROOT}/skills/verifier-semantic/scripts/semantic_check.py --spec criteria.json
# or inline:
python3 .../semantic_check.py --url https://dept.edu/faculty/jdoe \
    --require "Professor" --require "@.*\.edu" --section "Publications" --forbid "Page Not Found"
```

The source is a file or a URL (fetched live — a dead/wrong link fails). Criteria:
`min_words`, `require_all` (every pattern), `require_any` (≥1), `forbid` (none), `sections`
(heading-like lines), `date_after` (some real date ≥ cutoff). Verdict is PASS only if **all**
criteria hold. The script refuses to run with no criteria — a check that asserts nothing is a
vacuous oracle by construction.

## Make the oracle strong, not shaped

- Require **several independent signals**, not one. "Phase III" alone is weak; "Phase III" AND
  "Inclusion Criteria" AND a Methods section AND an enrollment date ≥ 2020 is hard to fake.
- Prefer criteria that a *wrong* document would fail: section structure, date windows, named
  entities — not generic words that any page in the domain contains.
- Validate the gold/expected set itself with `anti-fakery` before trusting comparisons against it
  (a calibration set of the wrong document type makes every number noise — Family D).

## When the verdict needs an LLM judge

Some semantic checks ("is this summary faithful to the source?") exceed pattern matching and need
an LLM-as-judge. The judge is itself a fallible oracle — calibrate before trusting it:

1. **Agreement** — run the judge on a small human-labeled slice; require high agreement before use.
2. **Consistency** — same input → same verdict across repeats; a judge that flips is noise.
3. **Distractor resistance** — it must reject plausible-but-wrong inputs, not rubber-stamp.

Record the agreement rate as evidence. If you cannot run a real judge (no API access in this
environment) or cannot calibrate it, report **BLOCKED** for the judged criterion — do not PASS on
an uncalibrated judge. (Automated judge-calibration tooling is a later phase; do it by hand and
record the numbers for now.)
