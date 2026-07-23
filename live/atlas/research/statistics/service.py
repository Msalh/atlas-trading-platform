"""
Phase N4 Sprint 5, corrected Sprint 6.1. compute_evidence() - see this
package's own __init__.py for the full boundary.

Sample statistics use the standard unbiased (n-1, Bessel-corrected) sample
variance - the correct estimator for inferring about a population from a
sample, not the population variance atlas.research.statistical_profiling's
own _pearson_correlation uses (that computation needs no such correction).
The 95% confidence interval uses the normal (z = 1.96) approximation, not
Student's t - disclosed explicitly here and in each metric's own key name,
since the t-distribution is the more precise choice for small samples and
this is a deliberate, honest simplification for Stage A, not an oversight.

--- Sprint 6.1: effective_sample_size (autocorrelation correction) ---

A Feature's per-bar series (e.g. mean_atr, a 14-bar rolling window) is NOT
a sequence of independent observations: consecutive values share all but
one of their underlying bars, so they are strongly serially correlated.
Treating the raw count `n` as if it were an independent-observations count
(standard_error = std_dev / sqrt(n)) systematically UNDERSTATES the true
standard error and therefore OVERSTATES statistical significance - an
anti-conservative bias, found and confirmed against this exact
implementation in the Sprint 6 statistical-correctness audit.

effective_sample_size corrects for this using the standard long-run-
variance inflation factor for autocorrelated time series (the same
quantity underlying Newey-West HAC standard errors in econometrics, and
Geyer's (1992) "initial positive sequence" effective-sample-size estimator
for autocorrelated Markov chains - directly applicable here, since a
rolling-window Feature series is exactly this kind of autocorrelated
sequence):

    Var(mean) = (std_dev^2 / n) * tau
    tau = 1 + 2 * sum_{k=1}^{K} (1 - k/n) * rho_k
    effective_sample_size = n / tau

where rho_k is the empirical lag-k autocorrelation of the per-bar values,
weighted by the Bartlett taper (1 - k/n) (the same taper Newey-West uses,
which down-weights noisier, higher-lag estimates), summed until the first
non-positive rho_k (Geyer's truncation rule - guarantees the partial sum
stays a genuine, non-fabricated estimate rather than accumulating sample
noise from lags with no real remaining structure), capped at min(n-1, 100)
lags to bound cost. effective_sample_size is clipped to [1, n] - it can
never exceed the raw count (independent data has tau=1, the boundary
case) and never drops below 1.

raw sample_size (`{prefix}__sample_size`) remains exactly as it was -
the true count of computed Feature values, kept for reporting/
computability gating (Design Principle III.4's own "at least 2 observed
values" bar) and never overwritten. effective_sample_size
(`{prefix}__effective_sample_size`) is a NEW, additive metric, used only
downstream, for inferential statistics (atlas.research.validation's own
standard-error/p-value/Monte Carlo calculations) - never for reporting
"how much data did we actually observe," which raw sample_size alone
answers honestly.
"""
import math
from typing import Mapping, Optional, Union

from atlas.research.backtesting.models import ResearchDecision, ResearchDispositionKind
from atlas.research.features.models import FeatureComputed, FeatureOutcome
from atlas.research.fingerprint import compute_fingerprint
from atlas.research.models import AcceptanceCriterion, Evidence, Experiment, TargetKind
from atlas.research.replay_bridge import ReplayFrame

_Number = Union[int, float, str, bool]
_MAX_AUTOCORRELATION_LAG = 100


def _autocorrelation(values: list[float], mean: float, denominator: float, lag: int) -> float:
    """Empirical lag-k autocorrelation of `values` around their own mean -
    the standard sample autocorrelation estimator. `denominator` (the
    sum of squared deviations) is passed in rather than recomputed per
    lag, since every call within one effective-sample-size computation
    shares the same value."""
    numerator = sum((values[i] - mean) * (values[i + lag] - mean) for i in range(len(values) - lag))
    return numerator / denominator


def _effective_sample_size(values: list[float]) -> float:
    """See this module's own docstring for the exact formula and its
    statistical justification. Returns the raw count unchanged when fewer
    than 3 points exist (no lag is even estimable) or when variance is
    zero (no autocorrelation is meaningful - the effect_size/p-value
    machinery downstream already special-cases zero variance on its
    own)."""
    n = len(values)
    if n < 3:
        return float(n)
    mean = sum(values) / n
    denominator = sum((v - mean) ** 2 for v in values)
    if denominator == 0:
        return float(n)

    max_lag = min(n - 1, _MAX_AUTOCORRELATION_LAG)
    tau = 1.0
    for lag in range(1, max_lag + 1):
        rho = _autocorrelation(values, mean, denominator, lag)
        if rho <= 0:
            break
        tau += 2.0 * (1.0 - lag / n) * rho

    effective_n = n / tau
    return max(1.0, min(effective_n, float(n)))


def _series_statistics_metrics(prefix: str, values: list[float], threshold: float) -> dict[str, _Number]:
    """Sprint 8.1. The one shared formula block, extracted verbatim (not
    rewritten) from compute_evidence()'s own per-criterion loop below -
    computes the full {prefix}__* metric family (sample_size/computable/
    mean/std_dev/effective_sample_size/confidence_interval_95_low/
    high_normal_approx/effect_size_computable/effect_size_vs_threshold)
    from an arbitrary per-observation float series. Used identically by
    compute_evidence() (a Feature's own per-bar values) and
    compute_decision_sequence_evidence() (a decision-rate target's own
    per-frame 0/1 indicator series) - a 0/1 indicator series is, for this
    formula's purposes, just another per-observation float series;
    nothing here assumes continuity. Every operation, in the same order,
    as this block's own pre-extraction form - relocated, not altered, so
    Feature-based Evidence remains numerically identical in every case."""
    n = len(values)
    metrics: dict[str, _Number] = {f"{prefix}__sample_size": n}
    computable = n >= 2
    metrics[f"{prefix}__computable"] = computable
    if not computable:
        return metrics

    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    std_dev = math.sqrt(variance)
    effective_sample_size = _effective_sample_size(values)
    # The confidence interval is an inferential statistic exactly like
    # the p-value Validation computes downstream, and was subject to
    # the identical raw-n anti-conservative bias - corrected here too
    # (Sprint 6.1), using the same effective_sample_size. The key name
    # (and its own "normal_approx" disclosure) is unchanged; only the
    # value is now honest about serial dependence.
    standard_error = std_dev / math.sqrt(effective_sample_size)

    metrics[f"{prefix}__mean"] = mean
    metrics[f"{prefix}__std_dev"] = std_dev
    metrics[f"{prefix}__effective_sample_size"] = effective_sample_size
    metrics[f"{prefix}__confidence_interval_95_low_normal_approx"] = mean - 1.96 * standard_error
    metrics[f"{prefix}__confidence_interval_95_high_normal_approx"] = mean + 1.96 * standard_error

    effect_size_computable = std_dev > 0
    metrics[f"{prefix}__effect_size_computable"] = effect_size_computable
    if effect_size_computable:
        metrics[f"{prefix}__effect_size_vs_threshold"] = (mean - threshold) / std_dev

    return metrics


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
        metrics.update(_series_statistics_metrics(feature_id, values, result.criterion.threshold))

    fingerprint = compute_fingerprint({"experiment_id": experiment.experiment_id, "metrics": metrics})
    return Evidence(
        evidence_id=evidence_id, experiment_id=experiment.experiment_id, computed_at=computed_at,
        metrics=metrics, fingerprint=fingerprint,
    )


_DECISION_RATE_TARGETS: dict[ResearchDispositionKind, str] = {
    ResearchDispositionKind.NO_ACTION: "no_action_rate",
    ResearchDispositionKind.ENTER_LONG: "enter_long_rate",
    ResearchDispositionKind.ENTER_SHORT: "enter_short_rate",
    ResearchDispositionKind.EXIT: "exit_rate",
}
_TARGET_TO_DISPOSITION: dict[str, ResearchDispositionKind] = {v: k for k, v in _DECISION_RATE_TARGETS.items()}


def decision_rate_target(disposition: ResearchDispositionKind) -> str:
    """Sprint 8.1. The one authoritative ResearchDispositionKind ->
    decision-rate target name mapping - never reproduced via scattered
    string concatenation elsewhere in this package. enter_long_rate means
    ENTER_LONG decisions per evaluated ReplayFrame. It does NOT mean trade
    win rate, probability of profit, profitable-trade frequency, or
    expectancy - those require matching decisions against price data plus
    commission/slippage assumptions that appear nowhere in the frozen
    roadmap for this sprint, deliberately not computed here."""
    return _DECISION_RATE_TARGETS[disposition]


def compute_decision_sequence_evidence(
    experiment: Experiment, decisions: tuple[ResearchDecision, ...], frames: tuple[ReplayFrame, ...],
    criteria: tuple[AcceptanceCriterion, ...], evidence_id: str, computed_at: str,
    decision_sequence_path: Optional[str] = None,
) -> Evidence:
    """Sprint 8, revised Sprint 8.1. Statistics's own decision-sequence
    counterpart to compute_evidence() (the Feature-series path above,
    Sprint 5, untouched) - given an already-executed decision sequence
    (atlas.research.backtesting's own output, never re-executed here: this
    function reads ResearchDecision as a plain value type, exactly the
    same "TYPE only, never the computation machinery" posture already
    established for FeatureOutcome/FeatureComputed above), computes:

    1. Descriptive decision-frequency metrics (sample_size, and per-
       disposition counts/rates for all four ResearchDispositionKind
       values) - unconditional, exactly as Sprint 8 first built them.

    2. Inferential metrics (mean/std_dev/effective_sample_size/confidence_
       interval/effect_size), via the identical _series_statistics_metrics()
       helper compute_evidence() uses - but ONLY for the decision-rate
       targets `criteria` actually asks for (each TargetKind.DECISION_SEQUENCE
       criterion's own `target`, resolved back to a ResearchDispositionKind
       via decision_rate_target()'s own closed mapping), never for every
       disposition merely because it exists. FEATURE/FACT/SETUP criteria in
       `criteria` are not this function's concern and are silently skipped
       here - the same symmetric posture compute_evidence() already applies
       to non-FEATURE criteria - never rejected, since a hypothesis may
       legitimately carry both kinds (see build_realization_experiment()'s
       own Sprint 8.1 update). An unrecognized decision-rate target name
       fails explicitly - never silently skipped, never producing empty or
       default metrics for it.

    Never realized P&L/win-rate: see decision_rate_target()'s own docstring
    for exactly what a decision-rate target does and does not mean.

    decision_sequence_path is a plain pass-through, never written by this
    function - Statistics stays pure/no-I/O (this package's own __init__.py),
    exactly mirroring Experiment.profiling_report_path's own long-standing
    "always None until something else deliberately writes one" precedent."""
    if len(decisions) != len(frames):
        raise ValueError(
            f"decisions ({len(decisions)}) and frames ({len(frames)}) must be the same length - "
            f"exactly one ResearchDecision per evaluated ReplayFrame"
        )

    n = len(decisions)
    metrics: dict[str, _Number] = {"decision_sequence__sample_size": n}
    computable = n > 0
    metrics["decision_sequence__computable"] = computable
    if computable:
        for kind in ResearchDispositionKind:
            count = sum(1 for d in decisions if d.disposition == kind)
            metrics[f"decision_sequence__{kind.value}_count"] = count
            metrics[f"decision_sequence__{kind.value}_rate"] = count / n

    for criterion in criteria:
        if criterion.target_kind != TargetKind.DECISION_SEQUENCE:
            continue
        disposition = _TARGET_TO_DISPOSITION.get(criterion.target)
        if disposition is None:
            raise ValueError(
                f"unknown decision-rate target {criterion.target!r} - must be one of "
                f"{sorted(_TARGET_TO_DISPOSITION)}"
            )
        indicator_series = [1.0 if d.disposition == disposition else 0.0 for d in decisions]
        metrics.update(_series_statistics_metrics(criterion.target, indicator_series, criterion.threshold))

    fingerprint = compute_fingerprint({"experiment_id": experiment.experiment_id, "metrics": metrics})
    return Evidence(
        evidence_id=evidence_id, experiment_id=experiment.experiment_id, computed_at=computed_at,
        metrics=metrics, fingerprint=fingerprint, decision_sequence_path=decision_sequence_path,
    )
