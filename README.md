# proof-of-done

**An agent can't say "done" until it proves it.**

A self-improving Claude Code skill that stops agents from emitting false-positive
"done" states. When you give agents higher-level scope, the bottleneck moves from
*writing* code to *trusting* that the agent actually verified it. `proof-of-done`
makes a PASS expensive to claim: the agent must route the change to the right
verification surface, reach that surface for real, and capture evidence — or it
reports BLOCKED instead of lying that it finished.

When a defect still slips through, a single agent-driven command turns that escape
into a permanent regression check, so the same gap can never pass silently twice.

---

## The problem this solves

Agentic dev only works if the agent's "done" is trustworthy. Today it isn't:

- The agent runs the build, sees no error, and declares success — but never exercised
  the actual surface (clicked the button, ran the query, played the audio).
- It re-runs the existing test suite (which CI already runs) and calls that
  "verification." That's a CI rerun, not a check of *what changed*.
- It can't tell that a docs-only or type-only change has **no runtime surface** and
  wastes a loop pretending to test it.
- When a human finally catches the miss, the lesson lives in a Slack thread and is
  lost by next week.

`proof-of-done` is the discipline layer that closes all four gaps.

---

## Core principles

1. **PASS requires evidence, not absence of errors.** A verdict must point at a
   real interaction with the changed surface (screenshot, query result, transcript,
   exit state). "Build succeeded" is not evidence.
2. **Route by surface, then prove at that surface.** Decide which orthogonal axis
   the diff touches and verify there — don't substitute a cheaper axis.
3. **SKIP honestly.** No runtime surface (docs, type decls, test-only PR, no
   behavioral diff) → `SKIP — no runtime surface: <reason>`. One line. Don't invent
   work.
4. **BLOCKED beats a false PASS.** If the surface can't be reached, say so with
   exactly where it stuck — never paper over it with a green check.
5. **Every escape becomes a regression.** A missed defect is a bug in the *skill*,
   not just the code. Capture it so it's caught structurally next time.

---

## Architecture

Three runtime layers plus one improvement loop.

```
        ┌─────────────────────────────────────────────┐
        │  GATE  (Stop hook — zero-token bash)         │
        │  Agent tries to stop → blocked until         │
        │  proof-of-done returns PASS or SKIP          │
        └───────────────────┬─────────────────────────┘
                            │
        ┌───────────────────▼─────────────────────────┐
        │  ROUTER  (the proof-of-done skill)           │
        │  • read the diff, classify surface(s)        │
        │  • no-surface → SKIP                         │
        │  • dispatch to verifier(s) for each surface  │
        └───────────────────┬─────────────────────────┘
                            │
   ┌────────────┬───────────┼───────────┬──────────────┐
   ▼            ▼           ▼           ▼              ▼
 browser      tui         api         data          audio
(playwright) (freeze)  (request)  (assertions)  (round-trip)

        ┌─────────────────────────────────────────────┐
        │  IMPROVEMENT LOOP  (/capture-gap)            │
        │  human finds a miss → agent reproduces it →  │
        │  writes a regression fixture + appends a      │
        │  Gotcha to the right verifier → re-runs to    │
        │  confirm red-then-green                       │
        └─────────────────────────────────────────────┘
```

### 1. The gate
A `Stop` hook that blocks the agent from finishing until `proof-of-done` has run and
returned a non-FAIL verdict. ~15 lines of bash, costs no tokens. This is the piece
that physically prevents a premature "done" — the router and verifiers are only
advisory without it.

### 2. The router (the skill itself)
`SKILL.md` encodes the surface taxonomy and the routing decision. It does **not**
re-implement test runners — it leans on Claude Code's native `verification-specialist`
+ `verifier-*` dispatch and `/init-verifiers`. What it adds is the false-positive
discipline: the surface-vs-CI distinction, the SKIP/BLOCKED rules, and the
evidence requirement.

### 3. The verifiers (per surface)
Orthogonal axes, each independently failable. Buy where it exists, build where it
doesn't:

| Surface | What "reaching it" means | Source |
|---|---|---|
| **browser** | drive the real UI by intent, screenshot, judge | off-the-shelf (Playwright MCP / opslane-style) |
| **tui / cli** | freeze the rendered terminal, LLM-as-judge, or TTY drive | off-the-shelf |
| **api / contract** | hit the route, assert shape + status on happy + edge | off-the-shelf |
| **data output** | schema, row-count deltas, uniqueness, FK integrity, **domain invariants** | **build — project-specific** |
| **audio / media** | file exists + non-silent + duration + optional transcript round-trip | **build — greenfield** |

The data verifier is the highest-value build: nothing off-the-shelf encodes *your*
business rules, and data bugs are invisible (wrong aggregation, dropped rows) where
UI bugs are loud. Mechanical checks (row counts, "file exists with expected dims")
should be verification **scripts**, not LLM judgment — scripts are deterministic and
reusable across iterations.

### 4. The self-improvement loop
The novel part. When a human catches a defect that passed, run one command:

```
/capture-gap
```

The agent then:
1. **Reproduces** the miss against the current code.
2. **Writes a regression fixture** — the minimal input + the assertion that *should*
   have failed — into `regressions/`.
3. **Patches the relevant verifier's `Gotchas`** section so the routing/check now
   covers this surface or edge.
4. **Re-runs red-then-green** — confirms the new fixture fails on the old skill and
   passes on the patched one.
5. Opens a PR with the fixture + the Gotcha diff.

Over time the skill's Gotchas section becomes a compounding asset — the
highest-signal content in any verification skill is exactly this accumulated list of
real failure points.

---

## Repo layout

```
proof-of-done/
├── README.md
├── skill/
│   ├── SKILL.md                 # the router: taxonomy + SKIP/BLOCKED/evidence rules
│   ├── references/
│   │   ├── surfaces.md          # how to recognize each surface from a diff
│   │   ├── evidence.md          # what counts as proof per surface
│   │   └── verifiers.md         # how to dispatch native + custom verifiers
│   └── scripts/
│       ├── classify_surface.py  # diff → surface set (deterministic where possible)
│       └── verdict.py           # collate verifier results → PASS/FAIL/SKIP/BLOCKED
├── verifiers/
│   ├── verifier-data/SKILL.md   # project-specific: schema, counts, invariants
│   └── verifier-audio/SKILL.md  # greenfield: existence, silence, duration, round-trip
├── hooks/
│   └── stop-gate.sh             # the Stop hook that blocks premature "done"
├── commands/
│   └── capture-gap.md           # /capture-gap — the self-improvement command
├── regressions/                 # one fixture per historical escape (the moat)
│   └── .gitkeep
└── evals/
    ├── cases.json               # prompts where the skill should/shouldn't trigger + assert
    └── grading.md               # assertion → PASS/FAIL rubric
```

---

## How it plugs into Claude Code

- **Skills**: `skill/` and each `verifiers/*` are standard `SKILL.md` skills. The
  router's `description` is intentionally pushy so it triggers on any
  "is this done / verify / finished" context, not just explicit asks.
- **Gate**: register `hooks/stop-gate.sh` as a `Stop` hook in your Claude Code
  settings so it fires when the agent tries to finish.
- **Native dispatch**: requires Claude Code v2.1.145+ for the bundled `/run`,
  `/verify`, and `/init-verifiers`. Run `/init-verifiers` once per project to
  generate the browser/tui/api verifiers; this repo supplies the data + audio ones
  the generator won't.
- **Self-improvement**: `/capture-gap` is a slash command (`commands/capture-gap.md`)
  that the agent executes; no human editing of the skill by hand.

---

## Build order (suggested)

1. **Gate first.** `hooks/stop-gate.sh` + the thinnest `SKILL.md` that returns
   PASS/SKIP/BLOCKED. This alone stops most false "done" states. (~1 day)
2. **Router rules.** Fill `references/surfaces.md` + `evidence.md` with the
   SKIP/BLOCKED discipline and per-surface evidence bar.
3. **Wire native verifiers** via `/init-verifiers` for browser/tui/api.
4. **Build `verifier-data`** with your domain invariants as deterministic scripts.
   This is the engineer-week that pays off. (~1 week)
5. **Add `/capture-gap`** and seed `regressions/` from the first real escape.
6. **Stand up `evals/`** so each skill change re-runs the trigger + assertion set
   before you ship it.
7. **(Optional) `verifier-audio`** if media output becomes frequent.

---

## Success criteria

- The agent never reports PASS without an evidence artifact for the changed surface.
- No-surface changes return SKIP in one line, not a fake test.
- `regressions/` grows by one fixture for every defect a human catches — and that
  fixture stays green forever after.
- Time-to-trust on an agent's "done" drops to the point where higher-level scope is
  actually delegable.

---

## License

TBD (MIT recommended for a tooling skill).
