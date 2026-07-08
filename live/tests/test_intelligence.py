"""
Unit tests for atlas/intelligence.py - pure functions, no I/O, driven directly with
hand-built trade dicts. Covers historical similarity search, the factor comparison,
the deterministic confidence rubric, and the top-level snapshot orchestration. See
that module's docstring for why none of this is machine learning: fixed thresholds
and a hand-designed distance measure, not anything fitted from data.
"""
from atlas.intelligence import (
    Factor,
    compute_confidence,
    compute_factors,
    compute_intelligence_snapshot,
    find_similar_trades,
)
from atlas.analytics import compute_summary

POINT_VALUE = 2.0

ENTRY = {
    "correlation_id": "new-1", "direction": "long", "setup_tag": "BRK",
    "entry_price": 100.0, "sl": 90.0, "tp": 130.0, "quantity": 2,
    "regime_slope_pct": 1.0, "ema_distance_atr": 0.5, "sweep_age_bars": 3,
}


def closed_trade(correlation_id, status, realized_pnl, *, direction="long", setup_tag="BRK", **overrides):
    trade = {
        "correlation_id": correlation_id, "status": status, "realized_pnl": realized_pnl,
        "closed_at": "2026-01-01T00:00:00+00:00",
        "direction": direction, "setup_tag": setup_tag,
        "entry_price": 100.0, "sl": 90.0, "tp": 130.0, "quantity": 2,
        "regime_slope_pct": 1.0, "ema_distance_atr": 0.5, "sweep_age_bars": 3,
    }
    trade.update(overrides)
    return trade


# --- find_similar_trades -------------------------------------------------------------

def test_find_similar_trades_matches_same_direction_and_setup_tag():
    trades = [
        closed_trade("a", "won", 500),
        closed_trade("b", "lost", -300, direction="short"),  # wrong direction
        closed_trade("c", "won", 400, setup_tag="RCL"),  # wrong setup
        closed_trade("d", "open", None),  # not closed - excluded
    ]
    similar = find_similar_trades(ENTRY, trades)
    assert [t["correlation_id"] for t in similar] == ["a"]


def test_find_similar_trades_excludes_the_entry_itself():
    trades = [closed_trade("new-1", "won", 500)]  # same correlation_id as ENTRY
    assert find_similar_trades(ENTRY, trades) == []


def test_find_similar_trades_ranks_by_closeness_and_respects_max_results():
    trades = [
        closed_trade("far", "won", 500, regime_slope_pct=5.0),  # distance from ENTRY's 1.0 is large
        closed_trade("near", "won", 500, regime_slope_pct=1.1),  # very close to ENTRY's 1.0
    ]
    similar = find_similar_trades(ENTRY, trades, max_results=1)
    assert [t["correlation_id"] for t in similar] == ["near"]


def test_find_similar_trades_empty_when_nothing_matches():
    assert find_similar_trades(ENTRY, []) == []


# --- compute_factors -------------------------------------------------------------------

def test_compute_factors_marks_favorable_when_entry_closer_to_winners():
    similar = [
        closed_trade("w1", "won", 500, regime_slope_pct=1.0),
        closed_trade("l1", "lost", -300, regime_slope_pct=3.0),
    ]
    factors = compute_factors(ENTRY, similar)  # ENTRY's regime_slope_pct is 1.0 - matches winners exactly
    regime_factor = next(f for f in factors if f.name == "regime_slope_pct")
    assert regime_factor.entry_value == 1.0
    assert regime_factor.winners_median == 1.0
    assert regime_factor.losers_median == 3.0
    assert regime_factor.favorable is True


def test_compute_factors_marks_unfavorable_when_entry_closer_to_losers():
    similar = [
        closed_trade("w1", "won", 500, regime_slope_pct=5.0),
        closed_trade("l1", "lost", -300, regime_slope_pct=1.0),
    ]
    factors = compute_factors(ENTRY, similar)  # ENTRY's regime_slope_pct is 1.0 - matches losers exactly
    regime_factor = next(f for f in factors if f.name == "regime_slope_pct")
    assert regime_factor.favorable is False


def test_compute_factors_favorable_is_none_without_both_sides():
    similar = [closed_trade("w1", "won", 500)]  # no losers at all in the sample
    factors = compute_factors(ENTRY, similar)
    assert all(f.favorable is None for f in factors)


def test_compute_factors_returns_one_factor_per_similarity_field():
    factors = compute_factors(ENTRY, [])
    assert {f.name for f in factors} == {"regime_slope_pct", "ema_distance_atr", "sweep_age_bars"}


# --- compute_confidence ----------------------------------------------------------------

def test_compute_confidence_zero_similar_trades_is_insufficient_history():
    summary = compute_summary([], point_value=POINT_VALUE)
    score, label = compute_confidence(summary, 0)
    assert score is None
    assert label == "Insufficient History"


def test_compute_confidence_few_trades_stays_insufficient_history_label_even_with_a_score():
    trades = [closed_trade("a", "won", 500), closed_trade("b", "won", 500)]
    summary = compute_summary(trades, point_value=POINT_VALUE)
    score, label = compute_confidence(summary, similar_trade_count=2)
    assert score is not None  # a score IS computed...
    assert label == "Insufficient History"  # ...but the label still flags a thin sample


def test_compute_confidence_high_sample_high_win_rate_positive_expectancy_is_high_confidence():
    trades = [closed_trade(f"w{i}", "won", 500) for i in range(15)]
    summary = compute_summary(trades, point_value=POINT_VALUE)
    score, label = compute_confidence(summary, similar_trade_count=15)
    assert score == 10  # 4 (sample>=15) + 4 (win_rate=100%) + 2 (positive expectancy), capped at 10
    assert label == "High Confidence"


def test_compute_confidence_negative_expectancy_and_low_win_rate_is_low_confidence():
    trades = (
        [closed_trade(f"w{i}", "won", 100) for i in range(2)]
        + [closed_trade(f"l{i}", "lost", -500) for i in range(6)]
    )
    summary = compute_summary(trades, point_value=POINT_VALUE)
    score, label = compute_confidence(summary, similar_trade_count=8)
    assert summary.expectancy < 0
    assert label == "Low Confidence"


# --- compute_intelligence_snapshot ------------------------------------------------------

def test_compute_intelligence_snapshot_end_to_end_with_no_history():
    snapshot = compute_intelligence_snapshot(ENTRY, [], point_value=POINT_VALUE)
    assert snapshot.similar_trade_count == 0
    assert snapshot.confidence_score is None
    assert snapshot.confidence_label == "Insufficient History"
    assert snapshot.summary.total_trades == 0
    assert len(snapshot.factors) == 3


def test_compute_intelligence_snapshot_end_to_end_with_history():
    trades = [closed_trade(f"w{i}", "won", 500) for i in range(10)] + [closed_trade("l1", "lost", -300)]
    snapshot = compute_intelligence_snapshot(ENTRY, trades, point_value=POINT_VALUE)

    assert snapshot.similar_trade_count == 11
    assert snapshot.summary.total_trades == 11
    assert snapshot.summary.wins == 10
    assert snapshot.confidence_score is not None
    assert snapshot.confidence_label in {"High Confidence", "Moderate Confidence", "Low Confidence"}
    assert all(isinstance(f, Factor) for f in snapshot.factors)
