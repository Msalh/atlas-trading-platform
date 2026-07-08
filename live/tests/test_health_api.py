"""
Tests for GET /health (Sprint 10 additions: uptime_seconds/started_at). The base
database-connectivity behavior predates this sprint; test_auth.py already covers that
this endpoint stays public (no API key required) even after Sprint 9.
"""
from datetime import datetime, timedelta, timezone


def test_health_ok_when_database_reachable(client):
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["database"] == "ok"


def test_health_reports_none_uptime_when_started_at_not_set(client):
    """The shared `client` fixture (tests/conftest.py) never runs atlas.main's real
    lifespan (TestClient doesn't trigger it unless used as a context manager), so
    app.state.started_at is never set in these unit tests - the endpoint must degrade
    gracefully (None, not a crash) rather than assume it's always present."""
    resp = client.get("/api/v1/health")
    body = resp.json()
    assert body["started_at"] is None
    assert body["uptime_seconds"] is None


def test_health_reports_uptime_when_started_at_is_set(client):
    from atlas.main import app

    started = datetime.now(timezone.utc) - timedelta(seconds=42)
    app.state.started_at = started
    try:
        resp = client.get("/api/v1/health")
    finally:
        del app.state.started_at

    body = resp.json()
    assert body["started_at"] == started.isoformat()
    assert body["uptime_seconds"] >= 42


def test_health_returns_503_when_database_unreachable(client, repository):
    async def broken_ping():
        raise RuntimeError("connection refused")

    repository.ping = broken_ping
    resp = client.get("/api/v1/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["ok"] is False
    assert "connection refused" in body["database"]


def test_health_includes_uptime_fields_even_on_failure(client, repository):
    """A degraded health check should still report how long the process has been up -
    that's useful context for diagnosing the failure, not something to hide."""
    from atlas.main import app

    async def broken_ping():
        raise RuntimeError("connection refused")

    repository.ping = broken_ping
    started = datetime.now(timezone.utc) - timedelta(seconds=10)
    app.state.started_at = started
    try:
        resp = client.get("/api/v1/health")
    finally:
        del app.state.started_at

    body = resp.json()
    assert body["ok"] is False
    assert body["uptime_seconds"] >= 10
