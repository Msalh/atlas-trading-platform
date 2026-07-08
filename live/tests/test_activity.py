"""
Unit tests for atlas/activity.py::build_activity_feed - pure function, no I/O, so
these drive it directly with hand-built trade/ai_note dicts and a RiskSnapshot rather
than going through the webhook or a repository. See atlas/activity.py's module
docstring for what each category can and can't show in Phase 1.
"""
from atlas.activity import build_activity_feed
from atlas.risk import KillSwitchStatus, OpenPositionRisk, RiskSnapshot

NO_BREACH_SNAPSHOT = RiskSnapshot(
    account_configured=True,
    starting_balance=50_000.0,
    current_balance=50_000.0,
    high_water_mark=50_000.0,
    daily_loss_limit=1_000.0,
    daily_realized_pnl=0.0,
    daily_loss_used=0.0,
    daily_loss_remaining=1_000.0,
    daily_loss_limit_breached=False,
    trailing_drawdown_limit=2_000.0,
    trailing_stop_balance=48_000.0,
    remaining_drawdown=2_000.0,
    trailing_drawdown_breached=False,
    max_contracts=5,
    point_value=2.0,
    open_position=None,
    kill_switch=KillSwitchStatus(should_trigger=False, reasons=[]),
)

BASE_SYSTEM_KWARGS = dict(
    database_ok=True,
    database_detail="ok",
    pmt_configured=False,
    pmt_last_error=None,
    pmt_last_forward_at=None,
    claude_configured=False,
    claude_last_error=None,
    claude_last_at=None,
)


def open_trade(correlation_id="corr-open", **overrides):
    trade = {
        "correlation_id": correlation_id, "status": "open", "direction": "long", "symbol": "MNQU6",
        "setup_tag": "BRK", "entry_price": 30000.0, "sl": 29950.0, "tp": 30050.0,
        "received_at": "2026-07-07T17:35:00+00:00", "closed_at": None, "realized_pnl": None,
        "pmt_forwarded": True, "pmt_error": None,
    }
    trade.update(overrides)
    return trade


def closed_trade(correlation_id="corr-closed", status="won", realized_pnl=500.0, **overrides):
    trade = open_trade(
        correlation_id=correlation_id, status=status, realized_pnl=realized_pnl,
        closed_at="2026-07-07T18:00:00+00:00",
    )
    trade.update(overrides)
    return trade


def test_empty_inputs_produce_no_events():
    events = build_activity_feed(
        trades=[], ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert events == []


def test_trade_entry_produces_info_event_linked_to_trade():
    events = build_activity_feed(
        trades=[open_trade()], ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert len(events) == 1
    assert events[0].category == "trading"
    assert events[0].severity == "info"
    assert events[0].correlation_id == "corr-open"


def test_pmt_forward_failure_produces_critical_trading_event():
    trade = open_trade(pmt_forwarded=False, pmt_error="connection refused")
    events = build_activity_feed(
        trades=[trade], ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    failure_events = [e for e in events if e.title == "PickMyTrade forward failed"]
    assert len(failure_events) == 1
    assert failure_events[0].severity == "critical"
    assert failure_events[0].description == "connection refused"


def test_won_trade_exit_is_success_lost_trade_exit_is_warning():
    events = build_activity_feed(
        trades=[
            closed_trade(status="won", realized_pnl=500.0),
            closed_trade(correlation_id="corr-lost", status="lost", realized_pnl=-300.0),
        ],
        ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    won_exit = next(e for e in events if e.correlation_id == "corr-closed" and "Trade closed" in e.title)
    lost_exit = next(e for e in events if e.correlation_id == "corr-lost" and "Trade closed" in e.title)
    assert won_exit.severity == "success"
    assert lost_exit.severity == "warning"


def test_entry_score_and_post_trade_review_are_ai_category():
    notes = [
        {"id": 1, "trade_correlation_id": "corr-open", "note_type": "entry_score",
         "created_at": "2026-07-07T17:36:00+00:00", "score": 8, "score_label": "strong",
         "content": "Good setup.", "error": None},
        {"id": 2, "trade_correlation_id": "corr-open", "note_type": "post_trade_review",
         "created_at": "2026-07-07T18:01:00+00:00", "content": "Held to target.", "error": None},
    ]
    events = build_activity_feed(
        trades=[], ai_notes=notes, risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert all(e.category == "ai" for e in events)
    entry_score_event = next(e for e in events if e.id == "ai-note-1")
    assert entry_score_event.title == "AI entry score 8/10 (strong)"
    assert entry_score_event.severity == "info"


def test_ai_note_error_is_warning_severity():
    notes = [{
        "id": 1, "trade_correlation_id": "corr-open", "note_type": "entry_score",
        "created_at": "2026-07-07T17:36:00+00:00", "score": None, "score_label": None,
        "content": None, "error": "Claude timed out",
    }]
    events = build_activity_feed(
        trades=[], ai_notes=notes, risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert events[0].severity == "warning"
    assert events[0].title == "AI entry scoring failed"


def test_daily_and_weekly_reports_are_analytics_category_not_ai():
    notes = [
        {"id": 1, "trade_correlation_id": None, "note_type": "daily_report",
         "created_at": "2026-07-07T20:00:00+00:00", "content": "Solid day.", "error": None,
         "score": None, "score_label": None},
        {"id": 2, "trade_correlation_id": None, "note_type": "weekly_report",
         "created_at": "2026-07-07T21:00:00+00:00", "content": "Solid week.", "error": None,
         "score": None, "score_label": None},
    ]
    events = build_activity_feed(
        trades=[], ai_notes=notes, risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert all(e.category == "analytics" for e in events)
    assert all(e.correlation_id is None for e in events)


def test_kill_switch_reasons_become_critical_risk_events():
    breached = RiskSnapshot(
        account_configured=True, starting_balance=50_000.0, current_balance=47_000.0,
        high_water_mark=50_000.0,
        daily_loss_limit=1_000.0, daily_realized_pnl=-1_200.0, daily_loss_used=1_200.0,
        daily_loss_remaining=0.0, daily_loss_limit_breached=True,
        trailing_drawdown_limit=2_000.0, trailing_stop_balance=48_000.0, remaining_drawdown=-1_000.0,
        trailing_drawdown_breached=True,
        max_contracts=5, point_value=2.0, open_position=None,
        kill_switch=KillSwitchStatus(
            should_trigger=True,
            reasons=["Daily loss limit reached: $1,200.00 of $1,000.00", "Trailing drawdown breached"],
        ),
    )
    events = build_activity_feed(
        trades=[], ai_notes=[], risk_snapshot=breached, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert len(events) == 2
    assert all(e.category == "risk" and e.severity == "critical" for e in events)


def test_open_position_exceeding_max_contracts_is_warning_risk_event():
    pos = OpenPositionRisk(
        correlation_id="corr-open", direction="long", quantity=10, entry_price=30000.0, sl=29950.0,
        tp=30050.0, current_price=30010.0, unrealized_pnl=100.0, risk_points=50.0, reward_points=50.0,
        risk_dollars=1000.0, reward_dollars=1000.0, exposure_contracts=10, exposure_pct_of_max=200.0,
        exceeds_max_contracts=True,
    )
    snapshot = RiskSnapshot(
        account_configured=True, starting_balance=50_000.0, current_balance=50_000.0,
        high_water_mark=50_000.0,
        daily_loss_limit=1_000.0, daily_realized_pnl=0.0, daily_loss_used=0.0,
        daily_loss_remaining=1_000.0, daily_loss_limit_breached=False,
        trailing_drawdown_limit=2_000.0, trailing_stop_balance=48_000.0, remaining_drawdown=2_000.0,
        trailing_drawdown_breached=False,
        max_contracts=5, point_value=2.0, open_position=pos,
        kill_switch=KillSwitchStatus(should_trigger=False, reasons=[]),
    )
    events = build_activity_feed(
        trades=[], ai_notes=[], risk_snapshot=snapshot, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert len(events) == 1
    assert events[0].category == "risk"
    assert events[0].severity == "warning"
    assert events[0].correlation_id == "corr-open"


def test_database_down_is_critical_system_event():
    events = build_activity_feed(
        trades=[], ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200,
        database_ok=False, database_detail="error: connection refused",
        pmt_configured=False, pmt_last_error=None, pmt_last_forward_at=None,
        claude_configured=False, claude_last_error=None, claude_last_at=None,
    )
    assert len(events) == 1
    assert events[0].category == "system"
    assert events[0].severity == "critical"


def test_pmt_and_claude_errors_are_warning_system_events():
    events = build_activity_feed(
        trades=[], ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200,
        database_ok=True, database_detail="ok",
        pmt_configured=True, pmt_last_error="502 from PickMyTrade",
        pmt_last_forward_at="2026-07-07T17:35:05+00:00",
        claude_configured=True, claude_last_error="rate limited",
        claude_last_at="2026-07-07T17:36:10+00:00",
    )
    assert len(events) == 2
    assert all(e.category == "system" and e.severity == "warning" for e in events)


def test_pmt_and_claude_errors_ignored_when_not_configured():
    events = build_activity_feed(
        trades=[], ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200,
        database_ok=True, database_detail="ok",
        pmt_configured=False, pmt_last_error="502 from PickMyTrade", pmt_last_forward_at=None,
        claude_configured=False, claude_last_error="rate limited", claude_last_at=None,
    )
    assert events == []


def test_events_sorted_most_recent_first():
    trades = [
        open_trade(correlation_id="corr-1", received_at="2026-07-01T10:00:00+00:00"),
        open_trade(correlation_id="corr-2", received_at="2026-07-05T10:00:00+00:00"),
    ]
    events = build_activity_feed(
        trades=trades, ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=200, **BASE_SYSTEM_KWARGS,
    )
    assert [e.correlation_id for e in events] == ["corr-2", "corr-1"]


def test_limit_caps_total_events():
    trades = [
        open_trade(correlation_id=f"corr-{i}", received_at=f"2026-07-01T10:{i:02d}:00+00:00")
        for i in range(10)
    ]
    events = build_activity_feed(
        trades=trades, ai_notes=[], risk_snapshot=NO_BREACH_SNAPSHOT, limit=3, **BASE_SYSTEM_KWARGS,
    )
    assert len(events) == 3
