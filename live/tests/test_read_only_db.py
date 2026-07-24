"""Read-only pool verification contract tests."""

import pytest

from atlas.read_only_db import verify_read_only_access


class Cursor:
    def __init__(self, row=None):
        self.row = row

    async def fetchone(self):
        return self.row


class Connection:
    def __init__(self, read_only="on"):
        self.read_only = read_only
        self.queries = []

    async def execute(self, query):
        self.queries.append(query)
        if query == "SHOW transaction_read_only":
            return Cursor((self.read_only,))
        return Cursor()


class ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_args):
        return None


class Pool:
    def __init__(self, read_only="on"):
        self.connection_value = Connection(read_only)

    def connection(self):
        return ConnectionContext(self.connection_value)


@pytest.mark.asyncio
async def test_verification_requires_read_only_and_probes_required_table():
    pool = Pool()

    await verify_read_only_access(pool)

    assert pool.connection_value.queries == [
        "SHOW transaction_read_only",
        "SELECT 1 FROM market_state_events LIMIT 1",
    ]


@pytest.mark.asyncio
async def test_verification_rejects_write_capable_session_before_table_probe():
    pool = Pool("off")

    with pytest.raises(RuntimeError, match="not transaction read-only"):
        await verify_read_only_access(pool)

    assert pool.connection_value.queries == ["SHOW transaction_read_only"]
