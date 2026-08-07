import { proxyPost } from "@/lib/proxyClient";

export type AdvisoryState = "long_candidate" | "short_candidate" | "no_candidate" | "unavailable";

export interface AdvisoryView {
  state: AdvisoryState;
  instrument: "MNQ";
  timeframe: "5m";
  dataTimestamp: string | null;
  freshness: string;
  entryPrice: number | null;
  stopLoss: number | null;
  takeProfit: number | null;
  confidence: number | null;
  setupQuality: string | null;
  sessionPhase: string | null;
  volatilityRegime: string | null;
  reason: string | null;
}

export interface AIExplanationView {
  status: "available" | "unavailable";
  summary: string | null;
  claims: ReadonlyArray<{ claimId: string; kind: string; text: string; citations: readonly string[] }>;
  limitations: readonly string[];
}

export interface ManualAdvisoryView {
  advisory: AdvisoryView;
  explanation: AIExplanationView;
}

type JsonObject = Record<string, unknown>;

function object(value: unknown): JsonObject | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as JsonObject)
    : null;
}

function string(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function number(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function price(value: unknown): number | null {
  return number(object(value)?.value);
}

function isTraderNowResponse(value: unknown): value is JsonObject {
  const root = object(value);
  return (
    root?.schema_version === "trader_now_response.v2" &&
    object(root.identity)?.product === "MNQ" &&
    object(root.identity)?.timeframe === "5m" &&
    object(root.trust) !== null &&
    object(root.market) !== null &&
    object(root.strategy) !== null
  );
}

function isAIExplanation(value: unknown): boolean {
  const root = object(value);
  if (!root || (root.status !== "available" && root.status !== "unavailable")) return false;
  if (root.status === "unavailable") {
    return root.summary === null && root.reason === "analysis_unavailable" &&
      Array.isArray(root.claims) && root.claims.length === 0 &&
      Array.isArray(root.limitations) && root.limitations.length === 0;
  }
  return typeof root.summary === "string" && root.summary.length > 0 &&
    root.reason === null && Array.isArray(root.claims) && root.claims.every((item) => {
      const claim = object(item);
      return typeof claim?.claim_id === "string" && typeof claim.kind === "string" &&
        typeof claim.text === "string" && Array.isArray(claim.citations) &&
        claim.citations.every((citation) => typeof citation === "string" && citation.startsWith("/evidence/"));
    }) && Array.isArray(root.limitations) && root.limitations.every((item) => typeof item === "string");
}

function isManualAdvisoryResponse(value: unknown): value is JsonObject {
  const root = object(value);
  return root?.schema_version === "manual_advisory_response.v1" &&
    isTraderNowResponse(root.trader_now) && isAIExplanation(root.ai_explanation);
}

function unavailable(root: JsonObject, reason: string): AdvisoryView {
  const sourceTrust = object(root.source_trust);
  const freshness = object(sourceTrust?.freshness);
  return {
    state: "unavailable",
    instrument: "MNQ",
    timeframe: "5m",
    dataTimestamp: string(freshness?.latest_closed_at) ?? string(root.input_snapshot_at),
    freshness: string(freshness?.status) ?? "unavailable",
    entryPrice: null,
    stopLoss: null,
    takeProfit: null,
    confidence: null,
    setupQuality: null,
    sessionPhase: null,
    volatilityRegime: null,
    reason,
  };
}

export function projectAdvisory(root: JsonObject): AdvisoryView {
  const identity = object(root.identity);
  if (identity?.product !== "MNQ" || identity.timeframe !== "5m") {
    return unavailable(root, "Only MNQ on the 5-minute timeframe is supported.");
  }

  const trust = object(root.trust);
  const sourceTrust = object(root.source_trust);
  const freshness = object(sourceTrust?.freshness);
  if (
    trust?.status !== "trusted" ||
    sourceTrust?.overall !== "trusted" ||
    sourceTrust.structural_validity !== "valid" ||
    freshness?.status !== "current"
  ) {
    return unavailable(root, "The latest market evidence is not current and trusted.");
  }

  const market = object(root.market);
  const strategy = object(root.strategy);
  const context = object(root.context);
  const contextData = object(context?.data);
  const session = object(contextData?.session);
  const volatility = object(contextData?.volatility);
  const latestBar = object(market?.latest_bar);
  const strategyAvailability = object(strategy?.availability);

  const latestClosedAt = string(freshness.latest_closed_at);
  if (
    !latestBar ||
    strategyAvailability?.status !== "available" ||
    latestClosedAt === null ||
    string(latestBar.occurred_at) !== latestClosedAt ||
    string(market?.latest_closed_at) !== latestClosedAt
  ) {
    return unavailable(root, "The latest strategy evidence is incomplete.");
  }

  const decisions = Array.isArray(strategy?.decisions) ? strategy.decisions : null;
  if (!decisions) return unavailable(root, "The strategy response is malformed.");
  const candidates = decisions.filter((item) => object(item)?.disposition === "candidate");
  if (candidates.length > 1) {
    return unavailable(root, "The latest evidence contains an ambiguous candidate state.");
  }

  const common = {
    instrument: "MNQ" as const,
    timeframe: "5m" as const,
    dataTimestamp: latestClosedAt,
    freshness: "current",
    entryPrice: price(latestBar.close),
    sessionPhase: string(session?.phase),
    volatilityRegime: string(volatility?.regime),
  };

  if (candidates.length === 0) {
    return {
      ...common,
      state: "no_candidate",
      entryPrice: null,
      stopLoss: null,
      takeProfit: null,
      confidence: null,
      setupQuality: null,
      reason: "No deterministic strategy candidate is present in the latest verified state.",
    };
  }

  const candidate = object(candidates[0]);
  const direction = string(candidate?.direction);
  const stopLoss = price(candidate?.stop);
  const takeProfit = price(candidate?.target);
  const confidence = number(candidate?.confidence);
  const setupIds = Array.isArray(candidate?.setup_ids)
    ? candidate.setup_ids.filter((item): item is string => typeof item === "string")
    : [];
  if (
    (direction !== "long" && direction !== "short") ||
    stopLoss === null ||
    takeProfit === null ||
    confidence === null ||
    common.entryPrice === null ||
    setupIds.length === 0
  ) {
    return unavailable(root, "The strategy candidate is incomplete.");
  }

  return {
    ...common,
    state: direction === "long" ? "long_candidate" : "short_candidate",
    stopLoss,
    takeProfit,
    confidence,
    setupQuality: setupIds.join(", "),
    reason: "Deterministic candidate from the latest trusted TraderNow state.",
  };
}

export async function fetchLatestAdvisory(): Promise<ManualAdvisoryView> {
  const response = await proxyPost(
    "trader-now/manual-advisory",
    { symbol: "MNQ", timeframe: "5m", strategy_id: "displacement_volume_context" },
    isManualAdvisoryResponse,
  );
  const explanation = object(response.ai_explanation)!;
  return {
    advisory: projectAdvisory(object(response.trader_now)!),
    explanation: {
      status: explanation.status as "available" | "unavailable",
      summary: string(explanation.summary),
      claims: (explanation.claims as JsonObject[]).map((claim) => ({
        claimId: claim.claim_id as string,
        kind: claim.kind as string,
        text: claim.text as string,
        citations: claim.citations as string[],
      })),
      limitations: explanation.limitations as string[],
    },
  };
}
