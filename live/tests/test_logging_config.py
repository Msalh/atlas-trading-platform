"""
Tests for atlas/logging_config.py (Sprint 10) - the JSON log formatter used by
atlas.main:app in production. Drives logging.LogRecord/JsonFormatter directly rather
than capturing real stdout, so these tests don't depend on any particular logger
configuration having been applied first.
"""
import json
import logging

import pytest

from atlas.logging_config import (
    JsonFormatter,
    _install_psycopg_pool_sanitizer,
    configure_logging,
)


@pytest.fixture(autouse=True)
def _restore_root_logger_handlers():
    """configure_logging() replaces the ROOT logger's handlers globally - restore
    whatever was there before each test so these tests can never leak state into
    tests elsewhere in the suite that run afterward."""
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.level = original_level


def _make_record(msg="hello", level=logging.INFO, extra=None) -> logging.LogRecord:
    record = logging.LogRecord(
        name="atlas.test", level=level, pathname=__file__, lineno=1, msg=msg, args=(), exc_info=None,
    )
    for key, value in (extra or {}).items():
        setattr(record, key, value)
    return record


def test_formats_a_plain_record_as_valid_json_with_the_expected_fields():
    record = _make_record("something happened")
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["message"] == "something happened"
    assert parsed["level"] == "INFO"
    assert parsed["logger"] == "atlas.test"
    assert "timestamp" in parsed


def test_extra_fields_become_top_level_json_keys_not_nested():
    record = _make_record("webhook handling failed", extra={"correlation_id": "corr-1"})
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["correlation_id"] == "corr-1"


def test_extra_dict_payload_is_preserved_as_a_real_json_object():
    """atlas/events/subscribers.py::log_event passes payload (a dict) via extra -
    confirms it round-trips as a nested JSON object, not a stringified blob."""
    record = _make_record("trade.entry.received", extra={"payload": {"correlation_id": "corr-1", "ok": True}})
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["payload"] == {"correlation_id": "corr-1", "ok": True}


def test_exception_info_is_included_when_present():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys
        record = _make_record("something failed", extra={})
        record.exc_info = sys.exc_info()
    parsed = json.loads(JsonFormatter().format(record))
    assert "ValueError: boom" in parsed["exception"]


def test_non_json_serializable_extra_values_fall_back_to_str():
    class Unserializable:
        def __str__(self):
            return "<unserializable>"

    record = _make_record("weird value", extra={"thing": Unserializable()})
    parsed = json.loads(JsonFormatter().format(record))
    assert parsed["thing"] == "<unserializable>"


def test_configure_logging_installs_exactly_one_json_handler():
    configure_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1
    assert isinstance(root.handlers[0].formatter, JsonFormatter)


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging()
    root = logging.getLogger()
    assert len(root.handlers) == 1  # still exactly one, not accumulating


def test_psycopg_pool_records_are_reduced_to_a_safe_operator_event(caplog):
    _install_psycopg_pool_sanitizer()
    pool_logger = logging.getLogger("psycopg.pool")
    pool_logger.warning(
        'connection to "127.0.0.1", port 1 failed: password=secret',
    )
    try:
        raise RuntimeError("connection refused for postgres://user:secret@localhost:1/db")
    except RuntimeError:
        pool_logger.warning("driver failure", exc_info=True)

    assert "postgres_pool_event" in caplog.text
    assert "127.0.0.1" not in caplog.text
    assert "localhost" not in caplog.text
    assert "port 1" not in caplog.text
    assert "password=secret" not in caplog.text
    assert "connection refused" not in caplog.text
    assert "RuntimeError" not in caplog.text
