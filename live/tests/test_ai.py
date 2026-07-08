"""
Tests for atlas/ai.py - the AI Copilot background-task orchestration (entry
intelligence, post-trade review, report generation). These call the orchestration
functions directly against an InMemoryTradeRepository and a real EventBus, with
atlas.ai.analyze_with_claude mocked so nothing here ever attempts a real Anthropic API
call. See atlas/ai.py's module docstring for the non-blocking guarantee these
functions exist to uphold - the webhook-integration side of that guarantee
(background_tasks.add_task, never awaited) is covered in test_webhook.py.

Entry scoring's underlying computation (similarity search, confidence rubric,
factors) is covered in isolation by tests/test_intelligence.py - the tests below only
verify atlas/ai.py wires that computation to Claude and the repository correctly:
Claude is skipped entirely with no history, and only ever asked to explain numbers
that were already computed, never to invent its own score.
"""
from datetime import datetime, timezone
from unittest.mock import patch

import atlas.ai as ai_module
from atlas.events import types as event_types
from atlas.events.bus import EventBus
from atlas.repositories.memory import InMemoryTradeRepository

ENTRY = {
    "correlation_id": "corr-1", "direction": "long", "setup_tag": "BRK", "symbol": "MNQU6",
    "entry_price": 100.0, "sl": 90.0, "tp": 130.0, "atr": 5.0, "ema_distance_atr": 0.5,
    "regime_slope_pct": 1.0, "sweep_age_bars": 3, "session": "NY", "quantity": 2,
}


async def _forward_ok():
    return True, 200, None


async def _seed_similar_trades(repo, count, *, won):
    """Seeds `count` closed trades sharing ENTRY's direction/setup_tag (and every
    continuous factor, since it's a plain copy of ENTRY) so find_similar_trades has
    real historical evidence to match against."""
    for i in range(count):
        corr_id = f"seed-{'won' if won else 'lost'}-{i}"
        entry = {**ENTRY, "correlation_id": corr_id}
        await repo.claim_and_forward(corr_id, entry, "{}", _forward_ok)
        realized = 600.0 if won else -300.0
        await repo.update_exit(
            corr_id, "won" if won else "lost", 130.0 if won else 95.0, realized, "2026-01-01T00:00:00+00:00",
        )


# --- run_entry_score -----------------------------------------------------------------

async def test_run_entry_score_with_no_history_skips_claude_and_records_insufficient_history():
    repo = InMemoryTradeRepository()
    bus = EventBus()
    received = []

    async def handler(event_type, payload):
        received.append((event_type, payload))

    bus.subscribe(event_types.AI_ENTRY_SCORED, handler)

    with patch.object(ai_module, "analyze_with_claude") as mock:
        await ai_module.run_entry_score(ENTRY, "corr-1", repo, bus)

    mock.assert_not_called()  # nothing to explain yet - Claude is never invoked

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert len(notes) == 1
    note = notes[0]
    assert note["note_type"] == "entry_score"
    assert note["score"] is None
    assert note["score_label"] == "Insufficient History"
    assert note["similar_trade_count"] == 0
    assert note["expected_r"] is None
    assert note["historical_win_rate_pct"] is None
    assert note["factors"] is None
    assert note["error"] is None

    assert received == [
        (event_types.AI_ENTRY_SCORED, {"correlation_id": "corr-1", "ok": True, "score": None, "error": None})
    ]


async def test_run_entry_score_with_history_computes_structured_fields_and_asks_claude_to_explain():
    repo = InMemoryTradeRepository()
    bus = EventBus()

    await _seed_similar_trades(repo, 5, won=True)
    await _seed_similar_trades(repo, 1, won=False)

    with patch.object(
        ai_module, "analyze_with_claude", return_value=("Strong historical alignment.", None),
    ) as mock:
        await ai_module.run_entry_score(ENTRY, "corr-1", repo, bus)

    # Claude was only asked to explain the pre-computed numbers, never a raw
    # SCORE:/LABEL: instruction asking it to invent its own.
    prompt = mock.call_args[0][0]
    assert "already-computed" in prompt
    assert "Do not propose a different score" in prompt

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert len(notes) == 1
    note = notes[0]
    assert note["note_type"] == "entry_score"
    assert note["content"] == "Strong historical alignment."
    assert note["error"] is None
    assert note["similar_trade_count"] == 6  # 5 wins + 1 loss, seeded above
    assert note["score"] == 8  # deterministic: sample=2 + win_rate=4 + expectancy=2, see atlas/intelligence.py
    assert note["score_label"] == "High Confidence"
    assert 83 < note["historical_win_rate_pct"] < 84  # 5/6
    assert note["expected_r"] is not None
    assert len(note["factors"]) == 3
    for factor in note["factors"]:
        assert factor["entry_value"] == factor["winners_median"] == factor["losers_median"]
        assert factor["favorable"] is True  # entry is a literal copy of the seeded trades


async def test_run_entry_score_handles_a_configuration_error_without_raising():
    repo = InMemoryTradeRepository()
    bus = EventBus()
    await _seed_similar_trades(repo, 5, won=True)

    with patch.object(ai_module, "analyze_with_claude", return_value=(None, "ANTHROPIC_API_KEY not configured")):
        await ai_module.run_entry_score(ENTRY, "corr-1", repo, bus)  # must not raise

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert notes[0]["error"] == "ANTHROPIC_API_KEY not configured"
    assert notes[0]["content"] is None
    # The score itself came from atlas/intelligence.py, not Claude - a Claude failure
    # only means no narrative explanation, the structured numbers are unaffected.
    assert notes[0]["score"] is not None


async def test_run_entry_score_handles_an_unexpected_exception_without_raising():
    repo = InMemoryTradeRepository()
    bus = EventBus()
    await _seed_similar_trades(repo, 5, won=True)

    def raises(*args, **kwargs):
        raise TimeoutError("simulated timeout")

    with patch.object(ai_module, "analyze_with_claude", side_effect=raises):
        await ai_module.run_entry_score(ENTRY, "corr-1", repo, bus)  # must not raise

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1")
    assert "simulated timeout" in notes[0]["error"]


# --- run_post_trade_review ------------------------------------------------------------

async def test_run_post_trade_review_uses_the_stored_trade_outcome():
    repo = InMemoryTradeRepository()
    bus = EventBus()

    await repo.claim_and_forward("corr-1", ENTRY, "{}", _forward_ok)
    await repo.update_exit("corr-1", "won", 130.0, 600.0, "2026-01-01T00:00:00+00:00")

    with patch.object(ai_module, "analyze_with_claude", return_value=("Played out as expected.", None)) as mock:
        await ai_module.run_post_trade_review("corr-1", repo, bus)

    # The prompt must reflect the actual OUTCOME (won, $600), not just entry conditions.
    prompt = mock.call_args[0][0]
    assert "600.0" in prompt
    assert "WIN" in prompt

    notes = await repo.list_ai_notes(trade_correlation_id="corr-1", note_type="post_trade_review")
    assert notes[0]["content"] == "Played out as expected."


async def test_run_post_trade_review_is_a_no_op_for_an_unknown_trade():
    repo = InMemoryTradeRepository()
    bus = EventBus()
    with patch.object(ai_module, "analyze_with_claude") as mock:
        await ai_module.run_post_trade_review("never-existed", repo, bus)  # must not raise
    mock.assert_not_called()


# --- run_report_generation ------------------------------------------------------------

async def test_run_report_generation_only_includes_trades_closed_within_the_period():
    repo = InMemoryTradeRepository()
    bus = EventBus()

    await repo.claim_and_forward("old", ENTRY, "{}", _forward_ok)
    await repo.update_exit("old", "won", 130.0, 600.0, "2020-01-01T00:00:00+00:00")  # outside any window

    await repo.claim_and_forward("recent", ENTRY, "{}", _forward_ok)
    await repo.update_exit(
        "recent", "won", 130.0, 300.0, datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )

    with patch.object(ai_module, "analyze_with_claude", return_value=("Summary text.", None)) as mock:
        await ai_module.run_report_generation("weekly", repo, bus)

    prompt = mock.call_args[0][0]
    assert "Trades: 1 " in prompt  # only the recent trade, not the one from 2020

    reports = await repo.list_ai_notes(note_type="weekly_report")
    assert len(reports) == 1
    assert reports[0]["trade_correlation_id"] is None
    assert reports[0]["content"] == "Summary text."


async def test_run_report_generation_handles_claude_failure_without_raising():
    repo = InMemoryTradeRepository()
    bus = EventBus()

    with patch.object(ai_module, "analyze_with_claude", return_value=(None, "ANTHROPIC_API_KEY not configured")):
        await ai_module.run_report_generation("daily", repo, bus)  # must not raise

    reports = await repo.list_ai_notes(note_type="daily_report")
    assert reports[0]["error"] == "ANTHROPIC_API_KEY not configured"
    assert reports[0]["content"] is None
