"""
Tests for the shared API key requirement (Sprint 9) - atlas/api/security.py. Every
non-webhook, non-health endpoint must require it; the webhook keeps its own
shared-secret scheme (TradingView can't send an Authorization header) and /health
stays public (Railway's health-check prober sends no custom headers).

Deliberately does NOT use the shared `client` fixture (tests/conftest.py), which
overrides require_api_key to a no-op so the rest of the suite tests what it was
actually written to test - these tests need the real dependency wired in to verify it
actually rejects/accepts requests.

/api/v1/stream now uses the same require_api_key dependency as every other protected
route (production hardening: SSE auth moved to a same-origin BFF proxy - see
frontend/src/app/api/stream/route.ts - which attaches the Authorization header
server-side; the browser-visible ?api_key=... query-parameter fallback has been
removed entirely, not kept for backward compatibility). A GET to /api/v1/stream is
still tested via a live TestClient request rather than by consuming the SSE body -
once auth succeeds the route starts an infinite generator, and TestClient does not
reliably simulate a client disconnect to stop it, which would hang the test session
rather than exercise anything meaningful about auth. Only the auth check itself
(headers in, status code out) is exercised here, never the stream body.
"""
import pytest
from fastapi.testclient import TestClient

from atlas.api.deps import get_event_bus, get_market_state_repository, get_repository, get_system_status
from atlas.api.security import require_api_key
from atlas.config import settings
from atlas.main import app

REAL_API_KEY = "real-api-key"


@pytest.fixture
def raw_client(monkeypatch, repository, market_state_repository, event_bus, system_status):
    monkeypatch.setattr(settings, "api_key", REAL_API_KEY)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_market_state_repository] = lambda: market_state_repository
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_system_status] = lambda: system_status
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", [
    "/api/v1/trades", "/api/v1/trades/current", "/api/v1/status", "/api/v1/stats/today",
    "/api/v1/risk", "/api/v1/analytics/summary", "/api/v1/ai/notes", "/api/v1/ai/reports",
    "/api/v1/activity",
    # Sprint 4 (Market Engine read API) - protected by the same shared API key,
    # applied per-route rather than at router-registration time since
    # api/v1/market_state.py's POST route shares this router but uses its own
    # secret instead - see that module's docstring.
    "/api/v1/market-state/latest?symbol=MNQU6&timeframe=5m",
    "/api/v1/market-state/history?symbol=MNQU6&timeframe=5m",
    # Sprint 8 (Data Validation & Integrity) - same shared API key as every
    # other read route above.
    "/api/v1/market-state/integrity?symbol=MNQU6&timeframe=5m",
    # Sprint 9 (Dataset Builder) - same shared API key as every other read
    # route above.
    "/api/v1/market-state/export?symbol=MNQU6&timeframe=5m&start=2026-07-18T00:00:00Z&end=2026-07-19T00:00:00Z",
    # Sprint 15 (Rule Engine observability) - same shared API key, applied at
    # router-registration time (rule_engine.router has one route, one auth
    # scheme - see atlas/main.py's registration comment).
    "/api/v1/rule-engine/latest?symbol=MNQU6&timeframe=5m",
    # UI v2 (research.py) - same shared API key, applied at
    # router-registration time.
    "/api/v1/research/re1/summary", "/api/v1/research/re2/summary", "/api/v1/research/dataset-health",
    # UI v2 (setup_engine.py) - same shared API key, applied at
    # router-registration time.
    "/api/v1/setup-engine/latest?symbol=MNQU6&timeframe=5m",
    "/api/v1/setup-engine/episodes/live?symbol=MNQU6&timeframe=5m",
])
def test_protected_endpoints_reject_missing_api_key(raw_client, path):
    resp = raw_client.get(path)
    assert resp.status_code == 401


def test_protected_endpoint_rejects_wrong_api_key(raw_client):
    resp = raw_client.get("/api/v1/trades", headers={"Authorization": "Bearer wrong-key"})
    assert resp.status_code == 401


def test_protected_endpoint_rejects_malformed_authorization_header(raw_client):
    """Missing the "Bearer " scheme prefix - not a valid token at all."""
    resp = raw_client.get("/api/v1/trades", headers={"Authorization": REAL_API_KEY})
    assert resp.status_code == 401


def test_protected_endpoint_accepts_correct_bearer_token(raw_client):
    resp = raw_client.get("/api/v1/trades", headers={"Authorization": f"Bearer {REAL_API_KEY}"})
    assert resp.status_code == 200


def test_market_state_read_endpoints_accept_correct_api_key(raw_client):
    resp = raw_client.get(
        "/api/v1/market-state/latest?symbol=MNQU6&timeframe=5m",
        headers={"Authorization": f"Bearer {REAL_API_KEY}"},
    )
    assert resp.status_code == 200


def test_market_state_webhook_secret_does_not_authenticate_reads(raw_client, monkeypatch):
    """The POST route's own MARKET_STATE_WEBHOOK_SECRET and the GET routes'
    shared API_KEY protect different trust domains (see
    atlas/api/v1/market_state.py's module docstring) - a valid ingestion
    secret must not double as read access."""
    monkeypatch.setattr(settings, "market_state_webhook_secret", "ms-secret")
    resp = raw_client.get(
        "/api/v1/market-state/latest?symbol=MNQU6&timeframe=5m",
        headers={"Authorization": "Bearer ms-secret"},
    )
    assert resp.status_code == 401


def test_webhook_does_not_require_the_api_key(raw_client, monkeypatch):
    """The webhook has its own shared-secret scheme (WEBHOOK_SECRET), not the API
    key - TradingView can't send a custom Authorization header."""
    monkeypatch.setattr(settings, "webhook_secret", "")
    monkeypatch.setattr(settings, "environment", "development")
    resp = raw_client.post("/webhook", json={"type": "entry", "correlation_id": "corr-no-api-key"})
    assert resp.status_code != 401


def test_health_does_not_require_the_api_key(raw_client):
    resp = raw_client.get("/api/v1/health")
    assert resp.status_code != 401


def test_stream_rejects_missing_api_key(raw_client):
    """Rejected before the streaming route body ever runs - a normal, immediately-
    complete 401 response, not a hang."""
    resp = raw_client.get("/api/v1/stream")
    assert resp.status_code == 401


def test_stream_accepts_correct_bearer_token(monkeypatch):
    """Production hardening: /api/v1/stream now uses the same require_api_key
    dependency as every other protected route (atlas/main.py's router registration) -
    the same-origin frontend BFF proxy (frontend/src/app/api/stream/route.ts) is the
    only caller expected to reach this endpoint in production, attaching the key as a
    normal Authorization header, never a query parameter.

    Checked by calling require_api_key directly (same discipline the rest of this
    module uses for /api/v1/trades etc. via a live request instead) rather than
    through a live GET to /api/v1/stream: once auth succeeds, that route's body is an
    infinite SSE generator, and TestClient does not reliably simulate a client
    disconnect to stop it - a live request would hang the test session rather than
    exercise anything meaningful about auth, exactly as this module's own docstring
    already documents for the stream endpoint generally."""
    monkeypatch.setattr(settings, "api_key", REAL_API_KEY)
    require_api_key(request=None, authorization=f"Bearer {REAL_API_KEY}")  # must not raise


def test_stream_rejects_correct_api_key_as_query_param_only(raw_client):
    """The browser-visible ?api_key=... fallback is removed entirely, not kept for
    backward compatibility (production hardening: SSE auth moved to a same-origin BFF
    proxy) - even the CORRECT key must now be rejected if it only ever arrives as a
    query parameter, never an Authorization header."""
    resp = raw_client.get(f"/api/v1/stream?api_key={REAL_API_KEY}")
    assert resp.status_code == 401


def test_stream_401_response_never_contains_the_real_api_key(raw_client):
    resp = raw_client.get("/api/v1/stream?api_key=wrong-key")
    assert resp.status_code == 401
    assert REAL_API_KEY not in resp.text
