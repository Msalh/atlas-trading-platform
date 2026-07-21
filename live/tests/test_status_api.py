"""Tests for GET /status - the Connection Status panel's data source."""
import asyncio
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.api.deps import get_snapshots_readiness
from atlas.api.v1 import webhook
from atlas.config import settings
from atlas.main import app
from atlas.research_export.startup_check import SnapshotCheckResult, SnapshotsReadiness
from tests.conftest import entry_payload


async def _seed_similar_trade(repository, correlation_id):
    """Seeds one closed trade sharing entry_payload()'s direction/setup_tag so
    run_entry_score has historical evidence and actually calls Claude (rather than
    taking the zero-history shortcut where Claude is never invoked at all)."""
    async def _forward_ok():
        return True, 200, None

    await repository.claim_and_forward(correlation_id, entry_payload(correlation_id), "{}", _forward_ok)
    await repository.update_exit(correlation_id, "won", 30050, 500.0, "2026-01-01T00:00:00+00:00")


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
         patch.object(ai_module, "analyze_with_claude", return_value=("bullish setup", None)):
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


def test_status_reflects_forward_failure(client, repository):
    asyncio.run(_seed_similar_trade(repository, "hist-status-fail"))

    with patch.object(webhook, "forward_to_pickmytrade", return_value=(False, None, "connection refused")), \
         patch.object(ai_module, "analyze_with_claude", return_value=(None, "no API key")):
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


class TestStatusExposesResearchSnapshotsReadiness:
    """Production-hardening amendment 3: GET /status - never
    /research/dataset-health - is where degraded snapshot state is
    visible operationally."""

    def test_all_ready_by_default(self, client):
        resp = client.get("/api/v1/status")
        body = resp.json()
        assert body["research_snapshots"]["all_ready"] is True
        assert set(body["research_snapshots"]["files"].keys()) == {
            "re1-summary.v1.json", "re2-summary.v1.json", "dataset-health.v1.json",
        }
        for detail in body["research_snapshots"]["files"].values():
            assert detail["status"] == "ready"
            assert detail["reason"] is None

    def test_degraded_state_is_visible(self, client):
        degraded = SnapshotsReadiness((
            SnapshotCheckResult("re1-summary.v1.json", "ready", None),
            SnapshotCheckResult("re2-summary.v1.json", "missing", "re2-summary.v1.json does not exist"),
            SnapshotCheckResult("dataset-health.v1.json", "invalid", "content checksum mismatch"),
        ))
        app.dependency_overrides[get_snapshots_readiness] = lambda: degraded
        try:
            resp = client.get("/api/v1/status")
        finally:
            del app.dependency_overrides[get_snapshots_readiness]

        body = resp.json()["research_snapshots"]
        assert body["all_ready"] is False
        assert body["files"]["re1-summary.v1.json"]["status"] == "ready"
        assert body["files"]["re2-summary.v1.json"]["status"] == "missing"
        assert body["files"]["dataset-health.v1.json"]["status"] == "invalid"
        assert "checksum mismatch" in body["files"]["dataset-health.v1.json"]["reason"]
