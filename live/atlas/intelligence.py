"""
AI Intelligence (Sprint 7): historical retrieval and statistics, computed
deterministically from the trades already in the database - explicitly NOT machine
learning. There is no training, no fitted parameters, no model file - `compute_confidence`
below is a fixed, documented rubric (hand-picked thresholds), and `find_similar_trades`
is a hand-designed distance measure over a few named fields, not a learned embedding.

This is "structured output first, narrative second" applied literally: every number in
an IntelligenceSnapshot is computed BEFORE Claude is ever called (see
atlas/ai.py::run_entry_score). Claude's only job for entry scoring is to explain these
specific, already-computed numbers - it never invents the score, the expected R, or
the historical win rate.

Pure functions, same shape as atlas/risk.py and atlas/analytics.py: no I/O, no
database, no FastAPI - fully unit-testable with hand-built trade lists. Reuses
atlas.analytics.compute_summary (not a parallel aggregation) so a similar-trades
summary and the /analytics page can never disagree about what "win rate" or
"expectancy" means.
"""
from dataclasses import dataclass
from statistics import median
from typing import Any, Optional

from atlas.analytics import SummaryMetrics, compute_summary

# Continuous factors compared between a new entry and its historical similar trades,
# each with a typical scale used to normalize distance (see _distance) - hand-picked
# from the strategy's own parameter ranges (see atlas/services/claude.py's original
# entry-analysis prompt for the same numbers used narratively), not fitted from data.
SIMILARITY_FACTORS = [
    ("regime_slope_pct", 2.0),
    ("ema_distance_atr", 2.0),
    ("sweep_age_bars", 15.0),
]


def _distance(entry: dict[str, Any], candidate: dict[str, Any]) -> float:
    total = 0.0
    count = 0
    for field, scale in SIMILARITY_FACTORS:
        a, b = entry.get(field), candidate.get(field)
        if a is None or b is None:
            continue
        total += ((a - b) / scale) ** 2
        count += 1
    return total ** 0.5 if count else float("inf")


def find_similar_trades(
    entry: dict[str, Any], trades: list[dict[str, Any]], *, max_results: int = 20,
) -> list[dict[str, Any]]:
    """"Similar" = same direction + same setup_tag (a hard filter - these are
    categorical, and changing either fundamentally changes what the trade IS) among
    CLOSED trades only (an open position has no outcome to learn from yet), ranked by
    closeness on the continuous factors using a simple normalized-distance measure -
    not a learned embedding. Excludes the entry's own correlation_id if present, so
    scoring a trade never counts itself as historical evidence for itself. Filters
    internally rather than trusting the caller to pre-filter, the same discipline
    atlas/analytics.py's compute_summary/compute_breakdown already use."""
    entry_id = entry.get("correlation_id")
    candidates = [
        t for t in trades
        if t.get("status") in ("won", "lost")
        and t.get("direction") == entry.get("direction")
        and t.get("setup_tag") == entry.get("setup_tag")
        and t.get("correlation_id") != entry_id
    ]
    ranked = sorted(candidates, key=lambda t: _distance(entry, t))
    return ranked[:max_results]


@dataclass
class Factor:
    name: str
    entry_value: Optional[float]
    winners_median: Optional[float]
    losers_median: Optional[float]
    favorable: Optional[bool]  # None when there isn't enough data on one side to judge


def compute_factors(entry: dict[str, Any], similar_trades: list[dict[str, Any]]) -> list[Factor]:
    """For each measurable factor, compares this entry's value against the median
    value among similar trades that won vs. lost - concrete, inspectable evidence for
    *why* a confidence score is what it is, not a black box. `favorable` is None (not
    guessed) when there aren't enough winners or losers in the sample to compare against."""
    winners = [t for t in similar_trades if t["status"] == "won"]
    losers = [t for t in similar_trades if t["status"] == "lost"]

    factors = []
    for field, _ in SIMILARITY_FACTORS:
        entry_value = entry.get(field)
        winners_vals = [t[field] for t in winners if t.get(field) is not None]
        losers_vals = [t[field] for t in losers if t.get(field) is not None]
        winners_median = median(winners_vals) if winners_vals else None
        losers_median = median(losers_vals) if losers_vals else None

        favorable = None
        if entry_value is not None and winners_median is not None and losers_median is not None:
            favorable = abs(entry_value - winners_median) <= abs(entry_value - losers_median)

        factors.append(Factor(
            name=field, entry_value=entry_value,
            winners_median=winners_median, losers_median=losers_median, favorable=favorable,
        ))
    return factors


def compute_confidence(summary: SummaryMetrics, similar_trade_count: int) -> tuple[Optional[int], str]:
    """A deterministic 1-10 confidence score from historical statistics - a fixed,
    documented rubric (max 4 points for sample size, max 4 for historical win rate,
    max 2 for positive expectancy), not a fitted/learned function. Returns
    (score, label); score is None only when there's no history at all to score against
    - "no data" is represented as missing, never as a fabricated low number."""
    if similar_trade_count == 0:
        return None, "Insufficient History"

    if similar_trade_count >= 15:
        sample_points = 4
    elif similar_trade_count >= 8:
        sample_points = 3
    elif similar_trade_count >= 4:
        sample_points = 2
    else:
        sample_points = 1

    win_rate = summary.win_rate_pct
    if win_rate >= 65:
        win_points = 4
    elif win_rate >= 55:
        win_points = 3
    elif win_rate >= 45:
        win_points = 2
    else:
        win_points = 1

    expectancy_points = 2 if summary.expectancy > 0 else 0

    score = min(10, sample_points + win_points + expectancy_points)

    if similar_trade_count < 4:
        label = "Insufficient History"
    elif score >= 8:
        label = "High Confidence"
    elif score >= 5:
        label = "Moderate Confidence"
    else:
        label = "Low Confidence"

    return score, label


@dataclass
class IntelligenceSnapshot:
    similar_trade_count: int
    summary: SummaryMetrics
    confidence_score: Optional[int]
    confidence_label: str
    factors: list[Factor]


def compute_intelligence_snapshot(
    entry: dict[str, Any], trades: list[dict[str, Any]], *, point_value: float, max_similar: int = 20,
) -> IntelligenceSnapshot:
    """Top-level orchestrator: find similar historical trades, compute their
    performance stats (via atlas.analytics.compute_summary - the exact function that
    powers the /analytics page), a deterministic confidence score, and the measurable
    factors behind it. This is everything atlas/ai.py::run_entry_score needs *before*
    it ever calls Claude - and everything atlas/api/v1/ai.py's on-demand intelligence
    endpoint needs without calling Claude at all."""
    similar = find_similar_trades(entry, trades, max_results=max_similar)
    summary = compute_summary(similar, point_value=point_value)
    confidence_score, confidence_label = compute_confidence(summary, len(similar))
    factors = compute_factors(entry, similar)

    return IntelligenceSnapshot(
        similar_trade_count=len(similar),
        summary=summary,
        confidence_score=confidence_score,
        confidence_label=confidence_label,
        factors=factors,
    )
