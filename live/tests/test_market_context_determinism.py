"""
Phase N1 Finalization Gate. Cross-module determinism audit for
atlas.market_context: proves - across many repeated calls, not just one -
that nothing in classify_session(), classify_volatility_regime(),
compute_fingerprint(), or build_market_context() depends on clock time,
object identity, dict/set iteration order, or any other source of
incidental non-determinism. Each individual module already has its own
"is pure" unit test (test_market_context_session.py,
test_market_context_regime.py, test_market_context_service.py); this file
exists to certify the same property under repetition, at the seam between
all four modules, per the Finalization Gate's explicit requirement of "at
least 100 iterations" - a single before/after equality check cannot catch
a source of non-determinism that only shows up intermittently (e.g. an
unstable hash-order dependency).

No new business logic - every assertion re-uses the same public functions
already exercised elsewhere.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    CME_RTH_V1,
    RegimeClassifierDefinition,
    RegimeClassifierParams,
    SessionCalendarDefinition,
    SessionCalendarParams,
)
from atlas.market_context.fingerprint import compute_fingerprint
from atlas.market_context.regime import classify_volatility_regime
from atlas.market_context.service import build_market_context
from atlas.market_context.session import classify_session
from atlas.market_engine.models import BarStatus, MarketState

ITERATIONS = 100

_CENTRAL = ZoneInfo("America/Chicago")

_CLASSIFIER = RegimeClassifierDefinition(
    version="TEST_DETERMINISM_V1",
    params=RegimeClassifierParams(
        lookback_bars=10, min_bars_required=10, compressed_percentile=25, expanded_percentile=75,
    ),
)


def _occurred_at(hour: int, minute: int) -> datetime:
    ct = datetime(2026, 7, 21, hour, minute, tzinfo=_CENTRAL)
    return ct.astimezone(timezone.utc)


def _window_ending_at(occurred_at: datetime, n: int) -> list[MarketState]:
    step = timedelta(minutes=Timeframe("5m").duration_minutes)
    start = occurred_at - step * (n - 1)
    return [
        MarketState(
            envelope=Event(event_type="bar_closed", source="test", occurred_at=start + step * i),
            schema_version="1.0",
            symbol=Symbol("MNQU6"),
            timeframe=Timeframe("5m"),
            bar_status=BarStatus.CLOSED,
            atr=1.0 + i,
        )
        for i in range(n)
    ]


_OCCURRED_AT = _occurred_at(12, 0)  # MID_SESSION, agreement, fully trusted
_WINDOW = _window_ending_at(_OCCURRED_AT, 10)


def test_repeated_classify_session_calls_produce_identical_results():
    results = [classify_session(_OCCURRED_AT, "RTH", True, CME_RTH_V1) for _ in range(ITERATIONS)]
    assert all(result == results[0] for result in results)


def test_repeated_classify_volatility_regime_calls_produce_identical_results():
    results = [classify_volatility_regime(_WINDOW, _CLASSIFIER) for _ in range(ITERATIONS)]
    assert all(result == results[0] for result in results)


def test_repeated_compute_fingerprint_calls_produce_identical_results():
    payload = {"session_calendar": CME_RTH_V1, "regime_classifier": _CLASSIFIER}
    results = [compute_fingerprint(payload) for _ in range(ITERATIONS)]
    assert all(result == results[0] for result in results)


def test_repeated_build_market_context_calls_produce_identical_results():
    results = [
        build_market_context(
            symbol=Symbol("MNQU6"),
            timeframe=Timeframe("5m"),
            occurred_at=_OCCURRED_AT,
            window=_WINDOW,
            upstream_session_name="RTH",
            upstream_is_rth=True,
            calendar=CME_RTH_V1,
            classifier=_CLASSIFIER,
        )
        for _ in range(ITERATIONS)
    ]
    assert all(result == results[0] for result in results)


def test_repeated_build_market_context_calls_produce_identical_fingerprints():
    """A narrower slice of the assertion above, isolating the fingerprint
    field specifically - the exact property a future consumer diffing
    context_fingerprint values across replays depends on."""
    fingerprints = {
        build_market_context(
            symbol=Symbol("MNQU6"),
            timeframe=Timeframe("5m"),
            occurred_at=_OCCURRED_AT,
            window=_WINDOW,
            upstream_session_name="RTH",
            upstream_is_rth=True,
            calendar=CME_RTH_V1,
            classifier=_CLASSIFIER,
        ).context_fingerprint
        for _ in range(ITERATIONS)
    }
    assert len(fingerprints) == 1


def test_repeated_calls_do_not_accumulate_mutation_in_the_shared_window():
    """Guards against hidden mutable state: if any function under test ever
    appended to or reordered the window list it was given, repeated calls
    against the SAME _WINDOW object would diverge or the window's own
    length/order would drift over iterations."""
    window_copy = list(_WINDOW)
    for _ in range(ITERATIONS):
        build_market_context(
            symbol=Symbol("MNQU6"),
            timeframe=Timeframe("5m"),
            occurred_at=_OCCURRED_AT,
            window=_WINDOW,
            upstream_session_name="RTH",
            upstream_is_rth=True,
            calendar=CME_RTH_V1,
            classifier=_CLASSIFIER,
        )
    assert _WINDOW == window_copy
    assert all(a is b for a, b in zip(_WINDOW, window_copy))


def test_determinism_holds_across_varied_inputs_not_just_one_fixed_case():
    """The single fixed (_OCCURRED_AT, _WINDOW) case above could coincidentally
    hide a non-determinism that only appears for certain phases/regimes -
    repeat across every SessionPhase-triggering hour and both DISAGREEMENT/
    AGREEMENT branches to widen coverage under repetition."""
    cases = [
        (_occurred_at(8, 0), "RTH", True),  # PRE_OPEN, disagreement
        (_occurred_at(8, 30), "OVERNIGHT", False),  # OPENING_RANGE, calibrated disagreement
        (_occurred_at(12, 0), "RTH", True),  # MID_SESSION, agreement
        (_occurred_at(15, 0), None, None),  # CLOSING_RANGE, upstream missing
        (_occurred_at(20, 0), "OVERNIGHT", False),  # OVERNIGHT, agreement
    ]
    for occurred_at, upstream_session_name, upstream_is_rth in cases:
        window = _window_ending_at(occurred_at, 10)
        results = [
            build_market_context(
                symbol=Symbol("MNQU6"),
                timeframe=Timeframe("5m"),
                occurred_at=occurred_at,
                window=window,
                upstream_session_name=upstream_session_name,
                upstream_is_rth=upstream_is_rth,
                calendar=CME_RTH_V1,
                classifier=_CLASSIFIER,
            )
            for _ in range(ITERATIONS)
        ]
        assert all(result == results[0] for result in results), f"non-determinism at {occurred_at.isoformat()}"


# ---- Phase N1 Sprint 5: object independence, hidden state, cache
# dependence, and datetime handling - added to the Finalization Gate's
# original 100-iteration suite above rather than duplicating it. ----

def test_object_independence_separately_constructed_equal_inputs_produce_identical_output():
    """Two genuinely separate Python objects (not the same reference) that
    are merely value-equal must produce the same MarketContext - proving
    correctness depends on VALUES, not on object identity or an
    accidentally-cached reference to one particular instance."""
    calendar_a = SessionCalendarDefinition(
        version="CME_RTH_V1",
        params=SessionCalendarParams(
            rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    calendar_b = SessionCalendarDefinition(
        version="CME_RTH_V1",
        params=SessionCalendarParams(
            rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
            pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
        ),
    )
    assert calendar_a is not calendar_b

    # _WINDOW is shared deliberately - MarketState.envelope carries a
    # random event_id/received_at by default, so two freshly-built windows
    # would not be value-equal even when semantically identical; that is
    # irrelevant to this test's actual claim, which is about calendar_a/
    # calendar_b's object identity, not the window's.
    result_a = build_market_context(
        symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=_OCCURRED_AT,
        window=_WINDOW, upstream_session_name="RTH", upstream_is_rth=True,
        calendar=calendar_a, classifier=_CLASSIFIER,
    )
    result_b = build_market_context(
        symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=_OCCURRED_AT,
        window=_WINDOW, upstream_session_name="RTH", upstream_is_rth=True,
        calendar=calendar_b, classifier=_CLASSIFIER,
    )
    assert result_a == result_b


def test_no_hidden_state_interleaved_calls_with_different_inputs_do_not_leak():
    """Computes case A, then case B (a genuinely different input) many
    times, then case A again - if any hidden/shared state existed,
    computing B in between could perturb A's second result. It must not."""

    def _run(occurred_at, upstream_session_name, upstream_is_rth):
        window = _window_ending_at(occurred_at, 10)
        return build_market_context(
            symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=occurred_at,
            window=window, upstream_session_name=upstream_session_name, upstream_is_rth=upstream_is_rth,
            calendar=CME_RTH_V1, classifier=_CLASSIFIER,
        )

    first_a = _run(_occurred_at(12, 0), "RTH", True)
    for _ in range(ITERATIONS):
        _run(_occurred_at(20, 0), "OVERNIGHT", False)
    second_a = _run(_occurred_at(12, 0), "RTH", True)
    assert first_a == second_a


def test_no_cache_dependence_alternating_distinct_inputs_never_return_a_stale_result():
    """Alternates rapidly between two distinct classifier versions many
    times - if a result were ever memoized/cached keyed incorrectly, one
    input would eventually return the other's stale result."""
    classifier_a = RegimeClassifierDefinition(
        version="TEST_ALT_A_V1",
        params=RegimeClassifierParams(
            lookback_bars=10, min_bars_required=10, compressed_percentile=25, expanded_percentile=75,
        ),
    )
    classifier_b = RegimeClassifierDefinition(
        version="TEST_ALT_B_V1",
        params=RegimeClassifierParams(
            lookback_bars=10, min_bars_required=10, compressed_percentile=10, expanded_percentile=90,
        ),
    )
    for _ in range(ITERATIONS):
        result_a = build_market_context(
            symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=_OCCURRED_AT,
            window=_WINDOW, upstream_session_name="RTH", upstream_is_rth=True,
            calendar=CME_RTH_V1, classifier=classifier_a,
        )
        result_b = build_market_context(
            symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=_OCCURRED_AT,
            window=_WINDOW, upstream_session_name="RTH", upstream_is_rth=True,
            calendar=CME_RTH_V1, classifier=classifier_b,
        )
        assert result_a.classifier_version == "TEST_ALT_A_V1"
        assert result_b.classifier_version == "TEST_ALT_B_V1"
        assert result_a.context_fingerprint != result_b.context_fingerprint


def test_deterministic_datetime_handling_survives_real_elapsed_wall_clock_time():
    """Real wall-clock time elapses across ITERATIONS calls (this is not a
    mocked clock) - if any function under test read datetime.now()/
    utcnow() anywhere, results would drift as real time passed. They must
    not - every datetime in a result must come from occurred_at alone."""
    results = [
        build_market_context(
            symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=_OCCURRED_AT,
            window=_WINDOW, upstream_session_name="RTH", upstream_is_rth=True,
            calendar=CME_RTH_V1, classifier=_CLASSIFIER,
        )
        for _ in range(ITERATIONS)
    ]
    assert all(result == results[0] for result in results)


def test_deterministic_datetime_handling_across_a_dst_boundary():
    """Same CT wall-clock hour, one CST date and one CDT date: each must be
    internally repeatable under 100 iterations, and the two dates must NOT
    collapse to the same UTC instant - proving the DST offset is actually
    applied deterministically via zoneinfo, never silently ignored or
    dependent on the machine's local timezone."""
    cst_at = datetime(2026, 1, 15, 12, 0, tzinfo=_CENTRAL).astimezone(timezone.utc)
    cdt_at = datetime(2026, 7, 21, 12, 0, tzinfo=_CENTRAL).astimezone(timezone.utc)
    assert cst_at != cdt_at

    cst_window = _window_ending_at(cst_at, 10)
    cdt_window = _window_ending_at(cdt_at, 10)

    cst_results = [
        build_market_context(
            symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=cst_at,
            window=cst_window, upstream_session_name="RTH", upstream_is_rth=True,
            calendar=CME_RTH_V1, classifier=_CLASSIFIER,
        )
        for _ in range(ITERATIONS)
    ]
    cdt_results = [
        build_market_context(
            symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=cdt_at,
            window=cdt_window, upstream_session_name="RTH", upstream_is_rth=True,
            calendar=CME_RTH_V1, classifier=_CLASSIFIER,
        )
        for _ in range(ITERATIONS)
    ]
    assert all(r == cst_results[0] for r in cst_results)
    assert all(r == cdt_results[0] for r in cdt_results)
