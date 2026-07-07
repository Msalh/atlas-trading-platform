"""
GET / - the live HTML trade dashboard. Read-only view over
TradeRepository.list_recent; identical rendering to Sprint 0 (render_trade), just
wired to the new repository interface instead of a raw SQLite connection. This is a
placeholder screen relative to the approved V2 frontend design (Next.js + SSE) - it
stays as-is for Sprint 1 since frontend work is out of scope for this sprint.
"""
from fastapi import APIRouter, Depends
from fastapi.responses import HTMLResponse

from atlas.api.deps import get_repository
from atlas.repositories.base import TradeRepository

router = APIRouter()


def render_trade(t: dict) -> str:
    color = "#1a7f37" if t["direction"] == "long" else "#c9302c"
    status_badge = {
        "open": ("#3b82f6", "OPEN"),
        "won": ("#1a7f37", "WON"),
        "lost": ("#c9302c", "LOST"),
    }.get(t["status"], ("#888", t["status"]))

    if t["status"] == "open":
        price_line = f"Current: <b>{t['current_price'] if t['current_price'] is not None else '-'}</b> &nbsp; Unrealized: <b>{t['unrealized_pnl'] if t['unrealized_pnl'] is not None else '-'}</b> &nbsp; (as of {t['last_update_at'] or 'no update yet'})"
    else:
        price_line = f"Exit: <b>{t['exit_price']}</b> &nbsp; Realized P&amp;L: <b>{t['realized_pnl']}</b> &nbsp; (closed {t['closed_at']})"

    if t["pmt_forwarded"]:
        pmt_line = f'<span style="color:#1a7f37;">forwarded to PickMyTrade (HTTP {t["pmt_status_code"]})</span>'
    else:
        pmt_line = f'<span style="color:#c9302c;">NOT forwarded to PickMyTrade{": " + t["pmt_error"] if t["pmt_error"] else ""}</span>'

    analysis = t["llm_analysis"] or (f"(analysis failed: {t['llm_error']})" if t["llm_error"] else "(pending)")

    return f"""
    <div style="border:1px solid #333;border-radius:8px;padding:12px;margin-bottom:12px;background:#111;">
      <div style="display:flex;justify-content:space-between;">
        <span style="color:{color};font-weight:bold;">{(t['direction'] or '?').upper()} - {t['setup_tag'] or '?'}
          <span style="background:{status_badge[0]};color:#fff;border-radius:4px;padding:1px 6px;font-size:11px;margin-left:8px;">{status_badge[1]}</span>
        </span>
        <span style="color:#888;">{t['received_at']}</span>
      </div>
      <div style="color:#ccc;margin-top:6px;">
        Entry: <b>{t['entry_price']}</b> &nbsp; SL: <b>{t['sl']}</b> &nbsp; TP: <b>{t['tp']}</b> &nbsp;
        ATR: {t['atr']} &nbsp; EMA dist (ATR): {t['ema_distance_atr']} &nbsp;
        Regime slope: {t['regime_slope_pct']}% &nbsp; Sweep age: {t['sweep_age_bars']} bars &nbsp; Session: {t['session']}
      </div>
      <div style="color:#ccc;margin-top:6px;">{price_line}</div>
      <div style="margin-top:6px;font-size:13px;">{pmt_line}</div>
      <div style="color:#9cdcfe;margin-top:8px;font-style:italic;">{analysis}</div>
    </div>
    """


@router.get("/", response_class=HTMLResponse)
async def dashboard(repository: TradeRepository = Depends(get_repository)):
    rows = await repository.list_recent(limit=100)
    trades_html = "".join(render_trade(row) for row in rows)

    return f"""<!DOCTYPE html>
<html>
<head>
  <title>MNQU6 Live Trades</title>
  <meta http-equiv="refresh" content="15">
  <style>
    body {{ background:#0a0a0a; color:#eee; font-family: -apple-system, sans-serif; padding: 20px; max-width: 900px; margin: 0 auto; }}
    h1 {{ font-size: 20px; }}
  </style>
</head>
<body>
  <h1>MNQU6 ICT_Funded_v1 - Live Trades</h1>
  <p style="color:#888;">Auto-refreshes every 15s. Showing latest 100 trades.</p>
  {trades_html or '<p style="color:#888;">No trades yet.</p>'}
</body>
</html>"""
