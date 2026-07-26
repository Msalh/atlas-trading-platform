import json
from pathlib import Path

SPEC = Path(__file__).parents[1] / "specs" / "product_p2a" / "v1"


def test_specification_is_static_and_complete():
    files = {path.name for path in SPEC.iterdir() if path.is_file()}
    assert files == {"README.md", "fixtures.json", "vectors.json"}
    vectors = json.loads((SPEC / "vectors.json").read_text(encoding="utf-8"))
    assert vectors["schema_version"] == "product_p2a_vectors.v1"
    for group in ("golden", "negative", "adversarial"):
        assert vectors[group]
        assert len(vectors[group]) == len(set(vectors[group]))


def test_golden_negative_and_adversarial_fixtures_are_explicit():
    fixtures = json.loads((SPEC / "fixtures.json").read_text(encoding="utf-8"))
    assert fixtures["identity"] == {
        "economic_instrument": "MNQ",
        "analysis_series": {
            "provider": "tradingview",
            "symbol": "MNQ1!",
            "series_type": "continuous",
        },
        "listed_instrument": {
            "venue": "CME",
            "contract_symbol": "MNQU6",
            "expiry": "2026-09",
        },
    }
    assert fixtures["golden"]["expected_alignment"] == "accepted"
    for group in ("negative", "adversarial"):
        assert all(vector["expected_reason"].startswith("proposal.") for vector in fixtures[group])


def test_specification_freezes_authority_and_exclusions():
    readme = (SPEC / "README.md").read_text(encoding="utf-8")
    for text in (
        "MNQ1!",
        "never parsed, aliased, or inferred",
        "approved`, `blocked`, `unassessable`",
        "no runtime wiring",
        "Decision Engine",
        "WAIT/PREPARE/ENTER",
    ):
        assert text in readme
