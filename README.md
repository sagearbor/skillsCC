# proof-of-done

**An agent can't say "done" until it proves it.**

A Claude Code **plugin** that stops agents from emitting false-positive "done" states. When you
give agents higher-level scope, the bottleneck moves from *writing* code to *trusting* that the
agent actually verified it. `proof-of-done` makes a PASS expensive to claim: the agent must route
the change to the right verification surface, reach that surface with an **independent**
verifier, prove any test it offers can actually fail, and capture evidence — or it reports
BLOCKED instead of lying that it finished.

> **Status:** Phase 1 is built and tested (see [Status](#status)). Phases 2–4 are planned.

---

## The problem this solves

Agentic dev only works if the agent's "done" is trustworthy. Today it isn't:

- The agent runs the build, sees no error, and declares success — but never exercised the actual
  surface (clicked the button, ran the query, fetched the URL, played the audio).
- It writes or re-runs tests that go green but **assert nothing about what changed** — a vacuous
  oracle. "Tests pass" becomes a lie.
- It verifies against a **fixture or gold set that is itself wrong** (dead URL, wrong document
  type, a "spike" that never changed the bytes), so the pass is meaningless.
- It can't tell that a docs-only or type-only change has **no runtime surface** and wastes a loop
  pretending to test it.

The two failure modes in the middle — vacuous tests and invalid oracles — are **Family D** of the
[Verification Surface Atlas](verification-surface-atlas.md): the *measuring instrument* is broken,
not the product. They are the most expensive because a broken oracle manufactures false PASS at
scale, silently. `proof-of-done` attacks them head-on.

---

## Core principles

1. **PASS requires evidence, not absence of errors.** A verdict must point at a real interaction
   with the changed surface (screenshot, query result, transcript, measured latency, mutation
   report). "Build succeeded" is not evidence.
2. **Verify independently — don't self-certify.** The agent that wrote a vacuous test will
   rubber-stamp it. Verification runs in a *separate* agent prompted to **refute** "done".
3. **Distrust the measuring instrument.** Any test offered as proof must be shown able to fail;
   any fixture must be validated against real criteria. (Family D.)
4. **Route by surface, then prove at that surface.** Name the orthogonal axes the diff touches
   and verify each — don't substitute a cheaper axis.
5. **SKIP honestly / BLOCKED beats a false PASS.** No runtime surface → one-line SKIP. Surface
   unreachable → BLOCKED with exactly where it stuck. Never a papered-over green check.

---

## Architecture

```
            ┌──────────────────────────────────────────────┐
   task →   │  GATE  (Stop hook, hooks/scripts/gate.py)     │  ← blocks "done" until a
            │  blocks finishing until a verdict exists for  │     verdict exists for the
            │  the CURRENT diff (tied to a git work sig)    │     current work signature
            └───────────────────┬──────────────────────────┘
                                │
            ┌───────────────────▼──────────────────────────┐
            │  SURFACE ROUTER  (skills/surface-router)      │  ← "how do I test this?"
            │  reads the diff → names exposed surfaces →     │
            │  routes to the proof that counts (atlas.md)    │
            │  no runtime surface → SKIP                     │
            └───────────────────┬──────────────────────────┘
                                │ dispatches an INDEPENDENT verifier
                                │ (agents/refute-done) + reused review agents
   ┌─────────┬─────────┬────────┼─────────┬──────────────────────────┐
   ▼         ▼         ▼        ▼         ▼                          ▼
 browser   auth     latency   data    semantic / LLM-doc      error-paths + test-quality
  (P2)     (P2)      (P2)     (P2)     ingestion (P2)          (reuse pr-review agents)
                                │
            ┌───────────────────▼──────────────────────────┐
            │  ANTI-FAKERY LAYER  (skills/anti-fakery)      │  ← always runs; the
            │  • mutate_python.py / mutate_ts.js: a test    │     deterministic core
            │    that survives mutation is WEAK             │
            │  • validate_fixture.py: quarantine dead URLs, │
            │    wrong-type gold, unapplied spikes          │
            └───────────────────┬──────────────────────────┘
                                │
            ┌───────────────────▼──────────────────────────┐
            │  /prove (P3) · /capture-gap + regressions/ (P4)│
            └────────────────────────────────────────────────┘
```

`(P2)`/`(P3)`/`(P4)` mark planned phases. Phase 1 (gate, router, anti-fakery, the `refute-done`
agent, evidence rules, evals seed) is built.

### Why this differs from the original design

The first draft of this README assumed Claude Code shipped native verification machinery
(`/init-verifiers`, `/verify`, `/run`, a `verification-specialist` agent). **It does not** — those
do not exist in current Claude Code. So `proof-of-done` builds verification dispatch itself on
subagents, and reuses the existing `pr-review-toolkit` agents
(`pr-test-analyzer` for test quality, `silent-failure-hunter` for swallowed errors) and the
Playwright MCP for browser surfaces.

---

## The gate, in detail

`hooks/scripts/gate.py` is a `Stop` hook. When the agent tries to finish, the gate:

1. Computes a **work signature** — a hash of the current `git diff` (excluding its own
   `.proof-of-done/` state). This shifts whenever the working tree changes.
2. Looks for `.proof-of-done/verdict.json`. The agent records this by running the verification and
   calling `hooks/scripts/record_verdict.py <PASS|SKIP|BLOCKED> "<evidence>"`.
3. **Allows** stopping only if a `PASS`/`SKIP`/`BLOCKED` verdict exists *for the current
   signature*. A stale verdict (code changed after it was recorded) re-blocks — this is what
   stops a big build from accumulating unverified "done"s.
4. **Blocks** otherwise, returning instructions to run the `surface-router` and `anti-fakery`
   checks first.

---

## Repo layout (actual)

```
proof-of-done/                         (this repo IS the plugin)
├── .claude-plugin/plugin.json         manifest
├── skills/
│   ├── surface-router/SKILL.md        detect how to test a diff
│   │   └── references/atlas.md        signal → surface → proof routing table
│   ├── anti-fakery/SKILL.md           Family-D discipline
│   │   └── scripts/
│   │       ├── mutate_python.py       AST mutation: prove a pytest suite can fail
│   │       ├── mutate_ts.js           text mutation: prove a JS/TS suite can fail
│   │       └── validate_fixture.py    quarantine invalid fixtures / oracles
│   └── evidence/SKILL.md              per-surface evidence bar + SKIP/BLOCKED rules
├── agents/refute-done.md              independent verifier, prompted to refute "done"
├── hooks/
│   ├── hooks.json                     registers the Stop gate
│   └── scripts/{gate.py, record_verdict.py}
├── evals/cases.json                   trigger + must-catch eval seeds
├── regressions/                       one fixture per historical escape (Phase 4)
├── verification-surface-atlas.md      the full reasoning behind the routing table
└── verification-surfaces.mermaid      the atlas mindmap source
```

---

## Install & activate

`proof-of-done` is a standard Claude Code plugin. The skills, agent, and scripts work as soon as
the plugin is loaded; the **Stop gate** additionally requires a session restart (Claude Code does
not hot-swap hooks).

1. **Load the plugin.** Add this repo as a plugin (e.g. via `/plugin` → install from the local
   path `…/skillsCC`, or from the GitHub repo `sagearbor/skillsCC`).
2. **Restart Claude Code** so the `Stop` hook in `hooks/hooks.json` registers.
3. **Verify it's live:** start a change in a git repo, try to end the turn — the gate should block
   with a "you have not proven this work is done" message until you record a verdict.

**Opt-in without packaging as a plugin** (e.g. to enable the gate only in one repo): add a `Stop`
hook to that project's `.claude/settings.json` pointing at the absolute path of `gate.py`:

```json
{
  "hooks": {
    "Stop": [
      { "matcher": "*", "hooks": [
        { "type": "command", "command": "python3 /ABSOLUTE/PATH/TO/skillsCC/hooks/scripts/gate.py", "timeout": 60 }
      ] }
    ]
  }
}
```

> The gate **blocks the agent from ending its turn** until a verdict is recorded. Enable it
> deliberately — it changes how every task in that scope finishes. `.proof-of-done/` (the verdict
> state) is git-ignored.

---

## Using the anti-fakery checks directly

These are deterministic and runnable on their own — useful even before the gate is wired up.

```bash
# Prove a Python test suite can actually fail (a surviving mutation ⇒ WEAK)
python3 skills/anti-fakery/scripts/mutate_python.py \
    --test-cmd "python3 -m pytest -q tests/test_foo.py" src/foo.py

# Same for JS/TS (text-based heuristic; the Python one is AST-precise)
node skills/anti-fakery/scripts/mutate_ts.js \
    --test-cmd "node --test foo.test.js" foo.js

# Quarantine an invalid fixture/oracle
python3 skills/anti-fakery/scripts/validate_fixture.py url https://example.edu/faculty/x \
    --must-match "Faculty"
python3 skills/anti-fakery/scripts/validate_fixture.py file gold.pdf --expect-type pdf --min-size 2000
```

`--test-cmd` is split without a shell (no pipes/`&&`); wrap complex invocations in a script.

---

## Status

| Phase | Scope | State |
|---|---|---|
| **1** | Gate · surface-router · anti-fakery scripts · `refute-done` · evidence rules · evals seed | **Done & tested** — all three scripts verified end-to-end; gate verified across 6 states; `plugin-validator` clean |
| 2 | Real surface verifiers: browser (Playwright MCP), semantic/LLM-doc, data invariants, auth ±, latency | Planned |
| 3 | `/prove` over an integrated milestone + auto-escalation from the gate | Planned |
| 4 | `/capture-gap` + `regressions/` moat + full eval runner red-teaming the verifier itself | Planned |

---

## Success criteria

- The agent never reports PASS without an evidence artifact for the changed surface.
- No-surface changes return SKIP in one line, not a fake test.
- A test offered as proof is shown able to fail; an invalid fixture is quarantined, not trusted.
- `regressions/` grows by one fixture for every defect a human catches — and stays green after.

---

## License

MIT.
