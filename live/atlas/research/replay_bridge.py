"""
Phase N4 Sprint 3 (Replay Bridge). The one, narrow gateway module through
which the Research Engine reaches Replay Engine - the single highest-risk
dependency in the whole roadmap, being the only Research Engine module that
touches certified, frozen production code. Nothing under atlas.replay_engine
is modified; this module only calls its two existing public functions and
passes their results through completely unchanged and unmutated.

No computation happens here. build_replay_frames_for_window() and
fetch_replay_frames() are direct pass-throughs to
atlas.replay_engine.service.build_replay_output_window()/replay()
respectively - not bare re-exports of those functions (a caller here gets
its own, Research-Engine-named, Research-Engine-located entry point, so a
future rename/restructure inside Replay Engine's own service.py is felt in
exactly one place), but genuinely nothing more: no ReplayFrame is ever
constructed, mutated, filtered, or re-typed by this module. If this module
ever grows a second responsibility beyond "call Replay Engine, pass the
result through," the "no computation in the bridge" boundary the roadmap's
own Sprint 3 risk note names has already eroded.

This is deliberately the ONLY Research Engine module importing
atlas.replay_engine - test_research_replay_bridge.py's own dependency audit
proves it from this side; test_replay_engine_dependencies.py's
existing, certified boundary test proves it from the other side (Replay
Engine's own allowlist of who may import it). If a second Research Engine
module ever needs Replay Engine directly, the roadmap's own guidance is
explicit: that is a signal to widen this module's surface, never to add a
second gateway.

--- Architectural resolution: Experiment identity under Replay (Sprint 5) ---

This module builds no Experiment and computes no fingerprint - Experiment
Builder is Sprint 5, not started here. This section records, as forward
guidance for that sprint, how the semantic_fingerprint/execution_fingerprint
split (docs/phase-n4-research-engine-blueprint.md; models.py's own
Experiment docstring) must be applied once Replay-sourced data starts
feeding Experiment construction, resolved now because Replay is the first
data source where the distinction below actually matters.

A new Experiment (a new experiment_id) is created whenever the candidate
run's (hypothesis_id, realization_id, dataset_manifest(s)-as-REQUEST,
evaluation_mode) tuple does not match any existing Experiment's
semantic_fingerprint - i.e. no prior Experiment asked this exact research
question. An existing Experiment IS the same semantic question exactly
when that tuple's hash does match.

When semantic_fingerprint matches an existing Experiment but code_version
or seed differ (the Rule/Setup Engine/Replay Engine code changed, or a
Monte Carlo seed differs, since the question was last asked - even though
nobody touched the hypothesis, realization, dataset, or mode), the correct
action is a NEW EXECUTION of the same semantic Experiment: append a new
Experiment row sharing the prior semantic_fingerprint but computing its
own, distinct execution_fingerprint - never an in-place edit to the prior
row (Experiments are immutable/append-only; there is no "update the
execution" operation). If BOTH fingerprints already match an existing
Experiment, this exact execution has already run - the correct action is
to reuse its existing Evidence (a cache hit), never re-run Replay at all.

One refinement genuine to Replay, not visible from Sprint 28's own static,
file-imported datasets: DatasetManifest mixes REQUEST fields (symbol,
timeframe, requested_start, requested_end) with RESOLVED fields (row_count,
first_occurred_at, last_occurred_at, generated_at, source_description). A
Replay-sourced dataset can genuinely grow between two otherwise-identical
requests as new bars are ingested - unlike a frozen CSV import, where the
resolved fields were as stable as the request. semantic_fingerprint's
curated projection of a DatasetManifest must therefore hash only its
REQUEST fields; the RESOLVED fields belong in execution_fingerprint's own
projection instead, alongside code_version/seed - they describe what a
specific execution actually saw, not what question was asked. This is a
clarification of which half of an already-frozen field each fingerprint
may touch, not a change to either fingerprint's field list or to
DatasetManifest itself.

Duplication is prevented at this semantic layer, before a new
experiment_id is ever minted - a Sprint 5 policy decision layered cleanly
on top of Sprint 2's own unchanged ExperimentTracker.record() idempotent-
or-reject mechanism, never replacing it. Every case above either appends
exactly one new Experiment row or appends none (a full match) - append-only
history is preserved in every branch.
"""
from collections.abc import AsyncIterator
from datetime import datetime

from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    REGIME_CLASSIFIER_V1,
    RegimeClassifierDefinition,
    SessionCalendarDefinition,
)
from atlas.market_engine.models import MarketState
from atlas.market_engine.ports import MarketStateRepository
from atlas.replay_engine.models import ReplayFrame
from atlas.replay_engine.service import build_replay_output_window, replay


def build_replay_frames_for_window(
    market_state_window: list[MarketState],
    calendar: SessionCalendarDefinition = CME_RTH_V1,
    classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
) -> list[ReplayFrame]:
    """Research Engine's own entry point for a caller that already holds
    one contiguous MarketState window in hand (no repository needed) - e.g.
    a future Backtesting sprint composing its own window. A direct,
    unmodified pass-through to
    atlas.replay_engine.service.build_replay_output_window(): every
    ReplayFrame returned, and every exception raised (including
    ReplayLengthMismatchError/ReplayOccurredAtMismatchError), comes from
    that function completely unchanged."""
    return build_replay_output_window(market_state_window, calendar, classifier)


async def fetch_replay_frames(
    symbol: Symbol,
    timeframe: Timeframe,
    start: datetime,
    end: datetime,
    repository: MarketStateRepository,
    limit: int = 10000,
    calendar: SessionCalendarDefinition = CME_RTH_V1,
    classifier: RegimeClassifierDefinition = REGIME_CLASSIFIER_V1,
) -> AsyncIterator[ReplayFrame]:
    """Research Engine's own entry point for a symbol/timeframe/date range
    fetched from a repository - the common case. A direct, unmodified
    pass-through to atlas.replay_engine.service.replay(): every ReplayFrame
    yielded, and every exception raised (a repository failure, a
    composition/alignment error), comes from that function completely
    unchanged. No try/except is added here, matching replay()'s own
    "propagate unchanged" posture."""
    async for frame in replay(symbol, timeframe, start, end, repository, limit, calendar, classifier):
        yield frame
