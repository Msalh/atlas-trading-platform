# ADR-0001: Market Context (Phase N1)

**Status:** Accepted
**Date:** 2026-07-21
**Package:** `live/atlas/market_context/`

## Purpose

Market Context is Atlas's own *interpretation* of the situation a bar
occurred in — session phase (pre-open / opening range / mid-session /
closing range / overnight) and volatility regime (compressed / normal /
expanded) — derived independently from `MarketState`, never merged into
it. `MarketState` stays exactly what it already was: a record of what a
bar objectively did. A `MarketContext` is joined to a `MarketState` only by
`(symbol, timeframe, occurred_at)`.

This split exists so Rule Engine, Setup Engine, RE-1, and RE-2 — all
frozen — never have to change to accommodate a new interpretation of
"what kind of moment is this." Market Context is purely additive.

## Responsibilities

| Module | Responsibility |
|---|---|
| `models.py` | Frozen dataclasses and enums for every Market Context shape (`SessionPhase`, `VolatilityRegime`, `DriftStatus`, `ContextQuality`, `SessionProgress`, `SessionClassification`, `VolatilityClassification`, `MarketContext`). No behavior. |
| `definitions.py` | Versioned, calibrated configuration (`CME_RTH_V1`, `REGIME_CLASSIFIER_V1`) as frozen dataclasses — config as versioned code, not env vars. No behavior beyond the values themselves. |
| `fingerprint.py` | Self-contained canonical JSON serialization + SHA-256 fingerprinting. No knowledge of what it's fingerprinting — a generic recursive converter (dataclass/Mapping/Enum/datetime/list/tuple → JSON-safe structure) plus a truncated hex digest. |
| `session.py` | `classify_session()` — occurred_at → `SessionClassification`, using a `SessionCalendarDefinition`. Pure minute-of-day arithmetic in Central Time via stdlib `zoneinfo`. |
| `regime.py` | `classify_volatility_regime()` — a validated `MarketState` window → `VolatilityClassification`, using a `RegimeClassifierDefinition`. Pure percentile-rank arithmetic over the window's `atr` values. |
| `service.py` | `build_market_context()` — the single composition point. Calls `classify_session()` and `classify_volatility_regime()` unchanged, derives `ContextQuality` from their combined output, computes the configuration fingerprint, and assembles `MarketContext`. No new business logic. |

## Why frozen dataclasses

Every model in `models.py` and `definitions.py` is `@dataclass(frozen=True)`.
Market Context values are computed once and read many times (by a caller,
by the fingerprint hasher, by a Replay Engine `ReplayFrame`); nothing about
them should ever be mutable after construction. Immutability is also what
makes the fingerprint guarantee below meaningful — a value that could
change after being hashed would defeat the point of hashing it.

## Why fingerprints hash configuration only

`context_fingerprint` exists as a machine-verifiable proof layered under
the human-facing `classifier_version` / `calendar_version` strings: if a
definition's params are ever hand-edited without bumping its version
string, the fingerprint still changes. This guarantee only holds if the
fingerprint's input is exactly the two active definitions
(`SessionCalendarDefinition`, `RegimeClassifierDefinition`) — nothing more,
nothing less. Hashing anything beyond configuration would either weaken
the guarantee (omitting a param that could silently drift) or make the
fingerprint noisy in a way that defeats its purpose (see the next section).

## Why runtime values are excluded from fingerprints

`occurred_at`, the input window, and upstream values are never hashed. A
fingerprint that changed on every bar would give a false impression of a
configuration change on every call — the one thing this fingerprint exists
to detect would become undetectable in the noise. `MarketContext` itself
is never hashed either: that would be circular (the fingerprint is a field
*of* `MarketContext`) and would silently pull every runtime field
(`occurred_at`, `session`, `volatility`, `quality`) into the hash by
construction. `test_market_context_determinism.py` and
`test_market_context_service.py::test_fingerprint_never_reflects_occurred_at_or_upstream_values`
both assert this directly: two calls that differ only in `occurred_at` and
upstream values, against the same definitions, must fingerprint
identically.

## Why `DEFAULT_*` aliases do not exist

Rule Engine's own `FactDefinition` convention names its constants
`DEFAULT_X_DEFINITION`. Market Context deliberately does not reuse that
convention: a `DEFAULT_*` name reads as "the one true default," which
invites an in-place params edit without a version bump — exactly the
failure mode the fingerprint exists to catch. Every Market Context
definition instead embeds its own version in its identifier
(`CME_RTH_V1`, `REGIME_CLASSIFIER_V1`), and each constant's own Python name
is required to equal its `.version` string exactly (enforced by test). A
future `CME_RTH_V2` sits beside `CME_RTH_V1` with no ambiguity about which
is which, and no constant ever implies it is interchangeable with a
same-named-but-differently-tuned successor.

## Why session and regime remain independent

`session.py` and `regime.py` do not import each other, and neither imports
`ContextQuality`, `fingerprint`, or `service`. Each answers exactly one
question — "what session phase is this bar in," "what volatility regime is
this bar in" — from its own narrow input (`occurred_at` alone;
a validated `MarketState` window alone). Keeping them decoupled means
either one can be recalibrated, re-versioned, or extended (e.g. a future
`VolatilityRegime` value, a session calendar for a different exchange)
without the other needing to change or even be re-tested. `service.py` is
the only module that knows both exist.

## Why `service.py` contains composition only

`service.py`'s `build_market_context()` calls `classify_session()` and
`classify_volatility_regime()` and combines their *outputs* — it never
recomputes a session phase or a percentile rank itself, and never
duplicates either module's internal logic. Its only genuinely new
decisions are: (1) how to combine `DriftStatus` and `VolatilityRegime`
into one `ContextQuality` (see below), and (2) what to return when
`classify_volatility_regime()` raises `WindowIntegrityError` on an invalid
window, so a caller building a `MarketContext` for display/audit purposes
always gets one back rather than an exception. Neither decision touches
session.py's or regime.py's own code.

**`ContextQuality` precedence** (first match wins):

1. window invalid, or `VolatilityRegime.INSUFFICIENT_HISTORY` → `UNKNOWN`
2. `DriftStatus.UPSTREAM_MISSING` → `UNKNOWN`
3. `DriftStatus.DISAGREEMENT` → `DEGRADED`
4. otherwise (valid window, sufficient history, `DriftStatus.AGREEMENT`) → `TRUSTED`

`UNKNOWN` outranks `DEGRADED` when both conditions hold at once (e.g.
disagreement plus insufficient history): a data-quality problem is treated
as the stronger signal than a session-labeling disagreement.

**Why exactly these three states, no more.** `TRUSTED`/`DEGRADED`/`UNKNOWN`
cover every case a caller needs to act on: trust the value, trust it but
flag a labeling disagreement, or don't trust it (invalid window,
insufficient history, or no upstream to compare against). A fourth state
would only exist to distinguish among `UNKNOWN`'s own sub-causes — and
`VolatilityClassification`/`SessionClassification` already expose that
detail individually for a caller that needs it. `ContextQuality` itself
stays a coarse, three-way routing signal, not a duplicate of information
already available elsewhere.

## Rule Engine dependency boundary

`market_context` imports from `atlas.rule_engine` in exactly one place:
`regime.py` and `service.py` both import from
`atlas.rule_engine.window_integrity` — `validate_market_state_window`
(the validation function itself, called by `regime.py`) and
`WindowIntegrityError` (the exception it raises, caught by `service.py` to
implement the invalid-window → `UNKNOWN` behavior above). No Rule Engine
fact, registry, definition, or output is ever read. This is a deliberate,
narrow exception to Market Context's otherwise complete independence from
Rule Engine: `validate_market_state_window` is a pure, side-effect-free
contiguity check with no knowledge of Rule Engine's own facts or
registries, and re-implementing it inside `market_context` would only risk
a second, independently-drifting copy of the same check. Importing its
paired exception type is the minimal, necessary complement — it lets
`service.py` handle *that specific, documented failure mode* without
catching bare `Exception` and silently swallowing unrelated bugs. See
`docs/adr/ADR-0001-market-context.md`'s own dependency audit (Finalization
Gate) for the full import inventory; no other symbol, module, or package
under `atlas.rule_engine`, `atlas.setup_engine`, `atlas.research`, or
`atlas.research_export` is imported anywhere in `market_context`.

## Future extension points (Phase N2+)

Explicitly out of scope for Phase N1, and not designed against here:

- **Persistence.** Phase N1 recomputes `MarketContext` deterministically on
  demand rather than persisting append-only rows — no real consumer exists
  yet, and classifier versions are still being tuned. A future phase
  choosing to persist would need its own schema design, not an extension
  of `MarketContext`'s current shape.
- **API / UI.** No route or view exists yet. A future API would serialize
  `MarketContext` (likely via a `_to_dict` shaped like
  `rule_engine_output_to_dict`) behind its own transport envelope.
- **Event wiring.** No event is published when a `MarketContext` is built.
  A future phase wiring this into live ingestion would add a new
  subscriber, not modify `service.py`'s pure composition contract.
- **New `VolatilityRegime`/`SessionPhase` values, or a `REGIME_CLASSIFIER_V2`
  / `CME_RTH_V2`.** The versioned-definition and fingerprint design exists
  specifically so a new calibration can sit beside the current one without
  breaking replay determinism for data already classified under `_V1`.
  `REGIME_CLASSIFIER_V1`'s 288-bar lookback and 25/75 percentile thresholds
  are calibrated from one dataset (Gate 1); a lookback-vs-25/100/288
  comparison already found meaningful sensitivity (only 53.6% call
  agreement between a 20-bar and a 100-bar lookback) — a flagged, unresolved
  risk for `_V2` to address, not something this ADR resolves. It is also
  validated for 5-minute bars only; no other timeframe's calibration exists
  yet.
- **A session calendar for a different exchange/instrument.** `session.py`'s
  "no wraparound past midnight" assumption and CME-specific calibration
  would both need revisiting for an instrument whose session doesn't fit
  that shape.
