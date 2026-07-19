from datetime import datetime, timedelta, timezone

import pytest

from atlas.core.errors import NaiveDatetimeError
from atlas.core.time import now_utc, now_utc_iso, require_utc


class TestNowUtc:
    def test_returns_timezone_aware_datetime(self):
        assert now_utc().tzinfo is not None

    def test_is_actually_utc(self):
        assert now_utc().utcoffset() == timedelta(0)

    def test_close_to_wall_clock(self):
        # sanity check, not a precision test - just confirms it isn't a fixed/frozen value
        delta = abs((now_utc() - datetime.now(timezone.utc)).total_seconds())
        assert delta < 1.0


class TestNowUtcIso:
    def test_matches_existing_project_convention(self):
        # atlas/repositories/{memory,postgres}.py and atlas/api/v1/webhook.py all
        # use datetime.now(timezone.utc).isoformat(timespec="seconds") - this
        # must produce the same shape, since it's meant to be the one place
        # that convention is defined going forward.
        iso = now_utc_iso()
        parsed = datetime.fromisoformat(iso)
        assert parsed.tzinfo is not None
        # seconds precision: no microseconds component in the string
        assert "." not in iso


class TestRequireUtc:
    def test_accepts_timezone_aware_datetime(self):
        value = datetime(2026, 7, 18, 12, 0, 0, tzinfo=timezone.utc)
        assert require_utc(value) is value

    def test_accepts_non_utc_but_aware_datetime(self):
        # require_utc's contract is "timezone-aware", not "specifically the UTC
        # zone" - a datetime with any explicit offset is not naive.
        eastern = timezone(timedelta(hours=-5))
        value = datetime(2026, 7, 18, 8, 0, 0, tzinfo=eastern)
        assert require_utc(value) is value

    def test_rejects_naive_datetime(self):
        naive = datetime(2026, 7, 18, 12, 0, 0)
        with pytest.raises(NaiveDatetimeError):
            require_utc(naive)

    def test_error_message_includes_the_offending_value(self):
        naive = datetime(2026, 7, 18, 12, 0, 0)
        with pytest.raises(NaiveDatetimeError, match="2026"):
            require_utc(naive)
