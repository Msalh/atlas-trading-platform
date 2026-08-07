"""FastAPI lifespan assembly and concrete repository read-path tests."""

from types import SimpleNamespace

import pytest

import atlas.main as main_module
from atlas.api.deps import get_trader_now_application


class FakeCursor:
    def __init__(self, statements):
        self.statements = statements

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return None

    async def execute(self, sql, params=None):
        self.statements.append((" ".join(sql.split()), params))

    async def fetchall(self):
        return []


class FakeConnection(FakeCursor):
    def cursor(self, **kwargs):
        return FakeCursor(self.statements)


class FakePool:
    def __init__(self):
        self.statements = []
        self.connection_instance = FakeConnection(self.statements)
        self.close_calls = 0

    def connection(self):
        return self.connection_instance

    async def close(self):
        self.close_calls += 1


def configure(monkeypatch, *, environment="development"):
    values = {
        "environment": environment,
        "research_ledger_dir": "",
        "webhook_secret": "webhook-secret",
        "api_key": "api-secret",
        "trader_now_results_api_key": "results-api-secret",
        "market_state_webhook_secret": "market-secret",
        "trader_now_product": "MNQ",
        "trader_now_market_data_provider": "tradingview",
        "trader_now_market_data_series_symbol": "MNQ1!",
        "trader_now_market_data_series_type": "continuous",
        "trader_now_series_resolution_version": "tradingview-mnq1.v1",
        "trader_now_series_effective_date": "2026-07-13",
        "trader_now_calendar_version": "cme-equity-index.2026.v1",
        "trader_now_holidays_json": "[]",
        "trader_now_early_closes_json": "{}",
    }
    for name, value in values.items():
        monkeypatch.setattr(main_module.settings, name, value)


@pytest.mark.asyncio
async def test_startup_builds_one_application_route_gets_same_instance_and_shutdown_closes_pool(
    monkeypatch,
):
    configure(monkeypatch)
    pool = FakePool()

    async def create_pool():
        return pool

    calls = []
    real_builder = main_module.build_trader_now_application

    def build_once(**kwargs):
        result = real_builder(**kwargs)
        calls.append(result)
        return result

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    monkeypatch.setattr(main_module, "build_trader_now_application", build_once)

    async with main_module.lifespan(main_module.app):
        assembled = main_module.app.state.trader_now_application
        provided = get_trader_now_application(SimpleNamespace(app=main_module.app))
        assert calls == [assembled]
        assert provided is assembled
        assert not hasattr(main_module.app.state, "manual_ai_explanation_service")

        result = await assembled.compose_latest(
            symbol="MNQ",
            timeframe="5m",
            strategy_id="displacement_volume_context",
        )
        assert result.risk is None
        assert result.availability["market"].status.value == "no_data"

    assert pool.close_calls == 1
    sql = [statement for statement, _ in pool.statements]
    assert sum(statement == "SELECT 1" for statement in sql) == 1
    assert (
        sum(
            statement.startswith("SELECT * FROM market_state_events")
            for statement in sql
        )
        == 1
    )
    assert not any(
        token in statement.upper()
        for statement in sql
        for token in ("INSERT ", "UPDATE ", "DELETE ", "TRUNCATE ", "ALTER ")
    )


@pytest.mark.asyncio
async def test_lifespan_attaches_manual_ai_service_only_for_its_existing_dependency(
    monkeypatch,
):
    configure(monkeypatch)
    pool = FakePool()
    service = object()

    async def create_pool():
        return pool

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    monkeypatch.setattr(
        main_module, "build_manual_ai_explanation_service", lambda _settings: service
    )

    async with main_module.lifespan(main_module.app):
        assert main_module.app.state.manual_ai_explanation_service is service

    assert not hasattr(main_module.app.state, "manual_ai_explanation_service")
    assert pool.close_calls == 1


@pytest.mark.asyncio
async def test_partial_startup_failure_never_retains_manual_ai_service(monkeypatch):
    configure(monkeypatch)
    pool = FakePool()
    manual_builder_calls = 0

    async def create_pool():
        return pool

    def build_manual(_settings):
        nonlocal manual_builder_calls
        manual_builder_calls += 1
        return object()

    def fail_persistence(_settings):
        raise RuntimeError("sanitized startup failure")

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    monkeypatch.setattr(main_module, "build_manual_ai_explanation_service", build_manual)
    monkeypatch.setattr(main_module, "build_ai_persistence_runtime", fail_persistence)

    with pytest.raises(RuntimeError, match="sanitized startup failure"):
        async with main_module.lifespan(main_module.app):
            pass

    assert manual_builder_calls == 0
    assert not hasattr(main_module.app.state, "manual_ai_explanation_service")
    assert pool.close_calls == 1


@pytest.mark.asyncio
async def test_repeated_lifespan_cycles_attach_and_remove_manual_service(monkeypatch):
    configure(monkeypatch)
    pools = []
    service = object()

    async def create_pool():
        pool = FakePool()
        pools.append(pool)
        return pool

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    monkeypatch.setattr(
        main_module, "build_manual_ai_explanation_service", lambda _settings: service
    )

    for _ in range(2):
        async with main_module.lifespan(main_module.app):
            assert main_module.app.state.manual_ai_explanation_service is service
        assert not hasattr(main_module.app.state, "manual_ai_explanation_service")

    assert [pool.close_calls for pool in pools] == [1, 1]


@pytest.mark.asyncio
async def test_missing_production_contract_configuration_fails_before_database(
    monkeypatch,
):
    configure(monkeypatch, environment="production")
    monkeypatch.setattr(main_module.settings, "trader_now_market_data_series_symbol", "")
    pool_called = False

    async def create_pool():
        nonlocal pool_called
        pool_called = True
        return FakePool()

    monkeypatch.setattr(main_module, "create_pool", create_pool)

    with pytest.raises(RuntimeError, match="TRADER_NOW_MARKET_DATA_SERIES_SYMBOL"):
        async with main_module.lifespan(main_module.app):
            pass
    assert pool_called is False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        (
            "trader_now_market_data_series_symbol",
            "MNQU6",
            "market-data series must be exactly",
        ),
        (
            "trader_now_holidays_json",
            "not-json",
            "valid JSON",
        ),
        (
            "trader_now_early_closes_json",
            '{"2026-11-27":"17:30"}',
            "early close",
        ),
    ],
)
async def test_invalid_trader_now_configuration_fails_before_database(
    monkeypatch,
    field,
    value,
    message,
):
    configure(monkeypatch, environment="production")
    monkeypatch.setattr(main_module.settings, field, value)
    pool_called = False

    async def create_pool():
        nonlocal pool_called
        pool_called = True
        return FakePool()

    monkeypatch.setattr(main_module, "create_pool", create_pool)

    with pytest.raises(ValueError, match=message):
        async with main_module.lifespan(main_module.app):
            pass
    assert pool_called is False
