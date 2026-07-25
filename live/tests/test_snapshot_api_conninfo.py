"""Regression tests for Snapshot API reader connection assembly."""

from __future__ import annotations

import shlex

import pytest
from atlas_snapshot_api.conninfo import build_reader_conninfo
from psycopg.conninfo import conninfo_to_dict, make_conninfo


def _dsn(*, options: str = "") -> str:
    return make_conninfo(
        host="synthetic.internal",
        dbname="synthetic",
        user="synthetic_reader",
        password="synthetic_secret",
        options=options,
    )


def _options(conninfo: str) -> list[str]:
    return shlex.split(conninfo_to_dict(conninfo)["options"], posix=True)


def test_reader_conninfo_preserves_role_and_adds_read_only() -> None:
    result = build_reader_conninfo(
        _dsn(options="-c role=atlas_snapshot_reader -c statement_timeout=5000")
    )

    options = _options(result)
    assert options == [
        "-c",
        "role=atlas_snapshot_reader",
        "-c",
        "statement_timeout=5000",
        "-c",
        "default_transaction_read_only=on",
    ]


@pytest.mark.parametrize(
    "existing",
    (
        "-c default_transaction_read_only=off",
        "-cdefault_transaction_read_only=off",
        "--default_transaction_read_only=off",
    ),
)
def test_reader_conninfo_replaces_existing_read_only_without_duplicates(
    existing: str,
) -> None:
    options = _options(build_reader_conninfo(_dsn(options=existing)))

    assert options.count("default_transaction_read_only=on") == 1
    assert all("default_transaction_read_only=off" not in option for option in options)


def test_reader_conninfo_does_not_change_other_connection_fields() -> None:
    original = conninfo_to_dict(_dsn(options="-c role=atlas_snapshot_reader"))
    result = conninfo_to_dict(build_reader_conninfo(make_conninfo(**original)))

    assert {key: value for key, value in result.items() if key != "options"} == {
        key: value for key, value in original.items() if key != "options"
    }


def test_reader_conninfo_error_is_sanitized() -> None:
    secret = "must-not-appear"

    with pytest.raises(RuntimeError) as captured:
        build_reader_conninfo(f"postgresql://reader:{secret}@host/db?options='")

    assert str(captured.value) == "SNAPSHOT_READER_DATABASE_URL is invalid"
    assert secret not in str(captured.value)
