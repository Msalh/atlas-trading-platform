"""Versioned CME equity-index expected-close policy for MNQ 5-minute bars.

Policy source: CME Globex equity-index regular electronic trading hours,
interpreted in America/Chicago. Operator-maintained holiday and early-close
overrides are required configuration because CME publishes those exceptions
per year and this service must not guess them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from types import MappingProxyType
from typing import Mapping
from zoneinfo import ZoneInfo

CME_EQUITY_INDEX_CALENDAR_SOURCE = (
    "CME Globex Equity Index trading hours; operator-maintained holiday overrides"
)
CHICAGO = ZoneInfo("America/Chicago")
MAINTENANCE_START = time(16, 0)
MAINTENANCE_END = time(17, 0)


@dataclass(frozen=True)
class CmeExpectedCloseConfig:
    version: str
    holidays: frozenset[date]
    early_closes: Mapping[date, time]

    def __post_init__(self) -> None:
        if not self.version or not self.version.strip():
            raise ValueError("TraderNow calendar version must not be blank")
        for holiday in self.holidays:
            if holiday in self.early_closes:
                raise ValueError(
                    f"calendar date {holiday.isoformat()} cannot be both a "
                    "holiday and an early close"
                )
        for close in self.early_closes.values():
            if close <= time(0, 0) or close > MAINTENANCE_START:
                raise ValueError(
                    "early close must be after 00:00 and no later than 16:00 "
                    "America/Chicago"
                )
        object.__setattr__(
            self,
            "early_closes",
            MappingProxyType(dict(sorted(self.early_closes.items()))),
        )

    @classmethod
    def from_json(
        cls,
        *,
        version: str,
        holidays_json: str,
        early_closes_json: str,
    ) -> "CmeExpectedCloseConfig":
        try:
            holiday_values = json.loads(holidays_json)
            early_close_values = json.loads(early_closes_json)
        except json.JSONDecodeError as error:
            raise ValueError(
                "TraderNow calendar overrides must be valid JSON"
            ) from error
        if not isinstance(holiday_values, list) or not all(
            isinstance(value, str) for value in holiday_values
        ):
            raise ValueError("TraderNow holidays must be a JSON array of ISO dates")
        if not isinstance(early_close_values, dict) or not all(
            isinstance(key, str) and isinstance(value, str)
            for key, value in early_close_values.items()
        ):
            raise ValueError(
                "TraderNow early closes must be a JSON object of ISO date to HH:MM"
            )
        try:
            holidays = frozenset(date.fromisoformat(value) for value in holiday_values)
            early_closes = {
                date.fromisoformat(key): time.fromisoformat(value)
                for key, value in early_close_values.items()
            }
        except ValueError as error:
            raise ValueError(
                "TraderNow calendar overrides contain an invalid date or time"
            ) from error
        return cls(version, holidays, early_closes)


class CmeMnqExpectedCloseProvider:
    """Expected latest completed MNQ 5m bar under one explicit calendar."""

    def __init__(self, config: CmeExpectedCloseConfig) -> None:
        self._config = config

    @property
    def policy_version(self) -> str:
        return self._config.version

    def expected_close(
        self,
        symbol: str,
        timeframe: str,
        evaluation_time: datetime,
    ) -> datetime | None:
        if timeframe != "5m" or not symbol.startswith("MNQ"):
            return None
        if evaluation_time.tzinfo is None or evaluation_time.utcoffset() is None:
            raise ValueError("evaluation_time must be timezone-aware")

        local_now = evaluation_time.astimezone(CHICAGO)
        candidates = []
        for days_back in range(10):
            trading_date = local_now.date() - timedelta(days=days_back)
            for start, end in self._intervals(trading_date):
                if local_now <= start:
                    continue
                capped = min(local_now, end)
                elapsed = capped - start
                completed = int(elapsed.total_seconds() // 300)
                if completed <= 0:
                    continue
                candidate = start + timedelta(minutes=completed * 5)
                if candidate <= end:
                    candidates.append(candidate)
            if candidates:
                return max(candidates).astimezone(timezone.utc)
        return None

    def _intervals(self, trading_date: date) -> tuple[tuple[datetime, datetime], ...]:
        if trading_date in self._config.holidays:
            return ()
        weekday = trading_date.weekday()
        if weekday == 5:
            return ()
        early_close = self._config.early_closes.get(trading_date)
        midnight = datetime.combine(trading_date, time(0, 0), CHICAGO)
        if weekday == 6:
            if early_close is not None:
                return ()
            return (
                (
                    datetime.combine(trading_date, MAINTENANCE_END, CHICAGO),
                    datetime.combine(
                        trading_date + timedelta(days=1), time(0, 0), CHICAGO
                    ),
                ),
            )
        close = early_close or MAINTENANCE_START
        intervals = ((midnight, datetime.combine(trading_date, close, CHICAGO)),)
        if weekday < 4 and early_close is None:
            intervals += (
                (
                    datetime.combine(trading_date, MAINTENANCE_END, CHICAGO),
                    datetime.combine(
                        trading_date + timedelta(days=1), time(0, 0), CHICAGO
                    ),
                ),
            )
        return intervals
