"""Tests for GET /status - the Connection Status panel's data source."""
from unittest.mock import patch

from atlas.api.v1 import webhook
from atlas.config import settings
from tests.conftest import entry_payload


def test_status_with_no_activity_yet(client, monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")

    resp = client.get("/api/v1/status")
    assert resp.status_code == 200
    body = resp.json()

    assert body["database"]["ok"] is True
    assert body["tradingview"]["last_webhook_at"] is None
    assert body["pickmytrade"]["configured"] is False
    assert body["pickmytrade"]["last_forward_at"] is None
    assert body["claude"]["configured"] is False
    assert body["claude"]["last_analysis_at"] is None


def test_status_reflects_successful_forward_and_analysis(client, monkeypatch):
    monkeypatch.setattr(settings, "pickmytrade_webhook_url", "https://pmt.example.com/hook")
    monkeypatch.setattr(settings, "anthropic_api_key", "sk-test")

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(True, 200, None)), \
         patch.object(webhook, "analyze_with_claude", return_value=("bullish setup", None)):
        client.post("/webhook", json=entry_payload("corr-status-ok"))

    resp = client.get("/api/v1/status")
    body = resp.json()

    assert body["tradingview"]["last_webhook_at"] is not None
    assert body["tradingview"]["last_webhook_type"] == "trade.entry.received"

    assert body["pickmytrade"]["configured"] is True
    assert body["pickmytrade"]["last_forward_at"] is not None
    assert body["pickmytrade"]["last_forward_ok"] is True
    assert body["pickmytrade"]["last_error"] is None

    assert body["claude"]["last_analysis_at"] is not None
    assert body["claude"]["last_error"] is None


def test_status_reflects_forward_failure(client):
    with patch.object(webhook, "forward_to_pickmytrade", return_value=(False, None, "connection refused")), \
         patch.object(webhook, "analyze_with_claude", return_value=(None, "no API key")):
        client.post("/webhook", json=entry_payload("corr-status-fail"))

    resp = client.get("/api/v1/status")
    body = resp.json()

    assert body["pickmytrade"]["last_forward_ok"] is False
    assert body["pickmytrade"]["last_error"] == "connection refused"
    assert body["claude"]["last_error"] == "no API key"


def test_status_database_error_is_surfaced(client, repository):
    async def broken_ping():
        raise RuntimeError("connection pool exhausted")
    repository.ping = broken_ping

    resp = client.get("/api/v1/status")
    body = resp.json()
    assert body["database"]["ok"] is False
    assert "connection pool exhausted" in body["database"]["detail"]
