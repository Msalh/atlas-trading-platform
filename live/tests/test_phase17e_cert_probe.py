"""Certification-tool tests; no production application imports this module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

from atlas_snapshot_api.conninfo import build_reader_conninfo

SCRIPT = Path(__file__).parents[1] / "scripts" / "phase17e_cert_probe.py"
SPEC = importlib.util.spec_from_file_location("phase17e_cert_probe", SCRIPT)
assert SPEC is not None and SPEC.loader is not None
probe = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = probe
SPEC.loader.exec_module(probe)


def test_probe_reuses_the_production_reader_connection_builder():
    assert probe.build_reader_conninfo is build_reader_conninfo


def _classification(**overrides):
    values = {
        "current_user": "atlas_snapshot_reader",
        "session_user": "snapshot_runtime_reader",
        "transaction_read_only": "on",
        "default_transaction_read_only": "on",
        "schema_usage": True,
        "schema_create": False,
        "table_select": True,
        "table_insert": False,
        "table_update": False,
        "table_delete": False,
        "table_truncate": False,
        "mutation_rejected": True,
    }
    values.update(overrides)
    return probe.classify_reader(**values)


def test_reader_contract_reports_every_assertion_independently():
    result = _classification()

    assert result.passed is True
    assert tuple(result.__dataclass_fields__) == (
        "current_user",
        "session_user",
        "transaction_read_only",
        "default_transaction_read_only",
        "schema_usage",
        "schema_create_denied",
        "table_select",
        "table_insert_denied",
        "table_update_denied",
        "table_delete_denied",
        "table_truncate_denied",
        "mutation_rejected",
    )


def test_each_reader_contract_failure_is_independently_visible():
    cases = {
        "current_user": {"current_user": "unexpected"},
        "session_user": {"session_user": "atlas_snapshot_reader"},
        "transaction_read_only": {"transaction_read_only": "off"},
        "default_transaction_read_only": {"default_transaction_read_only": "off"},
        "schema_usage": {"schema_usage": False},
        "schema_create_denied": {"schema_create": True},
        "table_select": {"table_select": False},
        "table_insert_denied": {"table_insert": True},
        "table_update_denied": {"table_update": True},
        "table_delete_denied": {"table_delete": True},
        "table_truncate_denied": {"table_truncate": True},
        "mutation_rejected": {"mutation_rejected": False},
    }

    for field, overrides in cases.items():
        result = _classification(**overrides)
        failed = [
            name
            for name in result.__dataclass_fields__
            if getattr(result, name) is False
        ]
        assert failed == [field]
        assert result.passed is False
