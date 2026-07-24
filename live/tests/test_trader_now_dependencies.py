"""Architecture checks for the deliberately thin Part 1 package."""

import ast
from pathlib import Path

_PACKAGE = Path(__file__).resolve().parent.parent / "atlas" / "trader_now"


def _atlas_imports(filename: str) -> set[str]:
    tree = ast.parse((_PACKAGE / filename).read_text(encoding="utf-8"))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(
                alias.name for alias in node.names if alias.name.startswith("atlas.")
            )
        elif (
            isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("atlas.")
        ):
            imports.add(node.module)
    return imports


def test_service_uses_only_approved_composition_dependencies():
    assert _atlas_imports("service.py") == {
        "atlas.core.primitives",
        "atlas.market_engine.models",
        "atlas.market_engine.ports",
        "atlas.risk_assessment.models",
        "atlas.risk_assessment.service",
        "atlas.risk_projection.projection",
        "atlas.strategy_engine.models",
        "atlas.trader_now.errors",
        "atlas.trader_now.identity",
        "atlas.trader_now.models",
        "atlas.trader_now.ports",
    }


def test_models_and_errors_have_no_project_layer_dependencies():
    assert _atlas_imports("models.py") == {
        "atlas.market_context.models",
        "atlas.market_engine.models",
        "atlas.risk_projection.models",
        "atlas.rule_engine.models",
        "atlas.setup_engine.models",
        "atlas.setup_interpretation.models",
        "atlas.strategy_engine.models",
    }
    assert _atlas_imports("errors.py") == set()


def test_freshness_and_trust_depend_only_on_trader_now_models():
    assert _atlas_imports("freshness.py") == {
        "atlas.trader_now.models",
        "atlas.trader_now.ports",
    }
    assert _atlas_imports("trust.py") == {"atlas.trader_now.models"}


def test_rule_composer_uses_only_the_canonical_rule_service_and_models():
    assert _atlas_imports("rules.py") == {
        "atlas.market_engine.models",
        "atlas.rule_engine.models",
        "atlas.rule_engine.service",
        "atlas.trader_now.models",
    }
    all_rule_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith("atlas.rule_engine")
    }
    assert all_rule_imports == {
        "atlas.rule_engine.models",
        "atlas.rule_engine.registry",
        "atlas.rule_engine.service",
    }


def test_setup_composer_uses_only_canonical_setup_public_modules():
    assert _atlas_imports("setups.py") == {
        "atlas.rule_engine.models",
        "atlas.rule_engine.registry",
        "atlas.setup_engine.models",
        "atlas.setup_engine.registry",
        "atlas.setup_engine.service",
        "atlas.trader_now.models",
    }
    all_setup_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith("atlas.setup_engine")
    }
    assert all_setup_imports == {
        "atlas.setup_engine.models",
        "atlas.setup_engine.registry",
        "atlas.setup_engine.service",
    }


def test_context_composer_uses_only_canonical_market_context_public_modules():
    assert _atlas_imports("contexts.py") == {
        "atlas.core.primitives",
        "atlas.market_context.definitions",
        "atlas.market_context.models",
        "atlas.market_context.service",
        "atlas.market_engine.models",
        "atlas.trader_now.models",
    }
    all_context_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith("atlas.market_context")
    }
    assert all_context_imports == {
        "atlas.market_context.definitions",
        "atlas.market_context.models",
        "atlas.market_context.service",
    }


def test_interpretation_composer_uses_only_canonical_public_modules():
    assert _atlas_imports("interpretations.py") == {
        "atlas.rule_engine.models",
        "atlas.setup_engine.models",
        "atlas.setup_interpretation.models",
        "atlas.setup_interpretation.service",
        "atlas.trader_now.models",
    }
    all_interpretation_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith("atlas.setup_interpretation")
    }
    assert all_interpretation_imports == {
        "atlas.setup_interpretation.models",
        "atlas.setup_interpretation.service",
    }


def test_strategy_composer_uses_canonical_strategy_api_and_replay_model_only():
    assert _atlas_imports("strategies.py") == {
        "atlas.replay_engine.models",
        "atlas.strategy_engine.models",
        "atlas.strategy_engine.ports",
        "atlas.strategy_engine.service",
        "atlas.strategy_engine.strategies.displacement_volume_context",
        "atlas.trader_now.models",
    }
    all_strategy_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith("atlas.strategy_engine")
    }
    assert all_strategy_imports == {
        "atlas.strategy_engine.models",
        "atlas.strategy_engine.ports",
        "atlas.strategy_engine.service",
        "atlas.strategy_engine.strategies.displacement_volume_context",
    }
    all_replay_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith("atlas.replay_engine")
    }
    assert all_replay_imports == {"atlas.replay_engine.models"}


def test_repository_and_contract_dependencies_are_declared_as_ports():
    assert _atlas_imports("ports.py") == {
        "atlas.market_engine.ports",
        "atlas.trader_now.models",
    }


def test_part_1_has_no_forbidden_composition_or_transport_imports():
    forbidden_prefixes = (
        "atlas.api",
        "atlas.risk.",
        "atlas.repositories",
    )
    for file_path in _PACKAGE.glob("*.py"):
        for imported in _atlas_imports(file_path.name):
            assert not imported.startswith(forbidden_prefixes), (
                f"{file_path.name} imports forbidden Part 2 dependency {imported}"
            )


def test_risk_composition_uses_only_canonical_public_modules():
    all_risk_imports = {
        imported
        for file_path in _PACKAGE.glob("*.py")
        for imported in _atlas_imports(file_path.name)
        if imported.startswith(("atlas.risk_assessment", "atlas.risk_projection"))
    }
    assert all_risk_imports == {
        "atlas.risk_assessment.models",
        "atlas.risk_assessment.service",
        "atlas.risk_projection.models",
        "atlas.risk_projection.projection",
    }
