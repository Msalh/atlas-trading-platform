"""
Atlas AI Trading Platform - backend entrypoint.

Receives three event types from TradingView on one webhook (unchanged from Sprint 0),
all correlated by "correlation_id" (the entry bar's timestamp, unique per trade since
only one position is open at a time):

  - "entry":        forwarded to PickMyTrade first (order relay must never wait on
                     Claude), then stored, then Claude analysis runs as a background
                     task. Idempotent and concurrency-safe - see
                     PostgresTradeRepository.claim_and_forward.
  - "price_update": periodic update for an open position. Never forwarded anywhere.
  - "exit":         the position closed. Never forwarded - PickMyTrade already runs
                     its own bracket exit once it has the entry order.

Response codes on POST /webhook (2xx range only, so TradingView never retries in a
way that could cause a duplicate order):
  - 200: fully normal
  - 207: entry stored, but the PickMyTrade forward failed or is unconfigured
  - 208: duplicate entry - already forwarded previously, nothing re-sent

Mounted at both "/webhook" (legacy path - this is what the existing TradingView alert
points at today, and it keeps working unchanged) and "/api/v1/webhook" (the versioned
path new integrations should use going forward). Same for "/health".

Run locally (requires DATABASE_URL pointing at a Postgres instance):
    uvicorn atlas.main:app --reload

Deploy: see README.md and ../docs/sprint1/deployment-checklist.md.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from atlas.api.v1 import analytics, dashboard, health, risk, status, stats, stream, trades, webhook
from atlas.config import settings
from atlas.db import create_pool
from atlas.events.bus import EventBus
from atlas.events.subscribers import log_event
from atlas.events.types import ALL as ALL_EVENT_TYPES
from atlas.repositories.postgres import PostgresTradeRepository
from atlas.status import SystemStatus

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


@asynccontextmanager
async def lifespan(app: FastAPI):
    pool = await create_pool()
    app.state.pool = pool
    app.state.repository = PostgresTradeRepository(pool)
    app.state.event_bus = EventBus()
    app.state.system_status = SystemStatus()
    for event_type in ALL_EVENT_TYPES:
        app.state.event_bus.subscribe(event_type, log_event)
        app.state.event_bus.subscribe(event_type, app.state.system_status.record)
    yield
    await pool.close()


app = FastAPI(title="Atlas AI Trading Platform", lifespan=lifespan)

# The Next.js frontend (local dev and/or deployed) calls the read endpoints below
# cross-origin. TradingView's webhook and PickMyTrade's relay are server-to-server -
# neither goes through a browser, so CORS has no effect on them either way.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_methods=["GET"],
    allow_headers=["*"],
)

# Versioned surface - new integrations (frontend, mobile, other brokers) should
# target this.
app.include_router(webhook.router, prefix="/api/v1", tags=["v1"])
app.include_router(health.router, prefix="/api/v1", tags=["v1"])
app.include_router(trades.router, prefix="/api/v1", tags=["v1"])
app.include_router(status.router, prefix="/api/v1", tags=["v1"])
app.include_router(stats.router, prefix="/api/v1", tags=["v1"])
app.include_router(stream.router, prefix="/api/v1", tags=["v1"])
app.include_router(risk.router, prefix="/api/v1", tags=["v1"])
app.include_router(analytics.router, prefix="/api/v1", tags=["v1"])

# Legacy, unversioned surface - preserved so the existing TradingView alert and any
# existing bookmark to "/" keep working without any change on TradingView's side.
app.include_router(webhook.router, tags=["legacy"])
app.include_router(health.router, tags=["legacy"])
app.include_router(dashboard.router, tags=["legacy"])
