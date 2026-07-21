"""
Production-hardening amendment 3, extended by the dataset-identity
cross-check and the structured reason/detail contract. Pure tests for
check_snapshots() against a tmp_path - never the real checked-in files,
and never touching cwd (check_snapshots takes an explicit directory,
exactly like the real lifespan wiring passes atlas.api.v1.research.
SNAPSHOTS_DIR - a path resolved relative to research.py's own module
location, not the test process's working directory).
"""
import json

from atlas.research_export.serialization import content_checksum
from atlas.research_export.startup_check import EXPECTED_SNAPSHOT_FILES, check_snapshots


def _identity(**overrides) -> dict:
    base = {
        "symbol": "MNQ1!",
        "timeframe": "5m",
        "row_count": 97858,
        "date_range": {"start": "2025-03-02T23:05:00+00:00", "end": "2026-07-20T11:35:00+00:00"},
    }
    base.update(overrides)
    return base


def _valid_snapshot_json(payload=None, identity=None):
    payload = payload if payload is not None else {"a": 1, "b": [1, 2, 3]}
    envelope = {
        "schema_version": "1.0",
        "source_computation_version": "aaa1111aaa1111aaa1111aaa1111aaa1111aaa1",
        "snapshot_exporter_version": "bbb2222bbb2222bbb2222bbb2222bbb2222bbb2",
        "source_freeze_document": "docs/market_engine/re1-phase5-freeze.md",
        "source_report_versions": {},
        "content_checksum": content_checksum(payload),
        "exported_at": "2026-07-20T12:00:00+00:00",
        "dataset_identity": identity if identity is not None else _identity(),
    }
    return {"envelope": envelope, "payload": payload}


def _write(directory, filename, content: str):
    (directory / filename).write_text(content, encoding="utf-8")


def _write_valid(directory, filename, payload=None, identity=None):
    _write(directory, filename, json.dumps(_valid_snapshot_json(payload, identity)))


class TestCheckSnapshots:
    def test_all_three_missing_reports_missing_with_no_startup_crash(self, tmp_path):
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is False
        assert readiness.status == "missing"
        assert len(readiness.results) == 3
        for filename in EXPECTED_SNAPSHOT_FILES:
            result = readiness.status_for(filename)
            assert result.status == "missing"
            assert result.reason == "missing_file"
            assert result.detail is not None

    def test_all_three_valid_reports_ready(self, tmp_path):
        for filename in EXPECTED_SNAPSHOT_FILES:
            _write_valid(tmp_path, filename)
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is True
        assert readiness.status == "ready"
        assert readiness.reason is None
        for filename in EXPECTED_SNAPSHOT_FILES:
            result = readiness.status_for(filename)
            assert result.status == "ready"
            assert result.reason is None
            assert result.detail is None

    def test_malformed_json_is_invalid_not_a_crash(self, tmp_path):
        _write(tmp_path, "re1-summary.v1.json", "{not valid json")
        for filename in EXPECTED_SNAPSHOT_FILES[1:]:
            _write_valid(tmp_path, filename)
        readiness = check_snapshots(tmp_path)
        result = readiness.status_for("re1-summary.v1.json")
        assert result.status == "invalid"
        assert result.reason == "json_error"
        assert "valid JSON" in result.detail

    def test_missing_envelope_key_is_invalid(self, tmp_path):
        broken = _valid_snapshot_json()
        del broken["envelope"]["content_checksum"]
        _write(tmp_path, "re1-summary.v1.json", json.dumps(broken))
        for filename in EXPECTED_SNAPSHOT_FILES[1:]:
            _write_valid(tmp_path, filename)
        readiness = check_snapshots(tmp_path)
        result = readiness.status_for("re1-summary.v1.json")
        assert result.status == "invalid"
        assert result.reason == "schema_error"
        assert "content_checksum" in result.detail

    def test_checksum_mismatch_is_invalid(self, tmp_path):
        broken = _valid_snapshot_json()
        broken["payload"]["b"] = [9, 9, 9]  # payload changed after the checksum was computed
        _write(tmp_path, "re1-summary.v1.json", json.dumps(broken))
        for filename in EXPECTED_SNAPSHOT_FILES[1:]:
            _write_valid(tmp_path, filename)
        readiness = check_snapshots(tmp_path)
        result = readiness.status_for("re1-summary.v1.json")
        assert result.status == "invalid"
        assert result.reason == "checksum_mismatch"
        assert "checksum mismatch" in result.detail

    def test_mixed_readiness_is_reported_per_file(self, tmp_path):
        _write_valid(tmp_path, "re1-summary.v1.json")
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
            _write_valid(tmp_path, filename)
        monkeypatch.chdir(tmp_path.parent)  # cwd is now a sibling directory with none of these files
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is True

    def test_detail_never_contains_an_absolute_filesystem_path(self, tmp_path):
        readiness = check_snapshots(tmp_path)  # every file missing
        for filename in EXPECTED_SNAPSHOT_FILES:
            detail = readiness.status_for(filename).detail
            assert detail == "snapshot file not found - run scripts/export_research_snapshots.py"
            assert str(tmp_path) not in detail
            assert ":\\" not in detail


class TestDatasetIdentityConsistency:
    """Production-hardening amendment: cross-snapshot dataset_identity
    consistency, checked only after all three files pass phase 1
    (existence/JSON/schema/checksum) independently."""

    def test_matching_identities_across_all_three_is_ready(self, tmp_path):
        for filename in EXPECTED_SNAPSHOT_FILES:
            _write_valid(tmp_path, filename, identity=_identity())
        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is True
        assert readiness.status == "ready"

    def test_symbol_mismatch_invalidates_all_three_with_the_stable_reason(self, tmp_path):
        _write_valid(tmp_path, "re1-summary.v1.json", identity=_identity(symbol="MNQ1!"))
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(symbol="MNQU6"))  # differs
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(symbol="MNQ1!"))

        readiness = check_snapshots(tmp_path)
        assert readiness.all_ready is False
        assert readiness.status == "invalid"
        assert readiness.reason == "dataset_identity_mismatch"
        # Every file is marked invalid - never just the one that "looks
        # different" from an arbitrarily chosen reference - see the
        # "do not silently select one as authoritative" test below.
        for filename in EXPECTED_SNAPSHOT_FILES:
            result = readiness.status_for(filename)
            assert result.status == "invalid"
            assert result.reason == "dataset_identity_mismatch"
            assert "symbol" in result.detail

    def test_timeframe_mismatch_is_detected(self, tmp_path):
        _write_valid(tmp_path, "re1-summary.v1.json", identity=_identity(timeframe="5m"))
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(timeframe="1m"))  # differs
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(timeframe="5m"))

        readiness = check_snapshots(tmp_path)
        assert readiness.status == "invalid"
        assert readiness.reason == "dataset_identity_mismatch"
        assert "timeframe" in readiness.status_for("re1-summary.v1.json").detail

    def test_row_count_mismatch_is_detected(self, tmp_path):
        _write_valid(tmp_path, "re1-summary.v1.json", identity=_identity(row_count=97858))
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(row_count=97858))
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(row_count=12345))  # differs

        readiness = check_snapshots(tmp_path)
        assert readiness.status == "invalid"
        assert readiness.reason == "dataset_identity_mismatch"
        assert "row_count" in readiness.status_for("re1-summary.v1.json").detail

    def test_start_date_mismatch_is_detected(self, tmp_path):
        base_range = {"start": "2025-03-02T23:05:00+00:00", "end": "2026-07-20T11:35:00+00:00"}
        other_range = {"start": "2025-01-01T00:00:00+00:00", "end": "2026-07-20T11:35:00+00:00"}
        _write_valid(tmp_path, "re1-summary.v1.json", identity=_identity(date_range=base_range))
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(date_range=other_range))  # differs
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(date_range=base_range))

        readiness = check_snapshots(tmp_path)
        assert readiness.status == "invalid"
        assert readiness.reason == "dataset_identity_mismatch"
        assert "date_range.start" in readiness.status_for("re1-summary.v1.json").detail

    def test_end_date_mismatch_is_detected(self, tmp_path):
        base_range = {"start": "2025-03-02T23:05:00+00:00", "end": "2026-07-20T11:35:00+00:00"}
        other_range = {"start": "2025-03-02T23:05:00+00:00", "end": "2026-06-01T00:00:00+00:00"}
        _write_valid(tmp_path, "re1-summary.v1.json", identity=_identity(date_range=base_range))
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(date_range=base_range))
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(date_range=other_range))  # differs

        readiness = check_snapshots(tmp_path)
        assert readiness.status == "invalid"
        assert readiness.reason == "dataset_identity_mismatch"
        assert "date_range.end" in readiness.status_for("re1-summary.v1.json").detail

    def test_identity_mismatch_is_never_checked_before_individual_validation_succeeds(self, tmp_path):
        """A checksum failure on one file must be reported as
        checksum_mismatch, never masked by (or confused with) a
        dataset_identity_mismatch - phase 2 only runs once every file
        independently passes phase 1."""
        broken = _valid_snapshot_json(identity=_identity(symbol="MNQ1!"))
        broken["payload"]["b"] = [9, 9, 9]  # corrupts the checksum
        _write(tmp_path, "re1-summary.v1.json", json.dumps(broken))
        # The other two files are individually valid AND already disagree
        # on symbol - if phase 2 ran regardless of phase 1, this would
        # incorrectly report a dataset_identity_mismatch instead.
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(symbol="MNQU6"))
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(symbol="MNQ1!"))

        readiness = check_snapshots(tmp_path)
        re1_result = readiness.status_for("re1-summary.v1.json")
        assert re1_result.status == "invalid"
        assert re1_result.reason == "checksum_mismatch"  # not dataset_identity_mismatch

        # The other two, individually valid, are untouched by re1's
        # failure - phase 2 never ran at all since not all three reached
        # "ready" in phase 1.
        assert readiness.status_for("re2-summary.v1.json").status == "ready"
        assert readiness.status_for("dataset-health.v1.json").status == "ready"

    def test_does_not_silently_select_one_snapshot_as_authoritative(self, tmp_path):
        """No matter which file's identity "looks like the odd one out",
        all three are marked invalid - there is no way to know which of
        three disagreeing snapshots is actually correct, so none is
        trusted over the others."""
        _write_valid(tmp_path, "re1-summary.v1.json", identity=_identity(row_count=1))
        _write_valid(tmp_path, "re2-summary.v1.json", identity=_identity(row_count=2))
        _write_valid(tmp_path, "dataset-health.v1.json", identity=_identity(row_count=3))

        readiness = check_snapshots(tmp_path)
        for filename in EXPECTED_SNAPSHOT_FILES:
            assert readiness.status_for(filename).status == "invalid"
