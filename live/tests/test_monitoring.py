from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest

from atlas.monitoring import MarketStateStalenessMonitor, compute_staleness_minutes, is_market_hours_expected

CT = ZoneInfo("America/Chicago")


def _ct(year, month, day, hour, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=CT)


class TestIsMarketHoursExpected:
    def test_saturday_is_excluded_any_hour(self):
        # 2026-07-18 is a Saturday
        assert is_market_hours_expected(_ct(2026, 7, 18, 12, 0)) is False
        assert is_market_hours_expected(_ct(2026, 7, 18, 23, 0)) is False

    def test_sunday_before_open_is_excluded(self):
        # 2026-07-19 is a Sunday
        assert is_market_hours_expected(_ct(2026, 7, 19, 10, 0)) is False
        assert is_market_hours_expected(_ct(2026, 7, 19, 16, 59)) is False

    def test_sunday_at_and_after_open_is_included(self):
        assert is_market_hours_expected(_ct(2026, 7, 19, 17, 0)) is True
        assert is_market_hours_expected(_ct(2026, 7, 19, 20, 0)) is True

    def test_friday_before_close_is_included(self):
        # 2026-07-17 is a Friday
        assert is_market_hours_expected(_ct(2026, 7, 17, 10, 0)) is True
        assert is_market_hours_expected(_ct(2026, 7, 17, 15, 59)) is True

    def test_friday_at_and_after_close_is_excluded(self):
        assert is_market_hours_expected(_ct(2026, 7, 17, 16, 0)) is False
        assert is_market_hours_expected(_ct(2026, 7, 17, 23, 0)) is False

    @pytest.mark.parametrize("day", [14, 15, 16, 17])  # Mon(14)-Thu... 17 is Friday, checked separately below
    def test_weekday_maintenance_window_is_excluded(self, day):
        if day == 17:
            pytest.skip("Friday's own close-time exclusion already covers 16:00 CT onward")
        assert is_market_hours_expected(_ct(2026, 7, day, 16, 0)) is False
        assert is_market_hours_expected(_ct(2026, 7, day, 16, 59)) is False

    @pytest.mark.parametrize("day", [13, 14, 15, 16])  # Mon-Thu 2026-07-13..16
    def test_weekday_outside_maintenance_is_included(self, day):
        assert is_market_hours_expected(_ct(2026, 7, day, 10, 0)) is True
        assert is_market_hours_expected(_ct(2026, 7, day, 17, 0)) is True  # right after maintenance ends

    def test_accepts_utc_input_and_converts_correctly(self):
        # 2026-07-18 (Saturday) 12:00 UTC is still Saturday in CT (CDT = UTC-5 in July)
        utc_saturday = datetime(2026, 7, 18, 12, 0, tzinfo=timezone.utc)
        assert is_market_hours_expected(utc_saturday) is False

    def test_dst_boundary_does_not_crash_and_produces_a_bool(self):
        # Just past a US DST transition (2026-03-08) - the point of this test
        # is that zoneinfo's own DST handling is trusted, not re-implemented;
        # a crash or a non-bool here would indicate a real problem.
        result = is_market_hours_expected(datetime(2026, 3, 9, 12, 0, tzinfo=timezone.utc))
        assert isinstance(result, bool)


class TestComputeStalenessMinutes:
    def test_uses_last_seen_at_when_present(self):
        last_seen = datetime(2026, 7, 18, 13, 0, tzinfo=timezone.utc)
        started = datetime(2026, 7, 18, 8, 0, tzinfo=timezone.utc)
        now = datetime(2026, 7, 18, 13, 10, tzinfo=timezone.utc)
        assert compute_staleness_minutes(last_seen, started, now) == pytest.approx(10.0)

    def test_falls_back_to_started_at_when_nothing_seen_yet(self):
        started = datetime(2026, 7, 18, 13, 0, tzinfo=timezone.utc)
        now = datetime(2026, 7, 18, 13, 5, tzinfo=timezone.utc)
        assert compute_staleness_minutes(None, started, now) == pytest.approx(5.0)

    def test_zero_when_event_just_arrived(self):
        now = datetime(2026, 7, 18, 13, 0, tzinfo=timezone.utc)
        assert compute_staleness_minutes(now, now, now) == pytest.approx(0.0)


class TestMarketStateStalenessMonitor:
    def _within_market_hours(self):
        return _ct(2026, 7, 15, 10, 0)  # a normal Wednesday mid-session

    def _outside_market_hours(self):
        return _ct(2026, 7, 18, 12, 0)  # a Saturday

    @patch("atlas.monitoring.send_alert")
    def test_no_alert_when_fresh(self, mock_send_alert):
        monitor = MarketStateStalenessMonitor(threshold_minutes=15)
        now = self._within_market_hours()
        monitor.check(last_seen_at=now, started_at=now, now=now)
        mock_send_alert.assert_not_called()

    @patch("atlas.monitoring.send_alert")
    def test_alerts_once_when_threshold_crossed(self, mock_send_alert):
        monitor = MarketStateStalenessMonitor(threshold_minutes=15)
        started = self._within_market_hours()
        now = started + timedelta(minutes=16)
        monitor.check(last_seen_at=None, started_at=started, now=now)
        mock_send_alert.assert_called_once()
        assert "no market_state event" in mock_send_alert.call_args[0][0]

    @patch("atlas.monitoring.send_alert")
    def test_does_not_re_alert_while_still_stale(self, mock_send_alert):
        monitor = MarketStateStalenessMonitor(threshold_minutes=15)
        started = self._within_market_hours()
        stale_time = started + timedelta(minutes=20)

        monitor.check(last_seen_at=None, started_at=started, now=stale_time)
        monitor.check(last_seen_at=None, started_at=started, now=stale_time)
        monitor.check(last_seen_at=None, started_at=started, now=stale_time)

        assert mock_send_alert.call_count == 1

    @patch("atlas.monitoring.send_alert")
    def test_alerts_on_recovery_after_being_stale(self, mock_send_alert):
        monitor = MarketStateStalenessMonitor(threshold_minutes=15)
        started = self._within_market_hours()
        stale_time = started + timedelta(minutes=20)

        monitor.check(last_seen_at=None, started_at=started, now=stale_time)  # goes stale
        recovered_time = stale_time + timedelta(minutes=1)
        monitor.check(last_seen_at=recovered_time, started_at=started, now=recovered_time)  # fresh event arrives

        assert mock_send_alert.call_count == 2
        assert "resumed" in mock_send_alert.call_args_list[1][0][0]

    @patch("atlas.monitoring.send_alert")
    def test_never_alerts_outside_market_hours_regardless_of_staleness(self, mock_send_alert):
        monitor = MarketStateStalenessMonitor(threshold_minutes=15)
        saturday = self._outside_market_hours()
        long_ago = saturday - timedelta(days=3)  # 3 days "stale" - still must not alert
        monitor.check(last_seen_at=long_ago, started_at=long_ago, now=saturday)
        mock_send_alert.assert_not_called()

    @patch("atlas.monitoring.send_alert")
    def test_threshold_boundary_is_inclusive(self, mock_send_alert):
        monitor = MarketStateStalenessMonitor(threshold_minutes=15)
        now = self._within_market_hours()
        last_seen = now - timedelta(minutes=15)
        monitor.check(last_seen_at=last_seen, started_at=last_seen, now=now)
        mock_send_alert.assert_called_once()
