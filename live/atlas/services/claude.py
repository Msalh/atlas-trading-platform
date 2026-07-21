"""
Raw Claude API access, plus the prompt builders for every AI Copilot feature: entry
intelligence (Sprint 7), post-trade review, and daily/weekly reports (Sprint 6).
`analyze_with_claude` is the one function that actually calls the Anthropic API - it
takes a finished prompt string and returns raw text, with no opinion about what kind
of analysis it's for.

As of Sprint 7, build_intelligence_prompt no longer asks Claude to produce a score at
all - atlas/intelligence.py computes the score, expected R, and win rate
deterministically from historical trades first, and this prompt only asks Claude to
explain those numbers in prose. There is nothing left to parse out of Claude's
response for entry scoring; its raw text is stored as-is.

Advisory only, always. See atlas/ai.py's module docstring for why none of this ever
sits on the order-relay critical path.
"""
from typing import Any, Optional

from atlas.config import settings

# Production-hardening: analyze_with_claude() previously made the Anthropic
# request with no timeout at all, relying entirely on the SDK's own default
# (which is generous - minutes, not seconds). Since every caller of this
# function already runs it in a background thread, off the order-relay
# critical path (see this module's own docstring and atlas/ai.py), a slow
# or hung Anthropic request could never block a trade - but it could still
# tie up a thread-pool worker for an unbounded amount of time. 30 seconds is
# generous for a single short completion (max_tokens=400, a few hundred
# words of prompt) while still bounding the worst case to something finite.
CLAUDE_REQUEST_TIMEOUT_SECONDS = 30.0

SETUP_TAG_MEANING = {
    "BRK": "breakout/continuation setup - needs a real trend to work",
    "RCL": "liquidity reclaim setup",
    "UNK": "unrecognized setup tag",
}


def _entry_conditions_block(entry: dict[str, Any]) -> str:
    tag_meaning = SETUP_TAG_MEANING.get(entry.get("setup_tag"), "unknown setup")
    return f"""- Direction: {entry.get('direction')}
- Setup type: {entry.get('setup_tag')} ({tag_meaning})
- Entry price: {entry.get('entry_price')}
- Stop loss: {entry.get('sl')}
- Take profit: {entry.get('tp')}
- ATR: {entry.get('atr')}
- Distance from 50 EMA (in ATR multiples): {entry.get('ema_distance_atr')}
- Daily regime slope (%): {entry.get('regime_slope_pct')}
- Bars since the liquidity sweep this entry is based on: {entry.get('sweep_age_bars')}
- Session: {entry.get('session')}"""


def build_intelligence_prompt(
    entry: dict[str, Any], summary: Any, confidence_score: int, confidence_label: str, factors: list[Any],
) -> str:
    """Sprint 7: unlike build_entry_score_prompt above, the score itself is NOT
    Claude's job here - atlas/intelligence.py already computed confidence_score,
    confidence_label, and every number in `summary`/`factors` deterministically from
    historical trades before this prompt is ever built. Claude's only task is to
    explain, in prose, why those specific numbers came out the way they did - it is
    explicitly told not to invent or override the score."""

    def factor_line(f):
        if f.favorable is None:
            verdict = "n/a (not enough historical winners/losers to compare)"
        else:
            verdict = "favorable" if f.favorable else "unfavorable"
        return (
            f"  - {f.name}: this entry = {f.entry_value}, historical winners' median = {f.winners_median}, "
            f"historical losers' median = {f.losers_median} ({verdict})"
        )

    avg_r = "n/a" if summary.avg_r is None else f"{summary.avg_r:.2f}R"

    return f"""You are explaining an already-computed confidence score for one new trade entry from an
automated ICT-style futures strategy (MNQ, liquidity-sweep + FVG/reclaim continuation entries). The
score below was computed deterministically from historical trades sharing this entry's direction and
setup tag - you are NOT scoring this trade yourself, only explaining the numbers already computed.

New entry:
{_entry_conditions_block(entry)}

Computed from {summary.total_trades} historically similar trades (same direction + setup tag):
- Confidence score: {confidence_score}/10 ({confidence_label})
- Historical win rate for similar setups: {summary.win_rate_pct:.0f}%
- Expected R (average R-multiple of similar trades): {avg_r}

Measurable factors behind this score:
{chr(10).join(factor_line(f) for f in factors)}

In 2-3 sentences: explain WHY the score is what it is, referencing the specific factors above that
support or undercut it. Do not propose a different score and do not invent numbers not given above -
your only job is to explain these ones, directly and specifically."""


def build_post_trade_review_prompt(trade: dict[str, Any]) -> str:
    outcome = "a WIN" if trade.get("status") == "won" else "a LOSS"
    return f"""You are reviewing one completed trade from an automated ICT-style futures strategy
(MNQ, liquidity-sweep + FVG/reclaim continuation entries), after the fact - the position is closed.

Entry conditions:
{_entry_conditions_block(trade)}

Outcome: {outcome}
- Exit price: {trade.get('exit_price')}
- Realized P&L: {trade.get('realized_pnl')}

In 3-4 sentences: did this trade play out the way the entry conditions suggested it should, or did
it defy them? If it won, was that a well-earned result of genuine trend alignment or did it work
despite marginal conditions? If it lost, was that an entry that looked risky going in, or did a
reasonable-looking setup just not work out? Be direct and specific, no generic disclaimers."""


def build_report_prompt(period: str, summary: Any, breakdown: Any) -> str:
    label = "today" if period == "daily" else "this week"

    def group_lines(groups):
        if not groups:
            return "  (no closed trades)"
        return "\n".join(
            f"  - {g.key}: {g.total_trades} trades, {g.win_rate_pct:.0f}% win rate, "
            f"${g.total_realized_pnl:,.2f} P&L"
            for g in groups
        )

    profit_factor = "undefined (no losses)" if summary.profit_factor is None else f"{summary.profit_factor:.2f}"
    avg_r = "n/a" if summary.avg_r is None else f"{summary.avg_r:.2f}R (n={summary.r_multiple_sample_size})"

    return f"""You are writing a short {period} trading journal summary for an automated ICT-style
futures strategy (MNQ, liquidity-sweep + FVG/reclaim continuation entries), covering {label}.

Performance {label}:
- Trades: {summary.total_trades} ({summary.wins}W / {summary.losses}L, {summary.win_rate_pct:.1f}% win rate)
- Expectancy: ${summary.expectancy:,.2f} per trade
- Profit factor: {profit_factor}
- Average R: {avg_r}

By session:
{group_lines(breakdown.by_session)}

By setup:
{group_lines(breakdown.by_setup)}

In 4-6 sentences: summarize how the strategy performed {label}, call out anything notable (a
session or setup that stood out, positively or negatively), and note one thing worth watching
going into the next period. Be specific and grounded in the numbers above, not generic."""


def analyze_with_claude(prompt: str) -> tuple[Optional[str], Optional[str]]:
    """Sends one prompt, returns (text, error). Never raises - callers offload this to
    a thread (it's a blocking network call) and treat both return values as always
    present, never an exception to catch from this function specifically.

    Bounded by CLAUDE_REQUEST_TIMEOUT_SECONDS - a timeout raises inside the try/except
    below exactly like any other Anthropic SDK error, so it degrades the same way an
    API outage already does: (None, str(e)), never an unhandled exception, and never a
    retry (a single attempt was already this function's contract before this change)."""
    if not settings.anthropic_api_key:
        return None, "ANTHROPIC_API_KEY not configured"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=CLAUDE_REQUEST_TIMEOUT_SECONDS)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=400,
            messages=[{"role": "user", "content": prompt}],
            timeout=CLAUDE_REQUEST_TIMEOUT_SECONDS,
        )
        return response.content[0].text, None
    except Exception as e:
        return None, str(e)
