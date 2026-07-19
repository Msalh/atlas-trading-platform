import pytest

from atlas.setup_engine.models import SetupFamily
from atlas.setup_engine.models import InsufficientData as SetupInsufficientData
from atlas.setup_engine.models import SetupDefinition
from atlas.setup_engine.registry import REGISTRY, SetupRegistration, required_history, validate_registry


def _definition(name="x", version="1.0", family=SetupFamily.ICT, **params):
    return SetupDefinition(name=name, version=version, family=family, params=params)


def _no_op_evaluate(context, definition):
    return SetupInsufficientData(setup_name=definition.name, definition_version=definition.version, reason="test stub")


class TestDefaultRegistry:
    def test_default_registry_holds_all_real_setups_in_registration_order(self):
        # Sprint 18 added the first; Sprint 20 the second; Sprint 21 the third.
        assert [r.name for r in REGISTRY] == [
            "displacement_with_volume_confirmation",
            "liquidity_sweep_with_volume_confirmation",
            "sustained_displacement_streak",
        ]

    def test_default_registry_passes_validation(self):
        validate_registry(REGISTRY)  # must not raise

    def test_empty_registry_still_passes_validation(self):
        validate_registry(())  # must not raise - Setup Engine's registry
        # is allowed to be empty, unlike Rule Engine's (Sprint 17B)


class TestSetupRegistrationRequiredHistory:
    def test_no_history_param_requires_one_bar(self):
        r = SetupRegistration("x", _no_op_evaluate, _definition())
        assert r.required_history == 1

    def test_history_param_derives_from_definition_params(self):
        r = SetupRegistration("x", _no_op_evaluate, _definition(lookback=10), history_param="lookback")
        assert r.required_history == 10

    def test_required_history_reflects_the_definition_live_not_a_cached_copy(self):
        r = SetupRegistration("x", _no_op_evaluate, _definition(lookback=42), history_param="lookback")
        assert r.required_history == 42


class TestValidateRegistry:
    def test_duplicate_names_rejected(self):
        r1 = SetupRegistration("dup", _no_op_evaluate, _definition(name="dup"))
        r2 = SetupRegistration("dup", _no_op_evaluate, _definition(name="dup"))
        with pytest.raises(ValueError, match="duplicate"):
            validate_registry((r1, r2))

    def test_name_definition_mismatch_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="b"))
        with pytest.raises(ValueError, match="does not match"):
            validate_registry((r,))

    def test_blank_definition_name_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name=""))
        with pytest.raises(ValueError, match="name must not be blank"):
            validate_registry((r,))

    def test_blank_definition_version_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a", version=""))
        with pytest.raises(ValueError, match="version must not be blank"):
            validate_registry((r,))

    def test_missing_history_param_key_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a"), history_param="lookback")
        with pytest.raises(ValueError, match="is not present"):
            validate_registry((r,))

    def test_non_int_history_value_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a", lookback=20.5), history_param="lookback")
        with pytest.raises(ValueError, match="must be an int"):
            validate_registry((r,))

    def test_bool_history_value_rejected_despite_being_an_int_subclass(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a", lookback=True), history_param="lookback")
        with pytest.raises(ValueError, match="must be an int"):
            validate_registry((r,))

    def test_zero_history_value_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a", lookback=0), history_param="lookback")
        with pytest.raises(ValueError, match="must be >= 1"):
            validate_registry((r,))

    def test_negative_history_value_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a", lookback=-5), history_param="lookback")
        with pytest.raises(ValueError, match="must be >= 1"):
            validate_registry((r,))

    def test_unknown_required_fact_rejected(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a"), required_facts=("not_a_real_fact",))
        with pytest.raises(ValueError, match="required_facts names facts not present"):
            validate_registry((r,))

    def test_known_required_fact_accepted(self):
        r = SetupRegistration("a", _no_op_evaluate, _definition(name="a"), required_facts=("volume_spike",))
        validate_registry((r,))  # must not raise - volume_spike is a real Rule Engine fact

    def test_multiple_required_facts_all_checked(self):
        r = SetupRegistration(
            "a", _no_op_evaluate, _definition(name="a"), required_facts=("volume_spike", "not_real"),
        )
        with pytest.raises(ValueError, match="not_real"):
            validate_registry((r,))


class TestRequiredHistory:
    def test_empty_registry_required_history_is_one(self):
        # Regression test: max() over an empty generator would otherwise
        # raise. required_history() must default to 1, matching the
        # "no history_param -> 1" convention every non-windowed setup uses.
        assert required_history(()) == 1

    def test_default_registry_required_history_is_two(self):
        # sustained_displacement_streak (Sprint 21) raised the registry-wide
        # maximum from 1 to 2 - the other two registered setups still only
        # need 1 bar each.
        assert required_history(REGISTRY) == 2

    def test_reflects_a_different_registry_not_hardcoded(self):
        larger = (
            SetupRegistration("big", _no_op_evaluate, _definition(name="big", lookback=100), history_param="lookback"),
            SetupRegistration("small", _no_op_evaluate, _definition(name="small")),
        )
        assert required_history(larger) == 100
