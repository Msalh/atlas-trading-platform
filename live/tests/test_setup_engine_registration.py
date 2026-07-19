"""
Sprint 18. Import-order smoke tests for the SetupRegistration split.

registration.py exists specifically so no module in atlas.setup_engine needs
a bottom-of-file or otherwise order-dependent import to obtain
SetupRegistration. These tests prove that property directly, in a form that
would fail if the split were ever reverted or a new setup module
reintroduced a dependency on registry.py to get SetupRegistration.
"""
import importlib
import sys


def _fresh_import(module_name):
    """Import module_name with none of atlas.setup_engine's modules already
    in sys.modules, so import order is exactly what a real first-time import
    would see - not whatever order an earlier test happened to trigger."""
    for name in list(sys.modules):
        if name == "atlas.setup_engine" or name.startswith("atlas.setup_engine."):
            del sys.modules[name]
    return importlib.import_module(module_name)


class TestNoCircularImport:
    def test_registration_module_imports_standalone(self):
        # Must not require atlas.setup_engine.registry (or anything in
        # atlas.setup_engine.setups) to already be imported first.
        module = _fresh_import("atlas.setup_engine.registration")
        assert hasattr(module, "SetupRegistration")
        assert hasattr(module, "SetupEvaluator")

    def test_setup_module_imports_standalone_without_the_registry(self):
        # A setup module must be importable on its own - it should depend on
        # atlas.setup_engine.registration, never on atlas.setup_engine.registry.
        module = _fresh_import("atlas.setup_engine.setups.displacement_with_volume_confirmation")
        assert module.DISPLACEMENT_WITH_VOLUME_CONFIRMATION_REGISTRATION.name == "displacement_with_volume_confirmation"
        assert "atlas.setup_engine.registry" not in sys.modules

    def test_registry_re_exports_the_same_class_not_a_duplicate(self):
        from atlas.setup_engine.registration import SetupRegistration as FromRegistration
        from atlas.setup_engine.registry import SetupRegistration as FromRegistry
        assert FromRegistry is FromRegistration

    def test_registry_still_imports_cleanly_top_to_bottom(self):
        module = _fresh_import("atlas.setup_engine.registry")
        assert len(module.REGISTRY) == 4  # Sprint 20 a second setup, Sprint 21 a third, Sprint 23B a fourth
        module.validate_registry(module.REGISTRY)  # must not raise
