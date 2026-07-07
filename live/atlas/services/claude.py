"""
Claude commentary on new trade entries. Advisory only - see
atlas/api/v1/webhook.py::run_claude_analysis for why this never sits on the
order-relay critical path. Unchanged in behavior from Sprint 0; kept synchronous
because the anthropic SDK's client is sync - the caller offloads it to a thread.
"""
from typing import Any, Optional

from atlas.config import settings

SETUP_TAG_MEANING = {
    "BRK": "breakout/continuation setup - needs a real trend to work",
    "RCL": "liquidity reclaim setup",
    "UNK": "unrecognized setup tag",
}


def build_prompt(entry: dict[str, Any]) -> str:
    tag_meaning = SETUP_TAG_MEANING.get(entry.get("setup_tag"), "unknown setup")
    return f"""You are reviewing one new trade entry from an automated ICT-style futures strategy
(MNQ, liquidity-sweep + FVG/reclaim continuation entries). Known context: this strategy only has a
real edge when the broader market is trending; it loses money in choppy/range-bound conditions. A
daily-timeframe trend regime filter is supposed to screen out chop, but it is not perfectly reliable.

New entry:
- Direction: {entry.get('direction')}
- Setup type: {entry.get('setup_tag')} ({tag_meaning})
- Entry price: {entry.get('entry_price')}
- Stop loss: {entry.get('sl')}
- Take profit: {entry.get('tp')}
- ATR: {entry.get('atr')}
- Distance from 50 EMA (in ATR multiples): {entry.get('ema_distance_atr')}
- Daily regime slope (%): {entry.get('regime_slope_pct')}
- Bars since the liquidity sweep this entry is based on: {entry.get('sweep_age_bars')}
- Session: {entry.get('session')}

In 3-4 sentences: does this entry look aligned with a genuinely trending market (steep regime
slope, not chasing too far from the EMA, a fresh sweep) or does it look like a marginal/chop-risk
entry (weak slope, stale sweep, overextended from EMA)? Be direct and specific about which factor(s)
stand out, don't hedge with generic disclaimers."""


def analyze_with_claude(entry: dict[str, Any]) -> tuple[Optional[str], Optional[str]]:
    if not settings.anthropic_api_key:
        return None, "ANTHROPIC_API_KEY not configured"
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        response = client.messages.create(
            model=settings.claude_model,
            max_tokens=300,
            messages=[{"role": "user", "content": build_prompt(entry)}],
        )
        return response.content[0].text, None
    except Exception as e:
        return None, str(e)
