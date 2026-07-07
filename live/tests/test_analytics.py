"""
Unit tests for atlas/analytics.py - pure functions, no I/O, driven directly with
hand-built trade dicts. See that module's docstring for the scope being tested:
closed-trades-only, closed_at-attributed, and the documented R-multiple sample-size
exclusion.
"""
from datetime import datetime

from atlas.analytics import compute_breakdown, compute_equity_curve, compute_summary

POINT_VALUE = 2.0


def closed_trade(
    correlation_id, status, realized_pnl, closed_at,
    direction="long", entry_price=None, sl=None, tp=None, quantity=None,
    session=None, setup_tag=None,
):
    return {
        "correlation_id": correlation_id, "status": status, "realized_pnl": realized_pnl,
        "closed_at": closed_at, "direction": direction, "entry_price": entry_price,
        "sl": sl, "tp": tp, "quantity": quantity, "session": session, "setup_tag": setup_tag,
    }


# --- compute_summary ---------------------------------------------------------------

def test_summary_with_no_trades():
    s = compute_summary([], point_value=POINT_VALUE)
    assert s.total_trades == 0
    assert s.win_rate_pct == 0.0
    assert s.profit_factor is None
    assert s.expectancy == 0.0
    assert s.avg_win is None
    assert s.avg_loss is None
    assert s.avg_r is None
    assert s.r_multiple_sample_size == 0


def test_summary_mixed_wins_and_losses():
    trades = [
        closed_trade("a", "won", 600, "2026-07-06T10:00:00+00:00"),
        closed_trade("b", "won", 400, "2026-07-06T11:00:00+00:00"),
        closed_trade("c", "lost", -300, "2026-07-06T12:00:00+00:00"),
    ]
    s = compute_summary(trades, point_value=POINT_VALUE)

    assert s.total_trades == 3
    assert s.wins == 2
    assert s.losses == 1
    assert s.win_rate_pct == (2 / 3) * 100
    assert s.gross_profit == 1000
    assert s.gross_loss == 300
    assert s.profit_factor == 1000 / 300
    assert s.expectancy == (600 + 400 - 300) / 3
    assert s.avg_win == 500
    assert s.avg_loss == -300


def test_summary_profit_factor_is_none_with_no_losses():
    trades = [closed_trade("a", "won", 500, "2026-07-06T10:00:00+00:00")]
    s = compute_summary(trades, point_value=POINT_VALUE)
    assert s.profit_factor is None
    assert s.avg_loss is None


def test_summary_avg_r_only_counts_trades_with_computable_risk():
    trades = [
        # Full risk data: long, entry 100, sl 90 -> risk 10 pts, qty 2 -> $40 risk. Won +80 -> R = 2.0
        closed_trade("a", "won", 80, "2026-07-06T10:00:00+00:00",
                      direction="long", entry_price=100, sl=90, tp=130, quantity=2),
        # Missing quantity - excluded from R average, but still counts toward win_rate/expectancy
        closed_trade("b", "won", 200, "2026-07-06T11:00:00+00:00",
                      direction="long", entry_price=100, sl=90, tp=130, quantity=None),
    ]
    s = compute_summary(trades, point_value=POINT_VALUE)

    assert s.total_trades == 2
    assert s.r_multiple_sample_size == 1
    assert s.avg_r == 2.0


# --- compute_equity_curve -----------------------------------------------------------

def test_equity_curve_with_no_trades():
    curve = compute_equity_curve([], starting_balance=50_000.0)
    assert curve.points == []
    assert curve.ending_equity == 50_000.0
    assert curve.max_drawdown == 0.0
    assert curve.max_drawdown_pct == 0.0


def test_equity_curve_tracks_running_balance_and_max_drawdown():
    trades = [
        closed_trade("a", "won", 1_000, "2026-07-06T10:00:00+00:00"),   # 51,000 (new peak)
        closed_trade("b", "lost", -600, "2026-07-06T11:00:00+00:00"),   # 50,400 (dd 600 from peak)
        closed_trade("c", "lost", -700, "2026-07-06T12:00:00+00:00"),   # 49,700 (dd 1,300 from peak)
        closed_trade("d", "won", 500, "2026-07-06T13:00:00+00:00"),     # 50,200 (dd 800 from peak)
    ]
    curve = compute_equity_curve(trades, starting_balance=50_000.0)

    assert [p.equity for p in curve.points] == [51_000.0, 50_400.0, 49_700.0, 50_200.0]
    assert [p.high_water_mark for p in curve.points] == [51_000.0, 51_000.0, 51_000.0, 51_000.0]
    assert curve.ending_equity == 50_200.0
    assert curve.max_drawdown == 1_300.0


def test_equity_curve_points_are_sorted_by_closed_at_regardless_of_input_order():
    trades = [
        closed_trade("later", "won", 100, "2026-07-06T15:00:00+00:00"),
        closed_trade("earlier", "won", 200, "2026-07-06T09:00:00+00:00"),
    ]
    curve = compute_equity_curve(trades, starting_balance=10_000.0)
    assert [p.correlation_id for p in curve.points] == ["earlier", "later"]


# --- compute_breakdown ---------------------------------------------------------------

def test_breakdown_groups_by_session_and_setup():
    trades = [
        closed_trade("a", "won", 500, "2026-07-06T10:00:00+00:00", session="NY", setup_tag="BRK"),
        closed_trade("b", "lost", -200, "2026-07-06T11:00:00+00:00", session="NY", setup_tag="RCL"),
        closed_trade("c", "won", 300, "2026-07-06T12:00:00+00:00", session="London", setup_tag="BRK"),
    ]
    result = compute_breakdown(trades)

    ny = next(g for g in result.by_session if g.key == "NY")
    assert ny.total_trades == 2
    assert ny.wins == 1
    assert ny.losses == 1
    assert ny.total_realized_pnl == 300

    brk = next(g for g in result.by_setup if g.key == "BRK")
    assert brk.total_trades == 2
    assert brk.total_realized_pnl == 800


def test_breakdown_uses_unknown_bucket_for_missing_session_or_setup():
    trades = [closed_trade("a", "won", 100, "2026-07-06T10:00:00+00:00", session=None, setup_tag=None)]
    result = compute_breakdown(trades)
    assert result.by_session[0].key == "Unknown"
    assert result.by_setup[0].key == "Unknown"


def test_breakdown_by_weekday_is_sorted_monday_to_sunday_not_by_count():
    # Build one trade per day across a full week and confirm the returned order is
    # calendar order, regardless of how many trades land on each day.
    dates = ["2026-07-06", "2026-07-07", "2026-07-08", "2026-07-09", "2026-07-10", "2026-07-11", "2026-07-12"]
    trades = [
        closed_trade(f"t{i}", "won", 100, f"{d}T10:00:00+00:00")
        for i, d in enumerate(dates)
    ]
    # Give Sunday's day two extra trades so a count-based sort would move it to the front.
    sunday = next(d for d in dates if datetime.fromisoformat(d).weekday() == 6)
    trades.append(closed_trade("extra1", "won", 50, f"{sunday}T11:00:00+00:00"))
    trades.append(closed_trade("extra2", "won", 50, f"{sunday}T12:00:00+00:00"))

    result = compute_breakdown(trades)
    keys = [g.key for g in result.by_weekday]
    assert keys == ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
