# ADR-0003: Setup Interpretation

**Status:** Accepted — integration complete
**Date:** 2026-07-21 (integrated into Replay Engine Sprint 5; Strategy Engine migrated Sprint 6; certified Sprint 7 — Phase N3 final certification)
**Package:** `live/atlas/setup_interpretation/`

## Purpose

Setup Interpretation turns a detected `SetupOutcome` into a canonical
directional reading — bullish, bearish, neutral, ambiguous, or unavailable
— using only evidence that already exists: a setup's own required-facts
evidence where that evidence genuinely carries a side, or one specific,
externally-referenced Rule Engine fact (`trend_5m`) where it does not. It
computes nothing new about the market; it only interprets outcomes Setup
Engine and Rule Engine already produced.

## Motivation / architectural problem

Strategy Engine's first concrete plugin, `DisplacementVolumeContext`,
needed a directional signal that Setup Engine's own
`displacement_with_volume_confirmation` outcome does not carry —
displacement and volume_spike are both magnitude-only facts (a bar's
range/ATR and volume/baseline ratio, never a sign). The plugin's only
option under Phase N3 Sprint 3's constraints was to read
`frame.rule_engine_output.facts["trend_5m"]` directly, bypassing Setup
Engine's own output entirely for the one thing (direction) it couldn't
supply.

This was flagged as a real, scaling architecture risk rather than a
one-off pragmatic shortcut: every future strategy needing direction would
face the same gap, and absent a shared answer, each would independently
invent its own trend-inference logic, its own conflicting-evidence
handling, and its own vocabulary for "I don't know" — twenty strategies
each solving the same problem twenty different, undisclosed ways. The
mapping from a setup's own evidence (or a specific referenced fact) to a
direction is a single, well-defined question with one correct answer per
setup; it belongs in exactly one place, computed once, not re-derived
per-plugin.

## Rejected alternatives

**Widen `SetupResult`/`SetupEvidence` to carry a direction field.**
Rejected outright — Setup Engine, `SetupResult`, and every certified setup
definition are frozen. `displacement_with_volume_confirmation`'s own
evidence is provably direction-free (see the Sprint 2/architecture review
grounding below); adding a direction field to `SetupResult` would force
that setup to either fabricate one (violating "never invent evidence") or
carry a permanently-null field, both worse than not having it there.

**Fold interpretation logic directly into each `StrategyPlugin`.** The
status quo this ADR replaces. Rejected because it does not scale past one
plugin: no shared vocabulary, no shared fingerprint, no way to audit "did
every strategy resolve `trend_5m == 'flat'` the same way" without reading
every plugin's own source.

**Put interpretation logic inside `atlas.setup_engine` as a new
subpackage.** Rejected. Setup Engine's own `REGISTRY` is deliberately
static, in-package code (its own docstring: "not a dynamic/pluggable
registration API") — nesting a second, direction-inferring layer inside it
would blur that boundary and require touching a frozen, certified package
for purely additive work. It would also entangle interpretation's own
(potentially independent) versioning/fingerprint lifecycle with Setup
Engine's.

**Put interpretation logic inside `atlas.strategy_engine` as a
subpackage.** Rejected. `atlas.strategy_engine`'s own dependency ceiling
(Sprint 1) is deliberately narrow (`atlas.replay_engine.models`,
`atlas.setup_engine.models`, `atlas.market_context.models`, `atlas.core`
primitives — never `atlas.rule_engine`). Interpretation genuinely needs
`atlas.rule_engine.models.FactResult` to read `trend_5m` for the two
MOMENTUM-family setups; housing it inside Strategy Engine would force that
package's own dependency ceiling open for every plugin, not just the ones
that need it. It would also make interpretation Strategy-Engine-specific
in name and location even though its actual consumer is "anything that
wants a setup's direction," which is not necessarily limited to a
`StrategyPlugin`.

## Final design — sibling package, not a subpackage of either

`atlas.setup_interpretation` sits beside Setup Engine, Rule Engine, and
Strategy Engine — a peer, not a child of any of them — mirroring
`atlas.market_context`'s own precedent exactly: Market Context sits beside
Rule Engine rather than inside it, for the identical reason (ADR-0001:
"this split exists so Rule Engine, Setup Engine, RE-1, and RE-2 — all
frozen — never have to change to accommodate a new interpretation of 'what
kind of moment is this'"). Setup Interpretation extends that same pattern
one layer up: it reads Setup Engine's and Rule Engine's already-computed
outputs, unchanged, and adds a new interpretation on top — purely
additive, no frozen package touched.

| Module | Responsibility |
|---|---|
| `models.py` | `SetupDirection`, `DirectionSource`, `SetupInterpretation` — frozen dataclasses/enums with unconstructable-invalid-state invariants. No behavior. |
| `definitions.py` | `SETUP_INTERPRETATION_V1` — the versioned, canonical per-setup interpretation ruleset, as data. No behavior beyond the values themselves. |
| `fingerprint.py` | Self-contained canonical JSON + truncated SHA-256 fingerprinting, independent from `atlas.market_context.fingerprint` — no cross-package fingerprint import. |
| `service.py` | `interpret_setups()` — the single pure function that applies `SETUP_INTERPRETATION_V1` against a real `RuleEngineOutput`/`SetupEngineOutput` pair. |

## Interpretation ownership: per-setup, evidence-grounded, never invented

Every rule in `SETUP_INTERPRETATION_V1` reflects only what a setup's own
evidence can honestly support — grounded in a direct reading of
`atlas/rule_engine/facts.py` and `atlas/setup_engine/setups/*.py`, not
assumed:

- **`liquidity_sweep_with_volume_confirmation`** (ICT): `liquidity_sweep`'s
  own evidence already tags every qualifying reference level with which
  side it breached (`"high"`/`"low"`) — genuine, latent directional
  evidence, read directly from the setup's own required facts. A
  low-side sweep is bullish, a high-side sweep is bearish, and a bar that
  qualifies on both sides at once is the real, structurally possible
  ambiguous case — never silently resolved to one side.
- **`displacement_with_volume_confirmation`** and
  **`sustained_displacement_streak`** (MOMENTUM): both setups' own
  required facts (displacement, volume_spike) are magnitude-only —
  genuinely no sign. Direction is inferred from `trend_5m`, an externally
  referenced Rule Engine fact that is deliberately *not* among either
  setup's own `required_facts`. `trend_5m`'s contract is closed
  (`"up"`/`"down"`/`"flat"`); a flat trend is the real ambiguous case, and
  any other value is a genuine upstream contract violation
  (`SetupInterpretationInvalidFactValueError`), never silently coerced.
- **`vwap_extension_with_volume_confirmation`** (CONFLUENCE): this setup's
  own docstring explicitly declines to assert continuation, reversal,
  exhaustion, or any directional thesis, even though its own
  `vwap_relationship` evidence (`extended_above`/`extended_below`) reads
  as directional at a glance. Treating it as directional here would invent
  a thesis the setup's own author rejected — it is intentionally neutral
  whenever detected, by design (`DirectionSource.INTENTIONALLY_NEUTRAL`),
  never a per-bar judgment call.

`interpret_setups()` never hardcodes a second copy of *which* fact a rule
reads, or *what* reason code a successful call emits — every one of those
is read from `SETUP_INTERPRETATION_V1`'s own rule at call time (Sprint 2's
own correction: `bullish_reason`/`bearish_reason` moved from a hardcoded
service.py literal into the definition itself specifically so the
fingerprint guarantee below covers them too).

## Versioning and fingerprint philosophy

`SETUP_INTERPRETATION_V1` follows `CME_RTH_V1`/`REGIME_CLASSIFIER_V1`'s own
naming convention exactly (`<SCOPE>_V<N>`, never `DEFAULT_*`) — a future
`SETUP_INTERPRETATION_V2` sits beside it with no ambiguity about which is
active. `interpretation_version` (the declared identity) and
`interpretation_fingerprint` (a machine-verifiable SHA-256 proof of the
definition's actual serialized content) are the same two-layer audit
pattern Market Context established for `context_fingerprint`: a version
bump without a fingerprint change is impossible, and a fingerprint change
without a version bump reveals an undisclosed edit. The fingerprint hashes
`SETUP_INTERPRETATION_V1` itself — its own module-level constant, computed
once at import time — never a runtime value (`occurred_at`, the
`RuleEngineOutput`/`SetupEngineOutput` being interpreted), for the same
reason Market Context's fingerprint excludes runtime values: a fingerprint
that changed on every bar would make the one thing it exists to detect (a
configuration edit) undetectable in the noise.

## Deterministic guarantees

`interpret_setups()` is pure and synchronous — no I/O, no logging, no
caching, no wall-clock read, no randomness. Given the same
`RuleEngineOutput`/`SetupEngineOutput` pair, it always returns the same
tuple. Sprint 3's Integration Review and Sprint 4's Certification both
confirm this at real-data scale: **zero mismatches across 100 repeated
`interpret_setups()` passes over the largest real contiguous segment
(276 bars) of a 21,062-bar real MNQ1! export**, in addition to the
hand-built determinism suites covering mixed detected/undetected,
insufficient-data, and ambiguous cases with full-tuple equality, stable
reason-code ordering, and zero mutation of either input.

## Dense output contract

`interpret_setups()` returns exactly one `SetupInterpretation` per
`SetupOutcome` in `setup_engine_output.setups`, in the same order — never
filtered, never reordered, never a shorter list. This mirrors
`SetupEngineOutput`'s own existing dense contract
(`build_setup_engine_output` evaluates every registration unconditionally)
rather than introducing a sparser, "only report what I could interpret"
shape — a setup that is not detected still gets an explicit
`detected=False, direction=UNAVAILABLE, source=INSUFFICIENT_DATA` entry,
not an omission.

## Migration completed (Sprints 5–6)

Setup Interpretation was validated stand-alone (Sprint 3), certified as a
stable component (Sprint 4), and is now fully wired into production. Both
steps the original architecture review deferred are done:

- **`ReplayFrame` was widened** (Sprint 5) to carry
  `setup_interpretations: tuple[SetupInterpretation, ...]` as its fifth
  field, populated by `atlas.replay_engine.service.build_replay_output_window()`
  calling `interpret_setups()` once per bar — see ADR-0002's own "Setup
  Interpretation composition" section for the construction-side detail.
- **`DisplacementVolumeContext` was migrated** (Sprint 6) to read
  `frame.setup_interpretations` instead of `frame.rule_engine_output.facts["trend_5m"]`
  directly. It no longer imports anything from `atlas.rule_engine` and
  never accesses `RuleEngineOutput.facts` — confirmed by AST-based
  dependency audits in three independent places (the strategy's own test
  file, `test_strategy_engine_dependencies.py`'s whole-package audit, and
  Setup Interpretation's own integration test suite).

The Sprint 3 Integration Review's equivalence study had already proven,
against synthetic-but-real-pipeline replay data, that a hypothetical
migrated strategy would produce identical `disposition`/`direction`
decisions with translatable-but-different reason codes. Sprint 6's actual
migration confirmed this empirically rather than hypothetically: an exact
`StrategyDecision` equivalence study (every field — disposition,
direction, `reason_codes`, `strategy_id`, `strategy_version`, `setup_ids`,
`occurred_at`, `context_fingerprint`) against both a synthetic real-pipeline
dataset (80 bars) and a real 21,062-bar MNQ1! export produced **zero
mismatches** in both cases — the legacy strategy's exact string reason
codes (`"accepted"`, `"context_conflict"`, `"context_insufficient"`,
`"setup_absent"`) were preserved unchanged, per Sprint 6's own strict
full-output-equivalence decision (see that sprint's report for the
architectural reasoning: `StrategyDecision.reason_codes` names the
strategy's own acceptance rule, `SetupInterpretation.reason_codes` names
the interpretation's own evidence — two legitimate, distinct vocabularies,
never merged).

The production path is now, and is intended to remain, exactly:

```
Rule Engine → Setup Engine → Setup Interpretation → Replay Engine → Strategy Engine
```

with Setup Interpretation composed once, inside Replay Engine, and consumed
by Strategy Engine only through `ReplayFrame`'s own already-typed field —
never called a second time, never re-derived, never duplicated.

## Why Setup Engine was never modified

Every alternative that touched `SetupResult`, `SetupEvidence`, or any
certified setup definition was rejected specifically because those types
are frozen and certified — the same standing constraint this whole
engagement has enforced since Phase N1 (Market Context) forward. Setup
Interpretation's entire reason to exist as a separate package is to add a
new capability without that cost: Setup Engine's own tests, its own
registry, and its own certified behavior are provably untouched by this
work (confirmed by the dependency audit below — nothing in
`atlas.setup_engine` imports `atlas.setup_interpretation`, and nothing in
`atlas.setup_interpretation` imports `atlas.setup_engine` beyond its
already-public `models` module).

## Dependency boundaries

Setup Interpretation depends on: Rule Engine (`models` only — `FactResult`,
`RuleEngineOutput`), Setup Engine (`models` only — `SetupEngineOutput`,
`SetupResult`), and the Python standard library. Nothing else — never
`atlas.market_engine`, `atlas.replay_engine`, `atlas.market_context`,
`atlas.strategy_engine`, repositories, the API, events, research, or any
LLM service. The Sprint 7 Phase N3 Certification's whole-project
dependency audit confirms: no forbidden import, no circular import
(nothing under `atlas.core`, `atlas.market_engine`, `atlas.rule_engine`,
`atlas.setup_engine`, or `atlas.market_context` imports
`atlas.setup_interpretation` back), and **exactly two approved
dependents** — `atlas.replay_engine` (Sprint 5, calls
`interpret_setups()` to populate `ReplayFrame.setup_interpretations`) and
`atlas.strategy_engine` (Sprint 6, imports `.models.SetupDirection` only,
to read the already-computed field — never calls `interpret_setups()`
itself). Nothing else under `atlas/` imports `atlas.setup_interpretation`.
The package remains a pure, one-way downstream layer exactly as designed —
now genuinely consumed, not merely validated and waiting.
