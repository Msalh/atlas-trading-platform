"""
Phase N4 Sprint 6. Tests for atlas.research.validation.service.validate() -
unit tests against hand-built Evidence fixtures (mirroring the roadmap's own
test strategy), determinism tests for the one stochastic component (Monte
Carlo), a dedicated test proving in-sample-only evidence can never reach
SUPPORTED (Principle IV.3), and a dedicated multiple-testing-correction
test over a real batch sharing one dataset (Principle IV.4).
"""

import pytest
from atlas.research.models import AcceptanceCriterion, CriterionKind, Evidence, TargetKind, ValidationVerdict
from atlas.research.validation.models import MonteCarloSpec, WalkForwardSpec
from atlas.research.validation.service import (
    _monte_carlo_pass_probability,
    _normal_cdf,
    _one_sided_p_value,
    validate,
)

_OCCURRED_AT = "2026-07-22T00:00:00+00:00"
_TARGET = "mean_atr"


def _evidence(evidence_id: str, mean=None, std_dev=None, sample_size=20, computable=True, experiment_id="e1") -> Evidence:
    metrics = {f"{_TARGET}__sample_size": sample_size, f"{_TARGET}__computable": computable}
    if computable:
        metrics[f"{_TARGET}__mean"] = mean
        metrics[f"{_TARGET}__std_dev"] = std_dev
    return Evidence(
        evidence_id=evidence_id, experiment_id=experiment_id, computed_at=_OCCURRED_AT,
        metrics=metrics, fingerprint="0123456789abcdef",
    )


def _criterion(threshold=2.0) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        description="mean_atr clears threshold", kind=CriterionKind.MEAN_ABOVE_THRESHOLD,
        target_kind=TargetKind.FEATURE, target=_TARGET, threshold=threshold,
    )


def _wf_spec(in_count=1, out_count=1) -> WalkForwardSpec:
    return WalkForwardSpec(
        in_sample_fold_count=in_count, out_of_sample_fold_count=out_count,
        fold_scheme_description="test fixture folds",
    )


def _mc_spec(n_draws=2000, seed=42) -> MonteCarloSpec:
    return MonteCarloSpec(n_draws=n_draws, seed=seed)


def _validate(**overrides):
    fields = dict(
        hypothesis_id="h1",
        in_sample_evidence=(_evidence("ev_in", mean=5.0, std_dev=1.0),),
        out_of_sample_evidence=(_evidence("ev_out", mean=5.0, std_dev=1.0),),
        criterion=_criterion(threshold=2.0),
        walk_forward_spec=_wf_spec(),
        monte_carlo_spec=_mc_spec(),
        batch_size=1,
        validation_id="v1",
        validated_at=_OCCURRED_AT,
    )
    fields.update(overrides)
    return validate(**fields)


# ---- verdict: SUPPORTED / NOT_SUPPORTED / INCONCLUSIVE ----

def test_supported_when_in_sample_and_out_of_sample_both_clearly_clear_threshold():
    result = _validate()
    assert result.verdict == ValidationVerdict.SUPPORTED
    assert result.out_of_sample is True
    assert len(result.evidence_ids) == 2


def test_not_supported_when_no_out_of_sample_fold_clears():
    result = _validate(
        in_sample_evidence=(_evidence("ev_in", mean=5.0, std_dev=1.0),),
        out_of_sample_evidence=(_evidence("ev_out", mean=0.5, std_dev=1.0),),
    )
    assert result.verdict == ValidationVerdict.NOT_SUPPORTED


def test_inconclusive_when_out_of_sample_folds_are_mixed():
    result = _validate(
        in_sample_evidence=(_evidence("ev_in", mean=5.0, std_dev=1.0),),
        out_of_sample_evidence=(
            _evidence("ev_out1", mean=5.0, std_dev=1.0),
            _evidence("ev_out2", mean=0.5, std_dev=1.0),
        ),
        walk_forward_spec=_wf_spec(out_count=2),
    )
    assert result.verdict == ValidationVerdict.INCONCLUSIVE


def test_inconclusive_when_in_sample_fails_but_out_of_sample_clears():
    result = _validate(
        in_sample_evidence=(_evidence("ev_in", mean=0.5, std_dev=1.0),),
        out_of_sample_evidence=(_evidence("ev_out", mean=5.0, std_dev=1.0),),
    )
    assert result.verdict == ValidationVerdict.INCONCLUSIVE


def test_insufficient_sample_fold_never_passes():
    result = _validate(
        out_of_sample_evidence=(_evidence("ev_out", computable=False, sample_size=1),),
    )
    assert result.verdict != ValidationVerdict.SUPPORTED
    assert result.criteria_results[-1].actual_value is None
    assert "insufficient" in result.criteria_results[-1].reason


# ---- structurally impossible: in-sample-only evidence (Principle IV.3) ----

def test_validate_requires_out_of_sample_evidence_or_raises():
    """The dedicated test the roadmap's own test strategy calls out: a
    hypothesis validated on in-sample-only evidence must be structurally
    impossible - here, calling validate() at all without out-of-sample
    evidence raises, rather than silently defaulting to something."""
    # WalkForwardSpec itself already refuses a zero fold count - the
    # spec below intentionally still claims 1, so this test exercises
    # validate()'s own empty-tuple guard specifically, checked before any
    # spec cross-match.
    with pytest.raises(ValueError, match="out-of-sample"):
        validate(
            hypothesis_id="h1", in_sample_evidence=(_evidence("ev_in", mean=5.0, std_dev=1.0),),
            out_of_sample_evidence=(), criterion=_criterion(), walk_forward_spec=_wf_spec(out_count=1),
            monte_carlo_spec=_mc_spec(), batch_size=1, validation_id="v1", validated_at=_OCCURRED_AT,
        )


def test_validate_requires_in_sample_evidence_or_raises():
    with pytest.raises(ValueError, match="in-sample"):
        validate(
            hypothesis_id="h1", in_sample_evidence=(), out_of_sample_evidence=(_evidence("ev_out", mean=5.0, std_dev=1.0),),
            criterion=_criterion(), walk_forward_spec=_wf_spec(in_count=1), monte_carlo_spec=_mc_spec(),
            batch_size=1, validation_id="v1", validated_at=_OCCURRED_AT,
        )


def test_out_of_sample_field_is_always_true_by_construction():
    """Every successful validate() call necessarily used out-of-sample
    evidence (it is a required, non-empty parameter) - out_of_sample=True
    is therefore a guaranteed fact, not merely a claim."""
    assert _validate().out_of_sample is True


# ---- mandatory multiple-testing correction (Principle IV.4) ----

def test_batch_size_greater_than_one_requires_correction_method_or_raises():
    with pytest.raises(ValueError, match="multiple_testing_correction"):
        _validate(batch_size=5, multiple_testing_correction=None)


def test_batch_size_one_does_not_require_correction():
    result = _validate(batch_size=1, multiple_testing_correction=None)
    assert result.multiple_testing_correction is None


def test_bonferroni_correction_can_flip_a_borderline_result_from_supported_to_not_supported():
    """A borderline p-value that clears the uncorrected alpha=0.05 but not
    the Bonferroni-corrected alpha=0.05/10 for a 10-hypothesis batch."""
    # mean=2.5, threshold=2.0, std_dev=1.0, n=20 -> z ~ 2.236, p ~ 0.0127 - clears 0.05, not 0.005
    borderline = _evidence("ev_out", mean=2.5, std_dev=1.0, sample_size=20)
    uncorrected = _validate(
        in_sample_evidence=(_evidence("ev_in", mean=2.5, std_dev=1.0, sample_size=20),),
        out_of_sample_evidence=(borderline,), batch_size=1,
    )
    corrected = _validate(
        in_sample_evidence=(_evidence("ev_in", mean=2.5, std_dev=1.0, sample_size=20),),
        out_of_sample_evidence=(borderline,), batch_size=10, multiple_testing_correction="bonferroni",
    )
    assert uncorrected.verdict == ValidationVerdict.SUPPORTED
    assert corrected.verdict != ValidationVerdict.SUPPORTED
    assert corrected.multiple_testing_correction == "bonferroni"


# ---- WalkForwardSpec cross-check ----

def test_walk_forward_spec_fold_count_mismatch_raises():
    with pytest.raises(ValueError, match="in-sample folds"):
        _validate(walk_forward_spec=_wf_spec(in_count=3, out_count=1))


def test_walk_forward_spec_out_of_sample_count_mismatch_raises():
    with pytest.raises(ValueError, match="out-of-sample folds"):
        _validate(walk_forward_spec=_wf_spec(in_count=1, out_count=3))


def test_walk_forward_spec_rejects_blank_description():
    with pytest.raises(ValueError, match="blank"):
        WalkForwardSpec(in_sample_fold_count=1, out_of_sample_fold_count=1, fold_scheme_description="  ")


def test_monte_carlo_spec_rejects_non_positive_draws():
    with pytest.raises(ValueError, match="n_draws"):
        MonteCarloSpec(n_draws=0, seed=1)


# ---- determinism (the roadmap's own required test for every stochastic method) ----

def test_monte_carlo_same_seed_same_result():
    a = _monte_carlo_pass_probability(5.0, 1.0, 2.0, MonteCarloSpec(n_draws=500, seed=7))
    b = _monte_carlo_pass_probability(5.0, 1.0, 2.0, MonteCarloSpec(n_draws=500, seed=7))
    assert a == b


def test_monte_carlo_different_seed_still_a_valid_probability_possibly_different():
    a = _monte_carlo_pass_probability(5.0, 1.0, 2.0, MonteCarloSpec(n_draws=500, seed=7))
    b = _monte_carlo_pass_probability(5.0, 1.0, 2.0, MonteCarloSpec(n_draws=500, seed=8))
    assert 0.0 <= a <= 1.0
    assert 0.0 <= b <= 1.0


def test_monte_carlo_converges_to_the_closed_form_normal_probability():
    """Proof the seeded random-draw simulation path is actually correct,
    not just internally self-consistent - the closed-form value is
    computed independently via _normal_cdf, used as the oracle."""
    mean, std_dev, threshold = 5.0, 2.0, 3.0
    closed_form = 1.0 - _normal_cdf((threshold - mean) / std_dev)
    simulated = _monte_carlo_pass_probability(mean, std_dev, threshold, MonteCarloSpec(n_draws=200_000, seed=1))
    assert simulated == pytest.approx(closed_form, abs=0.01)


def test_monte_carlo_zero_variance_is_deterministic_not_simulated():
    assert _monte_carlo_pass_probability(5.0, 0.0, 2.0, MonteCarloSpec(n_draws=100, seed=1)) == 1.0
    assert _monte_carlo_pass_probability(1.0, 0.0, 2.0, MonteCarloSpec(n_draws=100, seed=1)) == 0.0


def test_validate_is_fully_deterministic_given_identical_inputs():
    first = _validate()
    second = _validate()
    assert first.verdict == second.verdict
    assert first.criteria_results == second.criteria_results
    assert first.fingerprint == second.fingerprint


# ---- p-value edge cases ----

def test_one_sided_p_value_zero_variance_mean_above_threshold_is_zero():
    assert _one_sided_p_value(mean=5.0, std_dev=0.0, sample_size=10, threshold=2.0) == 0.0


def test_one_sided_p_value_zero_variance_mean_below_threshold_is_one():
    assert _one_sided_p_value(mean=1.0, std_dev=0.0, sample_size=10, threshold=2.0) == 1.0


def test_one_sided_p_value_zero_variance_mean_equal_threshold_is_undefined():
    assert _one_sided_p_value(mean=2.0, std_dev=0.0, sample_size=10, threshold=2.0) is None


def test_one_sided_p_value_matches_hand_computed_value():
    # mean=3.0, threshold=2.0, std_dev=1.0, n=4 -> se=0.5, z=2.0
    p = _one_sided_p_value(mean=3.0, std_dev=1.0, sample_size=4, threshold=2.0)
    expected = 1.0 - _normal_cdf(2.0)
    assert p == pytest.approx(expected)


# ---- fingerprint sensitivity ----

def test_fingerprint_changes_when_criterion_threshold_changes():
    a = _validate(criterion=_criterion(threshold=2.0))
    b = _validate(criterion=_criterion(threshold=3.0))
    assert a.fingerprint != b.fingerprint


def test_fingerprint_changes_when_evidence_ids_change():
    a = _validate(out_of_sample_evidence=(_evidence("ev_out_a", mean=5.0, std_dev=1.0),))
    b = _validate(out_of_sample_evidence=(_evidence("ev_out_b", mean=5.0, std_dev=1.0),))
    assert a.fingerprint != b.fingerprint
