"""
Runs the Atlas API against an in-memory, seeded TradeRepository instead of Postgres -
for frontend development without needing a local/remote database. This is the same
InMemoryTradeRepository the backend's own pytest suite uses as a test double
(atlas/repositories/memory.py), just kept running behind a real HTTP server instead of
being torn down after one test.

Not used in production or in the automated test suite - production always goes through
atlas.main's lifespan and a real Postgres pool. This script builds its own standalone
FastAPI app that reuses the real routers but wires an in-memory repository directly
into app.state (never importing atlas.main, whose lifespan would try to reach a real
Postgres and refuse to start without DATABASE_URL).

Usage:
    python scripts/dev_seed_server.py
Then point the frontend's NEXT_PUBLIC_API_BASE_URL at http://localhost:8000.
"""
import asyncio
import logging
import os
import sys
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import datetime, timedelta, timezone

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas.alerting import ClaudeFailureTracker, alert_on_forward_failure  # noqa: E402
from atlas.api.v1 import ai as ai_router  # noqa: E402
from atlas.api.v1 import activity, analytics, health, risk, status, stats, stream, trades, webhook  # noqa: E402
from atlas.config import settings  # noqa: E402
from atlas.events import types as event_types  # noqa: E402
from atlas.events.bus import EventBus  # noqa: E402
from atlas.events.subscribers import log_event  # noqa: E402
from atlas.events.types import ALL as ALL_EVENT_TYPES  # noqa: E402
from atlas.intelligence import compute_intelligence_snapshot  # noqa: E402
from atlas.repositories.memory import InMemoryTradeRepository  # noqa: E402
from atlas.status import SystemStatus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def _narrative_for(snapshot) -> str:
    """A short templated stand-in for what Claude would say when handed
    build_intelligence_prompt's already-computed numbers - dev seed data never calls
    the real Anthropic API, but the numbers themselves are genuinely computed by
    atlas/intelligence.py from whatever's in the repository at seed time, not typed by
    hand."""
    if snapshot.similar_trade_count == 0:
        return (
            "No historical trades with this direction and setup tag yet, so there's nothing to "
            "compare this entry against. Confidence becomes available once similar trades close."
        )
    factor_bits = ", ".join(
        f"{f.name} {'favorable' if f.favorable else 'unfavorable' if f.favorable is False else 'inconclusive'}"
        for f in snapshot.factors
    )
    expected_r = "n/a" if snapshot.summary.avg_r is None else f"{snapshot.summary.avg_r:.2f}R"
    return (
        f"{snapshot.confidence_label} ({snapshot.confidence_score}/10) from {snapshot.similar_trade_count} "
        f"historically similar trades - {snapshot.summary.win_rate_pct:.0f}% historical win rate, "
        f"{expected_r} expected R. Measurable factors: {factor_bits}."
    )


async def _seed_intelligence_note(
    repository: InMemoryTradeRepository, correlation_id: str, entry: dict, *, simulate_claude_error: str = None,
) -> None:
    """Computes a real IntelligenceSnapshot from whatever's already in the repository
    (see atlas/intelligence.py) and stores it as an entry_score note - the same
    structured-first flow atlas/ai.py::run_entry_score uses in production, just with a
    templated narrative in place of an actual Claude call. `simulate_claude_error`
    demonstrates the case where Claude itself fails: the structured numbers are
    computed and stored regardless, matching production - only the narrative is
    missing, exactly as if analyze_with_claude had returned an error."""
    trades = await repository.list_recent(limit=2000)
    snapshot = compute_intelligence_snapshot(entry, trades, point_value=settings.account_point_value)
    await repository.add_ai_note(
        trade_correlation_id=correlation_id, note_type="entry_score",
        model=None if simulate_claude_error else ("claude-haiku-4-5-20251001" if snapshot.similar_trade_count else None),
        content=None if simulate_claude_error else _narrative_for(snapshot),
        error=simulate_claude_error,
        score=snapshot.confidence_score,
        score_label=snapshot.confidence_label,
        expected_r=snapshot.summary.avg_r if snapshot.similar_trade_count else None,
        historical_win_rate_pct=snapshot.summary.win_rate_pct if snapshot.similar_trade_count else None,
        similar_trade_count=snapshot.similar_trade_count,
        factors=[asdict(f) for f in snapshot.factors] if snapshot.similar_trade_count else None,
    )


async def seed(repository: InMemoryTradeRepository) -> None:
    now = datetime.now(timezone.utc)

    # Historical trades are seeded FIRST so the three demo trades below have real
    # history to compute an IntelligenceSnapshot against - see _seed_intelligence_note.
    await _seed_analytics_history(repository, now)

    # An open long position, forwarded successfully, with a couple of price updates.
    async def forward_ok():
        return True, 200, None

    open_entry = {
        "signal_time": iso(now - timedelta(minutes=18)), "direction": "long", "setup_tag": "BRK",
        "symbol": "MNQU6", "entry_price": 21500.0, "sl": 21460.0, "tp": 21600.0, "atr": 42.5,
        "ema_distance_atr": 0.6, "regime_slope_pct": 1.4, "sweep_age_bars": 4, "session": "NY",
        "quantity": 6,
    }
    await repository.claim_and_forward("seed-open-1", open_entry, raw_body="{}", forward=forward_ok)
    await repository.update_price("seed-open-1", 21538.25, 306.25, iso(now - timedelta(minutes=2)))
    await _seed_intelligence_note(repository, "seed-open-1", {**open_entry, "correlation_id": "seed-open-1"})

    # A winning trade from earlier today.
    won_entry = {
        "signal_time": iso(now - timedelta(hours=3)), "direction": "long", "setup_tag": "RCL",
        "symbol": "MNQU6", "entry_price": 21400.0, "sl": 21360.0, "tp": 21480.0, "atr": 38.0,
        "ema_distance_atr": 0.3, "regime_slope_pct": 1.1, "sweep_age_bars": 2, "session": "London",
        "quantity": 4,
    }
    await repository.claim_and_forward("seed-won-1", won_entry, raw_body="{}", forward=forward_ok)
    await repository.update_exit("seed-won-1", "won", 21480.0, 800.0, iso(now - timedelta(hours=2, minutes=10)))
    await _seed_intelligence_note(repository, "seed-won-1", {**won_entry, "correlation_id": "seed-won-1"})
    await repository.add_ai_note(
        trade_correlation_id="seed-won-1", note_type="post_trade_review", model="claude-haiku-4-5-20251001",
        content="This played out exactly as the entry conditions suggested - a fresh sweep with a "
                "steep regime slope gave this room to run to target without much drawdown along the way. "
                "A well-earned win, not a lucky one.",
        error=None,
    )

    # A losing trade with a PickMyTrade relay failure - the visible-failure case.
    async def forward_fails():
        return False, None, "connection refused"

    lost_entry = {
        "signal_time": iso(now - timedelta(hours=6)), "direction": "short", "setup_tag": "BRK",
        "symbol": "MNQU6", "entry_price": 21550.0, "sl": 21590.0, "tp": 21470.0, "atr": 45.0,
        "ema_distance_atr": 1.8, "regime_slope_pct": 0.4, "sweep_age_bars": 11, "session": "Asia",
        "quantity": 5,
    }
    await repository.claim_and_forward("seed-lost-1", lost_entry, raw_body="{}", forward=forward_fails)
    await repository.update_exit("seed-lost-1", "lost", 21590.0, -400.0, iso(now - timedelta(hours=5, minutes=40)))
    await _seed_intelligence_note(
        repository, "seed-lost-1", {**lost_entry, "correlation_id": "seed-lost-1"},
        simulate_claude_error="ANTHROPIC_API_KEY not configured",
    )


async def _seed_analytics_history(repository: InMemoryTradeRepository, now: datetime) -> None:
    """A couple weeks of additional closed trades spanning multiple sessions, setups,
    and days of the week - purely so the Sprint 5 analytics charts (equity curve,
    breakdown by session/setup/weekday) have enough shape to actually look like
    something during local development. Not meant to resemble any specific real
    trading history."""
    async def forward_ok():
        return True, 200, None

    # (days ago, direction, setup_tag, session, outcome, entry, sl, tp, quantity, realized_pnl)
    history = [
        (14, "long", "BRK", "NY", "won", 21100.0, 21060.0, 21200.0, 3, 300.0),
        (13, "short", "RCL", "London", "lost", 21150.0, 21190.0, 21060.0, 3, -240.0),
        (12, "long", "RCL", "NY", "won", 21200.0, 21160.0, 21280.0, 4, 320.0),
        (11, "long", "BRK", "Asia", "lost", 21250.0, 21210.0, 21350.0, 2, -80.0),
        (10, "short", "BRK", "London", "won", 21300.0, 21340.0, 21200.0, 3, 300.0),
        (8, "long", "RCL", "NY", "won", 21350.0, 21310.0, 21430.0, 4, 320.0),
        (7, "short", "BRK", "NY", "lost", 21400.0, 21440.0, 21300.0, 3, -240.0),
        (6, "long", "BRK", "London", "won", 21450.0, 21410.0, 21530.0, 3, 240.0),
        (5, "long", "RCL", "Asia", "lost", 21500.0, 21460.0, 21580.0, 2, -80.0),
        (4, "short", "BRK", "NY", "won", 21480.0, 21520.0, 21400.0, 4, 320.0),
        (3, "long", "RCL", "London", "won", 21520.0, 21480.0, 21600.0, 3, 240.0),
        (2, "long", "BRK", "NY", "lost", 21560.0, 21520.0, 21640.0, 3, -240.0),
        (1, "short", "RCL", "Asia", "won", 21540.0, 21580.0, 21460.0, 2, 160.0),
    ]

    for i, (days_ago, direction, setup_tag, session, outcome, entry, sl, tp, quantity, realized_pnl) in enumerate(history):
        correlation_id = f"seed-hist-{i}"
        entered_at = now - timedelta(days=days_ago, hours=2)
        closed_at = now - timedelta(days=days_ago, hours=1)
        entry_fields = {
            "signal_time": iso(entered_at), "direction": direction, "setup_tag": setup_tag,
            "symbol": "MNQU6", "entry_price": entry, "sl": sl, "tp": tp, "atr": 40.0,
            "ema_distance_atr": 0.5, "regime_slope_pct": 1.0, "sweep_age_bars": 5,
            "session": session, "quantity": quantity,
        }
        await repository.claim_and_forward(correlation_id, entry_fields, raw_body="{}", forward=forward_ok)
        exit_price = tp if outcome == "won" else sl
        await repository.update_exit(correlation_id, outcome, exit_price, realized_pnl, iso(closed_at))

        # AI notes on a subset of the history - enough for the AI Notes Timeline to
        # show real variety without seeding all 13 (which would be repetitive, not
        # more informative). The intelligence snapshot is computed from whichever
        # seed-hist-* trades exist so far (this loop runs chronologically, oldest
        # first) - same "only look at the past" discipline atlas/ai.py uses live.
        if i % 3 == 0:
            won = outcome == "won"
            await _seed_intelligence_note(
                repository, correlation_id, {**entry_fields, "correlation_id": correlation_id},
            )
            await repository.add_ai_note(
                trade_correlation_id=correlation_id, note_type="post_trade_review", model="claude-haiku-4-5-20251001",
                content=(
                    "Played out as the entry conditions suggested - genuine trend alignment carried this to target."
                    if won else
                    "The marginal entry conditions caught up with it - this looked risky going in and didn't work out."
                ),
                error=None,
            )

    await repository.add_ai_note(
        trade_correlation_id=None, note_type="daily_report", model="claude-haiku-4-5-20251001",
        content=(
            "Today saw a mix of BRK and RCL setups across all three sessions, skewed slightly toward "
            "wins. NY session continues to carry most of the volume and the strongest win rate. Worth "
            "watching whether Asia-session BRK entries keep underperforming - both losses this week came "
            "from stale sweeps in that session."
        ),
        error=None,
    )
    await repository.add_ai_note(
        trade_correlation_id=None, note_type="weekly_report", model="claude-haiku-4-5-20251001",
        content=(
            "A solid week overall: win rate held above 50% with RCL setups outperforming BRK on average "
            "R. London session was the standout, converting nearly every RCL entry into a winner. The "
            "recurring theme in this week's losses is entries taken late relative to the sweep (high "
            "sweep-age-bars) - tightening that filter is the most promising lever for next week."
        ),
        error=None,
    )


def build_app() -> FastAPI:
    """A standalone app that reuses the real routers but never touches Postgres -
    deliberately does not import atlas.main, since that module's lifespan calls
    create_pool() and would refuse to start without a real DATABASE_URL."""
    repository = InMemoryTradeRepository()
    event_bus = EventBus()
    system_status = SystemStatus()
    for event_type in ALL_EVENT_TYPES:
        event_bus.subscribe(event_type, log_event)
        event_bus.subscribe(event_type, system_status.record)

    # Sprint 10: same alerting wiring as atlas/main.py, for consistency between the
    # two entrypoints - both are no-ops here in practice since ALERT_WEBHOOK_URL is
    # expected to stay unset for local dev.
    event_bus.subscribe(event_types.TRADE_ENTRY_FORWARD_FAILED, alert_on_forward_failure)
    claude_failure_tracker = ClaudeFailureTracker(threshold=settings.claude_failure_alert_threshold)
    for ai_event_type in (event_types.AI_ENTRY_SCORED, event_types.AI_TRADE_REVIEWED, event_types.AI_REPORT_GENERATED):
        event_bus.subscribe(ai_event_type, claude_failure_tracker.record)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.repository = repository
        app.state.event_bus = event_bus
        app.state.system_status = system_status
        app.state.started_at = datetime.now(timezone.utc)
        await seed(repository)
        yield

    dev_app = FastAPI(title="Atlas (dev seed server)", lifespan=lifespan)
    dev_app.add_middleware(
        CORSMiddleware, allow_origins=settings.frontend_origins, allow_methods=["GET", "POST"], allow_headers=["*"],
    )
    dev_app.include_router(webhook.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(health.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(trades.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(status.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(stats.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(stream.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(risk.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(analytics.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(ai_router.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(activity.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(webhook.router, tags=["legacy"])
    dev_app.include_router(health.router, tags=["legacy"])
    return dev_app


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000, log_level="info")
