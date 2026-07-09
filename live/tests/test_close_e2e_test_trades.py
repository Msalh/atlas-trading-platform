"""Unit tests for scripts/close_e2e_test_trades.py's safety-critical filter - the one
check standing between this cleanup tool and touching a real trade. Pure function, no
database needed. The full close-and-verify-excluded-from-analytics behavior is covered
by an integration test in tests/integration/test_postgres_repository.py, since that
needs a real Postgres round trip to mean anything."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.close_e2e_test_trades import E2E_CORRELATION_ID_PREFIX, is_e2e_test_trade  # noqa: E402


def test_e2e_correlation_id_is_matched():
    assert is_e2e_test_trade("E2E-MNQU6-1720000000000") is True


def test_real_correlation_id_is_not_matched():
    # Real entries' correlation_id is just str.tostring(time) - a bare epoch-millisecond
    # string, never prefixed - see the Pine strategy's longCorrId/shortCorrId.
    assert is_e2e_test_trade("1720000000000") is False


def test_correlation_id_merely_containing_e2e_is_not_matched():
    """Must be a prefix match, not a substring match - a real trade whose setup_tag or
    symbol happened to contain "E2E" must never be swept up by this."""
    assert is_e2e_test_trade("1720000000000-E2E-note") is False


def test_prefix_constant_matches_documented_value():
    assert E2E_CORRELATION_ID_PREFIX == "E2E-"
