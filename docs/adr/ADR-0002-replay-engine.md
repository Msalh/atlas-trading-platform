# ADR-0002: Replay Engine (Phase N2)

**Status:** Accepted
**Date:** 2026-07-21
**Package:** `live/atlas/replay_engine/`

## Purpose

Replay Engine deterministically reproduces, bar by bar, the same
derived-state pipeline a live consumer already sees — `RuleEngineOutput`,
`SetupEngineOutput`, `MarketContext` — over an already-ingested historical
`MarketState` series. It computes nothing new: every value it produces
comes unchanged from Rule Engine, Setup Engine, and Market Context's own
existing public functions. Its only job is composition, segmentation, and
orchestration around calling them correctly, in order, once per historical
bar.

## Responsibilities

| Module | Responsibility |
|---|---|
| `models.py` | `ReplayFrame` — a frozen, aligned bundle of one bar's `MarketState`/`RuleEngineOutput`/`SetupEngineOutput`/`MarketContext`. No behavior. |
| `segmentation.py` | `segment_replay_window()` — a thin, explicitly-documented wrapper around `atlas.profiling.service.segment_by_gap`. No gap logic of its own. |
| `service.py` | `build_replay_output_window()` (pure sync core) composes Rule/Setup Engine + Market Context into `ReplayFrame`s for one already-contiguous segment; `replay()` (thin async wrapper) fetches, segments, and calls the core once per segment, yielding frames in order. |

## Dependency boundaries

Replay Engine depends on: Market Engine (`models`, `ports`, `service.replay_market_state`),
Rule Engine (`models`, `service.build_rule_engine_output_window`), Setup
Engine (`models`, `service.build_setup_engine_output_window`), Market
Context (`models`, `definitions`, `service.build_market_context`),
`atlas.profiling.service.segment_by_gap`, and `atlas.core.primitives`.
Nothing else. The Finalization Gate's dependency audit confirms: no
forbidden import (no `atlas.research`, `atlas.research_export`, `atlas.api`,
`atlas.events`), no circular import (none of Replay Engine's own
dependencies import it back), and Replay Engine has **zero dependents** —
nothing under `atlas/` imports `atlas.replay_engine` except its own tests.
It is a pure downstream consumer, sitting beside Market Engine rather than
inside the Market Engine → Rule Engine → Setup Engine pipeline, exactly as
the Phase N2 architecture proposal specified.

## `ReplayFrame`

A frozen dataclass bundling one bar's four already-computed descriptions.
It performs no cross-field validation itself — alignment is guaranteed by
construction (`build_replay_output_window`'s own `_assert_aligned` defense-in-depth
check) rather than re-derived inside the type. No strategy output, trade
decision, execution state, mutable lifecycle state, or persistence
metadata belongs on it, and none was added.

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
`build_setup_engine_output_window`, `build_market_context`, and Replay
Engine's own `build_replay_output_window` — is pure and synchronous; only
`replay()` touches I/O, and it does so exactly once (a single bounded
`repository.get_range` call via `replay_market_state`), with no retry,
cache, or wall-clock read anywhere in between. The Finalization Gate's
determinism audit confirms this at real-data scale: 100 repeated
`build_replay_output_window()` calls against the dataset's largest real
segment (276 bars) and 100 repeated full async `replay()` runs against a
seeded in-memory repository both produced **zero mismatches** and a single,
identical `context_fingerprint` sequence across all 100 runs.

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
