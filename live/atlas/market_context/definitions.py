"""
Versioned Market Context definitions - Phase N1, Sprint 1. Config as
versioned code, not env vars: tunable numbers live in version control, tied
to an explicit version string, never runtime-configurable via an
environment variable that could silently differ between deploys and break
replay determinism - the same discipline
atlas.rule_engine.models.FactDefinition already established for Rule
Engine's own tunable parameters.

Naming: every definition constant embeds its own version in its
identifier - <SCOPE>_V<N> - never DEFAULT_*. This is a deliberate departure
from Rule Engine's own DEFAULT_X_DEFINITION convention
(atlas/rule_engine/definitions.py): a DEFAULT_* name reads as "the one true
default," which invites an in-place params edit without a version bump. A
future CME_RTH_V2 sits beside CME_RTH_V1 with no ambiguity about which is
which. Each constant's own Python name equals its .version string exactly
(verified by test, not by runtime assertion - no validation framework is
invented here; atlas.rule_engine.models.FactDefinition, the closest
existing precedent, does not validate its own field values either, only
normalizes a mutable params dict for immutability, which these frozen,
all-int params dataclasses have no need of).

CME_RTH_V1 and REGIME_CLASSIFIER_V1's values are calibrated, not guessed -
see the Gate 1 calibration report (97,858 real, certified MNQ1! 5-minute
bars, 2025-03-02 to 2026-07-20). REGIME_CLASSIFIER_V1 is calibrated for
5-minute bars specifically; no other timeframe has been validated against
real data yet.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class SessionCalendarParams:
    rth_open_hour_ct: int
    rth_open_minute_ct: int
    rth_close_hour_ct: int
    rth_close_minute_ct: int
    pre_open_minutes: int
    opening_range_minutes: int
    closing_range_minutes: int


@dataclass(frozen=True)
class SessionCalendarDefinition:
    version: str
    params: SessionCalendarParams


@dataclass(frozen=True)
class RegimeClassifierParams:
    lookback_bars: int
    min_bars_required: int
    compressed_percentile: int
    expanded_percentile: int


@dataclass(frozen=True)
class RegimeClassifierDefinition:
    version: str
    params: RegimeClassifierParams


# Gate 1 calibration: RTH open/close are a direct, sharp-transition read of
# real Pine is_rth tagging (08:30/15:05 CT, zero fractional buckets at
# 5-minute resolution). The three buffer widths are lower-confidence,
# ranked by evidence strength in the calibration report: opening_range
# (volume_ratio clearly elevated through +25-30min post-open) > closing
# (a real but narrower/weaker bump) > pre_open (noisiest signal, a
# conventional round value). The one-bar-per-session RTH-open disagreement
# this produces (~0.39% of RTH-adjacent bars) is an expected bar-open vs.
# bar-close convention difference - occurred_at is bar-CLOSE, so the bar
# reported at 08:30 opened at 08:25, still pre-open, and Pine's is_rth for
# that one bar reflects its open - not a calibration bug, and not fixable
# by shifting this boundary (confirmed: shifting +-5/10min only relocates
# which single bar disagrees, per the calibration report).
CME_RTH_V1 = SessionCalendarDefinition(
    version="CME_RTH_V1",
    params=SessionCalendarParams(
        rth_open_hour_ct=8,
        rth_open_minute_ct=30,
        rth_close_hour_ct=15,
        rth_close_minute_ct=5,
        pre_open_minutes=60,
        opening_range_minutes=30,
        closing_range_minutes=15,
    ),
)

# Gate 1 calibration: compressed_percentile/expanded_percentile (25/75) are
# definitional quartile boundaries, not fitted - no threshold search was
# run, deliberately, to avoid overfitting to this one dataset.
# lookback_bars/min_bars_required (288, one full RTH+overnight day at 5m)
# are the parameters with the most real uncertainty behind them: RTH ATR
# runs ~2x overnight ATR in the calibration data, so a percentile-rank
# classifier is sensitive to how much of each session type its lookback
# window contains: a lookback=20-vs-100 comparison only agreed on the
# regime call 53.6% of the time. 288 bars was the most balanced of every
# lookback tested against the theoretical 25/50/25 split, not proven
# optimal - the session-mix sensitivity itself remains an open risk for a
# future REGIME_CLASSIFIER_V2, not resolved here. min_bars_required equals
# lookback_bars deliberately (no partial-window classification): given the
# demonstrated lookback-sensitivity, classifying against a shorter,
# not-yet-full warm-up window would produce exactly the kind of unstable
# call already shown to be unreliable.
REGIME_CLASSIFIER_V1 = RegimeClassifierDefinition(
    version="REGIME_CLASSIFIER_V1",
    params=RegimeClassifierParams(
        lookback_bars=288,
        min_bars_required=288,
        compressed_percentile=25,
        expanded_percentile=75,
    ),
)
