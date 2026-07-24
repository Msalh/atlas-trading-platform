"""Real PostgreSQL production-boundary verification for Phase 13A.

This test never substitutes a repository or pool. It is collected only when an
operator supplies the dedicated role URL and exact persisted 288-row contract.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from psycopg import sql

from atlas.config import settings
from atlas.core.primitives import Symbol, Timeframe
from atlas.read_only_service import app

READ_ONLY_URL = os.environ.get("TRADER_NOW_READ_ONLY_TEST_DATABASE_URL", "")
EMPTY_READ_ONLY_URL = os.environ.get(
    "TRADER_NOW_EMPTY_READ_ONLY_TEST_DATABASE_URL", ""
)
CONTRACT = os.environ.get("TRADER_NOW_READ_ONLY_TEST_CONTRACT_SYMBOL", "")

pytestmark = pytest.mark.skipif(
    not READ_ONLY_URL or not EMPTY_READ_ONLY_URL or not CONTRACT,
    reason=(
        "real read-only PostgreSQL verification requires "
        "TRADER_NOW_READ_ONLY_TEST_DATABASE_URL, "
        "TRADER_NOW_EMPTY_READ_ONLY_TEST_DATABASE_URL, and "
        "TRADER_NOW_READ_ONLY_TEST_CONTRACT_SYMBOL"
    ),
)


@pytest.fixture
def production_settings(monkeypatch):
    values = {
        "environment": "production",
        "database_url": READ_ONLY_URL,
        "api_key": "phase-13a-test-key",
        "trader_now_service_mode": "read_only",
        "trader_now_product": "MNQ",
        "trader_now_market_data_provider": "tradingview",
        "trader_now_market_data_series_symbol": CONTRACT,
        "trader_now_market_data_series_type": "continuous",
        "trader_now_series_resolution_version": "phase-14.real-postgres.v1",
        "trader_now_series_effective_date": "2026-07-13",
        "trader_now_calendar_version": "phase-13a.cme.v1",
        "trader_now_holidays_json": "[]",
        "trader_now_early_closes_json": "{}",
        "trader_now_build_commit": "1f10332a792c042dfab0bebb987f2e0610e00272",
        "trader_now_release_tag": "trader-now-read-only-v1.0.0",
        "trader_now_build_timestamp": "2026-07-24T10:00:00Z",
    }
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)
    return values


def _auth(api_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {api_key}"}


def test_real_postgres_full_service_boundary(production_settings):
    with TestClient(app) as client:
        pool = app.state.pool
        repository = app.state.market_state_repository

        assert client.get("/health").status_code == 200
        assert client.get("/readiness").status_code == 401
        assert (
            client.get(
                "/readiness",
                headers=_auth(production_settings["api_key"]),
            ).status_code
            == 200
        )

        rows = client.portal.call(
            repository.get_history,
            Symbol(CONTRACT),
            Timeframe.M5,
            288,
        )
        assert len(rows) == 288

        path = (
            "/api/v1/trader-now?symbol=MNQ&timeframe=5m"
            "&strategy_id=displacement_volume_context"
        )
        response = client.get(path, headers=_auth(production_settings["api_key"]))
        assert response.status_code == 200
        assert response.json()["schema_version"] == "trader_now_response.v2"
        assert response.headers["X-Correlation-ID"]

        async def audit_role_and_reject_writes():
            async with pool.connection() as connection:
                cursor = await connection.execute(
                    """
                    SELECT
                        role.rolsuper,
                        role.rolinherit,
                        role.rolcreatedb,
                        role.rolcreaterole,
                        role.rolreplication,
                        role.rolbypassrls,
                        has_database_privilege(
                            current_user, current_database(), 'CONNECT'
                        ),
                        has_schema_privilege(
                            current_user, current_schema(), 'USAGE'
                        ),
                        has_schema_privilege(
                            current_user, current_schema(), 'CREATE'
                        ),
                        has_table_privilege(
                            current_user, 'market_state_events', 'SELECT'
                        ),
                        has_table_privilege(
                            current_user, 'market_state_events', 'INSERT'
                        ),
                        has_table_privilege(
                            current_user, 'market_state_events', 'UPDATE'
                        ),
                        has_table_privilege(
                            current_user, 'market_state_events', 'DELETE'
                        ),
                        has_table_privilege(
                            current_user, 'market_state_events', 'TRUNCATE'
                        )
                    FROM pg_roles AS role
                    WHERE role.rolname = current_user
                    """
                )
                privileges = await cursor.fetchone()
                assert privileges == (
                    False,
                    False,
                    False,
                    False,
                    False,
                    False,
                    True,
                    True,
                    False,
                    True,
                    False,
                    False,
                    False,
                    False,
                )

                sequence_cursor = await connection.execute(
                    """
                    SELECT COALESCE(
                        bool_or(
                            has_sequence_privilege(
                                current_user,
                                quote_ident(sequence_schema) || '.' ||
                                    quote_ident(sequence_name),
                                'USAGE'
                            )
                        ),
                        FALSE
                    )
                    FROM information_schema.sequences
                    WHERE sequence_schema = current_schema()
                    """
                )
                assert await sequence_cursor.fetchone() == (False,)

                for statement in (
                    sql.SQL("INSERT INTO market_state_events DEFAULT VALUES"),
                    sql.SQL("UPDATE market_state_events SET event_id = event_id"),
                    sql.SQL("DELETE FROM market_state_events"),
                    sql.SQL("TRUNCATE market_state_events"),
                    sql.SQL("ALTER TABLE market_state_events ADD COLUMN forbidden int"),
                    sql.SQL("CREATE TABLE forbidden_phase_13a (id int)"),
                ):
                    with pytest.raises(Exception):
                        await connection.execute(statement)
                    await connection.rollback()

        client.portal.call(audit_role_and_reject_writes)

    assert pool.closed


def test_real_postgres_no_data_remains_http_200(production_settings, monkeypatch):
    from atlas.application.trader_now_production import TraderNowProductionConfig

    monkeypatch.setattr(settings, "trader_now_market_data_series_symbol", "MNQZ99")
    with pytest.raises(
        ValueError,
        match="market-data series must be exactly 'MNQ1!'",
    ):
        TraderNowProductionConfig.from_settings(settings)

    monkeypatch.setattr(settings, "database_url", EMPTY_READ_ONLY_URL)
    monkeypatch.setattr(settings, "trader_now_market_data_series_symbol", "MNQ1!")
    with TestClient(app) as client:
        pool = app.state.pool
        repository = app.state.market_state_repository
        rows = client.portal.call(
            repository.get_history,
            Symbol("MNQ1!"),
            Timeframe.M5,
            288,
        )
        assert rows == []

        async def reject_disposable_writes():
            async with pool.connection() as connection:
                cursor = await connection.execute(
                    """
                    SELECT
                        has_table_privilege(
                            current_user, 'market_state_events', 'SELECT'
                        ),
                        has_table_privilege(
                            current_user, 'market_state_events', 'INSERT'
                        ),
                        has_schema_privilege(
                            current_user, current_schema(), 'CREATE'
                        )
                    """
                )
                assert await cursor.fetchone() == (True, False, False)
                with pytest.raises(Exception):
                    await connection.execute(
                        "INSERT INTO market_state_events DEFAULT VALUES"
                    )
                await connection.rollback()

        client.portal.call(reject_disposable_writes)

        path = (
            "/api/v1/trader-now?symbol=MNQ&timeframe=5m"
            "&strategy_id=displacement_volume_context"
        )
        response = client.get(path, headers=_auth(production_settings["api_key"]))

    assert pool.closed
    assert response.status_code == 200
    assert response.json()["schema_version"] == "trader_now_response.v2"
    assert response.json()["availability"]["market"]["status"] == "no_data"
    assert response.json()["identity"]["product"] == "MNQ"
    assert response.json()["market"]["market_data_series"] is None
    assert response.json()["market"]["listed_instrument"] is None
    assert response.headers["X-Correlation-ID"]
