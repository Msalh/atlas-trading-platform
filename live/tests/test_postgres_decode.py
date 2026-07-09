"""Unit tests for atlas/repositories/postgres.py's row-decoding helpers - pure dict
transformations, no database needed. See _decode_trade's docstring for the bug this
exists to prevent: psycopg's dict_row only auto-decodes native JSON/JSONB columns:
pmt_relay_diagnostics is a TEXT column, so it always comes back as a raw JSON string
with no explicit decode step, and every trade-reading query needs one."""
import json

from atlas.repositories.postgres import _decode_trade


def test_decode_trade_parses_json_string_into_dict():
    row = {
        "correlation_id": "corr-1",
        "pmt_relay_diagnostics": json.dumps({"status_code": 200, "url": "https://pmt.example.com"}),
    }
    decoded = _decode_trade(row)
    assert decoded["pmt_relay_diagnostics"] == {"status_code": 200, "url": "https://pmt.example.com"}
    assert isinstance(decoded["pmt_relay_diagnostics"], dict)


def test_decode_trade_leaves_none_as_none():
    row = {"correlation_id": "corr-1", "pmt_relay_diagnostics": None}
    decoded = _decode_trade(row)
    assert decoded["pmt_relay_diagnostics"] is None


def test_decode_trade_handles_missing_key_gracefully():
    row = {"correlation_id": "corr-1"}
    decoded = _decode_trade(row)
    assert decoded["pmt_relay_diagnostics"] is None


def test_decode_trade_passes_through_none_row():
    assert _decode_trade(None) is None


def test_decode_trade_does_not_touch_other_fields():
    row = {"correlation_id": "corr-1", "status": "open", "pmt_forwarded": True, "pmt_relay_diagnostics": None}
    decoded = _decode_trade(row)
    assert decoded["correlation_id"] == "corr-1"
    assert decoded["status"] == "open"
    assert decoded["pmt_forwarded"] is True


def test_decode_trade_round_trips_a_realistic_nested_payload():
    """Mirrors the real shape atlas/services/pickmytrade.py's diagnostics dict has -
    nested dict/list, mixed types (str/int/float/bool/None)."""
    original = {
        "attempted_at": "2026-07-09T12:00:00.000Z",
        "url": "https://api.pickmytrade.trade/v2/add-trade-data",
        "method": "POST",
        "payload": {
            "symbol": "MNQU6", "data": "buy", "quantity": 1, "price": "21500.25",
            "pyramid": True, "multiple_accounts": [{"token": "***1234", "account_id": "ACCT1"}],
        },
        "status_code": 200,
        "response_body": '{"res":"Successfully send","error":false}',
        "exception": None,
        "duration_ms": 87.3,
    }
    row = {"pmt_relay_diagnostics": json.dumps(original)}
    decoded = _decode_trade(row)
    assert decoded["pmt_relay_diagnostics"] == original
