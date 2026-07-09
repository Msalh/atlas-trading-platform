"""End-to-end test that the webhook persists PickMyTrade relay diagnostics onto the
trade record - unlike test_webhook.py's tests (which mock forward_to_pickmytrade
wholesale, bypassing the diagnostics logic entirely), these mock httpx directly so the
real forward_to_pickmytrade + diagnostics-building code actually runs, matching how
test_alerting.py exercises _post_alert for the same reason."""
from unittest.mock import AsyncMock, Mock, patch

import atlas.ai as ai_module
from atlas.config import settings
from tests.conftest import entry_payload


def _post_entry_with_real_pmt_call(client, correlation_id, **overrides):
    with patch.object(ai_module, "analyze_with_claude", return_value=("ok", None)):
        return client.post("/webhook", json=entry_payload(correlation_id, **overrides))


def test_successful_relay_persists_diagnostics_on_the_trade(client, get_trade, monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text="OK")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        resp = _post_entry_with_real_pmt_call(client, "corr-diag-ok")

    assert resp.status_code == 200
    trade = get_trade("corr-diag-ok")
    assert trade["pmt_relay_diagnostics"] is not None
    diagnostics = trade["pmt_relay_diagnostics"]
    assert diagnostics["url"] == "https://pmt.example.com/hook"
    assert diagnostics["status_code"] == 200
    assert diagnostics["response_body"] == "OK"
    assert "token" not in str(diagnostics["payload"].get("token", "")).replace("***", "")  # masked, not the raw token


def test_relay_normalizes_data_price_date_for_pickmytrade(client, get_trade, monkeypatch):
    """Full webhook -> relay -> persisted-diagnostics path, confirmed against a real
    direct-to-PickMyTrade curl test: the entry_payload() fixture sends "BUY" (upper),
    a bare numeric price, and an epoch-millisecond date string - PickMyTrade's own
    documented format expects lowercase "buy", price as a string, and an ISO-8601 UTC
    date. This is what actually gets sent (and stored/logged), not what the strategy
    originally produced."""
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text='{"res":"Successfully send","error":false}')
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response):
        _post_entry_with_real_pmt_call(
            client, "corr-diag-normalize", data="BUY", price=21500.25, date="1720000000000",
        )

    diagnostics = get_trade("corr-diag-normalize")["pmt_relay_diagnostics"]
    assert diagnostics["payload"]["data"] == "buy"
    assert diagnostics["payload"]["price"] == "21500.25"
    assert diagnostics["payload"]["date"] == "2024-07-03T09:46:40Z"


def test_failed_relay_still_persists_diagnostics(client, get_trade, monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    with patch("httpx.AsyncClient.post", side_effect=Exception("connection refused")):
        resp = _post_entry_with_real_pmt_call(client, "corr-diag-fail")

    assert resp.status_code == 207  # not forwarded, but still a normal 2xx response
    trade = get_trade("corr-diag-fail")
    diagnostics = trade["pmt_relay_diagnostics"]
    assert diagnostics["exception"] == "connection refused"
    assert diagnostics["status_code"] is None


def test_duplicate_entry_does_not_touch_diagnostics(client, get_trade, monkeypatch):
    """A duplicate never calls forward() at all - update_pmt_diagnostics must never be
    called either, so the original attempt's diagnostics are left exactly as they were."""
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    mock_response = Mock(status_code=200, text="OK")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_response) as mock_post:
        _post_entry_with_real_pmt_call(client, "corr-diag-dup")
        first_diagnostics = get_trade("corr-diag-dup")["pmt_relay_diagnostics"]

        resp = _post_entry_with_real_pmt_call(client, "corr-diag-dup")

    assert resp.status_code == 208
    assert mock_post.call_count == 1  # never re-forwarded
    assert get_trade("corr-diag-dup")["pmt_relay_diagnostics"] == first_diagnostics
