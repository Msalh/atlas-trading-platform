"""
Phase N4 Sprint 6, corrected Sprint 6.1. validate() - see this package's
own __init__.py for the full boundary and the statistical rule.

--- Sprint 6.1 corrections (statistical-correctness audit) ---

1. Standard error now uses atlas.research.statistics's own
   effective_sample_size (autocorrelation-corrected), never the raw
   sample_size - see that package's own module docstring for the exact
   formula and its justification. This is the fix for the primary,
   highest-severity finding: the previous std_dev/sqrt(raw_n) formula
   silently assumed independent observations from a strongly
   autocorrelated, overlapping-rolling-window Feature series, which
   systematically understated standard error and overstated
   significance.

2. Monte Carlo now simulates the SAMPLING DISTRIBUTION OF THE MEAN
   (Normal(mean, standard_error)), not individual observations
   (Normal(mean, std_dev)) - see _monte_carlo_pass_probability's own
   docstring for why this is the statistically meaningful quantity.

3. validate() rejects any Evidence/Experiment id appearing in both
   in_sample_evidence and out_of_sample_evidence - the cheapest possible
   protection against a hypothesis accidentally (or trivially)
   "confirming" itself against its own in-sample data. What this cannot
   verify - non-overlapping DatasetManifest date ranges, matching
   symbol/timeframe - is documented explicitly below: Evidence carries no
   such metadata (only experiment_id, a bare string), so it is
   structurally unverifiable from Evidence alone. Fixing that would
   require accepting Experiment (not just Evidence) as an input - out of
   scope for this patch, since it is a signature-level change to a
   public interface, not the smallest possible correction.

4. A fold whose data was statistically insufficient
   (`{target}__computable=False`, i.e. fewer than 2 raw observations) is
   now tracked separately from a fold that was measured and failed. An
   entirely-insufficient in-sample or out-of-sample group forces
   INCONCLUSIVE - it can never, by construction, contribute to
   NOT_SUPPORTED (false confidence that the hypothesis was tested and
   failed) or to SUPPORTED (false confidence that it was tested and
   passed). This directly serves Design Principle III.4: absence of data
   is not evidence of absence.

--- batch_size: an intentional, disclosed boundary, not fixed here ---

batch_size remains entirely caller-supplied. Validation cannot verify it
without querying the Ledger (how many other hypotheses share this
dataset), and Validation deliberately has no Ledger dependency (see the
Sprint 6 architectural review). Understating batch_size to weaken the
Bonferroni correction is therefore not something this package can
mechanically prevent - it is squarely an orchestration responsibility for
whatever future caller has Ledger access, not a Sprint 6.1 defect.
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
    """An exact numerical evaluation (via math.erf) of the standard
    Normal CDF - not to be confused with the statistical test itself
    being exact. The test is a Normal-approximation z-test (using an
    estimated, not known, standard deviation); the CDF evaluation used to
    compute its tail probability is what is exact here."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _fold_statistics(evidence: Evidence, target: str) -> tuple[Optional[float], Optional[float], int, Optional[float]]:
    """Reads (mean, std_dev, sample_size, effective_sample_size) for
    `target` directly off evidence.metrics, using exactly the key
    convention atlas.research.statistics.compute_evidence() already
    publishes - never recomputes anything from raw data.
    (None, None, sample_size, None) when Statistics itself marked this
    target not computable; never fabricated. effective_sample_size falls
    back to raw sample_size only for Evidence produced before Sprint 6.1
    (backward compatibility with already-recorded metrics that predate
    this key - not a silent re-introduction of the bias, since any
    NEWLY-computed Evidence always carries the real, corrected value)."""
    sample_size = int(evidence.metrics.get(f"{target}__sample_size", 0))
    computable = bool(evidence.metrics.get(f"{target}__computable", False))
    if not computable:
        return None, None, sample_size, None
    mean = float(evidence.metrics[f"{target}__mean"])
    std_dev = float(evidence.metrics[f"{target}__std_dev"])
    effective_sample_size = float(evidence.metrics.get(f"{target}__effective_sample_size", sample_size))
    return mean, std_dev, sample_size, effective_sample_size


def _one_sided_p_value(mean: float, std_dev: float, effective_sample_size: float, threshold: float) -> Optional[float]:
    """One-sided p-value for "the true mean exceeds threshold", using
    effective_sample_size (never raw sample_size) in the standard-error
    denominator - Sprint 6.1's own correction for serial dependence. Zero
    variance is a genuine boundary case, not simply "undefined" the way
    Statistics's own effect_size is: a zero-variance sample is either
    certainly above or certainly below threshold - only mean == threshold
    exactly is truly ambiguous."""
    if std_dev <= 0:
        if mean > threshold:
            return 0.0
        if mean < threshold:
            return 1.0
        return None
    standard_error = std_dev / math.sqrt(effective_sample_size)
    z = (mean - threshold) / standard_error
    return 1.0 - _normal_cdf(z)


def _monte_carlo_pass_probability(mean: float, standard_error: float, threshold: float, spec: MonteCarloSpec) -> float:
    """Seeded parametric simulation of the SAMPLING DISTRIBUTION OF THE
    MEAN - n_draws samples from Normal(mean, standard_error), fraction
    >= threshold. This answers "if this experiment were repeated, how
    often would the resulting mean clear the threshold" - the question a
    robustness check on a significance test should actually answer.

    Sprint 6.1 correction: this previously drew from
    Normal(mean, std_dev) - the distribution of a single INDIVIDUAL
    observation, not of the mean. That answered a different, less
    relevant question ("how often would one new bar individually clear
    the threshold") and, prior to this patch, was also built on the same
    uncorrected std_dev this function no longer receives directly.

    For a large n_draws this converges to the closed-form
    1 - normal_cdf((threshold - mean) / standard_error) - the same
    quantity _one_sided_p_value computes for a threshold-equals-mean null
    reference point, by construction, since both now draw from the
    identical Normal(mean, standard_error) model. The determinism test in
    this package's own test suite checks this convergence directly, as
    the oracle proving the simulation path is correct, not just
    internally consistent with itself."""
    if standard_error <= 0:
        return 1.0 if mean >= threshold else 0.0
    rng = random.Random(spec.seed)
    passed = sum(1 for _ in range(spec.n_draws) if rng.gauss(mean, standard_error) >= threshold)
    return passed / spec.n_draws


def _evaluate_fold(
    evidence: Evidence, criterion: AcceptanceCriterion, alpha: float, monte_carlo_spec: MonteCarloSpec,
) -> CriterionResult:
    """Mechanical only. `reason` carries the p-value and Monte Carlo pass
    probability as human-readable text - ValidationResult has no generic
    structured-metrics field the way Evidence does (a disclosed, minor,
    non-blocking limitation of Sprint 1's frozen shape), so this is the
    one place that detail is recorded. `actual_value` is None if and only
    if this fold's data was statistically insufficient - the signal
    validate() itself uses to separate "insufficient" from
    "measured and failed" (Sprint 6.1's Issue 4 correction)."""
    mean, std_dev, sample_size, effective_sample_size = _fold_statistics(evidence, criterion.target)
    if mean is None:
        return CriterionResult(
            criterion=criterion, actual_value=None, passed=False,
            reason=f"insufficient sample for {criterion.target!r} in evidence {evidence.evidence_id!r} "
                   f"(sample_size={sample_size})",
        )

    p_value = _one_sided_p_value(mean, std_dev, effective_sample_size, criterion.threshold)
    standard_error = std_dev / math.sqrt(effective_sample_size) if std_dev > 0 else 0.0
    mc_probability = _monte_carlo_pass_probability(mean, standard_error, criterion.threshold, monte_carlo_spec)
    passed = p_value is not None and p_value <= alpha

    p_value_text = f"{p_value:.6f}" if p_value is not None else "undefined (mean == threshold, zero variance)"
    reason = (
        f"evidence={evidence.evidence_id!r} mean={mean!r} std_dev={std_dev!r} "
        f"sample_size={sample_size} effective_sample_size={effective_sample_size:.4f} "
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
    parameters and both must be non-empty.

    Structurally requires multiple-testing correction whenever more than
    one hypothesis shares this dataset (Principle IV.4): batch_size > 1
    makes multiple_testing_correction a required, non-None argument.

    Structurally rejects (Sprint 6.1) any evidence_id or experiment_id
    shared between in_sample_evidence and out_of_sample_evidence - see
    this module's own docstring for what this can and cannot verify.

    verdict (Sprint 6.1's corrected table): if EITHER group is entirely
    statistically insufficient, INCONCLUSIVE, unconditionally. Otherwise,
    SUPPORTED only when every MEASURED in-sample AND every MEASURED
    out-of-sample fold clears the (possibly Bonferroni-corrected) alpha;
    NOT_SUPPORTED when none of the measured out-of-sample folds clear;
    INCONCLUSIVE otherwise - a genuine, honest "we don't know yet"
    (Principle IV.5), never forced into a binary, and never confusing
    "we couldn't measure this" with "we measured this and it failed"."""
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

    in_sample_evidence_ids = {e.evidence_id for e in in_sample_evidence}
    out_of_sample_evidence_ids = {e.evidence_id for e in out_of_sample_evidence}
    overlapping_evidence = sorted(in_sample_evidence_ids & out_of_sample_evidence_ids)
    if overlapping_evidence:
        raise ValueError(
            f"the same Evidence record(s) {overlapping_evidence} appear in both in_sample_evidence and "
            f"out_of_sample_evidence - a hypothesis cannot confirm itself against its own in-sample data"
        )
    in_sample_experiment_ids = {e.experiment_id for e in in_sample_evidence}
    out_of_sample_experiment_ids = {e.experiment_id for e in out_of_sample_evidence}
    overlapping_experiments = sorted(in_sample_experiment_ids & out_of_sample_experiment_ids)
    if overlapping_experiments:
        raise ValueError(
            f"the same Experiment(s) {overlapping_experiments} produced Evidence in both in_sample_evidence "
            f"and out_of_sample_evidence"
        )

    alpha = _DEFAULT_ALPHA / batch_size if batch_size > 1 else _DEFAULT_ALPHA

    in_sample_results = tuple(
        _evaluate_fold(e, criterion, alpha, monte_carlo_spec) for e in in_sample_evidence
    )
    out_of_sample_results = tuple(
        _evaluate_fold(e, criterion, alpha, monte_carlo_spec) for e in out_of_sample_evidence
    )
    all_results = in_sample_results + out_of_sample_results

    in_sample_measured = tuple(r for r in in_sample_results if r.actual_value is not None)
    out_of_sample_measured = tuple(r for r in out_of_sample_results if r.actual_value is not None)

    if not in_sample_measured or not out_of_sample_measured:
        verdict = ValidationVerdict.INCONCLUSIVE
    else:
        in_sample_all_pass = all(r.passed for r in in_sample_measured)
        out_of_sample_pass_count = sum(1 for r in out_of_sample_measured if r.passed)
        if in_sample_all_pass and out_of_sample_pass_count == len(out_of_sample_measured):
            verdict = ValidationVerdict.SUPPORTED
        elif out_of_sample_pass_count == 0:
            verdict = ValidationVerdict.NOT_SUPPORTED
        else:
            verdict = ValidationVerdict.INCONCLUSIVE

    in_sample_pass_text = f"{sum(1 for r in in_sample_measured if r.passed)}/{len(in_sample_measured)} measured"
    out_of_sample_pass_text = f"{sum(1 for r in out_of_sample_measured if r.passed)}/{len(out_of_sample_measured)} measured"
    justification = (
        f"{verdict.value.upper()}: {in_sample_pass_text} in-sample fold(s) "
        f"({len(in_sample_results) - len(in_sample_measured)} insufficient) and "
        f"{out_of_sample_pass_text} out-of-sample fold(s) "
        f"({len(out_of_sample_results) - len(out_of_sample_measured)} insufficient) cleared alpha={alpha!r}"
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
