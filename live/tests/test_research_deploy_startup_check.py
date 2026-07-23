"""
Sprint 8.2. Tests for atlas.research_deploy.startup_check -
check_ledger_storage()'s five-check contract, LedgerReadiness's status/
reason derivation, and build_startup_report()'s rendering.
"""
from pathlib import Path

import pytest

from atlas.research_deploy.startup_check import (
    LEDGER_CHECK_NAMES,
    build_startup_report,
    check_ledger_storage,
    internal_error_readiness,
)


def test_check_ledger_storage_all_ready_on_a_fresh_writable_directory(tmp_path: Path):
    directory = tmp_path / "research"
    readiness, stores = check_ledger_storage(directory)
    assert readiness.status == "ready"
    assert readiness.reason is None
    assert stores is not None
    assert directory.exists()


def test_check_ledger_storage_creates_missing_parent_directories(tmp_path: Path):
    directory = tmp_path / "a" / "b" / "research"
    readiness, stores = check_ledger_storage(directory)
    assert readiness.status == "ready"
    assert directory.exists()


def test_check_ledger_storage_stores_can_actually_read_and_write(tmp_path: Path):
    from atlas.research.models import ProvenanceKind, Realization, RealizationKind, RealizationStatus

    _, stores = check_ledger_storage(tmp_path / "research")
    realization = Realization(
        realization_id="r1", hypothesis_id="h1", kind=RealizationKind.STATISTICAL_TEST, version="1.0",
        parameters={}, status=RealizationStatus.DRAFTED, provenance=ProvenanceKind.HUMAN,
        created_at="2026-07-23T00:00:00+00:00", fingerprint="0123456789abcdef",
    )
    stores.realizations.register(realization)
    assert stores.realizations.get("r1") == realization


def test_check_ledger_storage_rejects_blank_configuration():
    readiness, stores = check_ledger_storage(Path(""))
    assert readiness.status == "degraded"
    assert readiness.reason == "configuration_valid"
    assert stores is not None  # always constructed - side-effect-free, never None
    for name in LEDGER_CHECK_NAMES:
        if name != "jsonl_stores_initialized":
            assert readiness.result_for(name).ok is False


def test_check_ledger_storage_all_five_checks_always_present(tmp_path: Path):
    readiness, _ = check_ledger_storage(tmp_path / "research")
    assert {r.name for r in readiness.results} == set(LEDGER_CHECK_NAMES)


def test_check_ledger_storage_result_for_unknown_name_raises(tmp_path: Path):
    readiness, _ = check_ledger_storage(tmp_path / "research")
    with pytest.raises(KeyError):
        readiness.result_for("does_not_exist")


def test_ledger_readiness_to_dict_shape(tmp_path: Path):
    readiness, _ = check_ledger_storage(tmp_path / "research")
    body = readiness.to_dict()
    assert body["status"] == "ready"
    assert body["reason"] is None
    assert set(body["checks"].keys()) == set(LEDGER_CHECK_NAMES)
    for check in body["checks"].values():
        assert check["ok"] is True


def test_internal_error_readiness_is_uniformly_degraded():
    readiness = internal_error_readiness()
    assert readiness.status == "degraded"
    assert readiness.reason == readiness.results[0].name
    for r in readiness.results:
        assert r.ok is False
        assert "server logs" in r.detail


# ---- build_startup_report() ----

def test_build_startup_report_all_checkmarks_when_ready(tmp_path: Path):
    readiness, _ = check_ledger_storage(tmp_path / "research")
    report = build_startup_report(readiness, environment="production", elapsed_ms=12.3)
    assert report.startswith("Research Startup")
    assert "✓ Ledger directory" in report
    assert "✓ Volume mounted" in report
    assert "✓ JSONL stores initialized" in report
    assert "✓ Registries available" in report
    assert "✓ Configuration valid" in report
    assert "✓ API mounted" in report
    assert "✓ Environment: production" in report
    assert "Startup completed in 12 ms" in report
    assert "✗" not in report


def test_build_startup_report_shows_failures_with_x_marks_when_degraded():
    readiness = internal_error_readiness()
    report = build_startup_report(readiness, environment="production", elapsed_ms=5.0)
    assert "✗ Ledger directory" in report
    assert "degraded ledger storage" in report


def test_build_startup_report_is_logged_once_pattern(tmp_path: Path, caplog):
    """Not a test of atlas.main itself (covered in a later slice) - just
    proves the report string is a single, complete block suitable for one
    logger.info() call, not multiple fragmented lines a caller would need
    to reassemble."""
    readiness, _ = check_ledger_storage(tmp_path / "research")
    report = build_startup_report(readiness, environment="development", elapsed_ms=1.0)
    assert report.count("Research Startup") == 1
    assert isinstance(report, str)
