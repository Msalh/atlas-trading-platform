"""
Route-level functional tests for GET /api/v1/market-state/latest and
GET /api/v1/market-state/history, against the in-memory repository via the
`client` fixture (which overrides require_api_key to a no-op, per its own
docstring - real auth behavior for these paths is tested centrally in
tests/test_auth.py's raw_client, alongside every other protected endpoint,
not duplicated here).
"""
from tests.conftest import market_state_payload


class TestGetLatest:
    def test_no_data_returns_found_false(self, client):
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["found"] is False
        assert body["data"] is None

    def test_ingested_data_is_readable(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(event_id="e-read-1"))
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        body = resp.json()
        assert body["found"] is True
        assert body["data"]["event_id"] == "e-read-1"
        assert body["data"]["close"] == 20125.75

    def test_returns_the_actual_latest_of_several(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-early", timestamp="2026-07-18T13:35:00Z",
        ))
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-late", timestamp="2026-07-18T13:40:00Z",
        ))
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.json()["data"]["event_id"] == "e-late"

    def test_different_symbol_not_returned(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(event_id="e-x", symbol="MNQZ6"))
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.json()["found"] is False

    def test_invalid_timeframe_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "MNQU6", "timeframe": "3m"}
        )
        assert resp.status_code == 422

    def test_blank_symbol_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "", "timeframe": "5m"}
        )
        assert resp.status_code == 422

    def test_missing_query_params_rejected(self, client):
        resp = client.get("/api/v1/market-state/latest")
        assert resp.status_code == 422  # FastAPI's own required-query-param validation


class TestGetHistory:
    def test_no_data_returns_empty_list(self, client):
        resp = client.get(
            "/api/v1/market-state/history", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["count"] == 0
        assert body["data"] == []

    def test_returns_most_recent_first(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-h1", timestamp="2026-07-18T13:35:00Z",
        ))
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-h2", timestamp="2026-07-18T13:40:00Z",
        ))
        resp = client.get(
            "/api/v1/market-state/history", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        body = resp.json()
        assert [d["event_id"] for d in body["data"]] == ["e-h2", "e-h1"]
        assert body["count"] == 2

    def test_limit_respected(self, client):
        for i in range(5):
            client.post("/api/v1/market-state", json=market_state_payload(
                event_id=f"e-lim-{i}", timestamp=f"2026-07-18T13:{30+i}:00Z",
            ))
        resp = client.get(
            "/api/v1/market-state/history",
            params={"symbol": "MNQU6", "timeframe": "5m", "limit": 2},
        )
        assert resp.json()["count"] == 2

    def test_limit_default_is_100(self, client):
        resp = client.get(
            "/api/v1/market-state/history", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.status_code == 200  # no limit provided, default applies without error

    def test_limit_above_max_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/history",
            params={"symbol": "MNQU6", "timeframe": "5m", "limit": 10000},
        )
        assert resp.status_code == 422

    def test_limit_below_minimum_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/history",
            params={"symbol": "MNQU6", "timeframe": "5m", "limit": 0},
        )
        assert resp.status_code == 422

    def test_invalid_symbol_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/history", params={"symbol": "  ", "timeframe": "5m"}
        )
        assert resp.status_code == 422


class TestGetIntegrity:
    def test_no_data_returns_zero_gaps(self, client):
        resp = client.get(
            "/api/v1/market-state/integrity", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["checked_count"] == 0
        assert body["gap_count"] == 0
        assert body["gaps"] == []

    def test_evenly_spaced_bars_report_no_gaps(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-int-1", timestamp="2026-07-18T13:30:00Z",
        ))
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-int-2", timestamp="2026-07-18T13:35:00Z",
        ))
        resp = client.get(
            "/api/v1/market-state/integrity", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        body = resp.json()
        assert body["checked_count"] == 2
        assert body["gap_count"] == 0

    def test_missing_bar_is_reported_as_a_gap(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-gap-1", timestamp="2026-07-18T13:30:00Z",
        ))
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-gap-2", timestamp="2026-07-18T13:40:00Z",
        ))
        resp = client.get(
            "/api/v1/market-state/integrity", params={"symbol": "MNQU6", "timeframe": "5m"}
        )
        body = resp.json()
        assert body["gap_count"] == 1
        assert body["gaps"][0]["estimated_missing_bars"] == 1

    def test_invalid_timeframe_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/integrity", params={"symbol": "MNQU6", "timeframe": "3m"}
        )
        assert resp.status_code == 422

    def test_invalid_symbol_rejected(self, client):
        resp = client.get(
            "/api/v1/market-state/integrity", params={"symbol": "  ", "timeframe": "5m"}
        )
        assert resp.status_code == 422


class TestGetExport:
    def _params(self, **overrides):
        params = {
            "symbol": "MNQU6", "timeframe": "5m",
            "start": "2026-07-18T00:00:00Z", "end": "2026-07-19T00:00:00Z",
        }
        params.update(overrides)
        return params

    def test_no_data_returns_empty_export(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params())
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["count"] == 0
        assert body["gap_count"] == 0
        assert body["data"] == []

    def test_ingested_data_is_exported_chronologically(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-exp-2", timestamp="2026-07-18T13:40:00Z",
        ))
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-exp-1", timestamp="2026-07-18T13:35:00Z",
        ))
        resp = client.get("/api/v1/market-state/export", params=self._params())
        body = resp.json()
        assert [d["event_id"] for d in body["data"]] == ["e-exp-1", "e-exp-2"]
        assert body["count"] == 2

    def test_missing_bar_is_reported_as_a_gap(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-exp-gap-1", timestamp="2026-07-18T13:30:00Z",
        ))
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-exp-gap-2", timestamp="2026-07-18T13:40:00Z",
        ))
        resp = client.get("/api/v1/market-state/export", params=self._params())
        assert resp.json()["gap_count"] == 1

    def test_data_outside_range_excluded(self, client):
        client.post("/api/v1/market-state", json=market_state_payload(
            event_id="e-exp-out", timestamp="2026-07-10T13:30:00Z",
        ))
        resp = client.get("/api/v1/market-state/export", params=self._params())
        assert resp.json()["data"] == []

    def test_invalid_timeframe_rejected(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params(timeframe="3m"))
        assert resp.status_code == 422

    def test_invalid_symbol_rejected(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params(symbol="  "))
        assert resp.status_code == 422

    def test_invalid_start_timestamp_rejected(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params(start="not-a-date"))
        assert resp.status_code == 422

    def test_naive_start_timestamp_rejected(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params(start="2026-07-18T00:00:00"))
        assert resp.status_code == 422

    def test_start_after_end_rejected(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params(
            start="2026-07-19T00:00:00Z", end="2026-07-18T00:00:00Z",
        ))
        assert resp.status_code == 422

    def test_limit_above_max_rejected(self, client):
        resp = client.get("/api/v1/market-state/export", params=self._params(limit=100000))
        assert resp.status_code == 422
