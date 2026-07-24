"""Production CME expected-close policy tests."""

from datetime import date, datetime, time, timezone

import pytest

from atlas.trader_now.expected_close import (
    CHICAGO,
    CME_EQUITY_INDEX_CALENDAR_SOURCE,
    CmeExpectedCloseConfig,
    CmeMnqExpectedCloseProvider,
)


def local(year, month, day, hour, minute):
    return datetime(year, month, day, hour, minute, tzinfo=CHICAGO)


def provider(*, holidays=(), early_closes=None):
    return CmeMnqExpectedCloseProvider(
        CmeExpectedCloseConfig(
            version="cme-equity-index.2026.v1",
            holidays=frozenset(holidays),
            early_closes=early_closes or {},
        )
    )


def expected(value):
    return value.astimezone(timezone.utc)


def test_normal_session_uses_latest_completed_five_minute_close():
    result = provider().expected_close("MNQU6", "5m", local(2026, 7, 21, 10, 3))

    assert result == expected(local(2026, 7, 21, 10, 0))


def test_daily_maintenance_holds_at_the_1600_close():
    result = provider().expected_close("MNQU6", "5m", local(2026, 7, 21, 16, 30))

    assert result == expected(local(2026, 7, 21, 16, 0))


def test_weekend_holds_at_friday_close_until_sunday_session_has_a_closed_bar():
    sunday_before_open = provider().expected_close(
        "MNQU6", "5m", local(2026, 7, 26, 16, 0)
    )
    sunday_after_open = provider().expected_close(
        "MNQU6", "5m", local(2026, 7, 26, 17, 6)
    )

    assert sunday_before_open == expected(local(2026, 7, 24, 16, 0))
    assert sunday_after_open == expected(local(2026, 7, 26, 17, 5))


def test_dst_transition_is_resolved_by_america_chicago_zone_rules():
    result = provider().expected_close("MNQU6", "5m", local(2026, 3, 8, 17, 6))

    assert result == datetime(2026, 3, 8, 22, 5, tzinfo=timezone.utc)


def test_configured_holiday_is_not_guessed_as_an_open_session():
    result = provider(holidays=(date(2026, 7, 21),)).expected_close(
        "MNQU6", "5m", local(2026, 7, 21, 12, 0)
    )

    assert result == expected(local(2026, 7, 21, 0, 0))


def test_configured_early_close_is_authoritative():
    result = provider(early_closes={date(2026, 11, 27): time(12, 15)}).expected_close(
        "MNQU6", "5m", local(2026, 11, 27, 14, 0)
    )

    assert result == expected(local(2026, 11, 27, 12, 15))


def test_unsupported_identity_returns_not_applicable():
    service = provider()

    assert service.expected_close("ESZ6", "5m", local(2026, 7, 21, 10, 0)) is None
    assert service.expected_close("MNQU6", "15m", local(2026, 7, 21, 10, 0)) is None


def test_calendar_json_configuration_is_validated_and_immutable():
    config = CmeExpectedCloseConfig.from_json(
        version="calendar.v1",
        holidays_json='["2026-12-25"]',
        early_closes_json='{"2026-11-27":"12:15"}',
    )

    assert config.holidays == frozenset({date(2026, 12, 25)})
    assert config.early_closes[date(2026, 11, 27)] == time(12, 15)
    with pytest.raises(TypeError):
        config.early_closes[date(2026, 1, 1)] = time(12, 0)


@pytest.mark.parametrize(
    ("holidays", "early_closes"),
    [
        ("not-json", "{}"),
        ("{}", "{}"),
        ("[]", "[]"),
        ('["bad-date"]', "{}"),
        ('["2026-12-25"]', '{"2026-12-25":"12:00"}'),
        ("[]", '{"2026-11-27":"17:00"}'),
    ],
)
def test_invalid_calendar_configuration_fails(holidays, early_closes):
    with pytest.raises(ValueError):
        CmeExpectedCloseConfig.from_json(
            version="calendar.v1",
            holidays_json=holidays,
            early_closes_json=early_closes,
        )


def test_calendar_policy_source_is_explicit():
    assert "CME Globex Equity Index" in CME_EQUITY_INDEX_CALENDAR_SOURCE
