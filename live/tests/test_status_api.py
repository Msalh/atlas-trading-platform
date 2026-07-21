"""Tests for GET /status - the Connection Status panel's data source."""
import asyncio
from unittest.mock import patch

import pytest

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
    assert body["database"]["reason"] == "ping_failed"  # stable, machine-readable
    assert body["database"]["detail"] == "database ping failed - see server logs for details"


def test_status_database_error_never_exposes_connection_details(client, repository):
    """Production-hardening: a raw Postgres exception commonly embeds the DSN itself
    (host, port, sometimes the password) in its message - GET /status is client-facing
    and must never repeat that text back, only a sanitized, stable message."""
    sensitive_message = (
        'connection failed: connection to server at "db.internal.railway.app", port 5432 failed: '
        'FATAL: password authentication failed for user "atlas_prod" (password="hunter2")'
    )

    async def broken_ping():
        raise RuntimeError(sensitive_message)
    repository.ping = broken_ping

    resp = client.get("/api/v1/status")
    raw_body = resp.text
    for leaked in ("db.internal.railway.app", "5432", "atlas_prod", "hunter2", "password"):
        assert leaked not in raw_body

    body = resp.json()
    assert body["database"]["ok"] is False
    assert body["database"]["reason"] == "ping_failed"


class TestStatusExposesResearchSnapshotsReadiness:
    """Production-hardening amendment 3 (extended: structured
    status/reason/detail contract): GET /status - never
    /research/dataset-health - is where degraded snapshot state is
    visible operationally."""

    def _override(self, readiness: SnapshotsReadiness):
        app.dependency_overrides[get_snapshots_readiness] = lambda: readiness

    def teardown_method(self):
        app.dependency_overrides.pop(get_snapshots_readiness, None)

    def test_all_ready_by_default(self, client):
        resp = client.get("/api/v1/status")
        body = resp.json()["research_snapshots"]
        assert body["all_ready"] is True  # backward-compat field, still present
        assert body["status"] == "ready"
        assert body["reason"] is None
        assert set(body["files"].keys()) == {
            "re1-summary.v1.json", "re2-summary.v1.json", "dataset-health.v1.json",
        }
        for detail in body["files"].values():
            assert detail["status"] == "ready"
            assert detail["reason"] is None
            assert detail["detail"] is None

    def test_degraded_state_is_visible_with_structured_per_file_detail(self, client):
        self._override(SnapshotsReadiness((
            SnapshotCheckResult("re1-summary.v1.json", "ready", None, None),
            SnapshotCheckResult("re2-summary.v1.json", "missing", "missing_file", "snapshot file not found"),
            SnapshotCheckResult("dataset-health.v1.json", "invalid", "checksum_mismatch", "content checksum mismatch"),
        )))
        resp = client.get("/api/v1/status")

        body = resp.json()["research_snapshots"]
        assert body["all_ready"] is False
        assert body["status"] == "invalid"  # any invalid file wins over a merely-missing one
        assert body["reason"] == "missing_file"  # first non-None reason, in file order
        assert body["files"]["re1-summary.v1.json"]["status"] == "ready"
        assert body["files"]["re2-summary.v1.json"]["status"] == "missing"
        assert body["files"]["re2-summary.v1.json"]["reason"] == "missing_file"
        assert body["files"]["dataset-health.v1.json"]["status"] == "invalid"
        assert body["files"]["dataset-health.v1.json"]["reason"] == "checksum_mismatch"
        assert "checksum mismatch" in body["files"]["dataset-health.v1.json"]["detail"]

    @pytest.mark.parametrize(
        "reason,detail",
        [
            ("missing_file", "snapshot file not found - run scripts/export_research_snapshots.py"),
            ("json_error", "file is not valid JSON: Expecting value (line 1)"),
            ("schema_error", "envelope missing required keys: ['content_checksum']"),
            ("checksum_mismatch", "content checksum mismatch: envelope claims aaa..., recomputed bbb..."),
            ("dataset_identity_mismatch", "dataset_identity disagrees across snapshots in: symbol"),
        ],
    )
    def test_every_reason_category_is_exposed_verbatim(self, client, reason, detail):
        self._override(SnapshotsReadiness((
            SnapshotCheckResult("re1-summary.v1.json", "invalid", reason, detail),
            SnapshotCheckResult("re2-summary.v1.json", "ready", None, None),
            SnapshotCheckResult("dataset-health.v1.json", "ready", None, None),
        )))
        resp = client.get("/api/v1/status")
        file_body = resp.json()["research_snapshots"]["files"]["re1-summary.v1.json"]
        assert file_body["status"] == "invalid"
        assert file_body["reason"] == reason
        assert file_body["detail"] == detail

    def test_detail_never_contains_an_absolute_filesystem_path(self, client):
        # Sanitization contract: no consumer should ever see e.g. "C:\Users\..."
        # or "/home/..." in a status detail string.
        self._override(SnapshotsReadiness((
            SnapshotCheckResult("re1-summary.v1.json", "missing", "missing_file", "snapshot file not found - run scripts/export_research_snapshots.py"),
            SnapshotCheckResult("re2-summary.v1.json", "ready", None, None),
            SnapshotCheckResult("dataset-health.v1.json", "ready", None, None),
        )))
        resp = client.get("/api/v1/status")
        detail = resp.json()["research_snapshots"]["files"]["re1-summary.v1.json"]["detail"]
        assert ":\\" not in detail
        assert "/home/" not in detail
        assert "research_export" not in detail  # no package-internal path leakage either
