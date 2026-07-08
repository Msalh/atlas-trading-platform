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


async def test_add_ai_note_and_list_ai_notes_round_trip():
    repo = InMemoryTradeRepository()

    stored = await repo.add_ai_note(
        trade_correlation_id="corr-1", note_type="entry_score", model="claude-haiku-4-5-20251001",
        content="Looks aligned.", error=None, score=8, score_label="Strong Alignment",
    )
    assert stored["trade_correlation_id"] == "corr-1"
    assert stored["score"] == 8

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert len(notes) == 1
    assert notes[0]["content"] == "Looks aligned."


async def test_list_ai_notes_filters_by_note_type_and_trade():
    repo = InMemoryTradeRepository()
    await repo.add_ai_note(
        trade_correlation_id="corr-1", note_type="entry_score", model="x", content="a", error=None,
    )
    await repo.add_ai_note(
        trade_correlation_id="corr-1", note_type="post_trade_review", model="x", content="b", error=None,
    )
    await repo.add_ai_note(
        trade_correlation_id="corr-2", note_type="entry_score", model="x", content="c", error=None,
    )
    await repo.add_ai_note(
        trade_correlation_id=None, note_type="daily_report", model="x", content="d", error=None,
    )

    only_corr1 = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert {n["content"] for n in only_corr1} == {"a", "b"}

    only_entry_scores = await repo.list_ai_notes(note_type="entry_score")
    assert {n["content"] for n in only_entry_scores} == {"a", "c"}

    reports = await repo.list_ai_notes(note_type="daily_report")
    assert len(reports) == 1
    assert reports[0]["trade_correlation_id"] is None


async def test_list_ai_notes_most_recent_first():
    repo = InMemoryTradeRepository()
    await repo.add_ai_note(trade_correlation_id="corr-1", note_type="entry_score", model="x", content="first", error=None)
    await repo.add_ai_note(trade_correlation_id="corr-1", note_type="post_trade_review", model="x", content="second", error=None)

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert [n["content"] for n in notes] == ["second", "first"]
