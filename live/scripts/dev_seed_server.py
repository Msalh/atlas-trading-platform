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
from datetime import datetime, timedelta, timezone

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas.api.v1 import analytics, dashboard, health, risk, status, stats, stream, trades, webhook  # noqa: E402
from atlas.config import settings  # noqa: E402
from atlas.events.bus import EventBus  # noqa: E402
from atlas.events.subscribers import log_event  # noqa: E402
from atlas.events.types import ALL as ALL_EVENT_TYPES  # noqa: E402
from atlas.repositories.memory import InMemoryTradeRepository  # noqa: E402
from atlas.status import SystemStatus  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


async def seed(repository: InMemoryTradeRepository) -> None:
    now = datetime.now(timezone.utc)

    # An open long position, forwarded successfully, with a couple of price updates.
    async def forward_ok():
        return True, 200, None

    await repository.claim_and_forward(
        "seed-open-1",
        {
            "signal_time": iso(now - timedelta(minutes=18)), "direction": "long", "setup_tag": "BRK",
            "symbol": "MNQU6", "entry_price": 21500.0, "sl": 21460.0, "tp": 21600.0, "atr": 42.5,
            "ema_distance_atr": 0.6, "regime_slope_pct": 1.4, "sweep_age_bars": 4, "session": "NY",
            "quantity": 6,
        },
        raw_body="{}", forward=forward_ok,
    )
    await repository.update_price("seed-open-1", 21538.25, 306.25, iso(now - timedelta(minutes=2)))
    await repository.update_ai_analysis(
        "seed-open-1", "claude-haiku-4-5-20251001",
        "Regime slope is steep and the sweep is fresh - this lines up with the trending "
        "conditions this strategy needs. EMA distance is modest, not chasing.", None,
    )

    # A winning trade from earlier today.
    await repository.claim_and_forward(
        "seed-won-1",
        {
            "signal_time": iso(now - timedelta(hours=3)), "direction": "long", "setup_tag": "RCL",
            "symbol": "MNQU6", "entry_price": 21400.0, "sl": 21360.0, "tp": 21480.0, "atr": 38.0,
            "ema_distance_atr": 0.3, "regime_slope_pct": 1.1, "sweep_age_bars": 2, "session": "London",
            "quantity": 4,
        },
        raw_body="{}", forward=forward_ok,
    )
    await repository.update_exit("seed-won-1", "won", 21480.0, 800.0, iso(now - timedelta(hours=2, minutes=10)))
    await repository.update_ai_analysis(
        "seed-won-1", "claude-haiku-4-5-20251001", "Clean reclaim with a fresh sweep - textbook entry.", None,
    )

    # A losing trade with a PickMyTrade relay failure - the visible-failure case.
    async def forward_fails():
        return False, None, "connection refused"

    await repository.claim_and_forward(
        "seed-lost-1",
        {
            "signal_time": iso(now - timedelta(hours=6)), "direction": "short", "setup_tag": "BRK",
            "symbol": "MNQU6", "entry_price": 21550.0, "sl": 21590.0, "tp": 21470.0, "atr": 45.0,
            "ema_distance_atr": 1.8, "regime_slope_pct": 0.4, "sweep_age_bars": 11, "session": "Asia",
            "quantity": 5,
        },
        raw_body="{}", forward=forward_fails,
    )
    await repository.update_exit("seed-lost-1", "lost", 21590.0, -400.0, iso(now - timedelta(hours=5, minutes=40)))
    await repository.update_ai_analysis(
        "seed-lost-1", None, None, "ANTHROPIC_API_KEY not configured",
    )

    await _seed_analytics_history(repository, now)


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
        await repository.claim_and_forward(
            correlation_id,
            {
                "signal_time": iso(entered_at), "direction": direction, "setup_tag": setup_tag,
                "symbol": "MNQU6", "entry_price": entry, "sl": sl, "tp": tp, "atr": 40.0,
                "ema_distance_atr": 0.5, "regime_slope_pct": 1.0, "sweep_age_bars": 5,
                "session": session, "quantity": quantity,
            },
            raw_body="{}", forward=forward_ok,
        )
        exit_price = tp if outcome == "won" else sl
        await repository.update_exit(correlation_id, outcome, exit_price, realized_pnl, iso(closed_at))


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

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.repository = repository
        app.state.event_bus = event_bus
        app.state.system_status = system_status
        await seed(repository)
        yield

    dev_app = FastAPI(title="Atlas (dev seed server)", lifespan=lifespan)
    dev_app.add_middleware(
        CORSMiddleware, allow_origins=settings.frontend_origins, allow_methods=["GET"], allow_headers=["*"],
    )
    dev_app.include_router(webhook.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(health.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(trades.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(status.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(stats.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(stream.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(risk.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(analytics.router, prefix="/api/v1", tags=["v1"])
    dev_app.include_router(webhook.router, tags=["legacy"])
    dev_app.include_router(health.router, tags=["legacy"])
    dev_app.include_router(dashboard.router, tags=["legacy"])
    return dev_app


if __name__ == "__main__":
    uvicorn.run(build_app(), host="0.0.0.0", port=8000, log_level="info")
