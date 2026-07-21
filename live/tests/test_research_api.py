"""
UI v2. Route-level tests for GET /api/v1/research/re1/summary, /re2/summary,
/dataset-health - against small, hand-written synthetic snapshot files
(monkeypatched in place of the real checked-in
live/research/snapshots/*.json), matching this project's established
"fast synthetic fixtures" convention. Real-content correctness is
exercised once by actually generating and committing the real files via
scripts/export_research_snapshots.py, not by every test run.
"""
import json

import pytest

from atlas.api.deps import get_snapshots_readiness
from atlas.api.v1 import research as research_api
from atlas.main import app
from atlas.research_export.startup_check import SnapshotCheckResult, SnapshotsReadiness


def _fake_envelope(**overrides) -> dict:
    base = {
        "schema_version": "1.0",
        "source_computation_version": "aaa1111aaa1111aaa1111aaa1111aaa1111aaa1",
        "snapshot_exporter_version": "bbb2222bbb2222bbb2222bbb2222bbb2222bbb2",
        "source_freeze_document": "docs/market_engine/re1-phase5-freeze.md",
        "source_report_versions": {"RE1_Fact_Profile.md": "aaa1111aaa1111aaa1111aaa1111aaa1111aaa1"},
        "content_checksum": "deadbeef" * 8,
        "exported_at": "2026-07-20T12:00:00+00:00",
        "dataset_identity": {
            "symbol": "MNQ1!", "timeframe": "5m", "row_count": 97858,
            "date_range": {"start": "2025-03-02T23:05:00+00:00", "end": "2026-07-20T11:35:00+00:00"},
        },
    }
    base.update(overrides)
    return base


@pytest.fixture
def snapshots_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(research_api, "SNAPSHOTS_DIR", tmp_path)
    research_api._cache.clear()
    yield tmp_path
    research_api._cache.clear()


def _write_snapshot(directory, filename, payload, envelope_overrides=None):
    snapshot = {"envelope": _fake_envelope(**(envelope_overrides or {})), "payload": payload}
    (directory / filename).write_text(json.dumps(snapshot), encoding="utf-8")
    return snapshot


class TestRe1Summary:
    def test_returns_envelope_and_report(self, client, snapshots_dir):
        _write_snapshot(snapshots_dir, "re1-summary.v1.json", {"fact_profiles": {"volume_spike": {}}})

        resp = client.get("/api/v1/research/re1/summary")
        assert resp.status_code == 200
        body = resp.json()
        assert body["ok"] is True
        assert body["envelope"]["source_track"] == "frozen"
        assert body["envelope"]["symbol"] == "MNQ1!"
        assert body["envelope"]["timeframe"] == "5m"
        assert body["envelope"]["data_as_of"] == "2026-07-20T11:35:00+00:00"
        assert body["report"] == {"fact_profiles": {"volume_spike": {}}}

    def test_code_version_is_source_computation_version_not_exporter_version(self, client, snapshots_dir):
        _write_snapshot(snapshots_dir, "re1-summary.v1.json", {})
        resp = client.get("/api/v1/research/re1/summary")
        body = resp.json()
        assert body["envelope"]["code_version"] == "aaa1111aaa1111aaa1111aaa1111aaa1111aaa1"
        assert body["envelope"]["code_version"] != "bbb2222bbb2222bbb2222bbb2222bbb2222bbb2"

    def test_missing_file_returns_503_not_a_crash(self, client, snapshots_dir):
        resp = client.get("/api/v1/research/re1/summary")
        assert resp.status_code == 503
        assert resp.json()["ok"] is False


class TestRe2Summary:
    def test_returns_envelope_and_report(self, client, snapshots_dir):
        _write_snapshot(snapshots_dir, "re2-summary.v1.json", {"setup_profile": {"entries": []}})
        resp = client.get("/api/v1/research/re2/summary")
        assert resp.status_code == 200
        assert resp.json()["report"] == {"setup_profile": {"entries": []}}


class TestDatasetHealth:
    def test_returns_full_shape(self, client, snapshots_dir):
        payload = {
            "dataset_identity": {"symbol": "MNQ1!", "timeframe": "5m", "row_count": 97858, "date_range": {}},
            "segment_count": 359,
            "certification": {"checks_run": 27, "pass_count": 21, "warning_count": 5, "fail_count": 1, "verdict": "rejected", "checks": []},
            "known_warnings": [
                {"id": "trend-1m-lookback-limit", "severity": "warning", "title": "t", "detail": "d",
                 "source_document": "x", "source_section": "y"},
                {"id": "certification-verdict-rejected", "severity": "fail", "title": "t2", "detail": "d2",
                 "source_document": "x", "source_section": "y"},
            ],
            "warnings_source": "manual_transcription",
        }
        _write_snapshot(snapshots_dir, "dataset-health.v1.json", payload)

        resp = client.get("/api/v1/research/dataset-health")
        assert resp.status_code == 200
        body = resp.json()
        assert body["segment_count"] == 359
        assert body["certification"]["verdict"] == "rejected"
        assert len(body["known_warnings"]) == 2
        assert body["frozen_version"]["source_computation_version"] == "aaa1111aaa1111aaa1111aaa1111aaa1111aaa1"

    def test_fail_severity_warnings_surface_in_http_envelope_warnings(self, client, snapshots_dir):
        payload = {
            "dataset_identity": {"symbol": "MNQ1!", "timeframe": "5m", "row_count": 1, "date_range": {}},
            "segment_count": 1,
            "certification": {"checks_run": 1, "pass_count": 0, "warning_count": 0, "fail_count": 1, "verdict": "rejected", "checks": []},
            "known_warnings": [
                {"id": "certification-verdict-rejected", "severity": "fail", "title": "Rejected", "detail": "d",
                 "source_document": "x", "source_section": "y"},
            ],
            "warnings_source": "manual_transcription",
        }
        _write_snapshot(snapshots_dir, "dataset-health.v1.json", payload)
        resp = client.get("/api/v1/research/dataset-health")
        assert any("certification-verdict-rejected" in w for w in resp.json()["envelope"]["warnings"])

    def test_missing_file_returns_503(self, client, snapshots_dir):
        resp = client.get("/api/v1/research/dataset-health")
        assert resp.status_code == 503


class TestDegradedReadinessGating:
    """Production-hardening amendment 3: a FROZEN endpoint 503s off the
    startup-computed readiness state BEFORE attempting to load anything -
    covers "invalid" (bad checksum/schema), which the file-existence-only
    503 path above never could, since a corrupt-but-present file would
    otherwise be loaded and served as if it were trustworthy."""

    def _override(self, result: SnapshotCheckResult):
        readiness = SnapshotsReadiness((result,))
        app.dependency_overrides[get_snapshots_readiness] = lambda: readiness

    def teardown_method(self):
        app.dependency_overrides.pop(get_snapshots_readiness, None)

    def test_invalid_readiness_503s_re1_summary_without_touching_disk(self, client, snapshots_dir):
        # A real, valid file is on disk, but startup marked it invalid
        # (e.g. a checksum mismatch caught before this request) - the
        # gate must still 503, never silently serve the file's content.
        _write_snapshot(snapshots_dir, "re1-summary.v1.json", {"fact_profiles": {}})
        self._override(SnapshotCheckResult("re1-summary.v1.json", "invalid", "content checksum mismatch"))

        resp = client.get("/api/v1/research/re1/summary")
        assert resp.status_code == 503
        body = resp.json()
        assert body["ok"] is False
        assert "invalid" in body["error"]
        assert "checksum mismatch" in body["error"]

    def test_missing_readiness_503s_re2_summary_with_a_clear_reason(self, client, snapshots_dir):
        self._override(SnapshotCheckResult("re2-summary.v1.json", "missing", "re2-summary.v1.json does not exist"))
        resp = client.get("/api/v1/research/re2/summary")
        assert resp.status_code == 503
        assert "missing" in resp.json()["error"]

    def test_invalid_readiness_503s_dataset_health(self, client, snapshots_dir):
        self._override(SnapshotCheckResult("dataset-health.v1.json", "invalid", "malformed schema"))
        resp = client.get("/api/v1/research/dataset-health")
        assert resp.status_code == 503
        assert "malformed schema" in resp.json()["error"]

    def test_ready_readiness_still_serves_the_real_file(self, client, snapshots_dir):
        _write_snapshot(snapshots_dir, "re1-summary.v1.json", {"fact_profiles": {"x": 1}})
        self._override(SnapshotCheckResult("re1-summary.v1.json", "ready", None))
        resp = client.get("/api/v1/research/re1/summary")
        assert resp.status_code == 200
        assert resp.json()["report"] == {"fact_profiles": {"x": 1}}
