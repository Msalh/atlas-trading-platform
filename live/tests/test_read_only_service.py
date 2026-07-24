"""Lifecycle, smoke, and structural safety tests for the dedicated service."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from atlas.config import settings
from atlas.read_only_service import app

VALID_CONFIG = {
    "environment": "production",
    "database_url": "postgresql://read-only.invalid/atlas",
    "api_key": "read-service-key",
    "trader_now_product": "MNQ",
    "trader_now_market_data_provider": "tradingview",
    "trader_now_market_data_series_symbol": "MNQ1!",
    "trader_now_market_data_series_type": "continuous",
    "trader_now_series_resolution_version": "tradingview-mnq1.v1",
    "trader_now_series_effective_date": "2026-07-13",
    "trader_now_calendar_version": "cme-equity-index.2026.v1",
    "trader_now_holidays_json": "[]",
    "trader_now_early_closes_json": "{}",
    "trader_now_service_mode": "read_only",
}


class FakePool:
    def __init__(self):
        self.close_calls = 0

    async def close(self):
        self.close_calls += 1


class FakeRepository:
    instances = []

    def __init__(self, pool):
        self.pool = pool
        self.ping_calls = 0
        self.history_calls = 0
        self.write_calls = 0
        self.__class__.instances.append(self)

    async def ping(self):
        self.ping_calls += 1
        return True

    async def get_history(self, symbol, timeframe, limit=100):
        self.history_calls += 1
        assert limit == 288
        return []

    async def ingest(self, *_args, **_kwargs):
        self.write_calls += 1
        raise AssertionError("read-only service attempted a write")


@pytest.fixture
def configured_service(monkeypatch):
    for name, value in VALID_CONFIG.items():
        monkeypatch.setattr(settings, name, value)
    pool = FakePool()
    FakeRepository.instances.clear()

    async def create_pool(_database_url):
        return pool

    monkeypatch.setattr("atlas.read_only_service.create_read_only_pool", create_pool)

    async def verify_access(_pool):
        return None

    monkeypatch.setattr(
        "atlas.read_only_service.verify_read_only_access", verify_access
    )
    monkeypatch.setattr(
        "atlas.read_only_service.PostgresMarketStateRepository",
        FakeRepository,
    )
    with TestClient(app) as client:
        yield client, pool, FakeRepository.instances[0]
    assert pool.close_calls == 1


def _auth():
    return {"Authorization": f"Bearer {VALID_CONFIG['api_key']}"}


def test_smoke_lifecycle_routes_auth_no_data_and_shutdown(configured_service):
    client, pool, repository = configured_service
    application = app.state.trader_now_application

    assert client.get("/health").json() == {
        "ok": True,
        "service": "trader-now-read-only",
    }
    assert client.get("/readiness").status_code == 401
    assert (
        client.get(
            "/readiness",
            headers={"Authorization": "Bearer wrong"},
        ).status_code
        == 401
    )
    assert client.get("/readiness", headers=_auth()).status_code == 200

    path = (
        "/api/v1/trader-now?symbol=MNQ&timeframe=5m"
        "&strategy_id=displacement_volume_context"
    )
    assert client.get(path).status_code == 401
    assert (
        client.get(path, headers={"Authorization": "Bearer wrong"}).status_code == 401
    )
    response = client.get(path, headers=_auth())

    assert response.status_code == 200
    assert response.json()["schema_version"] == "trader_now_response.v2"
    assert response.json()["availability"]["market"]["status"] == "no_data"
    assert app.state.trader_now_application is application
    assert repository.history_calls == 1
    assert repository.write_calls == 0
    assert response.headers["X-Correlation-ID"]
    assert pool.close_calls == 0

    # Fixture shutdown happens after this test body.


def test_only_three_approved_routes_are_mounted():
    def flatten(routes, prefix=""):
        for route in routes:
            original = getattr(route, "original_router", None)
            if original is not None:
                included_prefix = route.include_context.prefix
                yield from flatten(original.routes, prefix + included_prefix)
            elif hasattr(route, "path"):
                yield route, prefix + route.path

    routes = {
        (method, path)
        for route, path in flatten(app.routes)
        for method in getattr(route, "methods", set())
    }
    assert routes == {
        ("GET", "/health"),
        ("GET", "/readiness"),
        ("GET", "/api/v1/trader-now"),
    }


@pytest.mark.parametrize(
    "path",
    [
        "/webhook",
        "/api/v1/webhook",
        "/api/v1/market-state",
        "/api/v1/trades",
        "/api/v1/ai/reports",
        "/api/v1/research/run",
        "/api/v1/promotion",
    ],
)
def test_write_and_unrelated_routes_do_not_exist(configured_service, path):
    client, _, _ = configured_service
    assert client.get(path, headers=_auth()).status_code == 404
    assert client.post(path, headers=_auth()).status_code == 404


def test_health_remains_live_when_repository_becomes_unavailable(
    configured_service, caplog
):
    client, _, _repository = configured_service

    async def failed_access(_pool):
        raise RuntimeError("secret database details")

    from atlas import read_only_service

    original = read_only_service.verify_read_only_access
    read_only_service.verify_read_only_access = failed_access
    assert client.get("/health").status_code == 200
    try:
        readiness = client.get("/readiness", headers=_auth())
        assert readiness.status_code == 503
        assert readiness.json() == {"ok": False, "code": "database_unavailable"}
        assert "secret database details" not in readiness.text
        assert "secret database details" not in caplog.text
        assert any(
            getattr(record, "error_code", None) == "database_read_failed"
            for record in caplog.records
        )
    finally:
        read_only_service.verify_read_only_access = original


def test_supplied_uuid_correlation_id_is_preserved(configured_service):
    client, _, _ = configured_service
    correlation_id = "8b77cb46-b80d-47c9-9c3d-03040b3c6400"
    response = client.get(
        "/health",
        headers={"X-Correlation-ID": correlation_id},
    )
    assert response.headers["X-Correlation-ID"] == correlation_id


def test_startup_database_failure_is_sanitized(monkeypatch, caplog):
    for name, value in VALID_CONFIG.items():
        monkeypatch.setattr(settings, name, value)

    async def failed_pool(_database_url):
        raise RuntimeError(
            "postgresql://secret-user:secret-password@secret-host/secret-database"
        )

    monkeypatch.setattr("atlas.read_only_service.create_read_only_pool", failed_pool)
    with pytest.raises(
        RuntimeError,
        match=r"TraderNow read-only startup failed \(database\)",
    ) as captured:
        with TestClient(app):
            pass

    combined = f"{captured.value} {caplog.text}"
    for secret in (
        "secret-user",
        "secret-password",
        "secret-host",
        "secret-database",
        "postgresql://",
    ):
        assert secret not in combined
    assert any(
        getattr(record, "failure_category", None) == "database"
        for record in caplog.records
    )


@pytest.mark.parametrize("missing", VALID_CONFIG)
def test_incomplete_configuration_fails_before_pool(monkeypatch, missing):
    for name, value in VALID_CONFIG.items():
        monkeypatch.setattr(settings, name, value)
    monkeypatch.setattr(settings, missing, "")
    calls = 0

    async def forbidden_pool(_database_url):
        nonlocal calls
        calls += 1
        raise AssertionError("pool must not open")

    monkeypatch.setattr("atlas.read_only_service.create_read_only_pool", forbidden_pool)
    with pytest.raises((RuntimeError, ValueError)):
        with TestClient(app):
            pass
    assert calls == 0


def test_entrypoint_imports_no_monolith_or_write_side_modules():
    source = Path("atlas/read_only_service.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imports = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imports.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    forbidden = {
        "atlas.main",
        "atlas.db",
        "atlas.api.v1.webhook",
        "atlas.api.v1.market_state",
        "atlas.api.v1.trades",
        "atlas.services.pickmytrade",
        "atlas.ai",
        "atlas.api.v1.research",
        "migrations.runner",
    }
    assert imports.isdisjoint(forbidden)


def test_domain_and_application_do_not_import_service_entrypoint():
    for directory in (Path("atlas/trader_now"), Path("atlas/application")):
        for path in directory.glob("*.py"):
            assert "atlas.read_only_service" not in path.read_text(encoding="utf-8")
