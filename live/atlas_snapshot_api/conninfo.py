"""Sanitized PostgreSQL connection assembly for the Snapshot API."""

from __future__ import annotations

import shlex

from psycopg.conninfo import conninfo_to_dict, make_conninfo

_READ_ONLY_SETTING = "default_transaction_read_only=on"
_READ_ONLY_NAME = "default_transaction_read_only"


def build_reader_conninfo(database_url: str) -> str:
    """Preserve DSN options while enforcing a read-only reader session."""
    try:
        parameters = conninfo_to_dict(database_url)
        existing_options = parameters.get("options", "")
        if not isinstance(existing_options, str):
            raise TypeError
        tokens = shlex.split(existing_options, posix=True)
        parameters["options"] = shlex.join(
            [*_without_read_only_setting(tokens), "-c", _READ_ONLY_SETTING]
        )
        clean_parameters = {
            name: value for name, value in parameters.items() if value is not None
        }
        return make_conninfo("", **clean_parameters)
    except (KeyError, TypeError, ValueError):
        raise RuntimeError("SNAPSHOT_READER_DATABASE_URL is invalid") from None


def _without_read_only_setting(tokens: list[str]) -> list[str]:
    preserved: list[str] = []
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token == "-c" and index + 1 < len(tokens):
            setting = tokens[index + 1]
            if _setting_name(setting) == _READ_ONLY_NAME:
                index += 2
                continue
            preserved.extend((token, setting))
            index += 2
            continue
        has_inline_setting = (token.startswith("-c") and len(token) > 2) or (
            token.startswith("--")
        )
        if has_inline_setting and _setting_name(token[2:]) == _READ_ONLY_NAME:
            index += 1
            continue
        preserved.append(token)
        index += 1
    return preserved


def _setting_name(setting: str) -> str:
    return setting.split("=", 1)[0]
