"""
Sprint 8.2, production-safety correction. Proves the real atlas.main
lifespan's own behavior for the exact scenario the correction exists to
prevent: RESEARCH_LEDGER_DIR missing in production/staging
(ENVIRONMENT=production, the default - "there is no separate staging
mode"). Research remains operationally isolated from trading (Principle
VIII.4, extended to the deployment layer): the app must start successfully
and every trading/webhook/status endpoint must keep working, but
research_ledger readiness must report degraded with reason
research_ledger_not_configured, no implicit write may occur anywhere, and
POST /api/v1/research/run must refuse with 503 rather than silently
writing to and reading from a path that would vanish on the next redeploy.

Does not touch a real Postgres - create_pool is replaced with a fake,
mirroring test_main_lifespan_snapshot_guard.py's own pattern exactly.
"""
from fastapi.testclient import TestClient

import atlas.main as main_module
from atlas.api.deps import get_repository
from atlas.repositories.memory import InMemoryTradeRepository


class _FakePool:
    async def close(self):
        pass


async def _fake_create_pool():
    return _FakePool()


async def test_required_2_production_without_research_ledger_dir_starts_but_degrades(monkeypatch):
    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "research_ledger_dir", "")
    monkeypatch.setattr(main_module.settings, "webhook_secret", "wh")
    monkeypatch.setattr(main_module.settings, "api_key", "key")
    monkeypatch.setattr(main_module.settings, "market_state_webhook_secret", "ms")
    monkeypatch.setattr(main_module, "create_pool", _fake_create_pool)

    app = main_module.app
    # Startup must complete without raising - a missing RESEARCH_LEDGER_DIR
    # is a research-only concern, never a reason to crash-loop the whole app
    # the way a missing WEBHOOK_SECRET/API_KEY correctly does.
    async with main_module.lifespan(app):
        readiness = app.state.ledger_readiness
        assert readiness.status == "degraded"
        assert readiness.reason == "research_ledger_not_configured"
        assert app.state.ledger_stores is None


async def test_required_6_no_implicit_write_under_data_research_in_production(monkeypatch, tmp_path):
    """No file or directory named "research" (or anything else) may be
    created anywhere under cwd when production has no RESEARCH_LEDGER_DIR -
    the exact false-persistence-success scenario the correction exists to
    prevent."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "research_ledger_dir", "")
    monkeypatch.setattr(main_module.settings, "webhook_secret", "wh")
    monkeypatch.setattr(main_module.settings, "api_key", "key")
    monkeypatch.setattr(main_module.settings, "market_state_webhook_secret", "ms")
    monkeypatch.setattr(main_module, "create_pool", _fake_create_pool)

    app = main_module.app
    async with main_module.lifespan(app):
        assert app.state.ledger_readiness.status == "degraded"

    assert list(tmp_path.iterdir()) == []


async def test_required_4_trading_and_status_routes_stay_available_when_ledger_degraded(monkeypatch):
    """Research readiness degrading must never take webhook/trades/status
    down with it - proven with a real TestClient request, not just an
    inspection of app.state."""
    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "research_ledger_dir", "")
    monkeypatch.setattr(main_module.settings, "webhook_secret", "wh")
    monkeypatch.setattr(main_module.settings, "api_key", "test-api-key")
    monkeypatch.setattr(main_module.settings, "market_state_webhook_secret", "ms")
    monkeypatch.setattr(main_module, "create_pool", _fake_create_pool)

    app = main_module.app
    async with main_module.lifespan(app):
        assert app.state.ledger_readiness.status == "degraded"

        # Deliberately TestClient(app) without the `with` context-manager
        # form - lifespan is already running (the outer `async with` above);
        # using the context-manager form here would trigger a second,
        # redundant lifespan invocation. Mirrors tests/conftest.py's own
        # client/raw_client fixtures exactly.
        repository = InMemoryTradeRepository()
        app.dependency_overrides[get_repository] = lambda: repository
        try:
            degraded_client = TestClient(app)
            status_resp = degraded_client.get(
                "/api/v1/status", headers={"Authorization": "Bearer test-api-key"},
            )
            assert status_resp.status_code == 200
            assert status_resp.json()["research_ledger"]["status"] == "degraded"

            trades_resp = degraded_client.get(
                "/api/v1/trades", headers={"Authorization": "Bearer test-api-key"},
            )
            assert trades_resp.status_code == 200

            health_resp = degraded_client.get("/health")
            assert health_resp.status_code == 200
        finally:
            app.dependency_overrides.pop(get_repository, None)


async def test_required_3_research_run_rejects_with_503_when_ledger_not_configured(monkeypatch):
    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "research_ledger_dir", "")
    monkeypatch.setattr(main_module.settings, "webhook_secret", "wh")
    monkeypatch.setattr(main_module.settings, "api_key", "test-api-key")
    monkeypatch.setattr(main_module.settings, "market_state_webhook_secret", "ms")
    monkeypatch.setattr(main_module, "create_pool", _fake_create_pool)

    app = main_module.app
    async with main_module.lifespan(app):
        no_override_client = TestClient(app)
        resp = no_override_client.post(
            "/api/v1/research/run", json={"mode": "smoke"},
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 503
        body = resp.json()
        assert body["ok"] is False
        assert body["reason"] == "research_ledger_not_configured"


async def test_required_5_production_with_explicit_writable_dir_stays_ready_and_smoke_passes(monkeypatch, tmp_path):
    monkeypatch.setattr(main_module.settings, "environment", "production")
    monkeypatch.setattr(main_module.settings, "research_ledger_dir", str(tmp_path / "research"))
    monkeypatch.setattr(main_module.settings, "webhook_secret", "wh")
    monkeypatch.setattr(main_module.settings, "api_key", "test-api-key")
    monkeypatch.setattr(main_module.settings, "market_state_webhook_secret", "ms")
    monkeypatch.setattr(main_module, "create_pool", _fake_create_pool)

    app = main_module.app
    async with main_module.lifespan(app):
        assert app.state.ledger_readiness.status == "ready"
        assert app.state.ledger_stores is not None

        ready_client = TestClient(app)
        resp = ready_client.post(
            "/api/v1/research/run", json={"mode": "smoke"},
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert all(body["steps"].values())
        assert body["verdict"] == "supported"


def teardown_module():
    # These tests deliberately mutate module-level dependency_overrides via
    # a real TestClient - make sure no override leaks into unrelated tests
    # that run after this file in the same session.
    from atlas.main import app
    app.dependency_overrides.clear()
