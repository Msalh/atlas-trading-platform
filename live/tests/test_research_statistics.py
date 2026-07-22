"""
Phase N4 Sprint 5. Tests for atlas.research.statistics.compute_evidence()
against hand-built Feature data - unit tests for sample-size edge cases,
zero-variance handling, and a dedicated reproducibility test proving the
same Experiment fingerprint always reproduces the same Evidence
(Principle VII.1's first real test).
"""
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
from atlas.research.statistics.service import compute_evidence

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
