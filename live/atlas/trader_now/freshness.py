"""Server-owned raw-bar freshness, independent of repositories and engines."""

from dataclasses import dataclass
from datetime import datetime, timedelta

from atlas.trader_now.models import (
    Freshness,
    FreshnessReason,
    FreshnessStatus,
)
from atlas.trader_now.ports import Clock, ExpectedCloseProvider


@dataclass(frozen=True)
class FreshnessPolicy:
    version: str = "trader_now_freshness_mnq_5m.v1"
    current_lateness: timedelta = timedelta(seconds=90)
    stale_lateness: timedelta = timedelta(seconds=390)
    future_skew_tolerance: timedelta = timedelta(seconds=5)

    def __post_init__(self) -> None:
        if not self.version or not self.version.strip():
            raise ValueError("freshness policy version must not be blank")
        if self.current_lateness < timedelta(0):
            raise ValueError("current_lateness must not be negative")
        if self.stale_lateness <= self.current_lateness:
            raise ValueError("stale_lateness must be greater than current_lateness")
        if self.future_skew_tolerance < timedelta(0):
            raise ValueError("future_skew_tolerance must not be negative")


class FreshnessService:
    def __init__(
        self,
        *,
        expected_close_provider: ExpectedCloseProvider,
        clock: Clock,
        policy: FreshnessPolicy,
    ) -> None:
        self._expected_close_provider = expected_close_provider
        self._clock = clock
        self._policy = policy

    def classify(
        self,
        *,
        symbol: str,
        timeframe: str,
        latest_closed_at: datetime | None,
    ) -> Freshness:
        evaluated_at = self._clock()
        self._require_aware(evaluated_at, "clock")

        try:
            expected_close = self._expected_close_provider.expected_close(
                symbol, timeframe, evaluated_at
            )
        except Exception:
            return self._result(
                FreshnessStatus.UNAVAILABLE,
                evaluated_at,
                None,
                latest_closed_at,
                None,
                FreshnessReason.EXPECTED_CLOSE_UNAVAILABLE,
            )

        if expected_close is None:
            return self._result(
                FreshnessStatus.NOT_APPLICABLE,
                evaluated_at,
                None,
                latest_closed_at,
                None,
                FreshnessReason.EXPECTED_CLOSE_NOT_APPLICABLE,
            )
        if not self._is_aware(expected_close):
            return self._result(
                FreshnessStatus.INVALID,
                evaluated_at,
                expected_close,
                latest_closed_at,
                None,
                FreshnessReason.EXPECTED_CLOSE_UNAVAILABLE,
            )
        if expected_close > evaluated_at + self._policy.future_skew_tolerance:
            return self._result(
                FreshnessStatus.INVALID,
                evaluated_at,
                expected_close,
                latest_closed_at,
                None,
                FreshnessReason.EXPECTED_CLOSE_IN_FUTURE,
            )
        if latest_closed_at is None:
            return self._result(
                FreshnessStatus.UNAVAILABLE,
                evaluated_at,
                expected_close,
                None,
                None,
                FreshnessReason.NO_LATEST_CLOSED_BAR,
            )
        if not self._is_aware(latest_closed_at):
            return self._result(
                FreshnessStatus.INVALID,
                evaluated_at,
                expected_close,
                latest_closed_at,
                None,
                FreshnessReason.LATEST_BAR_IN_FUTURE,
            )
        if latest_closed_at > evaluated_at + self._policy.future_skew_tolerance:
            return self._result(
                FreshnessStatus.INVALID,
                evaluated_at,
                expected_close,
                latest_closed_at,
                None,
                FreshnessReason.LATEST_BAR_IN_FUTURE,
            )

        lateness = max(expected_close - latest_closed_at, timedelta(0))
        if lateness <= self._policy.current_lateness:
            return Freshness(
                status=FreshnessStatus.CURRENT,
                policy_version=self._policy.version,
                evaluated_at=evaluated_at,
                expected_close_at=expected_close,
                latest_closed_at=latest_closed_at,
                lateness_seconds=lateness.total_seconds(),
            )
        if lateness <= self._policy.stale_lateness:
            return self._result(
                FreshnessStatus.DELAYED,
                evaluated_at,
                expected_close,
                latest_closed_at,
                lateness.total_seconds(),
                FreshnessReason.BAR_ARRIVAL_DELAYED,
            )
        return self._result(
            FreshnessStatus.STALE,
            evaluated_at,
            expected_close,
            latest_closed_at,
            lateness.total_seconds(),
            FreshnessReason.BAR_ARRIVAL_STALE,
        )

    def unavailable(self, *, evaluated_at: datetime | None = None) -> Freshness:
        """Project missing raw input without consulting the expected-close source."""
        at = evaluated_at or self._clock()
        self._require_aware(at, "clock")
        return self._result(
            FreshnessStatus.UNAVAILABLE,
            at,
            None,
            None,
            None,
            FreshnessReason.NO_LATEST_CLOSED_BAR,
        )

    def _result(
        self,
        status: FreshnessStatus,
        evaluated_at: datetime,
        expected_close_at: datetime | None,
        latest_closed_at: datetime | None,
        lateness_seconds: float | None,
        reason: FreshnessReason,
    ) -> Freshness:
        return Freshness(
            status=status,
            policy_version=self._policy.version,
            evaluated_at=evaluated_at,
            expected_close_at=expected_close_at,
            latest_closed_at=latest_closed_at,
            lateness_seconds=lateness_seconds,
            reason_codes=(reason,),
        )

    @staticmethod
    def _is_aware(value: datetime) -> bool:
        return value.tzinfo is not None and value.utcoffset() is not None

    @classmethod
    def _require_aware(cls, value: datetime, source: str) -> None:
        if not cls._is_aware(value):
            raise ValueError(f"{source} must return a timezone-aware datetime")
