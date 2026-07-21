# Phase N3 Release Notes — Replay Engine, Setup Interpretation, Strategy Engine

**Status:** Certified
**Date:** 2026-07-21
**Packages:** `live/atlas/replay_engine/`, `live/atlas/setup_interpretation/`, `live/atlas/strategy_engine/`

## Summary

Phase N3 delivers a complete, certified production path from stored
historical `MarketState` data to a strategy's trading decision:

```
Rule Engine → Setup Engine → Setup Interpretation → Replay Engine → Strategy Engine
```

Every layer in this chain is pure and deterministic except `replay()`'s
own single bounded repository fetch. No frozen, previously-certified
package (Rule Engine, Setup Engine, Market Context) was modified anywhere
in this phase — every capability was added additively, in its own sibling
package, exactly per this engagement's standing architectural discipline.

## Replay Engine evolution

- **Sprint 1–3 (original Phase N2):** `ReplayFrame` (a frozen, aligned
  four-field bundle of `MarketState`/`RuleEngineOutput`/`SetupEngineOutput`/
  `MarketContext`), `segment_replay_window()`, `build_replay_output_window()`,
  and the async `replay()` orchestration boundary. Certified in ADR-0002.
- **Sprint 5 (this phase):** `ReplayFrame` widened to a fifth, required,
  dense field — `setup_interpretations: tuple[SetupInterpretation, ...]` —
  populated by `build_replay_output_window()` calling `interpret_setups()`
  once per bar. `replay()` itself required zero code changes: the new
  field rides along for free through the existing async boundary.

## Setup Interpretation integration

- **Sprint 1–4 (prior work):** `atlas.setup_interpretation` built,
  validated, and certified as a stand-alone, sibling package beside Rule
  Engine/Setup Engine — canonical, versioned, fingerprinted direction
  mapping for every registered setup, with zero production consumers at
  certification time.
- **Sprint 5 (this phase):** Wired into Replay Engine — the one and only
  production caller of `interpret_setups()`.
- **Sprint 6 (this phase):** Wired into Strategy Engine — the reference
  strategy now reads the already-computed `ReplayFrame.setup_interpretations`
  field instead of calling Setup Interpretation itself.

## Strategy migration

`DisplacementVolumeContext` (Strategy Engine's first concrete
`StrategyPlugin`) migrated off direct Rule Engine fact consumption:

- Removed: `from atlas.rule_engine.models import FactResult` and every
  `frame.rule_engine_output.facts` read.
- Added: a name-based lookup into `frame.setup_interpretations`, mapping
  `SetupDirection.BULLISH`/`BEARISH` → `LONG`/`SHORT`, `AMBIGUOUS` →
  `context_conflict`, `UNAVAILABLE` → `context_insufficient`, and a new
  defensive `NEUTRAL` branch (`unexpected_neutral_interpretation`,
  structurally unreachable in practice) plus a typed
  `MissingSetupInterpretationError` for the internal-contract-violation
  case ReplayFrame's own dense guarantee is supposed to prevent.
- **Strict output equivalence, proven, not assumed:** an exact
  `StrategyDecision` equivalence study (every field) against both a
  synthetic real-pipeline dataset (80 bars) and a real 21,062-bar MNQ1!
  export produced **zero mismatches** in both cases. Existing reason
  codes (`"accepted"`, `"context_conflict"`, `"context_insufficient"`,
  `"setup_absent"`) are preserved byte-for-byte — `SetupInterpretation`'s
  own reason codes were deliberately not adopted (two distinct
  vocabularies at two distinct layers, the same split already established
  between `context_fingerprint` and `interpretation_fingerprint`).

## Architectural improvements

- One canonical per-bar snapshot type (`ReplayFrame`), never a second,
  parallel frame concept — widened in place rather than wrapped.
- Zero duplicated or parallel direction-interpretation logic anywhere in
  the codebase — confirmed structurally (AST-based, not textual) via the
  new Phase N3 certification suite: `interpret_setups()` has exactly one
  production caller (`atlas.replay_engine.service`); zero `.facts`
  attribute accesses and zero `atlas.rule_engine` imports anywhere under
  `atlas.replay_engine` or `atlas.strategy_engine`; no dict literal
  keyed by a raw trend string exists anywhere under `atlas.strategy_engine`.
- Strict downstream-only dependency direction confirmed for the whole
  pipeline: Rule Engine depends on nothing downstream of itself; Setup
  Engine depends on nothing downstream of itself; Setup Interpretation
  depends on nothing downstream of itself; Replay Engine depends on
  nothing downstream of itself. No circular imports anywhere.

## Test totals

| Suite | Result |
|---|---|
| Replay Engine | 72 passed |
| Setup Interpretation | 161 passed |
| Strategy Engine (incl. migration equivalence + Phase N3 certification) | 122 passed |
| Full backend suite | 1638 passed, 1 skipped |
| Ruff (all Phase N3 packages and tests) | clean |

## Certification totals

- **Real-data end-to-end run** (real 21,062-bar MNQ1! export,
  `data/CME_16_06_25_30_09_25.csv`, 77 contiguous segments): 21,062 bars
  processed → 21,062 replay frames → 84,248 setup interpretations (dense,
  4 per bar) → 21,062 strategy decisions. **Zero exceptions. Exact replay
  success.**
- **Dependency certification:** whole-project audit confirms zero
  `atlas.rule_engine` imports in Strategy Engine, Replay Engine as the
  sole `interpret_setups()` caller, exactly two approved downstream
  consumers of `atlas.setup_interpretation` (Replay Engine, Strategy
  Engine), no forbidden imports, no circular imports anywhere in the
  five-package chain.

## Known limitations (unchanged from prior sprints, still accurate)

- `ReplaySession` (pause/resume/step) remains deliberately deferred —
  no real interactive consumer exists yet.
- Only one concrete `StrategyPlugin` exists in production
  (`DisplacementVolumeContext`); the architecture is proven to generalize
  (Setup Interpretation is consumer-agnostic) but has not yet been
  exercised by a second plugin.
- No Paper Trading or Live Trading engine consumes this pipeline yet —
  Phase N3 delivers the replay/backtest-side path only.

## Certification statement

Every objective set for Phase N3 — Setup Interpretation certified as a
stand-alone component, integrated into Replay Engine without duplicating
or bypassing any frozen package, and consumed by Strategy Engine with
byte-for-byte-preserved decision behavior — is met, proven by real-data
evidence rather than assumed. See `docs/adr/ADR-0002-replay-engine.md`
and `docs/adr/ADR-0003-setup-interpretation.md` for the full architectural
record.
