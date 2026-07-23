"""
Atlas AI Trading Platform - backend entrypoint.

Receives three event types from TradingView on one webhook (unchanged from Sprint 0),
all correlated by "correlation_id" (the entry bar's timestamp, unique per trade since
only one position is open at a time):

  - "entry":        forwarded to PickMyTrade first (order relay must never wait on
                     Claude), then stored, then AI entry scoring runs as a background
                     task (atlas/ai.py). Idempotent and concurrency-safe - see
                     PostgresTradeRepository.claim_and_forward.
  - "price_update": periodic update for an open position. Never forwarded anywhere.
  - "exit":         the position closed. Never forwarded - PickMyTrade already runs
                     its own bracket exit once it has the entry order. A post-trade AI
                     review also runs as a background task after this.

Response codes on POST /webhook (2xx range only, so TradingView never retries in a
way that could cause a duplicate order):
  - 200: fully normal
  - 207: entry stored, but the PickMyTrade forward failed or is unconfigured
  - 208: duplicate entry - already forwarded previously, nothing re-sent

Mounted at both "/webhook" (legacy path - this is what the existing TradingView alert
points at today, and it keeps working unchanged) and "/api/v1/webhook" (the versioned
path new integrations should use going forward). Same for "/health".

Sprint 9 (security hardening - see docs/sprint9/security-notes.md): every router
except webhook (its own shared-secret scheme) and health (deliberately public - see
atlas/api/security.py) requires the shared API key. The app refuses to start in
production without WEBHOOK_SECRET/API_KEY set - see Settings.validate_for_startup.

Run locally (requires DATABASE_URL pointing at a Postgres instance):
    uvicorn atlas.main:app --reload

Deploy: see README.md and ../docs/sprint9/deployment-checklist.md.
"""
import asyncio
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from atlas.alerting import ClaudeFailureTracker, alert_on_forward_failure
from atlas.api.security import require_api_key
from atlas.api.v1 import (
    activity, ai, analytics, health, market_state, research, risk, rule_engine, setup_engine, status, stats,
    stream, trades, webhook,
)
from atlas.config import settings
from atlas.db import create_pool
from atlas.events import types as event_types
from atlas.events.bus import EventBus
from atlas.events.subscribers import log_event
from atlas.events.types import ALL as ALL_EVENT_TYPES
from atlas.logging_config import configure_logging
from atlas.market_engine.repositories.postgres import PostgresMarketStateRepository
from atlas.monitoring import MarketStateStalenessMonitor
from atlas.rate_limit import limiter
from atlas.repositories.postgres import PostgresTradeRepository
from atlas.research_deploy.startup_check import (
    build_startup_report,
    check_ledger_storage,
)
from atlas.research_deploy.startup_check import internal_error_readiness as ledger_internal_error_readiness
from atlas.research_export.startup_check import check_snapshots, internal_error_readiness
from atlas.status import SystemStatus

configure_logging()
logger = logging.getLogger(__name__)


async def _market_state_staleness_loop(app: FastAPI, monitor: MarketStateStalenessMonitor, interval_seconds: float) -> None:
    """Sprint 7. A thin adapter, deliberately - all the interesting logic
    (what counts as stale, what counts as expected market hours, alert-once-
    on-transition) lives in atlas.monitoring, fully unit-tested there. This
    loop's only job is extracting the two values that logic needs from
    app.state and calling into it, every `interval_seconds`."""
    while True:
        await asyncio.sleep(interval_seconds)
        last_at_str = app.state.system_status.last_at(event_types.MARKET_STATE_INGESTED)
        last_seen_at = datetime.fromisoformat(last_at_str) if last_at_str else None
        monitor.check(last_seen_at, app.state.started_at, datetime.now(timezone.utc))


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.validate_for_startup()
    app.state.started_at = datetime.now(timezone.utc)
    # Production-hardening amendment 3: computed once here, never per-request -
    # does not raise on a missing/invalid snapshot (LIVE endpoints have no
    # dependency on these files), only records the degraded state for
    # GET /status to expose. See atlas/research_export/startup_check.py.
    # The try/except is a second, outer safety net around that same
    # contract: check_snapshots() is expected to turn every bad-file case
    # it knows about into a normal "invalid" result rather than raising,
    # but if it ever raises something unanticipated (a genuine bug in that
    # module, not a bad snapshot file), that must still never prevent LIVE
    # endpoints (rule-engine/setup-engine) from starting.
    try:
        app.state.snapshots_readiness = check_snapshots(research.SNAPSHOTS_DIR)
    except Exception:
        logger.exception("snapshot readiness check failed unexpectedly at startup")
        app.state.snapshots_readiness = internal_error_readiness()

    # Sprint 8.2 (Railway Staging Deployment): same "never raise, never
    # block startup, never take LIVE endpoints down with it" contract as
    # the snapshot check above, applied to the write side - see
    # atlas/research_deploy/startup_check.py's own module docstring. The
    # startup report is logged exactly once here, reflecting true
    # per-check state on both a ready and a degraded run.
    ledger_check_started_at = time.monotonic()
    try:
        app.state.ledger_readiness, app.state.ledger_stores = check_ledger_storage(
            Path(settings.research_ledger_dir)
        )
    except Exception:
        logger.exception("ledger readiness check failed unexpectedly at startup")
        app.state.ledger_readiness = ledger_internal_error_readiness()
        app.state.ledger_stores = None
    ledger_elapsed_ms = (time.monotonic() - ledger_check_started_at) * 1000
    logger.info(build_startup_report(app.state.ledger_readiness, settings.environment, ledger_elapsed_ms))

    pool = await create_pool()
    app.state.pool = pool
    app.state.repository = PostgresTradeRepository(pool)
    # Sprint 3 (Market Engine): reuses the same connection pool - it's the same
    # Postgres database, a different table, no reason for a second pool.
    app.state.market_state_repository = PostgresMarketStateRepository(pool)
    app.state.event_bus = EventBus()
    app.state.system_status = SystemStatus()
    for event_type in ALL_EVENT_TYPES:
        app.state.event_bus.subscribe(event_type, log_event)
        app.state.event_bus.subscribe(event_type, app.state.system_status.record)

    # Sprint 10: operational alerting - see atlas/alerting.py. Both are no-ops
    # (send_alert never actually POSTs anything) when ALERT_WEBHOOK_URL is unset, so
    # this subscription is always safe to register.
    app.state.event_bus.subscribe(event_types.TRADE_ENTRY_FORWARD_FAILED, alert_on_forward_failure)
    claude_failure_tracker = ClaudeFailureTracker(threshold=settings.claude_failure_alert_threshold)
    for ai_event_type in (event_types.AI_ENTRY_SCORED, event_types.AI_TRADE_REVIEWED, event_types.AI_REPORT_GENERATED):
        app.state.event_bus.subscribe(ai_event_type, claude_failure_tracker.record)

    # Market Engine Sprint 7 - a long-running background task, a genuinely new
    # shape of code for this codebase (distinct from the request-triggered
    # BackgroundTasks pattern in atlas/ai.py and the purely event-driven
    # subscribers above). Cancelled and awaited on shutdown so it doesn't leak
    # or log an "unhandled task exception" warning on every restart.
    staleness_monitor = MarketStateStalenessMonitor(
        threshold_minutes=settings.market_state_staleness_threshold_minutes
    )
    staleness_task = asyncio.create_task(
        _market_state_staleness_loop(app, staleness_monitor, settings.market_state_staleness_check_interval_seconds)
    )

    yield

    staleness_task.cancel()
    try:
        await staleness_task
    except asyncio.CancelledError:
        pass
    await pool.close()


# Sprint 9: FastAPI's auto-generated /docs, /redoc, /openapi.json reveal the full API
# surface/schema publicly by default - harmless in development, unnecessary exposure
# in production now that every real endpoint requires the API key anyway. Disabled
# only in production so local development keeps the interactive docs.
_docs_kwargs = (
    {} if settings.environment == "development"
    else {"docs_url": None, "redoc_url": None, "openapi_url": None}
)
app = FastAPI(title="Atlas AI Trading Platform", lifespan=lifespan, **_docs_kwargs)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    """Sprint 9: baseline headers on every response. The backend serves JSON/SSE only
    (the HTML dashboard was removed this sprint - see docs/sprint9/architecture-
    decisions.md), so a strict CSP is safe here: there is no first-party HTML/script
    for a policy to break."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    return response


# The Next.js frontend (local dev and/or deployed) calls the endpoints below
# cross-origin. TradingView's webhook and PickMyTrade's relay are server-to-server -
# neither goes through a browser, so CORS has no effect on them either way. POST is
# needed as of Sprint 6 for the report-generation trigger (the only non-GET endpoint a
# browser calls) - it still only ever schedules a background task, never blocks. Added
# last so it's the outermost middleware layer - CORS headers still apply to error
# responses (401/422/429) from the layers underneath, not just 2xx success.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.frontend_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Versioned surface - new integrations (frontend, mobile, other brokers) should
# target this. webhook keeps its own shared-secret auth (unchanged relay semantics);
# health stays public (Railway's health-check prober sends no custom headers, and the
# response reveals nothing beyond "is the database reachable"). Every other router
# requires the shared API key - see atlas/api/security.py.
app.include_router(webhook.router, prefix="/api/v1", tags=["v1"])
app.include_router(health.router, prefix="/api/v1", tags=["v1"])
# Sprint 3 (Market Engine): its own body-embedded-secret auth scheme, same as
# webhook.router above - not the shared API key, and not dual-mounted at a
# legacy path, since no existing integration points at one yet (unlike
# /webhook, which TradingView's live alert already depends on).
app.include_router(market_state.router, prefix="/api/v1", tags=["v1"])
# Sprint 15 (Rule Engine): a dedicated namespace, not nested under
# market_state.router - Rule Engine is its own domain package. One route,
# one auth scheme, so require_api_key is applied here at registration time
# (unlike market_state.router, which mixes two schemes on one router and
# applies auth per-route instead).
app.include_router(rule_engine.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(trades.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(status.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(stats.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(stream.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(risk.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(analytics.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(ai.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
app.include_router(activity.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
# UI v2: reads only the checked-in live/research/snapshots/*.json files
# this router's own docstring describes - no computation on request, same
# shared-key auth as every other read-only router above.
app.include_router(research.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])
# UI v2: live Setup Engine state and episode projection - zero changes to
# atlas/setup_engine/ or atlas/rule_engine/, same shared-key auth.
app.include_router(setup_engine.router, prefix="/api/v1", tags=["v1"], dependencies=[Depends(require_api_key)])

# Legacy, unversioned surface - preserved so the existing TradingView alert keeps
# working without any change on TradingView's side. The legacy HTML dashboard
# (previously mounted at "/") was removed this sprint - see
# docs/sprint9/architecture-decisions.md.
app.include_router(webhook.router, tags=["legacy"])
app.include_router(health.router, tags=["legacy"])
