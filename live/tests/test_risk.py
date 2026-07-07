"""
Unit tests for atlas/risk.py::compute_risk_snapshot - pure function, no I/O, so these
drive it directly with hand-built trade dicts rather than going through the webhook or
a repository. See atlas/risk.py's module docstring for the scope this is testing:
display-only risk numbers derived purely from this account's own realized_pnl history.
"""
from atlas.risk import compute_risk_snapshot

TODAY = "2026-07-07"
YESTERDAY = "2026-07-06"

BASE_KWARGS = dict(
    starting_balance=50_000.0,
    daily_loss_limit=1_000.0,
    trailing_drawdown_limit=2_000.0,
    max_contracts=5,
    point_value=2.0,
    account_configured=True,
    today=TODAY,
)


def closed_trade(correlation_id, status, realized_pnl, closed_at=f"{TODAY}T12:00:00+00:00"):
    return {
        "correlation_id": correlation_id, "status": status, "realized_pnl": realized_pnl,
        "closed_at": closed_at, "direction": "long", "entry_price": None, "sl": None, "tp": None,
        "quantity": None, "current_price": None, "unrealized_pnl": None,
    }


def open_trade(correlation_id="corr-open", direction="long", entry_price=100.0, sl=90.0, tp=130.0,
                quantity=3, current_price=110.0, unrealized_pnl=30.0):
    return {
        "correlation_id": correlation_id, "status": "open", "realized_pnl": None, "closed_at": None,
        "direction": direction, "entry_price": entry_price, "sl": sl, "tp": tp, "quantity": quantity,
        "current_price": current_price, "unrealized_pnl": unrealized_pnl,
    }


def test_no_trades_starts_flat_at_starting_balance():
    snap = compute_risk_snapshot([], **BASE_KWARGS)

    assert snap.current_balance == 50_000.0
    assert snap.high_water_mark == 50_000.0
    assert snap.daily_realized_pnl == 0
    assert snap.daily_loss_used == 0
    assert snap.daily_loss_remaining == 1_000.0
    assert snap.daily_loss_limit_breached is False
    assert snap.trailing_stop_balance == 48_000.0
    assert snap.remaining_drawdown == 2_000.0
    assert snap.trailing_drawdown_breached is False
    assert snap.open_position is None
    assert snap.kill_switch.should_trigger is False
    assert snap.kill_switch.enforced is False  # display only, always
    assert snap.account_configured is True


def test_winning_trades_raise_balance_and_high_water_mark():
    trades = [
        closed_trade("a", "won", 500),
        closed_trade("b", "won", 300),
    ]
    snap = compute_risk_snapshot(trades, **BASE_KWARGS)

    assert snap.current_balance == 50_800.0
    assert snap.high_water_mark == 50_800.0
    assert snap.daily_realized_pnl == 800.0


def test_daily_loss_limit_breach_is_detected():
    trades = [closed_trade("a", "lost", -1_200)]
    snap = compute_risk_snapshot(trades, **BASE_KWARGS)

    assert snap.daily_loss_used == 1_200.0
    assert snap.daily_loss_remaining == 0.0  # floored at 0, not negative
    assert snap.daily_loss_limit_breached is True
    assert any("Daily loss limit" in r for r in snap.kill_switch.reasons)
    assert snap.kill_switch.should_trigger is True
    assert snap.kill_switch.enforced is False  # still never enforced


def test_losses_on_a_prior_day_do_not_count_toward_todays_daily_loss():
    trades = [closed_trade("a", "lost", -1_200, closed_at=f"{YESTERDAY}T12:00:00+00:00")]
    snap = compute_risk_snapshot(trades, **BASE_KWARGS)

    assert snap.daily_realized_pnl == 0
    assert snap.daily_loss_limit_breached is False
    # but the prior loss is still reflected in the running balance/high-water mark
    assert snap.current_balance == 48_800.0


def test_trailing_drawdown_breach_after_a_peak_and_a_pullback():
    trades = [
        closed_trade("a", "won", 3_000, closed_at=f"{YESTERDAY}T10:00:00+00:00"),   # balance 53,000, new peak
        closed_trade("b", "lost", -1_500, closed_at=f"{TODAY}T09:00:00+00:00"),      # balance 51,500
        closed_trade("c", "lost", -1_600, closed_at=f"{TODAY}T11:00:00+00:00"),      # balance 49,900
    ]
    snap = compute_risk_snapshot(trades, **BASE_KWARGS)

    assert snap.high_water_mark == 53_000.0
    assert snap.current_balance == 49_900.0
    assert snap.trailing_stop_balance == 51_000.0  # 53,000 - 2,000
    assert snap.remaining_drawdown == -1_100.0  # already past the trailing stop
    assert snap.trailing_drawdown_breached is True
    assert any("Trailing drawdown" in r for r in snap.kill_switch.reasons)


def test_open_position_risk_reward_for_long():
    snap = compute_risk_snapshot(
        [open_trade(direction="long", entry_price=100, sl=90, tp=130, quantity=3)], **BASE_KWARGS
    )
    pos = snap.open_position
    assert pos is not None
    assert pos.risk_points == 10
    assert pos.reward_points == 30
    assert pos.risk_dollars == 60.0   # 10 pts * 3 contracts * $2/pt
    assert pos.reward_dollars == 180.0
    assert pos.exposure_contracts == 3
    assert pos.exposure_pct_of_max == 60.0  # 3 of 5 max
    assert pos.exceeds_max_contracts is False


def test_open_position_risk_reward_for_short():
    snap = compute_risk_snapshot(
        [open_trade(direction="short", entry_price=100, sl=110, tp=70, quantity=2)], **BASE_KWARGS
    )
    pos = snap.open_position
    assert pos.risk_points == 10
    assert pos.reward_points == 30
    assert pos.risk_dollars == 40.0
    assert pos.reward_dollars == 120.0


def test_open_position_with_unknown_quantity_has_no_dollar_figures_but_no_crash():
    snap = compute_risk_snapshot([open_trade(quantity=None)], **BASE_KWARGS)
    pos = snap.open_position
    assert pos.quantity is None
    assert pos.risk_dollars is None
    assert pos.reward_dollars is None
    assert pos.exposure_pct_of_max is None
    assert pos.exceeds_max_contracts is False


def test_open_position_exceeding_max_contracts_is_flagged():
    snap = compute_risk_snapshot([open_trade(quantity=8)], **BASE_KWARGS)
    assert snap.open_position.exceeds_max_contracts is True


def test_account_configured_flag_passes_through():
    snap = compute_risk_snapshot([], **{**BASE_KWARGS, "account_configured": False})
    assert snap.account_configured is False
