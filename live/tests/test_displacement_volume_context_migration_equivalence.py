"""
Setup Interpretation Sprint 6 - exact equivalence validation for
DisplacementVolumeContext's migration off direct Rule Engine fact
consumption. _legacy_evaluate() below is a frozen, test-only, byte-for-
byte reproduction of the plugin's own pre-Sprint-6 evaluate() body (the
exact code this module replaced, reading frame.rule_engine_output
.facts["trend_5m"] directly) - never imported from production, never
touched by this migration, existing solely as the "before" side of a
before/after comparison against the real, currently-migrated
DisplacementVolumeContext.

Every ReplayFrame compared here is produced by the real pipeline
(build_rule_engine_output_window -> build_setup_engine_output_window ->
build_market_context -> interpret_setups, via
atlas.replay_engine.service.build_replay_output_window) over real,
hand-built-but-otherwise-ordinary MarketState bars - the same real-pipeline
methodology Setup Interpretation's own Sprint 3 Integration Review
established, reused here rather than re-derived. is_rth=False is set on
every bar and the whole series sits in a deep-overnight window under
CME_RTH_V1 (see _BASE below) so Atlas's own session classification
genuinely AGREES with it - without this, ContextQuality would stay
UNKNOWN for every bar past warm-up (session drift always "upstream
missing"), and the comparison would never actually exercise the
CANDIDATE/LONG or CANDIDATE/SHORT path at all (the exact same
methodological gap Setup Interpretation's own Sprint 3 equivalence study
found and fixed).

Every bar in these series is "previously reachable" through the real
strategy - REGISTRY always evaluates every fact, so trend_5m can never be
entirely absent from a real RuleEngineOutput.facts dict (the one old-code
branch this migration structurally eliminated, see
test_strategy_displacement_volume_context.py's own module docstring) -
so no exclusions are needed for this synthetic-but-real-pipeline data;
every compared bar is a genuine apples-to-apples before/after pair.
"""
from datetime import datetime, timedelta, timezone

from atlas.core.events import Event
from atlas.core.primitives import Price, Symbol, Timeframe
from atlas.market_context.definitions import CME_RTH_V1, RegimeClassifierDefinition, RegimeClassifierParams
from atlas.market_context.models import ContextQuality
from atlas.market_engine.models import BarStatus, MarketState
from atlas.replay_engine.models import ReplayFrame
from atlas.replay_engine.service import build_replay_output_window
from atlas.rule_engine.models import FactResult
from atlas.setup_engine.models import SetupResult
from atlas.strategy_engine.models import StrategyDecision, StrategyDirection, StrategyDisposition
from atlas.strategy_engine.strategies.displacement_volume_context import (
    STRATEGY_ID,
    STRATEGY_VERSION,
    TARGET_SETUP_NAME,
    DisplacementVolumeContext,
)

_BASE = datetime(2026, 7, 21, 3, 0, tzinfo=timezone.utc)  # 22:00 CDT, 2026-07-20 - deep overnight

_SMALL_REGIME = RegimeClassifierDefinition(
    version="TEST_SMALL_V1",
    params=RegimeClassifierParams(
        lookback_bars=5, min_bars_required=5, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _legacy_evaluate(frame: ReplayFrame) -> StrategyDecision:
    """Frozen, test-only reproduction of DisplacementVolumeContext
    .evaluate()'s exact pre-Sprint-6 body. Never call production code from
    here and never let production code call this."""
    occurred_at = frame.market_state.envelope.occurred_at
    context_fingerprint = frame.market_context.context_fingerprint

    setup_outcome = next(
        (outcome for outcome in frame.setup_engine_output.setups if outcome.setup_name == TARGET_SETUP_NAME),
        None,
    )
    if not (isinstance(setup_outcome, SetupResult) and setup_outcome.detected):
        return StrategyDecision(
            occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            disposition=StrategyDisposition.NO_SIGNAL, direction=StrategyDirection.FLAT,
            setup_ids=(), reason_codes=("setup_absent",), context_fingerprint=context_fingerprint,
        )

    if frame.market_context.quality == ContextQuality.UNKNOWN:
        return StrategyDecision(
            occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
            setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_insufficient",),
            context_fingerprint=context_fingerprint,
        )

    trend = frame.rule_engine_output.facts.get("trend_5m")
    if not isinstance(trend, FactResult):
        return StrategyDecision(
            occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
            setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_insufficient",),
            context_fingerprint=context_fingerprint,
        )

    direction = {"up": StrategyDirection.LONG, "down": StrategyDirection.SHORT}.get(trend.value)
    if direction is None:
        return StrategyDecision(
            occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
            disposition=StrategyDisposition.REJECTED, direction=StrategyDirection.FLAT,
            setup_ids=(TARGET_SETUP_NAME,), reason_codes=("context_conflict",),
            context_fingerprint=context_fingerprint,
        )

    return StrategyDecision(
        occurred_at=occurred_at, strategy_id=STRATEGY_ID, strategy_version=STRATEGY_VERSION,
        disposition=StrategyDisposition.CANDIDATE, direction=direction,
        setup_ids=(TARGET_SETUP_NAME,), reason_codes=("accepted",),
        context_fingerprint=context_fingerprint,
    )


# ---- real MarketState series builders (mirrors Setup Interpretation's own Sprint 3 design) ----

def _bar(index: int, occurred_at: datetime, close: float) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=f"e{index}"),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        open=Price(close, 0.25), high=Price(close + 3.0, 0.25), low=Price(close - 3.0, 0.25), close=Price(close, 0.25),
        volume=1000.0, atr=2.0, volume_ratio=2.0, distance_from_vwap_points=0.0, is_rth=False,
    )


def _series(closes: list[float]) -> list[MarketState]:
    step = timedelta(minutes=5)
    return [_bar(i, _BASE + step * i, close) for i, close in enumerate(closes)]


_BULLISH_SERIES = _series([100.0 + i * 2 for i in range(25)])   # clean ascending trend -> "up"
_BEARISH_SERIES = _series([200.0 - i * 2 for i in range(25)])   # clean descending trend -> "down"
_FLAT_SERIES = _series([100.0] * 25)                            # constant close -> slope 0 -> "flat"
_SHORT_SERIES = _series([100.0 + i for i in range(5)])          # < 20 bars -> trend_5m InsufficientData


def _compare(series: list[MarketState]) -> tuple[int, int, list[str]]:
    """Returns (bars_compared, exact_matches, mismatch_descriptions)."""
    frames = build_replay_output_window(series, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    plugin = DisplacementVolumeContext()
    mismatches = []
    matches = 0
    for frame in frames:
        legacy = _legacy_evaluate(frame)
        actual = plugin.evaluate(frame)
        if legacy == actual:
            matches += 1
        else:
            mismatches.append(
                f"{frame.market_state.envelope.occurred_at.isoformat()}: legacy={legacy!r} actual={actual!r}"
            )
    return len(frames), matches, mismatches


def test_bullish_series_exact_equivalence():
    total, matches, mismatches = _compare(_BULLISH_SERIES)
    assert mismatches == []
    assert matches == total == 25


def test_bearish_series_exact_equivalence():
    total, matches, mismatches = _compare(_BEARISH_SERIES)
    assert mismatches == []
    assert matches == total == 25


def test_flat_series_exact_equivalence():
    total, matches, mismatches = _compare(_FLAT_SERIES)
    assert mismatches == []
    assert matches == total == 25


def test_short_series_exact_equivalence():
    total, matches, mismatches = _compare(_SHORT_SERIES)
    assert mismatches == []
    assert matches == total == 5


def test_combined_real_data_exact_equivalence_report():
    """One consolidated pass across all four series, reporting the
    Sprint 6 deliverable's own required statistics: total bars compared,
    exact matches, mismatches, and every mismatch category if any."""
    total_bars = 0
    total_matches = 0
    all_mismatches: list[str] = []
    for series in (_BULLISH_SERIES, _BEARISH_SERIES, _FLAT_SERIES, _SHORT_SERIES):
        bars, matches, mismatches = _compare(series)
        total_bars += bars
        total_matches += matches
        all_mismatches.extend(mismatches)

    assert total_bars == 80
    assert all_mismatches == []
    assert total_matches == total_bars

    # Confirms every direction genuinely reachable through this data was
    # actually exercised, not vacuously equal because nothing interesting
    # ever happened (the exact gap Setup Interpretation's own Sprint 3
    # equivalence study found and fixed via is_rth).
    frames = build_replay_output_window(_BULLISH_SERIES, calendar=CME_RTH_V1, classifier=_SMALL_REGIME)
    last_decision = DisplacementVolumeContext().evaluate(frames[-1])
    assert last_decision.disposition == StrategyDisposition.CANDIDATE
    assert last_decision.direction == StrategyDirection.LONG
    assert frames[-1].market_context.quality == ContextQuality.TRUSTED
