"""
Phase N4 Sprint 6. validate() - see this package's own __init__.py for the
full boundary, the statistical rule, and why Monte Carlo here is
deliberately parametric.
"""
import math
import random
from typing import Optional

from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import (
    AcceptanceCriterion,
    CriterionResult,
    Evidence,
    ValidationResult,
    ValidationVerdict,
)
from atlas.research.validation.models import MonteCarloSpec, WalkForwardSpec

_DEFAULT_ALPHA = 0.05


def _normal_cdf(z: float) -> float:
    """Exact, via math.erf - no numerical approximation, no external
    dependency."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _fold_statistics(evidence: Evidence, target: str) -> tuple[Optional[float], Optional[float], int]:
    """Reads (mean, std_dev, sample_size) for `target` directly off
    evidence.metrics, using exactly the key convention
    atlas.research.statistics.compute_evidence() already publishes
    (f"{target}__mean" etc.) - never recomputes anything from raw data.
    (None, None, sample_size) when Statistics itself marked this target
    not computable; never fabricated."""
    sample_size = int(evidence.metrics.get(f"{target}__sample_size", 0))
    computable = bool(evidence.metrics.get(f"{target}__computable", False))
    if not computable:
        return None, None, sample_size
    return float(evidence.metrics[f"{target}__mean"]), float(evidence.metrics[f"{target}__std_dev"]), sample_size


def _one_sided_p_value(mean: float, std_dev: float, sample_size: int, threshold: float) -> Optional[float]:
    """One-sided p-value for "the true mean exceeds threshold". Zero
    variance is a genuine boundary case, not simply "undefined" the way
    Statistics's own effect_size is (that divides BY std_dev; a p-value's
    z-statistic does too, but a zero-variance sample is either certainly
    above or certainly below threshold - only mean == threshold exactly
    is truly ambiguous)."""
    if std_dev <= 0:
        if mean > threshold:
            return 0.0
        if mean < threshold:
            return 1.0
        return None
    standard_error = std_dev / math.sqrt(sample_size)
    z = (mean - threshold) / standard_error
    return 1.0 - _normal_cdf(z)


def _monte_carlo_pass_probability(mean: float, std_dev: float, threshold: float, spec: MonteCarloSpec) -> float:
    """Seeded parametric simulation - n_draws samples from
    Normal(mean, std_dev), fraction >= threshold. For a large n_draws
    this converges to the closed-form 1 - normal_cdf((threshold - mean) /
    std_dev) - the determinism test in this package's own test suite
    checks exactly that, as the oracle proving this simulation path is
    correct, not just internally consistent with itself."""
    if std_dev <= 0:
        return 1.0 if mean >= threshold else 0.0
    rng = random.Random(spec.seed)
    passed = sum(1 for _ in range(spec.n_draws) if rng.gauss(mean, std_dev) >= threshold)
    return passed / spec.n_draws


def _evaluate_fold(
    evidence: Evidence, criterion: AcceptanceCriterion, alpha: float, monte_carlo_spec: MonteCarloSpec,
) -> CriterionResult:
    """Mechanical only. `reason` carries the p-value and Monte Carlo pass
    probability as human-readable text - ValidationResult has no generic
    structured-metrics field the way Evidence does (a disclosed, minor,
    non-blocking limitation of Sprint 1's frozen shape - see this
    package's own architectural review), so this is the one place that
    detail is recorded."""
    mean, std_dev, sample_size = _fold_statistics(evidence, criterion.target)
    if mean is None:
        return CriterionResult(
            criterion=criterion, actual_value=None, passed=False,
            reason=f"insufficient sample for {criterion.target!r} in evidence {evidence.evidence_id!r} "
                   f"(sample_size={sample_size})",
        )

    p_value = _one_sided_p_value(mean, std_dev, sample_size, criterion.threshold)
    mc_probability = _monte_carlo_pass_probability(mean, std_dev, criterion.threshold, monte_carlo_spec)
    passed = p_value is not None and p_value <= alpha

    p_value_text = f"{p_value:.6f}" if p_value is not None else "undefined (mean == threshold, zero variance)"
    reason = (
        f"evidence={evidence.evidence_id!r} mean={mean!r} std_dev={std_dev!r} n={sample_size} "
        f"threshold={criterion.threshold!r} one_sided_p={p_value_text} alpha={alpha!r} "
        f"monte_carlo_pass_probability={mc_probability:.4f} (n_draws={monte_carlo_spec.n_draws}, "
        f"seed={monte_carlo_spec.seed})"
    )
    return CriterionResult(criterion=criterion, actual_value=mean, passed=passed, reason=reason)


def _compute_validation_fingerprint(
    hypothesis_id: str, evidence_ids: tuple[str, ...], criterion: AcceptanceCriterion,
    batch_size: int, multiple_testing_correction: Optional[str],
) -> str:
    return compute_fingerprint({
        "hypothesis_id": hypothesis_id,
        "evidence_ids": sorted(evidence_ids),
        "criterion": {
            "kind": criterion.kind.value, "target_kind": criterion.target_kind.value,
            "target": criterion.target, "threshold": criterion.threshold,
        },
        "batch_size": batch_size,
        "multiple_testing_correction": multiple_testing_correction,
    })


def validate(
    hypothesis_id: str,
    in_sample_evidence: tuple[Evidence, ...],
    out_of_sample_evidence: tuple[Evidence, ...],
    criterion: AcceptanceCriterion,
    walk_forward_spec: WalkForwardSpec,
    monte_carlo_spec: MonteCarloSpec,
    batch_size: int,
    validation_id: str,
    validated_at: str,
    multiple_testing_correction: Optional[str] = None,
) -> ValidationResult:
    """Deterministic given its inputs (including monte_carlo_spec.seed).

    Structurally requires out-of-sample evidence (Principle IV.3):
    in_sample_evidence/out_of_sample_evidence are both required
    parameters and both must be non-empty - it is impossible to call this
    function at all, let alone reach SUPPORTED, without at least one
    out-of-sample fold.

    Structurally requires multiple-testing correction whenever more than
    one hypothesis shares this dataset (Principle IV.4): batch_size > 1
    makes multiple_testing_correction a required, non-None argument -
    raises otherwise, rather than silently validating uncorrected.

    verdict: SUPPORTED only when every in-sample AND every out-of-sample
    fold clears the (possibly Bonferroni-corrected) alpha; NOT_SUPPORTED
    when none of the out-of-sample folds clear; INCONCLUSIVE otherwise -
    a genuine, honest "we don't know yet" (Principle IV.5), never forced
    into a binary."""
    if not in_sample_evidence:
        raise ValueError("validate() requires at least one in-sample Evidence record")
    if not out_of_sample_evidence:
        raise ValueError("validate() requires at least one out-of-sample Evidence record - Principle IV.3")
    if batch_size < 1:
        raise ValueError(f"batch_size must be >= 1, got {batch_size}")
    if batch_size > 1 and not multiple_testing_correction:
        raise ValueError(
            f"batch_size={batch_size} shares this dataset across multiple hypotheses - "
            f"multiple_testing_correction is mandatory (Principle IV.4), not merely recommended"
        )
    if walk_forward_spec.in_sample_fold_count != len(in_sample_evidence):
        raise ValueError(
            f"walk_forward_spec claims {walk_forward_spec.in_sample_fold_count} in-sample folds, "
            f"but {len(in_sample_evidence)} in_sample_evidence records were supplied"
        )
    if walk_forward_spec.out_of_sample_fold_count != len(out_of_sample_evidence):
        raise ValueError(
            f"walk_forward_spec claims {walk_forward_spec.out_of_sample_fold_count} out-of-sample folds, "
            f"but {len(out_of_sample_evidence)} out_of_sample_evidence records were supplied"
        )

    alpha = _DEFAULT_ALPHA / batch_size if batch_size > 1 else _DEFAULT_ALPHA

    in_sample_results = tuple(
        _evaluate_fold(e, criterion, alpha, monte_carlo_spec) for e in in_sample_evidence
    )
    out_of_sample_results = tuple(
        _evaluate_fold(e, criterion, alpha, monte_carlo_spec) for e in out_of_sample_evidence
    )
    all_results = in_sample_results + out_of_sample_results

    in_sample_all_pass = all(r.passed for r in in_sample_results)
    out_of_sample_pass_count = sum(1 for r in out_of_sample_results if r.passed)

    if in_sample_all_pass and out_of_sample_pass_count == len(out_of_sample_results):
        verdict = ValidationVerdict.SUPPORTED
    elif out_of_sample_pass_count == 0:
        verdict = ValidationVerdict.NOT_SUPPORTED
    else:
        verdict = ValidationVerdict.INCONCLUSIVE

    justification = (
        f"{verdict.value.upper()}: {sum(1 for r in in_sample_results if r.passed)}/{len(in_sample_results)} "
        f"in-sample fold(s) and {out_of_sample_pass_count}/{len(out_of_sample_results)} out-of-sample fold(s) "
        f"cleared alpha={alpha!r}"
        + (f" (Bonferroni-corrected for batch_size={batch_size})" if batch_size > 1 else "")
        + f". Fold scheme: {walk_forward_spec.fold_scheme_description!r}."
    )

    evidence_ids = tuple(e.evidence_id for e in in_sample_evidence) + tuple(e.evidence_id for e in out_of_sample_evidence)
    fingerprint = _compute_validation_fingerprint(
        hypothesis_id, evidence_ids, criterion, batch_size, multiple_testing_correction,
    )

    return ValidationResult(
        validation_id=validation_id, hypothesis_id=hypothesis_id, evidence_ids=evidence_ids,
        verdict=verdict, criteria_results=all_results, justification=justification,
        validated_at=validated_at, out_of_sample=True,
        multiple_testing_correction=multiple_testing_correction, fingerprint=fingerprint,
    )
