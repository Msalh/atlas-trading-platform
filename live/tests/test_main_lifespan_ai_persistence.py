"""Phase 18H-1 application-lifespan qualification without provider invocation."""

from __future__ import annotations

import pytest

import atlas.main as main_module
from atlas.ai_persistence_runtime import AIPersistenceStartupError


class _FakeApplicationPool:
    def __init__(self) -> None:
        self.close_calls = 0

    async def close(self) -> None:
        self.close_calls += 1


def _configure_development(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(main_module.settings, "environment", "development")
    monkeypatch.setattr(
        main_module.settings, "research_ledger_dir", str(tmp_path / "research")
    )
    for name in (
        "trader_now_product",
        "trader_now_market_data_provider",
        "trader_now_market_data_series_symbol",
        "trader_now_market_data_series_type",
        "trader_now_series_resolution_version",
        "trader_now_series_effective_date",
        "trader_now_calendar_version",
        "trader_now_holidays_json",
        "trader_now_early_closes_json",
    ):
        monkeypatch.setattr(main_module.settings, name, "")


async def test_lifespan_publishes_disabled_runtime_and_closes_once(
    monkeypatch, tmp_path
) -> None:
    _configure_development(monkeypatch, tmp_path)
    monkeypatch.setattr(main_module.settings, "atlas_ai_persistence_mode", "disabled")
    monkeypatch.setattr(
        main_module.settings, "atlas_ai_persistence_local_disposable_test", "false"
    )
    pool = _FakeApplicationPool()

    async def create_pool():
        return pool

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    try:
        async with main_module.lifespan(main_module.app):
            runtime = main_module.app.state.ai_persistence_runtime
            assert runtime.state == "disabled"
            assert runtime.coordinator is None
    finally:
        for name in ("ai_persistence_runtime", "started_at"):
            if hasattr(main_module.app.state, name):
                delattr(main_module.app.state, name)
    assert runtime.state == "shutdown"
    assert pool.close_calls == 1


async def test_lifespan_closes_existing_pool_on_persistence_startup_failure(
    monkeypatch, tmp_path
) -> None:
    _configure_development(monkeypatch, tmp_path)
    pool = _FakeApplicationPool()

    async def create_pool():
        return pool

    def fail_startup(_settings):
        raise AIPersistenceStartupError("schema_mismatch")

    monkeypatch.setattr(main_module, "create_pool", create_pool)
    monkeypatch.setattr(main_module, "build_ai_persistence_runtime", fail_startup)
    try:
        with pytest.raises(AIPersistenceStartupError) as caught:
            async with main_module.lifespan(main_module.app):
                pytest.fail("startup unexpectedly succeeded")
    finally:
        for name in ("ai_persistence_runtime", "started_at"):
            if hasattr(main_module.app.state, name):
                delattr(main_module.app.state, name)
    assert caught.value.classification == "schema_mismatch"
    assert pool.close_calls == 1
