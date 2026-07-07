"""
Pure risk computation over a list of trade rows - no I/O, no FastAPI, no database. Kept
separate from atlas/api/v1/risk.py (which only fetches trades and calls
compute_risk_snapshot) so the actual math is unit-testable in isolation, the same
pattern atlas/api/v1/trades.py::build_timeline already established.

Scope for Sprint 4, stated plainly because it matters for a real funded account:
  - This is DISPLAY ONLY. Nothing here blocks order execution or enforces anything -
    the webhook/relay path in atlas/api/v1/webhook.py is completely untouched.
    `KillSwitchStatus.enforced` is hardcoded False for exactly this reason.
  - "Current balance" and "high-water mark" are derived purely from this account's own
    realized_pnl history (starting_balance + running sum of closed trades, in the
    order they closed) - not from a real broker/prop-firm balance feed, which doesn't
    exist yet. If the account's actual broker balance ever diverges from this
    (deposits, fees, other activity outside this bot), this will be wrong until that
    integration exists.
  - "Today" is the UTC calendar day, matching the same simplification stats.py already
    made and documented in Sprint 2.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional


@dataclass
class OpenPositionRisk:
    correlation_id: str
    direction: Optional[str]
    quantity: Optional[int]
    entry_price: Optional[float]
    sl: Optional[float]
    tp: Optional[float]
    current_price: Optional[float]
    unrealized_pnl: Optional[float]
    risk_points: Optional[float]
    reward_points: Optional[float]
    risk_dollars: Optional[float]
    reward_dollars: Optional[float]
    exposure_contracts: Optional[int]
    exposure_pct_of_max: Optional[float]
    exceeds_max_contracts: bool


@dataclass
class KillSwitchStatus:
    should_trigger: bool
    reasons: list[str]
    enforced: bool = False  # Sprint 4 is display-only, by design - see module docstring


@dataclass
class RiskSnapshot:
    account_configured: bool
    starting_balance: float
    current_balance: float
    high_water_mark: float

    daily_loss_limit: float
    daily_realized_pnl: float
    daily_loss_used: float
    daily_loss_remaining: float
    daily_loss_limit_breached: bool

    trailing_drawdown_limit: float
    trailing_stop_balance: float
    remaining_drawdown: float
    trailing_drawdown_breached: bool

    max_contracts: int
    point_value: float

    open_position: Optional[OpenPositionRisk]
    kill_switch: KillSwitchStatus


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def risk_reward_points(direction: Optional[str], entry: Optional[float], sl: Optional[float], tp: Optional[float]):
    """Public (not module-private) because atlas/analytics.py also needs it for
    per-trade R-multiple calculations - one shared implementation of "risk/reward in
    points for a direction+entry+sl+tp", not two copies that could drift."""
    if entry is None or sl is None or tp is None:
        return None, None
    if direction == "long":
        return entry - sl, tp - entry
    if direction == "short":
        return sl - entry, entry - tp
    return None, None


def _build_open_position_risk(trade: dict[str, Any], max_contracts: int, point_value: float) -> OpenPositionRisk:
    risk_points, reward_points = risk_reward_points(
        trade.get("direction"), trade.get("entry_price"), trade.get("sl"), trade.get("tp")
    )
    quantity = trade.get("quantity")

    risk_dollars = risk_points * quantity * point_value if risk_points is not None and quantity is not None else None
    reward_dollars = (
        reward_points * quantity * point_value if reward_points is not None and quantity is not None else None
    )
    exposure_pct_of_max = (quantity / max_contracts * 100) if quantity is not None and max_contracts > 0 else None
    exceeds_max_contracts = quantity is not None and quantity > max_contracts

    return OpenPositionRisk(
        correlation_id=trade["correlation_id"],
        direction=trade.get("direction"),
        quantity=quantity,
        entry_price=trade.get("entry_price"),
        sl=trade.get("sl"),
        tp=trade.get("tp"),
        current_price=trade.get("current_price"),
        unrealized_pnl=trade.get("unrealized_pnl"),
        risk_points=risk_points,
        reward_points=reward_points,
        risk_dollars=risk_dollars,
        reward_dollars=reward_dollars,
        exposure_contracts=quantity,
        exposure_pct_of_max=exposure_pct_of_max,
        exceeds_max_contracts=exceeds_max_contracts,
    )


def compute_risk_snapshot(
    trades: list[dict[str, Any]],
    *,
    starting_balance: float,
    daily_loss_limit: float,
    trailing_drawdown_limit: float,
    max_contracts: int,
    point_value: float,
    account_configured: bool,
    today: Optional[str] = None,
) -> RiskSnapshot:
    today = today or _today_utc()

    closed_trades = [t for t in trades if t["status"] in ("won", "lost") and t.get("closed_at")]
    closed_trades.sort(key=lambda t: t["closed_at"])

    balance = starting_balance
    high_water_mark = starting_balance
    for t in closed_trades:
        balance += t.get("realized_pnl") or 0
        high_water_mark = max(high_water_mark, balance)
    current_balance = balance

    daily_realized_pnl = sum(
        t.get("realized_pnl") or 0 for t in closed_trades if t["closed_at"].startswith(today)
    )
    daily_loss_used = max(0.0, -daily_realized_pnl)
    daily_loss_remaining = max(0.0, daily_loss_limit - daily_loss_used)
    daily_loss_limit_breached = daily_loss_limit > 0 and daily_loss_used >= daily_loss_limit

    trailing_stop_balance = high_water_mark - trailing_drawdown_limit
    remaining_drawdown = current_balance - trailing_stop_balance
    trailing_drawdown_breached = current_balance <= trailing_stop_balance

    open_trade = next((t for t in trades if t["status"] == "open"), None)
    open_position = (
        _build_open_position_risk(open_trade, max_contracts, point_value) if open_trade else None
    )

    reasons = []
    if daily_loss_limit_breached:
        reasons.append(f"Daily loss limit reached: ${daily_loss_used:,.2f} of ${daily_loss_limit:,.2f}")
    if trailing_drawdown_breached:
        reasons.append(
            f"Trailing drawdown breached: balance ${current_balance:,.2f} at/below "
            f"trailing stop ${trailing_stop_balance:,.2f}"
        )
    kill_switch = KillSwitchStatus(should_trigger=bool(reasons), reasons=reasons)

    return RiskSnapshot(
        account_configured=account_configured,
        starting_balance=starting_balance,
        current_balance=current_balance,
        high_water_mark=high_water_mark,
        daily_loss_limit=daily_loss_limit,
        daily_realized_pnl=daily_realized_pnl,
        daily_loss_used=daily_loss_used,
        daily_loss_remaining=daily_loss_remaining,
        daily_loss_limit_breached=daily_loss_limit_breached,
        trailing_drawdown_limit=trailing_drawdown_limit,
        trailing_stop_balance=trailing_stop_balance,
        remaining_drawdown=remaining_drawdown,
        trailing_drawdown_breached=trailing_drawdown_breached,
        max_contracts=max_contracts,
        point_value=point_value,
        open_position=open_position,
        kill_switch=kill_switch,
    )
