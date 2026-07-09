"""
Tests for WebhookPayload validation (Sprint 9) - atlas/api/v1/webhook_models.py.
tests/test_webhook.py already covers the happy path end-to-end; these focus
specifically on malformed data being rejected with 422, closing the Sprint 8 audit
finding that a bad `direction` used to silently degrade
atlas/risk.py::risk_reward_points to (None, None) instead of being caught outright.
"""
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.v1 import webhook
from tests.conftest import entry_payload


def test_bad_direction_is_rejected(client):
    resp = client.post("/webhook", json=entry_payload("corr-bad-dir", direction="sideways"))
    assert resp.status_code == 422


def test_negative_quantity_is_rejected(client):
    resp = client.post("/webhook", json=entry_payload("corr-bad-qty", quantity=-5))
    assert resp.status_code == 422


def test_zero_quantity_is_rejected(client):
    resp = client.post("/webhook", json=entry_payload("corr-zero-qty", quantity=0))
    assert resp.status_code == 422


def test_non_numeric_entry_price_is_rejected(client):
    resp = client.post("/webhook", json=entry_payload("corr-bad-price", entry_price="not-a-number"))
    assert resp.status_code == 422


def test_blank_correlation_id_is_rejected(client):
    resp = client.post("/webhook", json=entry_payload(""))
    assert resp.status_code == 422


def test_missing_correlation_id_key_is_rejected(client):
    resp = client.post("/webhook", json={"type": "entry", "secret": "test-secret"})
    assert resp.status_code == 422


def test_unrecognized_event_type_is_rejected(client):
    resp = client.post("/webhook", json=entry_payload("corr-bad-type", type="cancel"))
    assert resp.status_code == 422


def test_invalid_json_is_still_a_400_not_a_422(client):
    """Not-JSON-at-all stays 400 (unchanged from before Sprint 9) - 422 is reserved for
    well-formed JSON that fails schema validation."""
    resp = client.post("/webhook", content=b"not json at all", headers={"Content-Type": "application/json"})
    assert resp.status_code == 400


def test_valid_entry_with_only_required_fields_is_accepted(client):
    """correlation_id is the only truly required field - a minimal but well-typed
    payload must still be accepted (see webhook_models.py's docstring on why every
    trade-data field stays optional)."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post(
            "/webhook", json={"type": "entry", "correlation_id": "corr-minimal", "secret": "test-secret"},
        )
    assert resp.status_code in (200, 207)


def test_extra_pickmytrade_only_fields_still_pass_through_unrejected(client):
    """extra="allow" - fields this model doesn't know about (PickMyTrade-only fields
    like strategy_name/data/price/token) must not be rejected or silently dropped,
    since atlas/services/pickmytrade.py's PMT_FIELDS extraction reads them straight
    off the same dict this model produces."""
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)) as mock_forward, \
         patch.object(ai_module, "analyze_with_claude"):
        resp = client.post("/webhook", json=entry_payload("corr-extra-fields", some_future_field="anything"))
    assert resp.status_code in (200, 207)
    forwarded_payload = mock_forward.call_args[0][0]
    assert forwarded_payload.get("some_future_field") == "anything"
    # strategy_name stays in Atlas's own internal payload/storage (this is what gets
    # passed INTO forward_to_pickmytrade, before that function's own PMT_FIELDS
    # filtering runs) - see test_pickmytrade.py for confirmation it's excluded from
    # what's actually sent to PickMyTrade specifically.
    assert forwarded_payload.get("strategy_name") == "NQ RECLAIM NY LONG"
