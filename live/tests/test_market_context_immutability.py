"""
Phase N1, Sprint 1. Every dataclass in atlas.market_context.models and
atlas.market_context.definitions is declared @dataclass(frozen=True) - this
proves that declaration actually holds (raises FrozenInstanceError on
mutation) rather than trusting the decorator was applied correctly and
never regresses.
"""
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone

import pytest
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_context.definitions import (
    RegimeClassifierDefinition,
    RegimeClassifierParams,
    SessionCalendarDefinition,
    SessionCalendarParams,
)
from atlas.market_context.models import (
    ContextQuality,
    DriftStatus,
    MarketContext,
    SessionClassification,
    SessionPhase,
    SessionProgress,
    VolatilityClassification,
    VolatilityRegime,
)

_OCCURRED_AT = datetime(2026, 7, 21, 13, 35, 0, tzinfo=timezone.utc)


def _session_progress() -> SessionProgress:
    return SessionProgress(
        session_open_at=_OCCURRED_AT, session_close_at=_OCCURRED_AT,
        minutes_since_session_open=5, minutes_until_session_close=395,
    )


def _session_classification() -> SessionClassification:
    return SessionClassification(
        phase=SessionPhase.MID_SESSION, progress=_session_progress(),
        upstream_session_name="RTH", upstream_is_rth=True, drift_status=DriftStatus.AGREEMENT,
    )


def _volatility_classification() -> VolatilityClassification:
    return VolatilityClassification(regime=VolatilityRegime.NORMAL, atr_percentile_rank=0.5, lookback_bars_used=288)


def _market_context() -> MarketContext:
    return MarketContext(
        symbol=Symbol("MNQU6"), timeframe=Timeframe("5m"), occurred_at=_OCCURRED_AT,
        session=_session_classification(), volatility=_volatility_classification(),
        quality=ContextQuality.TRUSTED, classifier_version="REGIME_CLASSIFIER_V1",
        calendar_version="CME_RTH_V1", context_fingerprint="0123456789abcdef",
    )


def _session_calendar_params() -> SessionCalendarParams:
    return SessionCalendarParams(
        rth_open_hour_ct=8, rth_open_minute_ct=30, rth_close_hour_ct=15, rth_close_minute_ct=5,
        pre_open_minutes=60, opening_range_minutes=30, closing_range_minutes=15,
    )


def _session_calendar_definition() -> SessionCalendarDefinition:
    return SessionCalendarDefinition(version="CME_RTH_V1", params=_session_calendar_params())


def _regime_classifier_params() -> RegimeClassifierParams:
    return RegimeClassifierParams(lookback_bars=288, min_bars_required=288,
                                   compressed_percentile=25, expanded_percentile=75)


def _regime_classifier_definition() -> RegimeClassifierDefinition:
    return RegimeClassifierDefinition(version="REGIME_CLASSIFIER_V1", params=_regime_classifier_params())


@pytest.mark.parametrize(
    "make_instance, field_name, new_value",
    [
        pytest.param(_session_progress, "minutes_since_session_open", 999, id="SessionProgress"),
        pytest.param(_session_classification, "phase", SessionPhase.OVERNIGHT, id="SessionClassification"),
        pytest.param(_volatility_classification, "regime", VolatilityRegime.EXPANDED, id="VolatilityClassification"),
        pytest.param(_market_context, "quality", ContextQuality.DEGRADED, id="MarketContext"),
        pytest.param(_session_calendar_params, "rth_open_hour_ct", 9, id="SessionCalendarParams"),
        pytest.param(_session_calendar_definition, "version", "CME_RTH_V2", id="SessionCalendarDefinition"),
        pytest.param(_regime_classifier_params, "lookback_bars", 100, id="RegimeClassifierParams"),
        pytest.param(_regime_classifier_definition, "version", "REGIME_CLASSIFIER_V2", id="RegimeClassifierDefinition"),
    ],
)
def test_dataclass_rejects_mutation(make_instance, field_name, new_value):
    instance = make_instance()
    with pytest.raises(FrozenInstanceError):
        setattr(instance, field_name, new_value)
