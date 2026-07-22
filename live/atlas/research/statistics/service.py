"""
Phase N4 Sprint 5. compute_evidence() - see this package's own __init__.py
for the full boundary.

Sample statistics use the standard unbiased (n-1, Bessel-corrected) sample
variance - the correct estimator for inferring about a population from a
sample, not the population variance atlas.research.statistical_profiling's
own _pearson_correlation uses (that computation needs no such correction).
The 95% confidence interval uses the normal (z = 1.96) approximation, not
Student's t - disclosed explicitly here and in each metric's own key name,
since the t-distribution is the more precise choice for small samples and
this is a deliberate, honest simplification for Stage A, not an oversight.
"""
import math
from typing import Mapping, Union

from atlas.research.features.models import FeatureComputed, FeatureOutcome
from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import Evidence, Experiment, TargetKind

_Number = Union[int, float, str, bool]


def compute_evidence(
    experiment: Experiment, feature_series: Mapping[str, tuple[FeatureOutcome, ...]],
    evidence_id: str, computed_at: str,
) -> Evidence:
    """Never None when a value could not be computed (Design Principle
    III.4 - insufficient data must be modeled as its own explicit
    outcome): every derived metric is guarded by its own `_computable`
    boolean flag, present alongside it, rather than being silently
    omitted or fabricated as a placeholder number. sample_size is always
    present, for every FEATURE-targeted criterion on `experiment`, even
    when nothing else could be computed."""
    metrics: dict[str, _Number] = {}

    for result in experiment.criteria_results:
        if result.criterion.target_kind != TargetKind.FEATURE:
            continue
        feature_id = result.criterion.target
        series = feature_series.get(feature_id, ())
        values = [outcome.value for outcome in series if isinstance(outcome, FeatureComputed)]
        n = len(values)

        prefix = feature_id
        metrics[f"{prefix}__sample_size"] = n
        computable = n >= 2
        metrics[f"{prefix}__computable"] = computable
        if not computable:
            continue

        mean = sum(values) / n
        variance = sum((v - mean) ** 2 for v in values) / (n - 1)
        std_dev = math.sqrt(variance)
        standard_error = std_dev / math.sqrt(n)

        metrics[f"{prefix}__mean"] = mean
        metrics[f"{prefix}__std_dev"] = std_dev
        metrics[f"{prefix}__confidence_interval_95_low_normal_approx"] = mean - 1.96 * standard_error
        metrics[f"{prefix}__confidence_interval_95_high_normal_approx"] = mean + 1.96 * standard_error

        effect_size_computable = std_dev > 0
        metrics[f"{prefix}__effect_size_computable"] = effect_size_computable
        if effect_size_computable:
            metrics[f"{prefix}__effect_size_vs_threshold"] = (mean - result.criterion.threshold) / std_dev

    fingerprint = compute_fingerprint({"experiment_id": experiment.experiment_id, "metrics": metrics})
    return Evidence(
        evidence_id=evidence_id, experiment_id=experiment.experiment_id, computed_at=computed_at,
        metrics=metrics, fingerprint=fingerprint,
    )
