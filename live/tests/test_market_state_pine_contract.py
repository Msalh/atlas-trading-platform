"""
Contract verification for pine/MNQU6_market_state_v1.pine (Sprint 5) - not a
Pine test (no automated Pine test framework exists, and this file makes no
claim that one does), but the closest honest equivalent: these payloads are
hand-transcribed to match, field-for-field, exactly what the Pine script's
f_buildPayload() template produces for a few realistic scenarios, then run
through the real, already-tested ingestion HTTP path (the same one Sprint 3's
own tests use) - proving the JSON *shape* the Pine script will send is valid
against the real backend contract, not a mock of it.

This does NOT prove the Pine script itself is bug-free (wrong EMA lengths, a
session-boundary edge case, etc.) - only real chart observation in TradingView
can do that. See the Sprint 5 write-up's manual verification protocol for the
part of this Sprint that cannot be automated at all.
"""
from tests.conftest import TEST_MARKET_STATE_SECRET


def _pine_shaped_payload(**overrides):
    """Mirrors MNQU6_market_state_v1.pine's f_buildPayload() output exactly -
    same field set, same null/false defaults for the deliberately-deferred
    fields (see that script's own module docstring), same string formats
    (ISO-8601 with a literal Z, "5m" not "5")."""
    payload = {
        "schema_version": "1.0",
        "event_id": "MNQU6:5m:2026-07-18T13:35:00Z",
        "symbol": "MNQU6",
        "source": "tradingview",
        "timeframe": "5m",
        "timestamp": "2026-07-18T13:35:00Z",
        "bar_status": "closed",
        "event_type": "bar_closed",
        "secret": TEST_MARKET_STATE_SECRET,
        "open": 20120.00, "high": 20128.50, "low": 20118.00, "close": 20125.75, "volume": 4210,
        "session_name": "RTH", "is_rth": True, "trading_date": "2026-07-18",
        "rth_open": 20100.00,
        "previous_day_high": 20180.00, "previous_day_low": 20050.25,
        "overnight_high": 20140.00, "overnight_low": 20080.50,
        "vwap": 20118.50, "distance_from_vwap_points": 7.25, "atr": 42.5, "volume_ratio": 1.35,
        "nearest_liquidity_level": 20180.00, "nearest_liquidity_type": "previous_day_high",
        "distance_to_liquidity_ticks": 217,
        "overnight_high_status": None, "overnight_low_status": None,
        "previous_day_high_status": None, "previous_day_low_status": None,
        "trend_1m": "up", "trend_5m": "up", "trend_15m": "flat", "trend_1h": "down",
        "liquidity_sweep": False, "reclaim": False, "rejection": False,
        "displacement": False, "volume_spike": False,
    }
    payload.update(overrides)
    return payload


class TestRealisticRthBar:
    def test_fully_populated_rth_bar_accepted(self, client):
        resp = client.post("/api/v1/market-state", json=_pine_shaped_payload())
        assert resp.status_code == 200, resp.json()

    def test_persisted_and_readable_back(self, client):
        client.post("/api/v1/market-state", json=_pine_shaped_payload(event_id="MNQU6:5m:pine-1"))
        resp = client.get(
            "/api/v1/market-state/latest", params={"symbol": "MNQU6", "timeframe": "5m"},
            headers={"Authorization": "Bearer test-api-key"},
        )
        assert resp.json()["data"]["event_id"] == "MNQU6:5m:pine-1"


class TestRealisticOvernightBar:
    """Overnight bars have no rth_open yet (RTH hasn't started this session),
    and Pine's f_num() would emit JSON null for it - exactly what na(x) does
    in the script for a var that hasn't been set yet this session."""

    def test_overnight_bar_with_null_rth_open_accepted(self, client):
        payload = _pine_shaped_payload(
            event_id="MNQU6:5m:pine-overnight",
            session_name="OVERNIGHT", is_rth=False,
            rth_open=None,
            timestamp="2026-07-18T02:35:00Z",
        )
        resp = client.post("/api/v1/market-state", json=payload)
        assert resp.status_code == 200, resp.json()


class TestEarlySessionBarWithUncomputedTrend:
    """Early in a fresh 1h bar's data history (or right after the indicator
    is first added to a chart), request.security's own [1]-offset EMA values
    can legitimately be na - f_trendLabel already returns na in that case,
    which f_str() must render as JSON null, not a Python-side crash."""

    def test_null_trend_fields_accepted(self, client):
        payload = _pine_shaped_payload(
            event_id="MNQU6:5m:pine-early",
            trend_1m=None, trend_5m=None, trend_15m=None, trend_1h=None,
        )
        resp = client.post("/api/v1/market-state", json=payload)
        assert resp.status_code == 200, resp.json()


class TestNoLiquidityLevelYet:
    """Before any reference level exists (e.g. the very first bars of a fresh
    instrument history), f_nearestLevel returns na for all three outputs."""

    def test_null_liquidity_fields_accepted(self, client):
        payload = _pine_shaped_payload(
            event_id="MNQU6:5m:pine-no-liquidity",
            nearest_liquidity_level=None, nearest_liquidity_type=None,
            distance_to_liquidity_ticks=None,
            previous_day_high=None, previous_day_low=None,
            overnight_high=None, overnight_low=None, rth_open=None,
        )
        resp = client.post("/api/v1/market-state", json=payload)
        assert resp.status_code == 200, resp.json()


class TestOffTickGuardStillAppliesToPineShapedData:
    """Confirms this contract-shaped payload doesn't accidentally bypass
    validation this project already relies on - the Pine shape must still be
    rejected if a price value is ever off-tick (e.g. a future tick-size input
    misconfiguration), not silently accepted because it "looks like" real
    Pine output."""

    def test_off_tick_close_still_rejected(self, client):
        resp = client.post("/api/v1/market-state", json=_pine_shaped_payload(
            event_id="MNQU6:5m:pine-off-tick", close=20125.80,
        ))
        assert resp.status_code == 422


class TestDuplicateBarRedelivery:
    """TradingView occasionally redelivers an alert (documented platform
    behavior, not a bug in this script) - the deterministic event_id
    construction (symbol:timeframe:timestamp) must make that safe."""

    def test_identical_redelivered_payload_is_idempotent(self, client):
        payload = _pine_shaped_payload(event_id="MNQU6:5m:pine-redelivered")
        first = client.post("/api/v1/market-state", json=payload)
        second = client.post("/api/v1/market-state", json=payload)
        assert first.status_code == 200
        assert second.status_code == 208
