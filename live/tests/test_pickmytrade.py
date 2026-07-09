"""Tests for atlas/services/pickmytrade.py - the relay call itself, and the
diagnostics instrumentation added for E2E integration-test debugging (masking,
timing, response capture). The actual relay behavior (URL, payload fields, timeout,
success/failure classification) is unchanged from before this sprint - these tests
cover the new diagnostics layer specifically. The existing 3-tuple return contract is
already exercised indirectly by every webhook test that mocks forward_to_pickmytrade
wholesale (see test_webhook.py and friends)."""
from unittest.mock import AsyncMock, Mock, patch

from atlas.config import settings
from atlas.services.pickmytrade import (
    PMT_FIELDS,
    _mask_payload,
    _mask_token,
    _normalize_pmt_payload,
    _to_iso_utc,
    forward_to_pickmytrade,
)


def _entry_payload(**overrides):
    payload = {
        "symbol": "MNQU6", "strategy_name": "test", "date": "123", "data": "BUY",
        "quantity": 1, "price": 100.0, "tp": 110.0, "sl": 90.0,
        "trail": 0, "trail_stop": 0, "trail_trigger": 0, "trail_freq": 0,
        "token": "supersecrettoken1234", "pyramid": True, "same_direction_ignore": False,
        "reverse_order_close": True,
        "multiple_accounts": [
            {"token": "acctsecrettoken5678", "account_id": "acct-1", "risk_percentage": 0, "quantity_multiplier": 1}
        ],
    }
    payload.update(overrides)
    return payload


# --- payload parity with the verified-working direct curl test ----------------------
# A direct curl straight to PickMyTrade's endpoint, verified end-to-end (status
# TradingLocked - correctly recognized, just blocked by account state), did not
# include `strategy_name` at all. Atlas's own internal payload/trade storage still
# keeps it (see conftest.py's entry_payload and test_webhook_validation.py) - only the
# outbound-to-PickMyTrade payload excludes it.

def test_strategy_name_is_not_in_pmt_fields():
    assert "strategy_name" not in PMT_FIELDS


async def test_forward_does_not_send_strategy_name_to_pickmytrade(monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text="OK")
    diagnostics: dict = {}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        await forward_to_pickmytrade(_entry_payload(), diagnostics=diagnostics)

    sent_body = mock_post.call_args.kwargs["json"]
    assert "strategy_name" not in sent_body
    assert "strategy_name" not in diagnostics["payload"]
    # everything else PMT_FIELDS still selects is untouched by this exclusion
    assert sent_body["symbol"] == "MNQU6"
    assert sent_body["token"] == "supersecrettoken1234"


# --- masking -------------------------------------------------------------------------

def test_mask_token_keeps_only_last_four_chars():
    assert _mask_token("supersecrettoken1234") == "***1234"


def test_mask_token_short_string_fully_masked():
    assert _mask_token("abc") == "***"


def test_mask_token_passes_through_non_string():
    assert _mask_token(None) is None


def test_mask_payload_masks_top_level_and_nested_tokens_only():
    masked = _mask_payload(_entry_payload())
    assert masked["token"] == "***1234"
    assert masked["multiple_accounts"][0]["token"] == "***5678"
    assert masked["multiple_accounts"][0]["account_id"] == "acct-1"  # not a secret, left alone
    assert masked["symbol"] == "MNQU6"  # untouched


# --- PickMyTrade field normalization --------------------------------------------------
# Confirmed via a direct curl test bypassing Atlas entirely: an identical payload with
# these three fields normalized was correctly recognized by PickMyTrade (status
# TradingLocked - rejected only because the connected account is locked, not because
# the payload was malformed). Atlas's own internal payload never matched PickMyTrade's
# documented format for `data`/`price`/`date` - see this module's docstring.

def test_to_iso_utc_converts_epoch_milliseconds_string():
    assert _to_iso_utc("1720000000000") == "2024-07-03T09:46:40Z"


def test_to_iso_utc_falls_back_to_now_for_missing_value():
    result = _to_iso_utc(None)
    assert result.endswith("Z") and "T" in result


def test_to_iso_utc_falls_back_to_now_for_non_numeric_value():
    result = _to_iso_utc("not-a-timestamp")
    assert result.endswith("Z") and "T" in result


def test_normalize_lowercases_data():
    normalized = _normalize_pmt_payload({"data": "BUY"})
    assert normalized["data"] == "buy"

    normalized = _normalize_pmt_payload({"data": "SELL"})
    assert normalized["data"] == "sell"


def test_normalize_stringifies_price():
    normalized = _normalize_pmt_payload({"price": 21500.25})
    assert normalized["price"] == "21500.25"
    assert isinstance(normalized["price"], str)


def test_normalize_leaves_tp_sl_numeric():
    normalized = _normalize_pmt_payload({"tp": 21515.0, "sl": 21485.0})
    assert normalized["tp"] == 21515.0 and isinstance(normalized["tp"], float)
    assert normalized["sl"] == 21485.0 and isinstance(normalized["sl"], float)


def test_normalize_converts_date_to_iso():
    normalized = _normalize_pmt_payload({"date": "1720000000000"})
    assert normalized["date"] == "2024-07-03T09:46:40Z"


def test_normalize_does_not_mutate_input_payload():
    original = {"data": "BUY", "price": 100.0}
    _normalize_pmt_payload(original)
    assert original == {"data": "BUY", "price": 100.0}


def test_normalize_handles_missing_fields_gracefully():
    assert _normalize_pmt_payload({}) == {}


# --- forward_to_pickmytrade diagnostics -----------------------------------------------

async def test_forward_not_configured_populates_diagnostics_without_calling_httpx(monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "")
    diagnostics: dict = {}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        forwarded, status_code, error = await forward_to_pickmytrade(_entry_payload(), diagnostics=diagnostics)

    mock_post.assert_not_called()
    assert (forwarded, status_code, error) == (False, None, "PICKMYTRADE_WEBHOOK_URL not configured")
    assert diagnostics["exception"] == "PICKMYTRADE_WEBHOOK_URL not configured"
    assert diagnostics["url"] is None
    assert diagnostics["status_code"] is None


async def test_forward_success_populates_full_diagnostics(monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text="OK")
    diagnostics: dict = {}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        forwarded, status_code, error = await forward_to_pickmytrade(_entry_payload(), diagnostics=diagnostics)

    assert (forwarded, status_code, error) == (True, 200, None)
    assert diagnostics["url"] == "https://pmt.example.com/hook"
    assert diagnostics["method"] == "POST"
    assert diagnostics["status_code"] == 200
    assert diagnostics["response_body"] == "OK"
    assert diagnostics["exception"] is None
    assert diagnostics["duration_ms"] >= 0
    assert diagnostics["payload"]["token"] == "***1234"  # masked, never the real secret
    # PickMyTrade-facing normalization (_entry_payload() sends "BUY"/100.0/"123"):
    assert diagnostics["payload"]["data"] == "buy"
    assert diagnostics["payload"]["price"] == "100.0"
    assert diagnostics["payload"]["date"] == "1970-01-01T00:00:00Z"


async def test_forward_http_error_populates_diagnostics_and_error_message(monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=422, text="Invalid account")
    diagnostics: dict = {}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        forwarded, status_code, error = await forward_to_pickmytrade(_entry_payload(), diagnostics=diagnostics)

    assert forwarded is True  # the HTTP call itself succeeded - PMT just rejected the order
    assert status_code == 422
    assert error == "HTTP 422: Invalid account"
    assert diagnostics["status_code"] == 422
    assert diagnostics["response_body"] == "Invalid account"


async def test_forward_connection_exception_populates_diagnostics(monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    diagnostics: dict = {}
    with patch("httpx.AsyncClient.post", side_effect=Exception("connection refused")):
        forwarded, status_code, error = await forward_to_pickmytrade(_entry_payload(), diagnostics=diagnostics)

    assert (forwarded, status_code, error) == (False, None, "connection refused")
    assert diagnostics["exception"] == "connection refused"
    assert diagnostics["status_code"] is None
    assert diagnostics["response_body"] is None


async def test_forward_works_without_diagnostics_kwarg(monkeypatch):
    """diagnostics is optional - omitting it must not change the return value at all."""
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text="OK")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        forwarded, status_code, error = await forward_to_pickmytrade(_entry_payload())
    assert (forwarded, status_code, error) == (True, 200, None)


async def test_forward_truncates_the_stored_response_body(monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text="x" * 10_000)
    diagnostics: dict = {}
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        await forward_to_pickmytrade(_entry_payload(), diagnostics=diagnostics)
    assert len(diagnostics["response_body"]) == 4000
