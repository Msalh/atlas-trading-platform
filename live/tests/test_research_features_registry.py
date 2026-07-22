"""
Phase N4 Sprint 4. Tests for atlas.research.features.registry - unit tests
against hand-built MarketState fixtures (mirroring how Rule Engine's own
facts were first tested), plus an integration test proving mean_atr
evaluates correctly over real ReplayFrame data obtained through Replay
Bridge (Sprint 3) - the roadmap's own required test shape for this sprint.
"""
from datetime import datetime, timedelta, timezone

import pytest
from atlas.core.events import Event
from atlas.core.primitives import Symbol, Timeframe
from atlas.market_engine.models import BarStatus, MarketState
from atlas.research.features.evaluators import evaluate_mean_atr
from atlas.research.features.models import FeatureComputed, FeatureInsufficientData
from atlas.research.features.registry import (
    REGISTRY,
    FeatureRegistration,
    required_history,
    validate_registry,
)
from atlas.research.models import Feature, FeatureStatus, FeatureTier, ProvenanceKind
from atlas.research.replay_bridge import build_replay_frames_for_window

_BASE = datetime(2026, 7, 20, 13, 0, tzinfo=timezone.utc)
_MEAN_ATR = REGISTRY[0].feature


def _state(event_id: str, occurred_at: datetime, atr) -> MarketState:
    return MarketState(
        envelope=Event(event_type="bar_closed", source="test", occurred_at=occurred_at, event_id=event_id),
        schema_version="1.0", symbol=Symbol("MNQU6"), timeframe=Timeframe.M5, bar_status=BarStatus.CLOSED,
        atr=atr,
    )


def _series(atrs: list, base: datetime = _BASE, cadence_minutes: int = 5) -> list[MarketState]:
    step = timedelta(minutes=cadence_minutes)
    return [_state(f"e{i}", base + step * i, atr) for i, atr in enumerate(atrs)]


# ---- evaluate_mean_atr: unit tests over hand-built fixtures ----

def test_mean_atr_computes_correctly_with_a_full_window():
    window = _series([1.0] * 13 + [2.0])  # 14 bars, required window = 14
    result = evaluate_mean_atr(window, _MEAN_ATR)
    assert isinstance(result, FeatureComputed)
    assert result.feature_name == "mean_atr"
    assert result.feature_version == "1.0"
    assert result.value == pytest.approx((1.0 * 13 + 2.0) / 14)


def test_mean_atr_uses_only_the_trailing_required_window_not_the_whole_series():
    window = _series([100.0] * 5 + [1.0] * 14)  # 19 bars; only the last 14 should count
    result = evaluate_mean_atr(window, _MEAN_ATR)
    assert isinstance(result, FeatureComputed)
    assert result.value == pytest.approx(1.0)


def test_mean_atr_insufficient_when_window_shorter_than_required():
    window = _series([1.0] * 5)
    result = evaluate_mean_atr(window, _MEAN_ATR)
    assert isinstance(result, FeatureInsufficientData)
    assert result.feature_name == "mean_atr"
    assert "requires 14" in result.reason


def test_mean_atr_insufficient_when_atr_missing_within_the_window():
    window = _series([1.0] * 10 + [None] * 2 + [1.0] * 2)
    result = evaluate_mean_atr(window, _MEAN_ATR)
    assert isinstance(result, FeatureInsufficientData)
    assert "missing" in result.reason


def test_mean_atr_empty_window_is_insufficient_not_a_crash():
    result = evaluate_mean_atr([], _MEAN_ATR)
    assert isinstance(result, FeatureInsufficientData)


# ---- integration: real ReplayFrame data via Replay Bridge (Sprint 3) ----

def test_mean_atr_evaluates_correctly_over_real_replay_frame_data():
    states = _series([1.0 + i * 0.1 for i in range(20)])
    frames = build_replay_frames_for_window(states)
    assert len(frames) == 20

    extracted = [frame.market_state for frame in frames]
    result = evaluate_mean_atr(extracted, _MEAN_ATR)

    assert isinstance(result, FeatureComputed)
    expected = sum(s.atr for s in states[-14:]) / 14
    assert result.value == pytest.approx(expected)
    # Frames pass through Replay Bridge unmutated - the MarketStates feature
    # evaluation reads are byte-identical to what was fed in.
    assert extracted == states


# ---- required_history() ----

def test_required_history_matches_the_one_registered_feature():
    assert required_history() == 14


# ---- validate_registry(): the real REGISTRY is valid (proven implicitly by import) ----

def test_the_real_registry_is_non_empty_and_registered_tier_only():
    assert len(REGISTRY) >= 1
    for registration in REGISTRY:
        assert registration.feature.tier == FeatureTier.REGISTERED


def _valid_feature(**overrides) -> Feature:
    fields = dict(
        feature_id="stub", name="stub", tier=FeatureTier.REGISTERED, version="1.0",
        description="stub", definition={"window": 5}, status=FeatureStatus.PROMOTED,
        provenance=ProvenanceKind.HUMAN, created_at="2026-07-22T00:00:00+00:00", fingerprint="0123456789abcdef",
    )
    fields.update(overrides)
    return Feature(**fields)


def test_validate_registry_rejects_empty_registry():
    with pytest.raises(ValueError, match="must not be empty"):
        validate_registry(())


def test_validate_registry_rejects_duplicate_names():
    reg = (
        FeatureRegistration(feature=_valid_feature(feature_id="a", name="a"), evaluate=evaluate_mean_atr),
        FeatureRegistration(feature=_valid_feature(feature_id="b", name="a"), evaluate=evaluate_mean_atr),
    )
    with pytest.raises(ValueError, match="duplicate feature names"):
        validate_registry(reg)


def test_validate_registry_rejects_a_candidate_tier_entry():
    reg = (FeatureRegistration(feature=_valid_feature(tier=FeatureTier.CANDIDATE), evaluate=evaluate_mean_atr),)
    with pytest.raises(ValueError, match="REGISTERED-tier"):
        validate_registry(reg)


def test_validate_registry_rejects_feature_id_name_mismatch():
    reg = (FeatureRegistration(feature=_valid_feature(feature_id="different"), evaluate=evaluate_mean_atr),)
    with pytest.raises(ValueError, match="does not match"):
        validate_registry(reg)


def test_validate_registry_rejects_missing_window_param():
    reg = (FeatureRegistration(feature=_valid_feature(definition={}), evaluate=evaluate_mean_atr),)
    with pytest.raises(ValueError, match="must declare a 'window' param"):
        validate_registry(reg)


def test_validate_registry_rejects_non_int_window():
    reg = (FeatureRegistration(feature=_valid_feature(definition={"window": 5.0}), evaluate=evaluate_mean_atr),)
    with pytest.raises(ValueError, match="must be an int"):
        validate_registry(reg)


def test_validate_registry_rejects_bool_window_despite_being_an_int_subclass():
    reg = (FeatureRegistration(feature=_valid_feature(definition={"window": True}), evaluate=evaluate_mean_atr),)
    with pytest.raises(ValueError, match="must be an int"):
        validate_registry(reg)


def test_validate_registry_rejects_non_positive_window():
    reg = (FeatureRegistration(feature=_valid_feature(definition={"window": 0}), evaluate=evaluate_mean_atr),)
    with pytest.raises(ValueError, match="must be >= 1"):
        validate_registry(reg)
