"""
AI Copilot orchestration (Sprint 6): entry scoring, post-trade review, and
daily/weekly report generation. Every function here is a background task - scheduled
via FastAPI's BackgroundTasks from atlas/api/v1/webhook.py (entry score, post-trade
review) or atlas/api/v1/ai.py (reports), never awaited on any response-critical path.

This is the one rule this whole module exists to prove by construction, not just by
convention: atlas/api/v1/webhook.py never awaits anything in this module directly -
it only ever does `background_tasks.add_task(run_..., ...)`, which schedules the call
to run *after* the HTTP response is already being sent. A slow or failing Claude call
can never delay a webhook response, and definitely never touches the PickMyTrade
relay call, which happens entirely before any of these are even scheduled.

Every function is defensive at the outermost level (try/except around both the Claude
call and the DB write) so nothing here can ever propagate into the background task
runner or surface as an error to whatever scheduled it - commentary and reports are
advisory only.
"""
import asyncio
import logging
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from typing import Any

from atlas.analytics import compute_breakdown, compute_summary
from atlas.config import settings
from atlas.events import types as event_types
from atlas.events.bus import EventBus
from atlas.intelligence import compute_intelligence_snapshot
from atlas.repositories.base import TradeRepository
from atlas.services.claude import (
    analyze_with_claude,
    build_intelligence_prompt,
    build_post_trade_review_prompt,
    build_report_prompt,
)

logger = logging.getLogger("atlas.ai")

HISTORY_SCAN_LIMIT = 2000


async def run_entry_score(
    payload: dict[str, Any], correlation_id: str, repository: TradeRepository, event_bus: EventBus,
) -> None:
    """Sprint 7: structured output first, narrative second. The confidence score,
    expected R, and historical win rate are computed deterministically by
    atlas/intelligence.py from past trades BEFORE Claude is ever involved - Claude is
    only asked to explain those already-computed numbers (see
    build_intelligence_prompt), never to produce the score itself. When there's no
    historical precedent at all (similar_trade_count == 0), Claude isn't called -
    there is nothing yet for it to explain."""
    trades = await repository.list_recent(limit=HISTORY_SCAN_LIMIT)
    snapshot = compute_intelligence_snapshot(payload, trades, point_value=settings.account_point_value)

    if snapshot.similar_trade_count == 0:
        try:
            await repository.add_ai_note(
                trade_correlation_id=correlation_id,
                note_type="entry_score",
                model=None,
                content=(
                    "No historical trades with this direction and setup tag yet, so there's nothing to "
                    "compare this entry against. Confidence becomes available once similar trades close."
                ),
                error=None,
                score=None,
                score_label=snapshot.confidence_label,
                expected_r=None,
                historical_win_rate_pct=None,
                similar_trade_count=0,
                factors=None,
            )
        except Exception:
            pass
        await event_bus.publish(event_types.AI_ENTRY_SCORED, {
            "correlation_id": correlation_id, "ok": True, "score": None, "error": None,
        })
        return

    prompt = build_intelligence_prompt(
        payload, snapshot.summary, snapshot.confidence_score, snapshot.confidence_label, snapshot.factors,
    )
    try:
        text, error = await asyncio.to_thread(analyze_with_claude, prompt)
    except Exception as e:
        text, error = None, str(e)

    try:
        await repository.add_ai_note(
            trade_correlation_id=correlation_id,
            note_type="entry_score",
            model=settings.claude_model if text else None,
            content=text,
            error=error,
            score=snapshot.confidence_score,
            score_label=snapshot.confidence_label,
            expected_r=snapshot.summary.avg_r,
            historical_win_rate_pct=snapshot.summary.win_rate_pct,
            similar_trade_count=snapshot.similar_trade_count,
            factors=[asdict(f) for f in snapshot.factors],
        )
    except Exception:
        pass  # commentary only - a DB hiccup here must never surface as an error

    await event_bus.publish(event_types.AI_ENTRY_SCORED, {
        "correlation_id": correlation_id, "ok": error is None, "score": snapshot.confidence_score, "error": error,
    })


async def run_post_trade_review(correlation_id: str, repository: TradeRepository, event_bus: EventBus) -> None:
    """Fetches the trade itself (rather than being handed the exit payload) because a
    useful review needs the full picture - entry conditions *and* the outcome - which
    only exists in the stored row once the exit update has already committed."""
    trade = await repository.get_by_correlation_id(correlation_id)
    if trade is None:
        return  # the caller only schedules this after a matched exit, but never crash a background task over it

    try:
        text, error = await asyncio.to_thread(analyze_with_claude, build_post_trade_review_prompt(trade))
    except Exception as e:
        text, error = None, str(e)

    try:
        await repository.add_ai_note(
            trade_correlation_id=correlation_id,
            note_type="post_trade_review",
            model=settings.claude_model if text else None,
            content=text,
            error=error,
        )
    except Exception:
        pass

    await event_bus.publish(event_types.AI_TRADE_REVIEWED, {
        "correlation_id": correlation_id, "ok": error is None, "error": error,
    })


def _period_start_iso(period: str) -> str:
    now = datetime.now(timezone.utc)
    if period == "daily":
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        start = now - timedelta(days=7)
    return start.isoformat(timespec="seconds")


async def run_report_generation(period: str, repository: TradeRepository, event_bus: EventBus) -> None:
    """Not on any order-execution path at all - there is no webhook involvement here.
    Still async/background (scheduled from POST /api/v1/ai/reports/{period}, see
    atlas/api/v1/ai.py) for the same reason every AI call in this system is: a report
    call can take a few seconds, and the HTTP client triggering it shouldn't have to
    hold a connection open waiting for it."""
    trades = await repository.list_recent(limit=HISTORY_SCAN_LIMIT)
    since = _period_start_iso(period)
    period_trades = [t for t in trades if t.get("closed_at") and t["closed_at"] >= since]

    summary = compute_summary(period_trades, point_value=settings.account_point_value)
    breakdown = compute_breakdown(period_trades)

    try:
        text, error = await asyncio.to_thread(
            analyze_with_claude, build_report_prompt(period, summary, breakdown)
        )
    except Exception as e:
        text, error = None, str(e)

    try:
        await repository.add_ai_note(
            trade_correlation_id=None,
            note_type=f"{period}_report",
            model=settings.claude_model if text else None,
            content=text,
            error=error,
        )
    except Exception:
        pass

    await event_bus.publish(event_types.AI_REPORT_GENERATED, {
        "period": period, "ok": error is None, "error": error, "trade_count": summary.total_trades,
    })
