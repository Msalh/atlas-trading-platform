"""Tests for atlas/services/pickmytrade.py - the relay call itself, and the
diagnostics instrumentation added for E2E integration-test debugging (masking,
timing, response capture). The actual relay behavior (URL, payload fields, timeout,
success/failure classification) is unchanged from before this sprint - these tests
cover the new diagnostics layer specifically. The existing 3-tuple return contract is
already exercised indirectly by every webhook test that mocks forward_to_pickmytrade
wholesale (see test_webhook.py and friends)."""
from unittest.mock import AsyncMock, Mock, patch

from atlas.config import settings
from atlas.services.pickmytrade import _mask_payload, _mask_token, forward_to_pickmytrade


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
