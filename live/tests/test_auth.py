"""
Tests for the shared API key requirement (Sprint 9) - atlas/api/security.py. Every
non-webhook, non-health endpoint must require it; the webhook keeps its own
shared-secret scheme (TradingView can't send an Authorization header) and /health
stays public (Railway's health-check prober sends no custom headers).

Deliberately does NOT use the shared `client` fixture (tests/conftest.py), which
overrides require_api_key/require_api_key_for_stream to a no-op so the rest of the
suite tests what it was actually written to test - these tests need the real
dependency wired in to verify it actually rejects/accepts requests.

/api/v1/stream's auth is tested by calling require_api_key_for_stream directly rather
than through a live HTTP connection (same discipline test_stream.py already uses for
the generator itself) - once auth succeeds, the route starts an infinite SSE
generator, and TestClient does not reliably simulate a client disconnect to stop it,
which would hang the test session rather than exercise anything meaningful about auth.
"""
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from atlas.api.deps import get_event_bus, get_repository, get_system_status
from atlas.api.security import require_api_key_for_stream
from atlas.config import settings
from atlas.main import app

REAL_API_KEY = "real-api-key"


@pytest.fixture
def raw_client(monkeypatch, repository, event_bus, system_status):
    monkeypatch.setattr(settings, "api_key", REAL_API_KEY)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_event_bus] = lambda: event_bus
    app.dependency_overrides[get_system_status] = lambda: system_status
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()


@pytest.mark.parametrize("path", [
    "/api/v1/trades", "/api/v1/trades/current", "/api/v1/status", "/api/v1/stats/today",
    "/api/v1/risk", "/api/v1/analytics/summary", "/api/v1/ai/notes", "/api/v1/ai/reports",
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


def test_stream_rejects_wrong_api_key_as_query_param(raw_client):
    resp = raw_client.get("/api/v1/stream?api_key=wrong-key")
    assert resp.status_code == 401


def test_require_api_key_for_stream_accepts_header(monkeypatch):
    monkeypatch.setattr(settings, "api_key", REAL_API_KEY)
    require_api_key_for_stream(request=None, authorization=f"Bearer {REAL_API_KEY}", api_key=None)  # must not raise


def test_require_api_key_for_stream_accepts_query_param(monkeypatch):
    """Browsers' native EventSource can't set custom headers - /api/v1/stream must
    also accept the key as ?api_key=... (see frontend/src/lib/live-updates.tsx)."""
    monkeypatch.setattr(settings, "api_key", REAL_API_KEY)
    require_api_key_for_stream(request=None, authorization=None, api_key=REAL_API_KEY)  # must not raise


def test_require_api_key_for_stream_rejects_missing_both(monkeypatch):
    monkeypatch.setattr(settings, "api_key", REAL_API_KEY)
    with pytest.raises(HTTPException) as exc:
        require_api_key_for_stream(request=None, authorization=None, api_key=None)
    assert exc.value.status_code == 401
