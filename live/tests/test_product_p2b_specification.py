import json
from pathlib import Path

SPEC = Path(__file__).parents[1] / "specs" / "product_p2b" / "v1"


def test_specification_files_and_five_contract_resolution_are_frozen():
    assert {path.name for path in SPEC.iterdir() if path.is_file()} == {
        "README.md",
        "fixtures.json",
        "vectors.json",
    }
    readme = (SPEC / "README.md").read_text(encoding="utf-8")
    assert "five versioned contracts" in readme
    assert "sole closed reason vocabulary" in readme
    for contract in (
        "trade_plan_input.v1",
        "trade_plan_policy.v1",
        "trade_plan_evidence_binding.v1",
        "trade_plan_result.v1",
        "trade_plan_refusal.v1",
    ):
        assert contract in readme


def test_fixtures_are_explicitly_test_only_and_never_defaults():
    fixtures = json.loads((SPEC / "fixtures.json").read_text(encoding="utf-8"))
    assert fixtures["fixture_scope"] == "authoritative_test_only"
    assert fixtures["runtime_default"] is False
    assert fixtures["identity"]["analysis_series"] == "tradingview:MNQ1!"
    assert fixtures["identity"]["listed_contract"] == "TEST-MNQU6"
    assert fixtures["instrument_specification"]["tick_size"] == "0.25"
    assert fixtures["policy"]["reward_multiple"] == "1.9"
    assert fixtures["policy"]["maximum_entry_bars"] == 2
    assert len(fixtures["golden_serialization"]["long_plan_id"]) == 64
    assert len(fixtures["golden_serialization"]["long_result_sha256"]) == 64


def test_vectors_cover_required_golden_negative_and_adversarial_cases():
    vectors = json.loads((SPEC / "vectors.json").read_text(encoding="utf-8"))
    assert vectors["schema_version"] == "product_p2b_vectors.v1"
    required = {
        "mirrored_long",
        "mirrored_short",
        "bar_count_expiry",
        "session_boundary_expiry",
        "missing_listed_contract",
        "continuous_series_as_listed",
        "missing_specification",
        "conflicting_specification",
        "context_unavailable",
        "stale_evidence",
        "candidate_source_mismatch",
        "strategy_geometry_conflict",
        "rounding_collapse",
        "no_partial_output",
    }
    actual = set().union(
        vectors["golden"], vectors["negative"], vectors["adversarial"]
    )
    assert required <= actual
