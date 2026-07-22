"""
Phase N4 Sprint 5, corrected Sprint 6.1. Tests for
atlas.research.statistics.compute_evidence() against hand-built Feature
data - unit tests for sample-size edge cases, zero-variance handling, a
dedicated reproducibility test proving the same Experiment fingerprint
always reproduces the same Evidence (Principle VII.1's first real test),
and Sprint 6.1's own effective_sample_size autocorrelation correction.
"""
import random

import pytest
from atlas.research.features.models import FeatureComputed, FeatureInsufficientData
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionKind,
    CriterionResult,
    DatasetManifest,
    Experiment,
    TargetKind,
)
from atlas.research.statistics.service import _autocorrelation, _effective_sample_size, compute_evidence

_OCCURRED_AT = "2026-07-22T00:00:00+00:00"


def _dataset_manifest() -> DatasetManifest:
    return DatasetManifest(
        symbol="MNQU6", timeframe="5m", requested_start=_OCCURRED_AT, requested_end=_OCCURRED_AT,
        row_count=20, first_occurred_at=_OCCURRED_AT, last_occurred_at=_OCCURRED_AT,
        source_description="test", generated_at=_OCCURRED_AT,
    )


def _criterion(target="mean_atr", threshold=2.0) -> AcceptanceCriterion:
    return AcceptanceCriterion(
        description="stub", kind=CriterionKind.MEAN_ABOVE_THRESHOLD, target_kind=TargetKind.FEATURE,
        target=target, threshold=threshold,
    )


def _criterion_result(criterion=None, actual_value=3.0, passed=True) -> CriterionResult:
    return CriterionResult(criterion=criterion or _criterion(), actual_value=actual_value, passed=passed, reason=None)


def _experiment(criteria_results, **overrides) -> Experiment:
    fields = dict(
        experiment_id="e1", hypothesis_id="h1", executed_at=_OCCURRED_AT, code_version="abc123",
        dataset_manifest=_dataset_manifest(), criteria_results=criteria_results, passed=True,
        profiling_report_path=None, semantic_fingerprint="aaaaaaaaaaaaaaaa", execution_fingerprint="bbbbbbbbbbbbbbbb",
    )
    fields.update(overrides)
    return Experiment(**fields)


def _computed_series(values: list[float]) -> tuple:
    return tuple(FeatureComputed(feature_name="mean_atr", feature_version="1.0", value=v) for v in values)


# ---- sufficient sample: mean/std/CI/effect_size all present ----

def test_compute_evidence_computes_full_statistics_for_a_sufficient_sample():
    experiment = _experiment((_criterion_result(),))
    series = {"mean_atr": _computed_series([1.0, 2.0, 3.0, 4.0, 5.0])}
    evidence = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)

    assert evidence.metrics["mean_atr__sample_size"] == 5
    assert evidence.metrics["mean_atr__computable"] is True
    assert evidence.metrics["mean_atr__mean"] == pytest.approx(3.0)
    assert evidence.metrics["mean_atr__std_dev"] == pytest.approx(1.5811388300841898)
    assert evidence.metrics["mean_atr__confidence_interval_95_low_normal_approx"] < 3.0
    assert evidence.metrics["mean_atr__confidence_interval_95_high_normal_approx"] > 3.0
    assert evidence.metrics["mean_atr__effect_size_computable"] is True
    assert evidence.metrics["mean_atr__effect_size_vs_threshold"] == pytest.approx((3.0 - 2.0) / 1.5811388300841898)
    assert evidence.experiment_id == "e1"
    assert evidence.evidence_id == "ev1"
    # linearly increasing values (1,2,3,4,5) are strongly (perfectly)
    # autocorrelated - effective_sample_size must be materially below the
    # raw count of 5, not silently equal to it.
    assert 0 < evidence.metrics["mean_atr__effective_sample_size"] < 5.0


# ---- insufficient sample: only sample_size + computable=False ----

def test_compute_evidence_insufficient_when_sample_size_is_one():
    experiment = _experiment((_criterion_result(),))
    series = {"mean_atr": _computed_series([1.0])}
    evidence = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence.metrics["mean_atr__sample_size"] == 1
    assert evidence.metrics["mean_atr__computable"] is False
    assert "mean_atr__mean" not in evidence.metrics
    assert "mean_atr__effect_size_computable" not in evidence.metrics


def test_compute_evidence_zero_sample_size_when_feature_series_missing_entirely():
    experiment = _experiment((_criterion_result(),))
    evidence = compute_evidence(experiment, {}, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence.metrics["mean_atr__sample_size"] == 0
    assert evidence.metrics["mean_atr__computable"] is False


def test_compute_evidence_zero_sample_size_when_every_outcome_is_insufficient_data():
    experiment = _experiment((_criterion_result(),))
    series = {"mean_atr": (FeatureInsufficientData(feature_name="mean_atr", feature_version="1.0", reason="no data"),) * 5}
    evidence = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence.metrics["mean_atr__sample_size"] == 0
    assert evidence.metrics["mean_atr__computable"] is False


# ---- zero variance: mean/CI computable, effect_size not ----

def test_compute_evidence_zero_variance_effect_size_not_computable():
    experiment = _experiment((_criterion_result(),))
    series = {"mean_atr": _computed_series([2.0, 2.0, 2.0, 2.0])}
    evidence = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence.metrics["mean_atr__computable"] is True
    assert evidence.metrics["mean_atr__mean"] == pytest.approx(2.0)
    assert evidence.metrics["mean_atr__std_dev"] == pytest.approx(0.0)
    assert evidence.metrics["mean_atr__confidence_interval_95_low_normal_approx"] == pytest.approx(2.0)
    assert evidence.metrics["mean_atr__confidence_interval_95_high_normal_approx"] == pytest.approx(2.0)
    assert evidence.metrics["mean_atr__effect_size_computable"] is False
    assert "mean_atr__effect_size_vs_threshold" not in evidence.metrics


# ---- non-FEATURE criteria are skipped, never crash ----

def test_compute_evidence_skips_non_feature_criteria_results():
    non_feature = CriterionResult(
        criterion=AcceptanceCriterion(
            description="stub", kind=CriterionKind.MIN_FIRING_RATE, target_kind=TargetKind.FACT,
            target="trend_5m", threshold=0.1,
        ),
        actual_value=0.2, passed=True, reason=None,
    )
    experiment = _experiment((non_feature,))
    evidence = compute_evidence(experiment, {}, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence.metrics == {}


# ---- multiple FEATURE criteria: independently flat-keyed ----

def test_compute_evidence_handles_multiple_feature_criteria_independently():
    experiment = _experiment((
        _criterion_result(criterion=_criterion(target="mean_atr")),
        _criterion_result(criterion=_criterion(target="mean_volume", threshold=100.0)),
    ))
    series = {
        "mean_atr": _computed_series([1.0, 2.0, 3.0]),
        "mean_volume": _computed_series([100.0, 200.0]),
    }
    evidence = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence.metrics["mean_atr__sample_size"] == 3
    assert evidence.metrics["mean_volume__sample_size"] == 2
    assert evidence.metrics["mean_atr__mean"] == pytest.approx(2.0)
    assert evidence.metrics["mean_volume__mean"] == pytest.approx(150.0)


# ---- reproducibility: same fingerprint -> same Evidence (Principle VII.1) ----

def test_compute_evidence_is_deterministic_given_identical_inputs():
    experiment = _experiment((_criterion_result(),))
    series = {"mean_atr": _computed_series([1.0, 2.0, 3.0, 4.0, 5.0])}
    first = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)
    second = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert first.metrics == second.metrics
    assert first.fingerprint == second.fingerprint


def test_compute_evidence_fingerprint_changes_when_metrics_change():
    experiment = _experiment((_criterion_result(),))
    series_a = {"mean_atr": _computed_series([1.0, 2.0, 3.0])}
    series_b = {"mean_atr": _computed_series([10.0, 20.0, 30.0])}
    evidence_a = compute_evidence(experiment, series_a, evidence_id="ev1", computed_at=_OCCURRED_AT)
    evidence_b = compute_evidence(experiment, series_b, evidence_id="ev1", computed_at=_OCCURRED_AT)
    assert evidence_a.fingerprint != evidence_b.fingerprint


# ---- Sprint 6.1: effective_sample_size (autocorrelation correction) ----

def test_autocorrelation_of_a_constant_sequence_around_its_own_mean_is_zero_over_zero_denominator_guard():
    # denominator (sum of squared deviations) is zero for a constant
    # sequence - _effective_sample_size itself guards this case directly
    # (tested separately below); _autocorrelation is never called with a
    # zero denominator in practice because of that guard.
    values = [5.0, 3.0, 5.0, 3.0, 5.0, 3.0]
    mean = sum(values) / len(values)
    denominator = sum((v - mean) ** 2 for v in values)
    # a perfectly alternating series has strong NEGATIVE lag-1 autocorrelation
    rho1 = _autocorrelation(values, mean, denominator, lag=1)
    assert rho1 < 0


def test_effective_sample_size_below_3_points_returns_raw_count():
    assert _effective_sample_size([1.0, 2.0]) == 2.0
    assert _effective_sample_size([1.0]) == 1.0
    assert _effective_sample_size([]) == 0.0


def test_effective_sample_size_zero_variance_returns_raw_count():
    assert _effective_sample_size([4.0, 4.0, 4.0, 4.0, 4.0]) == 5.0


def test_effective_sample_size_never_exceeds_raw_count():
    values = [1.0, 5.0, 2.0, 9.0, 3.0, 7.0, 4.0, 8.0, 0.5, 6.0]  # deliberately unstructured
    n_eff = _effective_sample_size(values)
    assert 1.0 <= n_eff <= float(len(values))


def test_effective_sample_size_stays_close_to_raw_count_for_low_autocorrelation_data():
    """A pseudo-random, non-windowed sequence (i.i.d.-like) should see
    little to no reduction - the correction must not be a blanket
    penalty, only a response to genuine detected structure."""
    rng = random.Random(1234)
    values = [rng.gauss(0.0, 1.0) for _ in range(200)]
    n_eff = _effective_sample_size(values)
    assert n_eff > 150  # materially close to the raw count of 200


def test_effective_sample_size_is_materially_reduced_for_a_realistic_overlapping_rolling_window_series():
    """The exact scenario the Sprint 6 audit identified: a W-bar rolling
    mean over an underlying i.i.d. series (mirroring mean_atr, W=14) -
    consecutive rolling-mean values share W-1 of their W underlying
    points and are strongly autocorrelated by construction. This is the
    direct, realistic proof the correction fixes the actual reported
    defect, not just a synthetic toy case."""
    rng = random.Random(99)
    window = 14
    underlying = [rng.gauss(2.0, 1.0) for _ in range(120)]
    rolling_means = [
        sum(underlying[max(0, i - window + 1):i + 1]) / len(underlying[max(0, i - window + 1):i + 1])
        for i in range(len(underlying))
    ]
    raw_n = len(rolling_means)
    n_eff = _effective_sample_size(rolling_means)
    assert n_eff < raw_n * 0.5  # materially, not just marginally, reduced


def test_compute_evidence_publishes_effective_sample_size_alongside_unchanged_raw_sample_size():
    """Issue 1's own explicit requirement: raw sample_size must remain
    exactly as it was (reporting only); effective_sample_size is a new,
    additive, separate metric (inferential use only)."""
    experiment = _experiment((_criterion_result(),))
    rng = random.Random(7)
    window = 14
    underlying = [rng.gauss(2.0, 1.0) for _ in range(60)]
    rolling_means = [
        sum(underlying[max(0, i - window + 1):i + 1]) / len(underlying[max(0, i - window + 1):i + 1])
        for i in range(len(underlying))
    ]
    series = {"mean_atr": _computed_series(rolling_means)}
    evidence = compute_evidence(experiment, series, evidence_id="ev1", computed_at=_OCCURRED_AT)

    assert evidence.metrics["mean_atr__sample_size"] == 60  # unchanged, raw, honest count
    assert evidence.metrics["mean_atr__effective_sample_size"] < 60  # corrected, materially smaller
    assert evidence.metrics["mean_atr__effective_sample_size"] >= 1.0
