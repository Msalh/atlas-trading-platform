"""
Route-level functional tests for GET /api/v1/rule-engine/latest, against the
in-memory repository via the `client` fixture (which overrides
require_api_key to a no-op, per its own docstring - real auth behavior is
tested centrally in tests/test_auth.py's raw_client, alongside every other
protected endpoint, not duplicated here).
"""
import pytest

from atlas.core.primitives import Symbol, Timeframe
from tests.conftest import market_state_payload


def _bar_payload(i, **overrides):
    """One 5-minute bar, i minutes*5 after 13:00, with every field every
    current fact needs to compute a real FactResult (not InsufficientData) -
    the wire-format analogue of test_rule_engine.py's _full_window helper."""
    payload = dict(
        event_id=f"e-api-{i}",
        timestamp=f"2026-07-18T13:{i:02d}:00Z",
        close=100.0 + i, open=100.0 + i - 1, high=100.0 + i + 5, low=100.0 + i - 5,
        volume_ratio=2.0, atr=10.0, distance_from_vwap_points=5.0,
        previous_day_high=200.0, previous_day_low=50.0,
        overnight_high=200.0, overnight_low=50.0,
    )
    payload.update(overrides)
    return payload


class TestGetLatestRuleEngineOutput:
    def test_no_market_state_returns_found_false(self, client):
        resp = client.get(
            "/api/v1/rule-engine/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["found"] is False
        assert body["data"] is None

    def test_complete_history_returns_seven_facts_in_registry_order(self, client):
        for i in range(20):
            client.post("/api/v1/market-state", json=market_state_payload(**_bar_payload(i)))

        resp = client.get(
            "/api/v1/rule-engine/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        data = body["data"]
        assert data["symbol"] == "MNQU6"
        assert data["timeframe"] == "5m"
        assert "schema_version" in data

        fact_names = [f["name"] for f in data["facts"]]
        assert fact_names == [
            "volume_spike", "displacement", "rejection", "trend_5m", "liquidity_sweep", "reclaim",
            "vwap_relationship",
        ]
        # a complete window - every fact should have computed, none insufficient
        assert all(f["status"] == "computed" for f in data["facts"])
        for f in data["facts"]:
            assert "definition_version" in f and f["definition_version"]

    def test_partial_history_returns_mixed_computed_and_insufficient_data(self, client):
        # only 5 of trend_5m's required 20 bars - trend_5m must report
        # insufficient_data while volume_spike (no window) still computes
        for i in range(5):
            client.post("/api/v1/market-state", json=market_state_payload(**_bar_payload(i)))

        resp = client.get(
            "/api/v1/rule-engine/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        body = resp.json()
        assert body["found"] is True
        facts_by_name = {f["name"]: f for f in body["data"]["facts"]}

        assert facts_by_name["trend_5m"]["status"] == "insufficient_data"
        assert "reason" in facts_by_name["trend_5m"]
        assert facts_by_name["volume_spike"]["status"] == "computed"
        assert facts_by_name["volume_spike"]["value"] is True

    def test_invalid_symbol_rejected(self, client):
        resp = client.get(
            "/api/v1/rule-engine/latest", params={"symbol": "  ", "timeframe": "5m"}
        )
        assert resp.status_code == 422

    def test_invalid_timeframe_rejected(self, client):
        resp = client.get(
            "/api/v1/rule-engine/latest", params={"symbol": "MNQU6", "timeframe": "3m"}
        )
        assert resp.status_code == 422

    def test_missing_query_params_rejected(self, client):
        resp = client.get("/api/v1/rule-engine/latest")
        assert resp.status_code == 422  # FastAPI's own required-query-param validation

    @pytest.mark.asyncio
    async def test_does_not_write_to_the_repository(self, client, market_state_repository):
        for i in range(3):
            client.post("/api/v1/market-state", json=market_state_payload(**_bar_payload(i)))
        before = await market_state_repository.get_history(Symbol("MNQU6"), Timeframe.M5, limit=100)

        client.get("/api/v1/rule-engine/latest", params={"symbol": "MNQU6", "timeframe": "5m"})

        after = await market_state_repository.get_history(Symbol("MNQU6"), Timeframe.M5, limit=100)
        assert before == after
