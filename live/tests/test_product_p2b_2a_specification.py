import ast
import json
from pathlib import Path

SPEC = Path(__file__).parents[1] / "specs" / "product_p2b_2a" / "v1"


def test_p2b_2a_specification_files_are_frozen():
    assert {path.name for path in SPEC.iterdir() if path.is_file()} == {
        "README.md",
        "fixtures.json",
        "vectors.json",
    }
    readme = (SPEC / "README.md").read_text(encoding="utf-8")
    for contract in (
        "trade_plan_authority_resolution.v1",
        "trade_plan_authority_source.v1",
        "trade_plan_effective_interval.v1",
        "listed_contract_authority_request.v1",
        "instrument_specification_authority_request.v1",
        "exchange_session_authority_request.v1",
        "trade_plan_expiry_inputs.v1",
        "trade_plan_policy_authority_request.v1",
        "canonical_market_evidence_authority.v1",
    ):
        assert contract in readme


def test_fixtures_are_test_only_and_not_runtime_defaults():
    fixtures = json.loads((SPEC / "fixtures.json").read_text(encoding="utf-8"))
    assert fixtures["fixture_scope"] == "authoritative_test_only"
    assert fixtures["runtime_default"] is False
    assert fixtures["identity"] == {
        "economic_product": "MNQ",
        "analysis_provider": "tradingview",
        "analysis_series": "MNQ1!",
        "analysis_series_type": "continuous",
        "listed_contract": "TEST-MNQU6",
        "venue": "TEST-CME",
    }
    assert len(fixtures["golden_serialization"]["listed_resolution_id"]) == 64
    assert len(fixtures["golden_serialization"]["listed_resolution_sha256"]) == 64


def test_vectors_cover_authority_and_fail_closed_requirements():
    vectors = json.loads((SPEC / "vectors.json").read_text(encoding="utf-8"))
    assert vectors["schema_version"] == "product_p2b_2a_vectors.v1"
    actual = set().union(vectors["golden"], vectors["negative"], vectors["adversarial"])
    assert {
        "deterministic_resolution_identity",
        "effective_start_inclusive",
        "effective_end_exclusive",
        "missing_authority",
        "stale_authority",
        "future_dated_authority",
        "unreconciled_authority",
        "continuous_series_as_listed_contract",
        "overlapping_authority_records",
        "conflicting_provider_values",
        "canonical_288_market_evidence",
        "context_insufficient_history",
        "partial_geometry_prohibited",
    } <= actual


def test_every_refusal_vector_is_bound_to_an_executed_behavior_test():
    vectors = json.loads((SPEC / "vectors.json").read_text(encoding="utf-8"))
    bindings = vectors["behavior_tests"]
    refusal_vectors = set(vectors["negative"]) | set(vectors["adversarial"])
    assert set(bindings) == refusal_vectors

    test_path = Path(__file__).with_name("test_trade_plan_authority.py")
    tree = ast.parse(test_path.read_text(encoding="utf-8"))
    test_names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    assert set(bindings.values()) <= test_names


def test_spec_preserves_context_and_prohibits_partial_geometry():
    readme = (SPEC / "README.md").read_text(encoding="utf-8")
    assert "`insufficient_history` remains a closed" in readme
    assert "no Entry, Stop, Target" in readme
    assert "No P2B-2A port has a provider implementation" in readme
