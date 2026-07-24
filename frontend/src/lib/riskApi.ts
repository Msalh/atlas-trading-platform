// Sprint 11A Group 0B. Typed client for GET /risk, reached through the
// same-origin BFF proxy (src/lib/proxyClient.ts). Shape mirrored from atlas/risk.py's
// RiskSnapshot/OpenPositionRisk/KillSwitchStatus dataclasses (the backend
// response is `asdict(compute_risk_snapshot(...))`) - see
// atlas/api/v1/risk.py.
//
// "risk" is a new proxy allowlist entry (src/lib/proxyAllowlist.ts), added
// alongside this client.

import { ApiFetchError, proxyGet } from "@/lib/proxyClient";

export { ApiFetchError };

export interface OpenPositionRisk {
  correlation_id: string;
  direction: "long" | "short" | null;
  quantity: number | null;
  entry_price: number | null;
  sl: number | null;
  tp: number | null;
  current_price: number | null;
  unrealized_pnl: number | null;
  risk_points: number | null;
  reward_points: number | null;
  risk_dollars: number | null;
  reward_dollars: number | null;
  exposure_contracts: number | null;
  exposure_pct_of_max: number | null;
  exceeds_max_contracts: boolean;
}

export interface KillSwitchStatus {
  should_trigger: boolean;
  reasons: string[];
  enforced: boolean;
}

export interface RiskResponse {
  account_configured: boolean;
  starting_balance: number;
  current_balance: number;
  high_water_mark: number;

  daily_loss_limit: number;
  daily_realized_pnl: number;
  daily_loss_used: number;
  daily_loss_remaining: number;
  daily_loss_limit_breached: boolean;

  trailing_drawdown_limit: number;
  trailing_stop_balance: number;
  remaining_drawdown: number;
  trailing_drawdown_breached: boolean;

  max_contracts: number;
  point_value: number;

  open_position: OpenPositionRisk | null;
  kill_switch: KillSwitchStatus;
}

function isNullableNumber(value: unknown): value is number | null {
  return value === null || typeof value === "number";
}

function isOpenPositionRisk(value: unknown): value is OpenPositionRisk {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.correlation_id === "string" &&
    (v.direction === null || v.direction === "long" || v.direction === "short") &&
    (v.quantity === null || typeof v.quantity === "number") &&
    isNullableNumber(v.entry_price) &&
    isNullableNumber(v.sl) &&
    isNullableNumber(v.tp) &&
    isNullableNumber(v.current_price) &&
    isNullableNumber(v.unrealized_pnl) &&
    isNullableNumber(v.risk_points) &&
    isNullableNumber(v.reward_points) &&
    isNullableNumber(v.risk_dollars) &&
    isNullableNumber(v.reward_dollars) &&
    (v.exposure_contracts === null || typeof v.exposure_contracts === "number") &&
    isNullableNumber(v.exposure_pct_of_max) &&
    typeof v.exceeds_max_contracts === "boolean"
  );
}

function isKillSwitchStatus(value: unknown): value is KillSwitchStatus {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.should_trigger === "boolean" &&
    Array.isArray(v.reasons) &&
    v.reasons.every((r) => typeof r === "string") &&
    typeof v.enforced === "boolean"
  );
}

function isRiskResponse(value: unknown): value is RiskResponse {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    typeof v.account_configured === "boolean" &&
    typeof v.starting_balance === "number" &&
    typeof v.current_balance === "number" &&
    typeof v.high_water_mark === "number" &&
    typeof v.daily_loss_limit === "number" &&
    typeof v.daily_realized_pnl === "number" &&
    typeof v.daily_loss_used === "number" &&
    typeof v.daily_loss_remaining === "number" &&
    typeof v.daily_loss_limit_breached === "boolean" &&
    typeof v.trailing_drawdown_limit === "number" &&
    typeof v.trailing_stop_balance === "number" &&
    typeof v.remaining_drawdown === "number" &&
    typeof v.trailing_drawdown_breached === "boolean" &&
    typeof v.max_contracts === "number" &&
    typeof v.point_value === "number" &&
    (v.open_position === null || isOpenPositionRisk(v.open_position)) &&
    isKillSwitchStatus(v.kill_switch)
  );
}

export function fetchRisk(): Promise<RiskResponse> {
  return proxyGet("risk", {}, isRiskResponse);
}
