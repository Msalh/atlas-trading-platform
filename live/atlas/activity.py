"""
Pure aggregation of existing trade/AI/risk/status data into a single chronological
list of ActivityEvent objects for the frontend's Activity Center - see
atlas/api/v1/activity.py for the fetch-and-serialize wrapper. Visibility only: this
reads data that atlas/risk.py, atlas/status.py, and the trades/ai_notes tables already
expose through their own read endpoints; it doesn't add persistence, doesn't touch the
webhook/relay path, and computing it can never affect order execution.

Phase 1 scope, stated plainly because it shapes what this can and can't show:
  - Trading/AI events are derived from real per-row timestamps (trades.received_at/
    closed_at, ai_notes.created_at), so trade and AI/analytics activity is a genuine
    history, most-recent first.
  - Risk events are NOT a history - atlas/risk.py's RiskSnapshot is a point-in-time
    computed view with no persisted "when did this breach happen" record (see that
    module's own docstring). Risk events here are synthesized at request time from the
    *current* snapshot only, timestamped "now" - a limit that was breached and later
    recovered won't show as a past event.
  - System events are similarly current-state, not history - atlas/status.py's
    SystemStatus only tracks the most recent occurrence of each event type per
    process, so at most one PickMyTrade/Claude/database event can appear here, not
    every failure that ever happened, and it resets on every deploy/restart.
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from atlas.risk import RiskSnapshot

CATEGORY_TRADING = "trading"
CATEGORY_AI = "ai"
CATEGORY_RISK = "risk"
CATEGORY_ANALYTICS = "analytics"
CATEGORY_SYSTEM = "system"

SEVERITY_INFO = "info"
SEVERITY_SUCCESS = "success"
SEVERITY_WARNING = "warning"
SEVERITY_CRITICAL = "critical"

# daily_report/weekly_report notes are categorized as Analytics, not AI: their content
# is a period performance summary, not per-trade AI reasoning - entry_score and
# post_trade_review are the ones that represent the AI actually reasoning about a
# specific trade, so those stay under AI.
TRADE_NOTE_TYPES = {"entry_score", "post_trade_review"}
REPORT_NOTE_TYPES = {"daily_report", "weekly_report"}


@dataclass
class ActivityEvent:
    id: str
    timestamp: str
    category: str
    severity: str
    title: str
    description: Optional[str]
    correlation_id: Optional[str]


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _trade_events(trades: list[dict[str, Any]]) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    for t in trades:
        corr = t["correlation_id"]
        direction_label = (t.get("direction") or "trade").title()
        symbol = t.get("symbol") or t.get("setup_tag") or corr

        if t.get("received_at"):
            events.append(ActivityEvent(
                id=f"trade-entry-{corr}",
                timestamp=t["received_at"],
                category=CATEGORY_TRADING,
                severity=SEVERITY_INFO,
                title=f"{direction_label} entry received — {symbol}",
                description=(
                    f"Entry {t['entry_price']}, SL {t['sl']}, TP {t['tp']}"
                    if t.get("entry_price") is not None else None
                ),
                correlation_id=corr,
            ))
            if not t.get("pmt_forwarded") and t.get("pmt_error"):
                events.append(ActivityEvent(
                    id=f"trade-pmt-failed-{corr}",
                    timestamp=t["received_at"],
                    category=CATEGORY_TRADING,
                    severity=SEVERITY_CRITICAL,
                    title="PickMyTrade forward failed",
                    description=t.get("pmt_error"),
                    correlation_id=corr,
                ))

        if t.get("closed_at") and t.get("status") in ("won", "lost"):
            won = t["status"] == "won"
            pnl = t.get("realized_pnl")
            events.append(ActivityEvent(
                id=f"trade-exit-{corr}",
                timestamp=t["closed_at"],
                category=CATEGORY_TRADING,
                severity=SEVERITY_SUCCESS if won else SEVERITY_WARNING,
                title=f"Trade closed — {'WIN' if won else 'LOSS'}",
                description=f"Realized PnL {pnl:+.2f}" if pnl is not None else None,
                correlation_id=corr,
            ))
    return events


def _entry_score_title(note: dict[str, Any]) -> str:
    if note.get("error"):
        return "AI entry scoring failed"
    if note.get("score") is not None:
        label = f" ({note['score_label']})" if note.get("score_label") else ""
        return f"AI entry score {note['score']}/10{label}"
    return "AI entry score generated"


def _ai_events(ai_notes: list[dict[str, Any]]) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    for n in ai_notes:
        note_type = n["note_type"]
        failed = bool(n.get("error"))

        if note_type in TRADE_NOTE_TYPES:
            category = CATEGORY_AI
            if note_type == "entry_score":
                title = _entry_score_title(n)
            else:
                title = "AI post-trade review failed" if failed else "AI post-trade review generated"
        elif note_type in REPORT_NOTE_TYPES:
            category = CATEGORY_ANALYTICS
            period_label = "daily" if note_type == "daily_report" else "weekly"
            title = f"AI {period_label} report {'failed' if failed else 'generated'}"
        else:
            continue

        events.append(ActivityEvent(
            id=f"ai-note-{n['id']}",
            timestamp=n["created_at"],
            category=category,
            severity=SEVERITY_WARNING if failed else SEVERITY_INFO,
            title=title,
            description=n.get("error") or n.get("content"),
            correlation_id=n.get("trade_correlation_id"),
        ))
    return events


def _risk_events(snapshot: RiskSnapshot) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    now = _now_iso()

    for i, reason in enumerate(snapshot.kill_switch.reasons):
        events.append(ActivityEvent(
            id=f"risk-breach-{i}",
            timestamp=now,
            category=CATEGORY_RISK,
            severity=SEVERITY_CRITICAL,
            title="Risk limit breached",
            description=reason,
            correlation_id=None,
        ))

    pos = snapshot.open_position
    if pos is not None and pos.exceeds_max_contracts:
        pct = f" ({pos.exposure_pct_of_max:.0f}% of limit)" if pos.exposure_pct_of_max is not None else ""
        events.append(ActivityEvent(
            id="risk-exceeds-max-contracts",
            timestamp=now,
            category=CATEGORY_RISK,
            severity=SEVERITY_WARNING,
            title="Open position exceeds max contract limit",
            description=f"{pos.exposure_contracts} contracts vs. {snapshot.max_contracts} max{pct}",
            correlation_id=pos.correlation_id,
        ))
    return events


def _system_events(
    *,
    database_ok: bool,
    database_detail: str,
    pmt_configured: bool,
    pmt_last_error: Optional[str],
    pmt_last_forward_at: Optional[str],
    claude_configured: bool,
    claude_last_error: Optional[str],
    claude_last_at: Optional[str],
) -> list[ActivityEvent]:
    events: list[ActivityEvent] = []
    now = _now_iso()

    if not database_ok:
        events.append(ActivityEvent(
            id="system-database",
            timestamp=now,
            category=CATEGORY_SYSTEM,
            severity=SEVERITY_CRITICAL,
            title="Database connectivity issue",
            description=database_detail,
            correlation_id=None,
        ))
    if pmt_configured and pmt_last_error:
        events.append(ActivityEvent(
            id="system-pickmytrade",
            timestamp=pmt_last_forward_at or now,
            category=CATEGORY_SYSTEM,
            severity=SEVERITY_WARNING,
            title="PickMyTrade relay error",
            description=pmt_last_error,
            correlation_id=None,
        ))
    if claude_configured and claude_last_error:
        events.append(ActivityEvent(
            id="system-claude",
            timestamp=claude_last_at or now,
            category=CATEGORY_SYSTEM,
            severity=SEVERITY_WARNING,
            title="Claude AI error",
            description=claude_last_error,
            correlation_id=None,
        ))
    return events


def build_activity_feed(
    *,
    trades: list[dict[str, Any]],
    ai_notes: list[dict[str, Any]],
    risk_snapshot: RiskSnapshot,
    database_ok: bool,
    database_detail: str,
    pmt_configured: bool,
    pmt_last_error: Optional[str],
    pmt_last_forward_at: Optional[str],
    claude_configured: bool,
    claude_last_error: Optional[str],
    claude_last_at: Optional[str],
    limit: int = 200,
) -> list[ActivityEvent]:
    events = (
        _trade_events(trades)
        + _ai_events(ai_notes)
        + _risk_events(risk_snapshot)
        + _system_events(
            database_ok=database_ok,
            database_detail=database_detail,
            pmt_configured=pmt_configured,
            pmt_last_error=pmt_last_error,
            pmt_last_forward_at=pmt_last_forward_at,
            claude_configured=claude_configured,
            claude_last_error=claude_last_error,
            claude_last_at=claude_last_at,
        )
    )
    events.sort(key=lambda e: e.timestamp, reverse=True)
    return events[:limit]
