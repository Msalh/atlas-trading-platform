"""
Direct unit tests against InMemoryTradeRepository - catches bugs in the repository
itself that wouldn't necessarily show up through the webhook route, because
real webhook payloads happen to duplicate correlation_id inside the JSON body (so a
repository that (wrongly) trusted entry["correlation_id"] instead of the explicit
parameter would still work by coincidence via that path).

This suite exists because exactly that bug shipped in Sprint 1 and Sprint 2's webhook
tests never caught it (their fixture always included correlation_id in the payload
body) - it only surfaced when scripts/dev_seed_server.py called claim_and_forward with
an entry dict that didn't happen to repeat correlation_id inside it.
"""
from atlas.repositories.memory import InMemoryTradeRepository


async def _forward_ok():
    return True, 200, None


async def test_stored_correlation_id_comes_from_the_explicit_parameter_not_the_entry_dict():
    repo = InMemoryTradeRepository()

    # Deliberately does NOT include "correlation_id" inside the entry dict - this is
    # the exact shape that exposed the bug.
    entry_without_correlation_id_key = {
        "direction": "long", "setup_tag": "BRK", "symbol": "MNQU6",
        "entry_price": 100, "sl": 90, "tp": 120,
    }

    await repo.claim_and_forward("corr-explicit", entry_without_correlation_id_key, "{}", _forward_ok)

    stored = await repo.get_by_correlation_id("corr-explicit")
    assert stored is not None
    assert stored["correlation_id"] == "corr-explicit"


async def test_list_recent_never_returns_a_null_correlation_id():
    repo = InMemoryTradeRepository()
    await repo.claim_and_forward("corr-1", {"direction": "long"}, "{}", _forward_ok)
    await repo.claim_and_forward("corr-2", {"direction": "short"}, "{}", _forward_ok)

    rows = await repo.list_recent(limit=10)
    assert len(rows) == 2
    assert all(r["correlation_id"] is not None for r in rows)
    assert {r["correlation_id"] for r in rows} == {"corr-1", "corr-2"}
