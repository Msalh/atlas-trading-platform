"""
Pure analytics computation over a list of trade rows - no I/O, same shape as
atlas/risk.py and atlas/api/v1/trades.py::build_timeline: the actual math lives here as
plain functions over plain data, fully unit-testable without a database or FastAPI.
atlas/api/v1/analytics.py is just fetch-trades-and-serialize.

Scope and simplifications, stated plainly (same discipline as risk.py and stats.py):
  - Every metric here is computed over CLOSED trades only (status won/lost with a
    closed_at) - an open position has no realized outcome to analyze yet.
  - The equity curve reuses `settings.account_starting_balance` (the same account
    config Sprint 4 introduced) so this sprint's numbers agree with what /api/v1/risk
    reports as current_balance - not a second, independent balance concept.
  - "Day of week" and ordering both use `closed_at`, not `received_at`/`signal_time` -
    a trade's P&L is attributed to the day it closed, matching how risk.py's daily
    loss tracking already attributes realized P&L to closed_at's date.
  - Average R-multiple only includes trades where risk in dollars is computable
    (direction/entry/sl/tp/quantity all present) - trades missing any of those are
    silently excluded from that one average (not from any other metric), and the
    sample size actually used is returned alongside the average so this isn't hidden.
  - The equity-curve loop intentionally duplicates ~6 lines of risk.py's running-
    balance/high-water-mark logic rather than importing it, to avoid touching Sprint
    4's already-approved, tested code for a sprint that only needed the *full series*
    version of the same idea. See docs/sprint5/architecture-decisions.md.
"""
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional

from atlas.risk import risk_reward_points

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _closed_trades(trades: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [t for t in trades if t["status"] in ("won", "lost") and t.get("closed_at")]


# --- Summary metrics --------------------------------------------------------------

@dataclass
class SummaryMetrics:
    total_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    gross_profit: float
    gross_loss: float
    profit_factor: Optional[float]
    expectancy: float
    avg_win: Optional[float]
    avg_loss: Optional[float]
    avg_r: Optional[float]
    r_multiple_sample_size: int


def compute_summary(trades: list[dict[str, Any]], *, point_value: float) -> SummaryMetrics:
    closed = _closed_trades(trades)
    total = len(closed)
    wins = [t for t in closed if t["status"] == "won"]
    losses = [t for t in closed if t["status"] == "lost"]

    gross_profit = sum(t.get("realized_pnl") or 0 for t in wins)
    gross_loss = -sum(t.get("realized_pnl") or 0 for t in losses)  # positive magnitude
    total_realized = sum(t.get("realized_pnl") or 0 for t in closed)

    r_multiples = []
    for t in closed:
        risk_points, _ = risk_reward_points(t.get("direction"), t.get("entry_price"), t.get("sl"), t.get("tp"))
        quantity = t.get("quantity")
        if risk_points and risk_points > 0 and quantity:
            risk_dollars = risk_points * quantity * point_value
            if risk_dollars > 0:
                r_multiples.append((t.get("realized_pnl") or 0) / risk_dollars)

    return SummaryMetrics(
        total_trades=total,
        wins=len(wins),
        losses=len(losses),
        win_rate_pct=(len(wins) / total * 100) if total else 0.0,
        gross_profit=gross_profit,
        gross_loss=gross_loss,
        profit_factor=(gross_profit / gross_loss) if gross_loss > 0 else None,
        expectancy=(total_realized / total) if total else 0.0,
        avg_win=(gross_profit / len(wins)) if wins else None,
        avg_loss=(-gross_loss / len(losses)) if losses else None,
        avg_r=(sum(r_multiples) / len(r_multiples)) if r_multiples else None,
        r_multiple_sample_size=len(r_multiples),
    )


# --- Equity / drawdown curve ------------------------------------------------------

@dataclass
class EquityPoint:
    correlation_id: str
    closed_at: str
    realized_pnl: float
    equity: float
    high_water_mark: float
    drawdown: float
    drawdown_pct: float


@dataclass
class EquityCurve:
    starting_balance: float
    points: list[EquityPoint]
    ending_equity: float
    max_drawdown: float
    max_drawdown_pct: float


def compute_equity_curve(trades: list[dict[str, Any]], *, starting_balance: float) -> EquityCurve:
    closed = sorted(_closed_trades(trades), key=lambda t: t["closed_at"])

    balance = starting_balance
    peak = starting_balance
    max_drawdown = 0.0
    max_drawdown_pct = 0.0
    points: list[EquityPoint] = []

    for t in closed:
        balance += t.get("realized_pnl") or 0
        peak = max(peak, balance)
        drawdown = peak - balance
        drawdown_pct = (drawdown / peak * 100) if peak > 0 else 0.0
        max_drawdown = max(max_drawdown, drawdown)
        max_drawdown_pct = max(max_drawdown_pct, drawdown_pct)
        points.append(EquityPoint(
            correlation_id=t["correlation_id"],
            closed_at=t["closed_at"],
            realized_pnl=t.get("realized_pnl") or 0,
            equity=balance,
            high_water_mark=peak,
            drawdown=drawdown,
            drawdown_pct=drawdown_pct,
        ))

    return EquityCurve(
        starting_balance=starting_balance,
        points=points,
        ending_equity=balance,
        max_drawdown=max_drawdown,
        max_drawdown_pct=max_drawdown_pct,
    )


# --- Breakdowns (session / setup / day-of-week) ------------------------------------

@dataclass
class BreakdownGroup:
    key: str
    total_trades: int
    wins: int
    losses: int
    win_rate_pct: float
    total_realized_pnl: float
    avg_realized_pnl: float


@dataclass
class BreakdownResult:
    by_session: list[BreakdownGroup]
    by_setup: list[BreakdownGroup]
    by_weekday: list[BreakdownGroup]


def _weekday_name(closed_at: str) -> str:
    try:
        return WEEKDAY_NAMES[datetime.fromisoformat(closed_at).weekday()]
    except (ValueError, TypeError):
        return "Unknown"


def _build_groups(closed_trades: list[dict[str, Any]], key_fn) -> list[BreakdownGroup]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for t in closed_trades:
        buckets.setdefault(key_fn(t), []).append(t)

    groups = []
    for key, ts in buckets.items():
        wins = [t for t in ts if t["status"] == "won"]
        total_pnl = sum(t.get("realized_pnl") or 0 for t in ts)
        groups.append(BreakdownGroup(
            key=key,
            total_trades=len(ts),
            wins=len(wins),
            losses=len(ts) - len(wins),
            win_rate_pct=(len(wins) / len(ts) * 100) if ts else 0.0,
            total_realized_pnl=total_pnl,
            avg_realized_pnl=(total_pnl / len(ts)) if ts else 0.0,
        ))
    return groups


def compute_breakdown(trades: list[dict[str, Any]]) -> BreakdownResult:
    closed = _closed_trades(trades)

    by_session = _build_groups(closed, lambda t: t.get("session") or "Unknown")
    by_session.sort(key=lambda g: g.total_trades, reverse=True)

    by_setup = _build_groups(closed, lambda t: t.get("setup_tag") or "Unknown")
    by_setup.sort(key=lambda g: g.total_trades, reverse=True)

    by_weekday = _build_groups(closed, lambda t: _weekday_name(t["closed_at"]))
    # Chronological (Mon-Sun), not by count - a day-of-week breakdown reads naturally
    # in calendar order, unlike session/setup where "most active first" is more useful.
    weekday_order = {name: i for i, name in enumerate(WEEKDAY_NAMES)}
    by_weekday.sort(key=lambda g: weekday_order.get(g.key, len(WEEKDAY_NAMES)))

    return BreakdownResult(by_session=by_session, by_setup=by_setup, by_weekday=by_weekday)
