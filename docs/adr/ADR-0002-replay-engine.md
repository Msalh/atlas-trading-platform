# ADR-0002: Replay Engine (Phase N2)

**Status:** Accepted
**Date:** 2026-07-21 (widened Sprint 5 — Setup Interpretation integration; certified Sprint 7 — Phase N3 final certification)
**Package:** `live/atlas/replay_engine/`

## Purpose

Replay Engine deterministically reproduces, bar by bar, the complete
derived-state pipeline a live consumer already sees — `RuleEngineOutput`,
`SetupEngineOutput`, `MarketContext`, and (as of Sprint 5)
`SetupInterpretation` — over an already-ingested historical `MarketState`
series. It computes nothing new: every value it produces comes unchanged
from Rule Engine, Setup Engine, Market Context, and Setup Interpretation's
own existing public functions. Its only job is composition, segmentation,
and orchestration around calling them correctly, in order, once per
historical bar.

## Responsibilities

| Module | Responsibility |
|---|---|
| `models.py` | `ReplayFrame` — a frozen, aligned bundle of one bar's `MarketState`/`RuleEngineOutput`/`SetupEngineOutput`/`MarketContext`/`setup_interpretations`. No behavior. |
| `segmentation.py` | `segment_replay_window()` — a thin, explicitly-documented wrapper around `atlas.profiling.service.segment_by_gap`. No gap logic of its own. |
| `service.py` | `build_replay_output_window()` (pure sync core) composes Rule/Setup Engine + Market Context + Setup Interpretation into `ReplayFrame`s for one already-contiguous segment; `replay()` (thin async wrapper) fetches, segments, and calls the core once per segment, yielding frames in order. |

## Dependency boundaries

Replay Engine depends on: Market Engine (`models`, `ports`, `service.replay_market_state`),
Rule Engine (`models`, `service.build_rule_engine_output_window`), Setup
Engine (`models`, `service.build_setup_engine_output_window`), Market
Context (`models`, `definitions`, `service.build_market_context`), Setup
Interpretation (`models`, `service.interpret_setups` — added Sprint 5, see
ADR-0003), `atlas.profiling.service.segment_by_gap`, and
`atlas.core.primitives`. Nothing else. The Sprint 7 Phase N3 Certification's
whole-project dependency audit reconfirms: no forbidden import (no
`atlas.research`, `atlas.research_export`, `atlas.api`, `atlas.events`,
`atlas.strategy_engine`), no circular import (none of Replay Engine's own
dependencies — including Setup Interpretation — import it back), and
Replay Engine has exactly **one production dependent** — `atlas.strategy_engine`
(via `StrategyPlugin.evaluate(frame: ReplayFrame)`, unchanged since Phase
N3 Sprint 1) — nothing else under `atlas/` imports `atlas.replay_engine`
except test files. It sits beside Market Engine rather than inside the
Market Engine → Rule Engine → Setup Engine pipeline, exactly as the Phase
N2 architecture proposal specified, now also sitting downstream of Setup
Interpretation (itself beside Rule Engine/Setup Engine — see ADR-0003) and
upstream of Strategy Engine. **Replay Engine is the only production code
that calls `interpret_setups()`** — confirmed by the Sprint 7 audit;
Strategy Engine consumes the already-computed `ReplayFrame.setup_interpretations`
field and never calls Setup Interpretation's service function itself.

## `ReplayFrame`: the canonical per-bar snapshot

A frozen dataclass bundling one historical bar's five already-computed
descriptions — `market_state`, `rule_engine_output`, `setup_engine_output`,
`market_context`, and `setup_interpretations`. It is the single canonical
answer to "everything Atlas currently knows about this bar," deliberately
chosen (Sprint 5 architecture review) over two rejected alternatives: passing
`setup_interpretations` to `StrategyPlugin.evaluate()` as a second, separate
argument (which would have made `StrategyPlugin`'s own interface plugin-
by-plugin inconsistent about what it receives, and pushed alignment
responsibility onto every future caller instead of guaranteeing it once,
here, by construction), and introducing a second, wrapping frame type
around `ReplayFrame` (which would have created exactly the "parallel frame
concept" risk this whole design exists to avoid — two canonical types for
one bar, with no single answer to which one a given consumer should use).
Widening the existing type, once, with every future consumer automatically
inheriting the new field for free, was the only option that kept `ReplayFrame`
singular.

It performs no cross-field validation itself and computes nothing —
alignment across all five fields is guaranteed by construction
(`build_replay_output_window`'s own `_assert_aligned` defense-in-depth
check, extended Sprint 5 to cover `setup_interpretations` the same way it
already covered the other four) rather than re-derived inside the type
itself. `setup_interpretations` is required, never `Optional` and never
defaulted — a `ReplayFrame` can no more be constructed with a missing
fifth field than a missing first one. No strategy output, trade decision,
execution state, mutable lifecycle state, or persistence metadata belongs
on it, and none was added. This immutable-snapshot philosophy is
deliberate and permanent, not a placeholder: `ReplayFrame` describes what
was true of one bar, once, computed by upstream layers — it is not a
place for a downstream consumer (a strategy, a future backtester) to
accumulate its own derived state.

## Setup Interpretation composition (Sprint 5)

`build_replay_output_window()` calls `interpret_setups(rule_engine_output=…,
setup_engine_output=…)` once per position, immediately after that
position's `setup_engine_output` is built, and attaches the resulting
dense tuple as `ReplayFrame.setup_interpretations`. This is composition
only — Replay Engine owns *calling* Setup Interpretation at the right
place, in the right order, with the right pair of already-computed
arguments; it does not own, alter, or duplicate any interpretation rule
itself (those remain entirely `atlas.setup_interpretation`'s own concern —
see ADR-0003). `SetupInterpretationMissingFactError`,
`SetupInterpretationUnknownSetupError`, `SetupInterpretationInvalidFactValueError`,
and `SetupInterpretationAlignmentError` all propagate completely uncaught
through `build_replay_output_window()`, exactly like every other composed
call's own errors already do — a real contract violation surfaces as
itself, never silently caught or papered over. In practice none of the
four can fire against a `RuleEngineOutput`/`SetupEngineOutput` pair this
module itself produced (both are always built from the same real
registries, at the same position, so alignment and fact/setup-name
presence are guaranteed by construction) — the same "structurally
unreachable through the real construction path, still checked" class of
guarantee this codebase relies on elsewhere.

## Segmentation philosophy

A historical `MarketState` series is split into maximal chronologically-contiguous
segments before any composition is attempted — a gap (weekend, holiday,
exchange maintenance) becomes a segment boundary, never an exception and
never something interpolated across. This reuses `segment_by_gap`
unchanged rather than re-implementing gap detection a second time.
Composition never spans a segment boundary: `build_replay_output_window`
is called once per segment, so a trailing window inside Rule Engine, Setup
Engine, or Market Context composition can never reach back across a gap
into a different segment's data.

## Deterministic guarantees

Every function in the chain — `segment_by_gap`, `build_rule_engine_output_window`,
`build_setup_engine_output_window`, `build_market_context`,
`interpret_setups`, and Replay Engine's own `build_replay_output_window` —
is pure and synchronous; only `replay()` touches I/O, and it does so
exactly once (a single bounded `repository.get_range` call via
`replay_market_state`), with no retry, cache, or wall-clock read anywhere
in between. The Phase N2 Finalization Gate's own determinism audit
confirmed this at real-data scale for the original four-field frame: 100
repeated `build_replay_output_window()` calls against the dataset's
largest real segment (276 bars) and 100 repeated full async `replay()`
runs against a seeded in-memory repository both produced **zero
mismatches** and a single, identical `context_fingerprint` sequence across
all 100 runs. The Sprint 7 Phase N3 Certification reconfirms this for the
now-five-field frame against a real 21,062-bar MNQ1! export end to end
(Rule Engine → Setup Engine → Market Context → Setup Interpretation →
Strategy Engine) with zero errors, zero exceptions, and zero mismatches —
see the Phase N3 release notes for the full real-data certification
report.

## Why `ReplaySession` was deferred

A stateful or configuration-wrapper session object (pause/resume/step/checkpoint)
was explicitly scoped out of every Phase N2 sprint. No real consumer exists
yet that needs interactive control over a replay run — the only two
consumers Replay Engine currently supports are "iterate a bounded range to
completion" and "iterate and stop early" (both already served by the
standard async-generator protocol: `async for` plus a plain `break`).
Building `ReplaySession` now, against no concrete requirement, would repeat
the exact speculative-abstraction mistake this project has already flagged
and avoided elsewhere (Setup Engine's own windowing landed only once a real
consumer needed it, Sprint 24C). It remains a legitimate future addition —
see below — the moment an actual consumer (e.g. an interactive backtest UI)
needs pause/resume/step behavior.

## Future extension points

- **`ReplaySession`**, once a real interactive consumer exists.
- **Pagination** beyond `get_range`'s current `limit` ceiling, once a real
  replay span exceeding it is needed (measured throughput: ~764 bars/sec
  for full Rule Engine + Setup Engine + Market Context composition against
  the certified dataset — see the Finalization Gate report for the full
  benchmark).
- **API / UI** — no route exists yet; a future one would serialize
  `ReplayFrame` behind its own transport envelope, the same domain/transport
  split every other read path in this codebase already uses.
- **Multi-page/streaming repository fetch** for a replay span too large for
  one bounded query.
