import {
  SNAPSHOT_API_SCHEMA_VERSION,
  SNAPSHOT_SCHEMA_VERSION,
  type JsonValue,
} from "./contract";

export const SUPPORTED_SEMANTIC_SCHEMAS = [
  SNAPSHOT_SCHEMA_VERSION,
] as const;
export const SEMANTIC_LIMITS = {
  maximumDepth: 12,
  maximumArrayItems: 500,
  maximumStringLength: 20_000,
  maximumNodes: 5_000,
  maximumFormattedCharacters: 512 * 1024,
} as const;

const SNAPSHOT_KEYS = new Set([
  "canonicalization_profile",
  "created_at",
  "evidence",
  "evidence_profile",
  "idempotency_key",
  "integrity",
  "snapshot_id",
  "snapshot_schema_version",
  "source",
  "supersedes_snapshot_id",
]);
const EVIDENCE_KEYS = new Set([
  "availability",
  "context",
  "decision",
  "evaluated_at",
  "identity",
  "input_snapshot_at",
  "interpretations",
  "market",
  "risk",
  "rules",
  "setups",
  "source_trust",
  "strategy",
  "trust",
]);
const BIDI_CONTROLS = /[\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]/g;

export type SemanticScalar = string | number | boolean | null;

export interface AvailabilityProjection {
  readonly name: string;
  readonly status: string;
  readonly reasonCodes: readonly string[];
}

export interface FactProjection {
  readonly id: string;
  readonly status: string;
  readonly value: SemanticScalar;
  readonly reason: string | null;
  readonly definitionVersion: string;
}

export interface SetupProjection {
  readonly id: string;
  readonly status: string;
  readonly detected: boolean;
  readonly severity: string;
  readonly reason: string | null;
  readonly definitionVersion: string;
  readonly supportingFactIds: readonly string[];
}

export interface InterpretationProjection {
  readonly setupId: string;
  readonly direction: string;
  readonly detected: boolean;
  readonly reasonCodes: readonly string[];
  readonly source: string | null;
}

export interface StrategyProjection {
  readonly strategyId: string;
  readonly strategyVersion: string;
  readonly direction: string;
  readonly disposition: string;
  readonly confidence: string | number | null;
  readonly reasonCodes: readonly string[];
  readonly setupIds: readonly string[];
}

export interface SemanticEvidenceProjection {
  readonly evaluatedAt: string | null;
  readonly inputSnapshotAt: string | null;
  readonly identity: {
    readonly product: string;
    readonly timeframe: string;
    readonly strategyId: string;
    readonly strategyVersion: string;
  };
  readonly trust: {
    readonly status: string;
    readonly policyVersion: string;
    readonly reasonCodes: readonly string[];
  };
  readonly availability: readonly AvailabilityProjection[];
  readonly market: {
    readonly status: string;
    readonly reasonCodes: readonly string[];
    readonly economicInstrument: string | null;
    readonly provider: string | null;
    readonly seriesSymbol: string | null;
    readonly seriesType: string | null;
    readonly latestClosedAt: string | null;
    readonly barCount: number;
  };
  readonly sourceTrust: {
    readonly overall: string;
    readonly structuralValidity: string;
    readonly freshnessStatus: string;
    readonly latenessSeconds: string | number | null;
    readonly reasonCodes: readonly string[];
  } | null;
  readonly rules: {
    readonly availability: AvailabilityProjection;
    readonly facts: readonly FactProjection[];
  };
  readonly setups: {
    readonly availability: AvailabilityProjection;
    readonly setups: readonly SetupProjection[];
  };
  readonly context: {
    readonly availability: AvailabilityProjection;
    readonly quality: string | null;
    readonly sessionPhase: string | null;
    readonly volatilityRegime: string | null;
  };
  readonly interpretations: {
    readonly availability: AvailabilityProjection;
    readonly interpretations: readonly InterpretationProjection[];
  };
  readonly strategy: {
    readonly availability: AvailabilityProjection;
    readonly decisions: readonly StrategyProjection[];
  };
  readonly risk: {
    readonly schemaVersion: string;
    readonly status: string;
    readonly primaryReason: string;
    readonly requestedQuantity: number;
    readonly approvedQuantity: number;
    readonly contributingReasons: readonly string[];
  } | null;
  readonly decision: {
    readonly availability: string;
    readonly state: SemanticScalar;
  };
}

export interface SemanticSnapshotProjection {
  readonly snapshotId: string;
  readonly snapshotSchemaVersion: typeof SNAPSHOT_SCHEMA_VERSION;
  readonly evidence: SemanticEvidenceProjection;
  readonly formattedJson: string;
}

export class SemanticProjectionError extends Error {
  constructor(
    readonly code:
      | "invalid_semantic_response"
      | "semantic_content_limit_exceeded"
      | "unsupported_snapshot_schema",
  ) {
    super(code);
  }
}

function fail(): never {
  throw new SemanticProjectionError("invalid_semantic_response");
}

function object(value: unknown): Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) fail();
  return value as Record<string, unknown>;
}

function string(value: unknown): string {
  if (typeof value !== "string") fail();
  return value;
}

function nullableString(value: unknown): string | null {
  if (value === null) return null;
  return string(value);
}

function number(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) fail();
  return value;
}

function stringOrNumberOrNull(value: unknown): string | number | null {
  if (value === null || typeof value === "string") return value;
  return number(value);
}

function boolean(value: unknown): boolean {
  if (typeof value !== "boolean") fail();
  return value;
}

function scalar(value: unknown): SemanticScalar {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean"
  ) {
    return value;
  }
  return number(value);
}

function array(value: unknown): readonly unknown[] {
  if (!Array.isArray(value)) fail();
  return value;
}

function strings(value: unknown): readonly string[] {
  return array(value).map(string);
}

function optionalObject(
  parent: Record<string, unknown>,
  key: string,
): Record<string, unknown> | null {
  const value = parent[key];
  return value === null || value === undefined ? null : object(value);
}

function availability(value: unknown, name: string): AvailabilityProjection {
  const item = object(value);
  return {
    name,
    status: string(item.status),
    reasonCodes: strings(item.reason_codes),
  };
}

function hasExactKeys(
  value: Record<string, unknown>,
  allowed: ReadonlySet<string>,
): boolean {
  const keys = Object.keys(value);
  return keys.length === allowed.size && keys.every((key) => allowed.has(key));
}

function enforceBounds(value: unknown): void {
  let nodes = 0;
  const seen = new WeakSet<object>();
  const visit = (current: unknown, depth: number) => {
    nodes += 1;
    if (
      nodes > SEMANTIC_LIMITS.maximumNodes ||
      depth > SEMANTIC_LIMITS.maximumDepth
    ) {
      throw new SemanticProjectionError("semantic_content_limit_exceeded");
    }
    if (typeof current === "string") {
      if (current.length > SEMANTIC_LIMITS.maximumStringLength) {
        throw new SemanticProjectionError("semantic_content_limit_exceeded");
      }
      return;
    }
    if (
      current === null ||
      typeof current === "boolean" ||
      (typeof current === "number" && Number.isFinite(current))
    ) {
      return;
    }
    if (typeof current !== "object") fail();
    if (seen.has(current)) fail();
    seen.add(current);
    if (Array.isArray(current)) {
      if (current.length > SEMANTIC_LIMITS.maximumArrayItems) {
        throw new SemanticProjectionError("semantic_content_limit_exceeded");
      }
      current.forEach((item) => visit(item, depth + 1));
      return;
    }
    Object.entries(current).forEach(([key, item]) => {
      visit(key, depth + 1);
      visit(item, depth + 1);
    });
  };
  visit(value, 0);
}

function formattedJson(snapshot: Record<string, unknown>): string {
  const formatted = JSON.stringify(snapshot, null, 2).replace(
    BIDI_CONTROLS,
    (control) =>
      `\\u${control.codePointAt(0)!.toString(16).padStart(4, "0")}`,
  );
  if (formatted.length > SEMANTIC_LIMITS.maximumFormattedCharacters) {
    throw new SemanticProjectionError("semantic_content_limit_exceeded");
  }
  return formatted;
}

function optionalNestedString(
  parent: Record<string, unknown> | null,
  key: string,
): string | null {
  if (!parent || parent[key] === null || parent[key] === undefined) return null;
  return string(parent[key]);
}

function projectEvidence(evidence: Record<string, unknown>): SemanticEvidenceProjection {
  if (!hasExactKeys(evidence, EVIDENCE_KEYS)) fail();
  const identity = object(evidence.identity);
  const trust = object(evidence.trust);
  const availabilityObject = object(evidence.availability);
  const market = object(evidence.market);
  const marketAvailability = availability(market.availability, "Market");
  const economicInstrument = optionalObject(market, "economic_instrument");
  const series = optionalObject(market, "market_data_series");
  const sourceTrust = optionalObject(evidence, "source_trust");
  const rules = object(evidence.rules);
  const setups = object(evidence.setups);
  const context = object(evidence.context);
  const contextData = optionalObject(context, "data");
  const session = contextData ? optionalObject(contextData, "session") : null;
  const volatility = contextData
    ? optionalObject(contextData, "volatility")
    : null;
  const interpretations = object(evidence.interpretations);
  const strategy = object(evidence.strategy);
  const risk = optionalObject(evidence, "risk");
  const decision = object(evidence.decision);
  const sourceFreshness = sourceTrust
    ? object(sourceTrust.freshness)
    : null;
  const availabilityNames = [
    ["market", "Market"],
    ["market_history", "Market history"],
    ["rules", "Rules"],
    ["setups", "Setups"],
    ["context", "Context"],
    ["interpretations", "Interpretations"],
    ["strategy", "Strategy"],
  ] as const;

  return {
    evaluatedAt: nullableString(evidence.evaluated_at),
    inputSnapshotAt: nullableString(evidence.input_snapshot_at),
    identity: {
      product: string(identity.product),
      timeframe: string(identity.timeframe),
      strategyId: string(identity.strategy_id),
      strategyVersion: string(identity.strategy_version),
    },
    trust: {
      status: string(trust.status),
      policyVersion: string(trust.policy_version),
      reasonCodes: strings(trust.reason_codes),
    },
    availability: availabilityNames.map(([key, name]) =>
      availability(availabilityObject[key], name),
    ),
    market: {
      status: marketAvailability.status,
      reasonCodes: marketAvailability.reasonCodes,
      economicInstrument: optionalNestedString(economicInstrument, "symbol"),
      provider: optionalNestedString(series, "provider"),
      seriesSymbol: optionalNestedString(series, "symbol"),
      seriesType: optionalNestedString(series, "series_type"),
      latestClosedAt: nullableString(market.latest_closed_at),
      barCount: number(market.bar_count),
    },
    sourceTrust: sourceTrust
      ? {
          overall: string(sourceTrust.overall),
          structuralValidity: string(sourceTrust.structural_validity),
          freshnessStatus: string(sourceFreshness!.status),
          latenessSeconds:
            sourceFreshness!.lateness_seconds === undefined
              ? null
              : stringOrNumberOrNull(sourceFreshness!.lateness_seconds),
          reasonCodes: strings(sourceTrust.reason_codes),
        }
      : null,
    rules: {
      availability: availability(rules.availability, "Rules"),
      facts: array(rules.facts).map((raw) => {
        const fact = object(raw);
        return {
          id: string(fact.fact_id),
          status: string(fact.status),
          value: scalar(fact.value),
          reason: nullableString(fact.reason),
          definitionVersion: string(fact.definition_version),
        };
      }),
    },
    setups: {
      availability: availability(setups.availability, "Setups"),
      setups: array(setups.setups).map((raw) => {
        const setup = object(raw);
        return {
          id: string(setup.setup_id),
          status: string(setup.status),
          detected: boolean(setup.detected),
          severity: string(setup.severity),
          reason: nullableString(setup.reason),
          definitionVersion: string(setup.definition_version),
          supportingFactIds: strings(setup.supporting_fact_ids),
        };
      }),
    },
    context: {
      availability: availability(context.availability, "Context"),
      quality: optionalNestedString(contextData, "quality"),
      sessionPhase: optionalNestedString(session, "phase"),
      volatilityRegime: optionalNestedString(volatility, "regime"),
    },
    interpretations: {
      availability: availability(
        interpretations.availability,
        "Interpretations",
      ),
      interpretations: array(interpretations.interpretations).map((raw) => {
        const item = object(raw);
        return {
          setupId: string(item.setup_id),
          direction: string(item.direction),
          detected: boolean(item.detected),
          reasonCodes: strings(item.reason_codes),
          source:
            item.source === undefined ? null : nullableString(item.source),
        };
      }),
    },
    strategy: {
      availability: availability(strategy.availability, "Strategy"),
      decisions: array(strategy.decisions).map((raw) => {
        const item = object(raw);
        return {
          strategyId: string(item.strategy_id),
          strategyVersion: string(item.strategy_version),
          direction: string(item.direction),
          disposition: string(item.disposition),
          confidence: stringOrNumberOrNull(item.confidence),
          reasonCodes: strings(item.reason_codes),
          setupIds: strings(item.setup_ids),
        };
      }),
    },
    risk: risk
      ? {
          schemaVersion: string(risk.schema_version),
          status: string(risk.status),
          primaryReason: string(risk.primary_reason),
          requestedQuantity: number(risk.requested_quantity),
          approvedQuantity: number(risk.approved_quantity),
          contributingReasons: strings(risk.contributing_reasons),
        }
      : null,
    decision: {
      availability: string(decision.availability),
      state: scalar(decision.state),
    },
  };
}

export function projectSemanticSnapshot(
  response: unknown,
  expectedSnapshotId: string,
): SemanticSnapshotProjection {
  enforceBounds(response);
  const envelope = object(response);
  if (
    envelope.schema_version !== SNAPSHOT_API_SCHEMA_VERSION ||
    !hasExactKeys(
      envelope,
      new Set(["schema_version", "snapshot"]),
    )
  ) {
    fail();
  }
  const snapshot = object(envelope.snapshot);
  if (!hasExactKeys(snapshot, SNAPSHOT_KEYS)) fail();
  if (snapshot.snapshot_id !== expectedSnapshotId) fail();
  if (snapshot.snapshot_schema_version !== SNAPSHOT_SCHEMA_VERSION) {
    throw new SemanticProjectionError("unsupported_snapshot_schema");
  }
  if (
    snapshot.evidence_profile !== "trader_now_complete.v1" ||
    snapshot.canonicalization_profile !== "atlas-jcs.v1"
  ) {
    fail();
  }
  const evidence = object(snapshot.evidence);
  return {
    snapshotId: expectedSnapshotId,
    snapshotSchemaVersion: SNAPSHOT_SCHEMA_VERSION,
    evidence: projectEvidence(evidence),
    formattedJson: formattedJson(snapshot),
  };
}

export function safeSemanticText(value: SemanticScalar): string {
  if (value === null) return "Unavailable";
  const text = String(value);
  return text.replace(
    BIDI_CONTROLS,
    (control) =>
      `<U+${control.codePointAt(0)!.toString(16).toUpperCase().padStart(4, "0")}>`,
  );
}

export function semanticJsonIsValid(value: string): JsonValue {
  return JSON.parse(value) as JsonValue;
}
