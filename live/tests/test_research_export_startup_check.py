"""
Production-hardening amendment 3. Pure tests for check_snapshots() against
a tmp_path - never the real checked-in files, and never touching cwd
(check_snapshots takes an explicit directory, exactly like the real
lifespan wiring passes atlas.api.v1.research.SNAPSHOTS_DIR - a path
resolved relative to research.py's own module location, not the test
process's working directory).
"""
import json

from atlas.research_export.serialization import content_checksum
from atlas.research_export.startup_check import EXPECTED_SNAPSHOT_FILES, check_snapshots


def _valid_snapshot_json(payload=None):
    payload = payload if payload is not None else {"a": 1, "b": [1, 2, 3]}
    envelope = {
        "schema_version": "1.0",
        "source_computation_version": "aaa1111aaa1111aaa1111aaa1111aaa1111aaa1",
        "snapshot_exporter_version": "bbb2222bbb2222bbb2222bbb2222bbb2222bbb2",
        "source_freeze_document": "docs/market_engine/re1-phase5-freeze.md",
        "source_report_versions": {},
        "content_checksum": content_checksum(payload),
        "exported_at": "2026-07-20T12:00:00+00:00",
        "dataset_identity": {
            "symbol": "MNQ1!", "timeframe": "5m", "row_count": 1,
            "date_range": {"start": "t0", "end": "t1"},
        },
    }
    return {"envelope": envelope, "payload": payload}


def _write(directory, filename, content: str):
    (directory / filename).write_text(content, encoding="utf-8")


class TestCheckSnapshots:
    def test_all_three_missing_reports_missing_with_no_startup_crash(self, tmp_path):
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is False
        assert len(readiness.results) == 3
        for filename in EXPECTED_SNAPSHOT_FILES:
            result = readiness.status_for(filename)
            assert result.status == "missing"
            assert result.reason is not None

    def test_all_three_valid_reports_ready(self, tmp_path):
        for filename in EXPECTED_SNAPSHOT_FILES:
            _write(tmp_path, filename, json.dumps(_valid_snapshot_json()))
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is True
        for filename in EXPECTED_SNAPSHOT_FILES:
            result = readiness.status_for(filename)
            assert result.status == "ready"
            assert result.reason is None

    def test_malformed_json_is_invalid_not_a_crash(self, tmp_path):
        _write(tmp_path, "re1-summary.v1.json", "{not valid json")
        for filename in EXPECTED_SNAPSHOT_FILES[1:]:
            _write(tmp_path, filename, json.dumps(_valid_snapshot_json()))
        readiness = check_snapshots(tmp_path)
        result = readiness.status_for("re1-summary.v1.json")
        assert result.status == "invalid"
        assert "parse" in result.reason

    def test_missing_envelope_key_is_invalid(self, tmp_path):
        broken = _valid_snapshot_json()
        del broken["envelope"]["content_checksum"]
        _write(tmp_path, "re1-summary.v1.json", json.dumps(broken))
        for filename in EXPECTED_SNAPSHOT_FILES[1:]:
            _write(tmp_path, filename, json.dumps(_valid_snapshot_json()))
        readiness = check_snapshots(tmp_path)
        result = readiness.status_for("re1-summary.v1.json")
        assert result.status == "invalid"
        assert "content_checksum" in result.reason

    def test_checksum_mismatch_is_invalid(self, tmp_path):
        broken = _valid_snapshot_json()
        broken["payload"]["b"] = [9, 9, 9]  # payload changed after the checksum was computed
        _write(tmp_path, "re1-summary.v1.json", json.dumps(broken))
        for filename in EXPECTED_SNAPSHOT_FILES[1:]:
            _write(tmp_path, filename, json.dumps(_valid_snapshot_json()))
        readiness = check_snapshots(tmp_path)
        result = readiness.status_for("re1-summary.v1.json")
        assert result.status == "invalid"
        assert "checksum mismatch" in result.reason

    def test_mixed_readiness_is_reported_per_file(self, tmp_path):
        _write(tmp_path, "re1-summary.v1.json", json.dumps(_valid_snapshot_json()))
        # re2-summary.v1.json and dataset-health.v1.json left missing.
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is False
        assert readiness.status_for("re1-summary.v1.json").status == "ready"
        assert readiness.status_for("re2-summary.v1.json").status == "missing"
        assert readiness.status_for("dataset-health.v1.json").status == "missing"

    def test_result_is_resolved_regardless_of_process_cwd(self, tmp_path, monkeypatch):
        """check_snapshots takes an explicit directory - confirm it never
        falls back to reading relative to os.getcwd()."""
        for filename in EXPECTED_SNAPSHOT_FILES:
            _write(tmp_path, filename, json.dumps(_valid_snapshot_json()))
        monkeypatch.chdir(tmp_path.parent)  # cwd is now a sibling directory with none of these files
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is True
