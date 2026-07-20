"""
Route-level tests for POST /api/v1/market-state, against the in-memory
repository via the `client` fixture's dependency override - the same pattern
tests/test_webhook.py already uses for /webhook.
"""
import asyncio
import json
import logging

from tests.conftest import TEST_MARKET_STATE_SECRET, entry_payload, market_state_payload

from atlas.config import settings
from atlas.core.primitives import Symbol, Timeframe


class TestAuthentication:
    def test_missing_secret_rejected(self, client):
        payload = market_state_payload()
        del payload["secret"]
        resp = client.post("/api/v1/market-state", json=payload)
        assert resp.status_code == 401

    def test_wrong_secret_rejected(self, client):
        resp = client.post("/api/v1/market-state", json=market_state_payload(secret="wrong"))
        assert resp.status_code == 401

    def test_correct_secret_accepted(self, client):
        resp = client.post("/api/v1/market-state", json=market_state_payload())
        assert resp.status_code == 200


class TestValidPayloadAcceptance:
    def test_valid_payload_returns_200(self, client):
        resp = client.post("/api/v1/market-state", json=market_state_payload())
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["duplicate"] is False

    def test_valid_payload_is_actually_persisted(self, client, market_state_repository):
        client.post("/api/v1/market-state", json=market_state_payload(event_id="e-persist"))
        state = asyncio.run(market_state_repository.get_latest(Symbol("MNQU6"), Timeframe.M5))
        assert state is not None
        assert state.envelope.event_id == "e-persist"

    def test_fully_populated_payload_accepted(self, client):
        resp = client.post(
            "/api/v1/market-state",
            json=market_state_payload(
                open=20120.00, high=20128.50, low=20118.00, close=20125.75, volume=4210,
                session_name="NY", is_rth=True, trading_date="2026-07-18",
                vwap=20118.50, trend_1h="down", liquidity_sweep=False, reclaim=True,
            ),
        )
        assert resp.status_code == 200


class TestMalformedPayloadRejection:
    def test_invalid_json_body_rejected(self, client):
        resp = client.post(
            "/api/v1/market-state",
            content=b"not json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_missing_required_field_rejected(self, client):
        payload = market_state_payload()
        del payload["timeframe"]
        resp = client.post("/api/v1/market-state", json=payload)
        assert resp.status_code == 422

    def test_illegal_bar_status_rejected(self, client):
        resp = client.post("/api/v1/market-state", json=market_state_payload(bar_status="half_open"))
        assert resp.status_code == 422

    def test_off_tick_price_rejected(self, client):
        resp = client.post("/api/v1/market-state", json=market_state_payload(close=20125.80))
        assert resp.status_code == 422

    def test_rejected_payload_not_persisted(self, client, market_state_repository):
        client.post("/api/v1/market-state", json=market_state_payload(close=20125.80))
        state = asyncio.run(market_state_repository.get_latest(Symbol("MNQU6"), Timeframe.M5))
        assert state is None

    def test_non_object_json_body_does_not_crash_the_server(self, client):
        # valid JSON, but not an object - raw_json.get("secret") must not be
        # called on a list (that would be an unhandled AttributeError, a 500,
        # not a clean rejection). The secret check runs first and correctly
        # treats a non-dict body as having no secret, so this resolves to 401
        # (matching webhook.py's exact request-processing order) - never a 500.
        resp = client.post(
            "/api/v1/market-state",
            content=b"[1, 2, 3]",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 401


class TestRejectionLogging:
    """Diagnostic logging added after a production 422 proved unrecoverable -
    the rejection path previously logged nothing at all (see
    atlas.api.v1.market_state's `if result.error is not None:` branch), so a
    real TradingView payload that failed validation left no trace beyond the
    access log's bare status code. These tests prove the new
    logger.warning("MarketState rejected", extra={...}) call fires with the
    right stage/exception-type breadcrumbs, never with the secret, and never
    on the success path."""

    def _rejection_records(self, caplog):
        return [r for r in caplog.records if r.message == "MarketState rejected"]

    def test_wire_model_validation_failure_is_logged(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="atlas.market_state"):
            resp = client.post("/api/v1/market-state", json=market_state_payload(bar_status="half_open"))
        assert resp.status_code == 422
        records = self._rejection_records(caplog)
        assert len(records) == 1
        record = records[0]
        assert record.validation_stage == "wire_model_validation"
        assert record.exception_type == "ValidationError"
        assert record.symbol == "MNQU6"
        assert record.timeframe == "5m"
        assert "bar_status" in record.error

    def test_domain_translation_failure_is_logged(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="atlas.market_state"):
            resp = client.post("/api/v1/market-state", json=market_state_payload(close=20125.80))
        assert resp.status_code == 422
        records = self._rejection_records(caplog)
        assert len(records) == 1
        record = records[0]
        assert record.validation_stage == "domain_translation"
        assert record.exception_type == "OffTickError"

    def test_secret_never_present_in_rejection_log(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="atlas.market_state"):
            resp = client.post("/api/v1/market-state", json=market_state_payload(bar_status="half_open"))
        assert resp.status_code == 422
        assert self._rejection_records(caplog), "expected a rejection log record to check"
        for record in caplog.records:
            rendered = json.dumps(record.__dict__, default=str)
            assert TEST_MARKET_STATE_SECRET not in rendered
            assert "secret" not in rendered.lower()

    def test_successful_request_logs_no_rejection(self, client, caplog):
        with caplog.at_level(logging.WARNING, logger="atlas.market_state"):
            resp = client.post("/api/v1/market-state", json=market_state_payload(event_id="e-log-success"))
        assert resp.status_code == 200
        assert self._rejection_records(caplog) == []

    def test_duplicate_request_logs_no_rejection(self, client, caplog):
        payload = market_state_payload(event_id="e-log-dup")
        client.post("/api/v1/market-state", json=payload)
        with caplog.at_level(logging.WARNING, logger="atlas.market_state"):
            resp = client.post("/api/v1/market-state", json=payload)
        assert resp.status_code == 208
        assert self._rejection_records(caplog) == []


class TestDevelopmentModeBlankSecret:
    def test_non_object_body_rejected_as_422_when_secret_check_is_bypassed(self, client, monkeypatch):
        # A blank market_state_webhook_secret makes _secret_matches accept
        # anything (the same "development only" convention WEBHOOK_SECRET
        # already uses) - in that specific configuration, a non-dict JSON
        # body reaches the isinstance(raw_json, dict) guard instead of being
        # stopped earlier by a failed secret check. Confirms that guard is
        # real, reachable code, not dead defensive code.
        monkeypatch.setattr(settings, "market_state_webhook_secret", "")
        resp = client.post(
            "/api/v1/market-state",
            content=b"[1, 2, 3]",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 422


class TestUnexpectedFailure:
    def test_repository_failure_returns_500_not_a_crash(self, client, market_state_repository, monkeypatch):
        async def _boom(*args, **kwargs):
            raise RuntimeError("simulated database outage")

        monkeypatch.setattr(market_state_repository, "ingest", _boom)
        resp = client.post("/api/v1/market-state", json=market_state_payload(event_id="e-boom"))
        assert resp.status_code == 500
        assert "internal error" in resp.json()["error"]


class TestDuplicateHandling:
    def test_duplicate_event_id_returns_208(self, client):
        payload = market_state_payload(event_id="e-dup")
        first = client.post("/api/v1/market-state", json=payload)
        second = client.post("/api/v1/market-state", json=payload)
        assert first.status_code == 200
        assert second.status_code == 208
        assert second.json()["duplicate"] is True

    def test_duplicate_does_not_error(self, client):
        payload = market_state_payload(event_id="e-dup2")
        client.post("/api/v1/market-state", json=payload)
        resp = client.post("/api/v1/market-state", json=payload)
        assert resp.json()["ok"] is True


class TestSecretNeverPersisted:
    def test_secret_field_stripped_before_persistence(self, client, market_state_repository):
        client.post("/api/v1/market-state", json=market_state_payload(event_id="e-secret"))
        raw = market_state_repository.raw_payload_for(Symbol("MNQU6"), Timeframe.M5, "e-secret")
        assert TEST_MARKET_STATE_SECRET not in raw
        assert '"secret"' not in raw


class TestExistingWebhookUnaffected:
    """The whole point of Sprint 3's isolation - this is the same check as
    Sprint 1/2's self-review, now verified at the route level against a real
    request to the pre-existing /webhook endpoint."""

    def test_trade_webhook_still_works_unchanged(self, client):
        resp = client.post("/webhook", json=entry_payload())
        assert resp.status_code in (200, 207)  # normal trade-webhook outcomes, unrelated to market-state

    def test_trade_webhook_secret_check_unaffected_by_market_state_secret(self, client):
        resp = client.post("/webhook", json=entry_payload(secret="wrong-trade-secret"))
        assert resp.status_code == 401
