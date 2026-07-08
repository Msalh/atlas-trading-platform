// AI Copilot Phase 1: rule-based, deterministic advisory notes derived from data that
// already exists (intelligence snapshot + risk snapshot) - no Claude call, nothing
// persisted, purely a client-side read of numbers the backend already computed. This
// never suggests an action to take (no "close this trade" / "reduce size" buttons) -
// only observations, matching "advisory only, never affects order execution."
import { IntelligenceSnapshot, RiskResponse } from "@/lib/api";

export interface ManagementNote {
  severity: "info" | "warning";
  text: string;
}

export function buildManagementNotes(params: {
  intelligence: IntelligenceSnapshot | null;
  risk: RiskResponse | null;
}): ManagementNote[] {
  const { intelligence, risk } = params;
  const notes: ManagementNote[] = [];

  if (risk?.daily_loss_limit_breached) {
    notes.push({
      severity: "warning",
      text: `Daily loss limit is currently breached (used ${risk.daily_loss_used.toFixed(2)} of ${risk.daily_loss_limit.toFixed(2)}).`,
    });
  }

  if (risk?.trailing_drawdown_breached) {
    notes.push({
      severity: "warning",
      text: `Trailing drawdown limit is breached (balance ${risk.current_balance.toFixed(2)} at/below trailing stop ${risk.trailing_stop_balance.toFixed(2)}).`,
    });
  }

  if (risk?.open_position?.exceeds_max_contracts) {
    notes.push({
      severity: "warning",
      text: `Position size (${risk.open_position.exposure_contracts} contracts) exceeds the configured max (${risk.max_contracts}).`,
    });
  }

  if (intelligence) {
    if (intelligence.similar_trade_count === 0) {
      notes.push({
        severity: "info",
        text: "No historical trades with this direction and setup tag yet - confidence isn't available until similar trades close.",
      });
    } else if (intelligence.confidence_score !== null) {
      if (intelligence.confidence_score <= 4) {
        notes.push({
          severity: "warning",
          text: `Low historical confidence (${intelligence.confidence_score}/10) for this setup - similar trades have historically had a thinner edge.`,
        });
      } else if (intelligence.confidence_score >= 8) {
        notes.push({
          severity: "info",
          text: `Strong historical precedent (${intelligence.confidence_score}/10) - similar setups have performed well historically.`,
        });
      }
    }

    const favorable = intelligence.factors.filter((f) => f.favorable === true).length;
    const unfavorable = intelligence.factors.filter((f) => f.favorable === false).length;
    if (unfavorable > favorable) {
      notes.push({
        severity: "warning",
        text: `More factors are unfavorable (${unfavorable}) than favorable (${favorable}) compared to historical winners.`,
      });
    }
  }

  const pos = risk?.open_position;
  if (pos && pos.unrealized_pnl !== null && pos.risk_dollars !== null && pos.risk_dollars > 0) {
    if (pos.unrealized_pnl <= -0.8 * pos.risk_dollars) {
      notes.push({
        severity: "warning",
        text: `Unrealized P&L (${pos.unrealized_pnl.toFixed(2)}) is within 20% of the position's stop-loss risk budget (${(-pos.risk_dollars).toFixed(2)}).`,
      });
    }
  }

  if (notes.length === 0) {
    notes.push({ severity: "info", text: "No notable risk or historical flags for this position right now." });
  }

  return notes;
}
