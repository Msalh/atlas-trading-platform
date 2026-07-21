import os
import sys

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from atlas.api.deps import (  # noqa: E402
    get_event_bus, get_market_state_repository, get_repository, get_snapshots_readiness, get_system_status,
)
from atlas.api.security import require_api_key, require_api_key_for_stream  # noqa: E402
from atlas.config import settings  # noqa: E402
from atlas.events.bus import EventBus  # noqa: E402
from atlas.events.subscribers import log_event  # noqa: E402
from atlas.events.types import ALL as ALL_EVENT_TYPES  # noqa: E402
from atlas.main import app  # noqa: E402
from atlas.market_engine.repositories.memory import InMemoryMarketStateRepository  # noqa: E402
from atlas.rate_limit import limiter  # noqa: E402
from atlas.repositories.memory import InMemoryTradeRepository  # noqa: E402
from atlas.research_export.startup_check import (  # noqa: E402
    EXPECTED_SNAPSHOT_FILES, SnapshotCheckResult, SnapshotsReadiness,
)
from atlas.status import SystemStatus  # noqa: E402

TEST_SECRET = "test-secret"
TEST_API_KEY = "test-api-key"
TEST_MARKET_STATE_SECRET = "test-market-state-secret"


@pytest.fixture(autouse=True)
def _reset_rate_limiter():
    """The slowapi Limiter's in-memory counters live on the module-level `limiter`
    singleton (atlas/rate_limit.py), which persists across every test in a pytest run
    (atlas.main:app is imported once). Without this, tests that post several webhooks
    in a row (or run after test_rate_limiting.py's deliberately-over-the-limit tests)
    would fail for a reason unrelated to what they're actually testing."""
    limiter.reset()
    yield
    limiter.reset()


@pytest.fixture
def repository():
    return InMemoryTradeRepository()


@pytest.fixture
def market_state_repository():
    return InMemoryMarketStateRepository()


@pytest.fixture
def system_status():
    return SystemStatus()


def all_ready_snapshots_readiness() -> SnapshotsReadiness:
    """The default the `client` fixture wires in - every test that doesn't
    care about degraded snapshot state gets a plain "everything's fine"
    result, without needing real files on disk. Tests for the degraded
    states themselves (tests/test_status_api.py) override
    get_snapshots_readiness directly with a purpose-built SnapshotsReadiness."""
    return SnapshotsReadiness(tuple(SnapshotCheckResult(f, "ready", None) for f in EXPECTED_SNAPSHOT_FILES))


@pytest.fixture
def snapshots_readiness():
    return all_ready_snapshots_readiness()


@pytest.fixture
def event_bus(system_status):
    """A real EventBus with the same logging + SystemStatus subscribers production
    uses attached - exercises the same wiring as atlas.main's lifespan, just without a
    real Postgres pool behind it."""
    bus = EventBus()
    for event_type in ALL_EVENT_TYPES:
        bus.subscribe(event_type, log_event)
        bus.subscribe(event_type, system_status.record)
    return bus


@pytest.fixture
def client(repository, market_state_repository, event_bus, system_status, snapshots_readiness, monkeypatch):
    """A TestClient wired to an in-memory repository via FastAPI's
    dependency_overrides - the standard way to test routes without a real database.
    This bypasses the Postgres-backed lifespan entirely (TestClient never triggers it
    unless used as a context manager, and dependency_overrides win regardless).

    require_api_key/require_api_key_for_stream are overridden to no-ops here so the
    existing test suite (none of which sends an Authorization header) keeps testing
    what it was actually written to test, rather than universally needing an auth
    header bolted on. The auth check itself is verified for real, without this
    override, in tests/test_auth.py.

    market_state_webhook_secret IS set to a real value (not overridden to a
    no-op) - unlike API_KEY, /api/v1/market-state has no dependency-injected
    auth check to override; its secret check is inline in the route (same
    shape as /webhook's), so tests exercise it for real via
    market_state_payload()'s default secret, mirroring exactly how
    entry_payload() already does for /webhook."""
    monkeypatch.setattr(settings, "webhook_secret", TEST_SECRET)
    monkeypatch.setattr(settings, "api_key", TEST_API_KEY)
    monkeypatch.setattr(settings, "market_state_webhook_secret", TEST_MARKET_STATE_SECRET)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_market_state_repository] = lambda: market_state_repository
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_system_status] = lambda: system_status
    app.dependency_overrides[get_snapshots_readiness] = lambda: snapshots_readiness
    app.dependency_overrides[require_api_key] = lambda: None
    app.dependency_overrides[require_api_key_for_stream] = lambda: None
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.fixture
def get_trade(repository):
    """Returns a helper that reads back a trade row as a dict, given a correlation_id."""
    def _get(correlation_id):
        import asyncio
        rows = asyncio.run(repository.list_recent(limit=1000))
        for row in rows:
            if row["correlation_id"] == correlation_id:
                return row
        return None
    return _get


@pytest.fixture
def get_ai_notes(repository):
    """Returns a helper that reads back AI notes for a correlation_id (most recent
    first), optionally filtered to one note_type."""
    def _get(correlation_id, note_type=None):
        import asyncio
        return asyncio.run(
            repository.list_ai_notes(trade_correlation_id=correlation_id, note_type=note_type)
        )
    return _get


def market_state_payload(event_id="MNQU6:5m:2026-07-18T13:35:00Z", **overrides):
    payload = {
        "schema_version": "1.0",
        "event_id": event_id,
        "symbol": "MNQU6",
        "source": "tradingview",
        "timeframe": "5m",
        "timestamp": "2026-07-18T13:35:00Z",
        "bar_status": "closed",
        "secret": TEST_MARKET_STATE_SECRET,
        "close": 20125.75,
    }
    payload.update(overrides)
    return payload


def entry_payload(correlation_id="corr-1", **overrides):
    payload = {
        "type": "entry",
        "correlation_id": correlation_id,
        "secret": TEST_SECRET,
        "symbol": "MNQU6",
        "strategy_name": "NQ RECLAIM NY LONG",
        "data": "BUY",
        "quantity": 12,
        "price": 30000,
        "tp": 30050,
        "sl": 29950,
        "token": "x",
        "direction": "long",
        "setup_tag": "BRK",
        "entry_price": 30000,
        "atr": 42.5,
        "ema_distance_atr": 0.8,
        "regime_slope_pct": 1.2,
        "sweep_age_bars": 6,
        "session": "NY",
        "signal_time": "2026-07-07T17:35:00Z",
    }
    payload.update(overrides)
    return payload
