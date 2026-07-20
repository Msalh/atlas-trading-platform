"""
UI v2. Route-level tests for GET /api/v1/setup-engine/latest and
GET /api/v1/setup-engine/episodes/live, against the in-memory repository
via the shared `client` fixture (same pattern as test_rule_engine_api.py).
"""
from atlas.live_view.episode_projector import HARD_MAX_WINDOW
from tests.conftest import market_state_payload


def _timestamp(i: int) -> str:
    """Genuine 5-minute-cadence timestamps, unlike test_rule_engine_api
    .py's own _bar_payload (1-minute apart, tolerated there only because
    its tests never exceed a single fact's required_history far enough to
    hit window_integrity's contiguity check the way a 25-bar series does
    here)."""
    hour = 13 + i // 12
    minute = (i % 12) * 5
    return f"2026-07-18T{hour:02d}:{minute:02d}:00Z"


def _active_bar_payload(i, **overrides):
    """A bar with displacement/volume_spike genuinely computable and
    True: (high-low)/atr > 1.5 and volume_ratio > 1.5 - the real Rule
    Engine inputs, not the unused MarketState wire fields."""
    payload = dict(
        event_id=f"e-api-{i}",
        timestamp=_timestamp(i),
        close=100.0 + i, open=100.0 + i - 1, high=100.0 + i + 50, low=100.0 + i - 50,
        volume_ratio=2.0, atr=10.0, distance_from_vwap_points=5.0,
        previous_day_high=200.0, previous_day_low=50.0,
        overnight_high=200.0, overnight_low=50.0,
    )
    payload.update(overrides)
    return payload


def _inactive_bar_payload(i, **overrides):
    payload = dict(
        event_id=f"e-api-{i}",
        timestamp=_timestamp(i),
        close=100.0 + i, open=100.0 + i - 1, high=100.0 + i + 1, low=100.0 + i - 1,
        volume_ratio=1.0, atr=10.0, distance_from_vwap_points=5.0,
        previous_day_high=200.0, previous_day_low=50.0,
        overnight_high=200.0, overnight_low=50.0,
    )
    payload.update(overrides)
    return payload


class TestGetLatestSetupEngineOutput:
    def test_no_market_state_returns_found_false(self, client):
        resp = client.get("/api/v1/setup-engine/latest", params={"symbol": "MNQU6", "timeframe": "5m"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["found"] is False
        assert body["data"] is None

    def test_complete_history_returns_four_setups_and_a_live_envelope(self, client):
        for i in range(25):
            client.post("/api/v1/market-state", json=market_state_payload(**_active_bar_payload(i)))

        resp = client.get("/api/v1/setup-engine/latest", params={"symbol": "MNQU6", "timeframe": "5m"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert body["envelope"]["source_track"] == "live"
        assert body["envelope"]["symbol"] == "MNQU6"
        assert "data_as_of" in body["envelope"]

        setup_names = [s["name"] for s in body["data"]["setups"]]
        assert setup_names == [
            "displacement_with_volume_confirmation", "liquidity_sweep_with_volume_confirmation",
            "sustained_displacement_streak", "vwap_extension_with_volume_confirmation",
        ]

    def test_invalid_symbol_rejected(self, client):
        resp = client.get("/api/v1/setup-engine/latest", params={"symbol": "  ", "timeframe": "5m"})
        assert resp.status_code == 422

    def test_missing_query_params_rejected(self, client):
        resp = client.get("/api/v1/setup-engine/latest")
        assert resp.status_code == 422


class TestGetLiveEpisodes:
    def test_no_market_state_returns_found_false(self, client):
        resp = client.get("/api/v1/setup-engine/episodes/live", params={"symbol": "MNQU6", "timeframe": "5m"})
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is False

    def test_returns_window_setups_segments_and_activation_events(self, client):
        for i in range(10):
            client.post("/api/v1/market-state", json=market_state_payload(**_inactive_bar_payload(i)))
        for i in range(10, 15):
            client.post("/api/v1/market-state", json=market_state_payload(**_active_bar_payload(i)))

        resp = client.get(
            "/api/v1/setup-engine/episodes/live", params={"symbol": "MNQU6", "timeframe": "5m", "window": 20},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["found"] is True
        assert body["envelope"]["source_track"] == "live"
        assert "window" in body and body["window"]["requested"] == 20
        assert "segments" in body
        assert "activation_events" in body

        snapshot = body["setups"]["displacement_with_volume_confirmation"]
        assert snapshot["current_episode"] is not None
        assert snapshot["current_episode"]["is_active"] is True
        assert snapshot["current_episode"]["end_timestamp_observed"] is None
        assert snapshot["current_episode"]["termination_reason"] is None

    def test_window_is_bounded_to_the_hard_maximum(self, client):
        for i in range(5):
            client.post("/api/v1/market-state", json=market_state_payload(**_inactive_bar_payload(i)))
        resp = client.get(
            "/api/v1/setup-engine/episodes/live",
            params={"symbol": "MNQU6", "timeframe": "5m", "window": HARD_MAX_WINDOW * 10},
        )
        assert resp.status_code == 200
        # never crashes or hangs trying to fetch an absurd window - bounded server-side

    def test_second_identical_request_is_served_from_cache(self, client):
        for i in range(5):
            client.post("/api/v1/market-state", json=market_state_payload(**_active_bar_payload(i)))
        resp_1 = client.get("/api/v1/setup-engine/episodes/live", params={"symbol": "MNQU6", "timeframe": "5m"})
        resp_2 = client.get("/api/v1/setup-engine/episodes/live", params={"symbol": "MNQU6", "timeframe": "5m"})
        assert resp_1.json()["envelope"]["data_as_of"] == resp_2.json()["envelope"]["data_as_of"]
        assert resp_1.json()["setups"] == resp_2.json()["setups"]

    def test_invalid_timeframe_rejected(self, client):
        resp = client.get(
            "/api/v1/setup-engine/episodes/live", params={"symbol": "MNQU6", "timeframe": "3m"},
        )
        assert resp.status_code == 422
