"""
UI v2, amendment 8. Tests for atlas.research_export.known_warnings - proves
the typed, traceable warning list is well-formed and, most importantly,
that the specific baseline warnings this project has already disclosed
cannot be silently dropped by a future edit without a test failure.
"""
from atlas.research_export.known_warnings import KNOWN_BASELINE_WARNING_IDS, KNOWN_BASELINE_WARNINGS

_EXPECTED_IDS = {
    "trend-1m-lookback-limit",
    "certification-verdict-rejected",
    "no-tick-size-roll-registry",
    "no-contract-roll-detection",
    "symbol-timeframe-cli-asserted",
    "runmanifest-package-coupling",
    "volume-ratio-null-cluster",
}


def test_every_expected_baseline_warning_is_present():
    assert _EXPECTED_IDS <= KNOWN_BASELINE_WARNING_IDS


def test_no_unexpected_extra_or_missing_ids():
    assert KNOWN_BASELINE_WARNING_IDS == _EXPECTED_IDS


def test_ids_are_unique():
    ids = [w.id for w in KNOWN_BASELINE_WARNINGS]
    assert len(ids) == len(set(ids))


def test_every_warning_has_full_traceability():
    for w in KNOWN_BASELINE_WARNINGS:
        assert w.id.strip()
        assert w.title.strip()
        assert w.detail.strip()
        assert w.source_document.strip()
        assert w.source_section.strip()


def test_every_warning_has_a_valid_severity():
    for w in KNOWN_BASELINE_WARNINGS:
        assert w.severity in {"warning", "fail"}


def test_the_one_fail_severity_is_the_certification_verdict():
    fails = [w for w in KNOWN_BASELINE_WARNINGS if w.severity == "fail"]
    assert [w.id for w in fails] == ["certification-verdict-rejected"]
