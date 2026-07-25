"use client";

import { useCallback, useEffect, useState } from "react";
import {
  SNAPSHOT_API_SCHEMA_VERSION,
  isSnapshotId,
  type SnapshotIntegrityResponse,
  type SnapshotMetadata,
} from "./contract";
import {
  projectSemanticSnapshot,
  SemanticProjectionError,
  type SemanticEvidenceProjection,
} from "./semanticProjection";

export interface SnapshotDetailHeader {
  readonly snapshotId: string;
  readonly snapshotSchemaVersion: string;
}

export type IntegrityFailureState =
  | "failed"
  | "metadata_disagreement"
  | "unsupported_schema"
  | "unavailable"
  | "timeout"
  | "malformed_response"
  | "unauthorized"
  | "forbidden"
  | "not_found";

export type SnapshotDetailState =
  | { readonly status: "integrity_loading"; readonly snapshotId: string }
  | {
      readonly status: "verified";
      readonly snapshotId: string;
      readonly header: SnapshotDetailHeader;
      readonly metadata: SnapshotMetadata;
      readonly integrity: SnapshotIntegrityResponse;
      readonly semanticEvidence: SemanticEvidenceProjection;
      readonly formattedJson: string;
    }
  | {
      readonly status: "integrity_error";
      readonly snapshotId: string;
      readonly integrityState: IntegrityFailureState;
    };

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function metadataFrom(value: unknown, snapshotId: string): SnapshotMetadata | null {
  if (!isObject(value)) return null;
  if (
    value.schema_version !== SNAPSHOT_API_SCHEMA_VERSION ||
    value.snapshot_id !== snapshotId ||
    typeof value.evidence_digest !== "string" ||
    !/^[0-9a-f]{64}$/.test(value.evidence_digest) ||
    typeof value.created_at !== "string" ||
    !isNullableString(value.evaluated_at) ||
    !isNullableString(value.latest_closed_at) ||
    !isNullableString(value.economic_instrument) ||
    !isNullableString(value.market_data_provider) ||
    !isNullableString(value.market_data_series_symbol) ||
    !isNullableString(value.market_data_series_type) ||
    typeof value.timeframe !== "string" ||
    typeof value.strategy_id !== "string" ||
    typeof value.strategy_version !== "string" ||
    typeof value.trust_status !== "string" ||
    !isNullableString(value.supersedes_snapshot_id)
  ) {
    return null;
  }
  return value as unknown as SnapshotMetadata;
}

function metadataMatchesEvidence(
  metadata: SnapshotMetadata,
  evidence: SemanticEvidenceProjection,
): boolean {
  return (
    metadata.economic_instrument === evidence.identity.product &&
    metadata.market_data_provider === evidence.market.provider &&
    metadata.market_data_series_symbol === evidence.market.seriesSymbol &&
    metadata.market_data_series_type === evidence.market.seriesType &&
    metadata.timeframe === evidence.identity.timeframe &&
    metadata.strategy_id === evidence.identity.strategyId &&
    metadata.strategy_version === evidence.identity.strategyVersion &&
    metadata.trust_status === evidence.trust.status &&
    metadata.evaluated_at === evidence.evaluatedAt &&
    metadata.latest_closed_at === evidence.market.latestClosedAt
  );
}

function integrityFrom(
  value: unknown,
  snapshotId: string,
): SnapshotIntegrityResponse | null {
  if (!isObject(value)) return null;
  const keys = Object.keys(value);
  if (
    keys.length !== 4 ||
    !["schema_version", "snapshot_id", "evidence_digest", "valid"].every(
      (key) => keys.includes(key),
    ) ||
    value.schema_version !== SNAPSHOT_API_SCHEMA_VERSION ||
    value.snapshot_id !== snapshotId ||
    typeof value.evidence_digest !== "string" ||
    !/^[0-9a-f]{64}$/.test(value.evidence_digest) ||
    value.valid !== true
  ) {
    return null;
  }
  return value as unknown as SnapshotIntegrityResponse;
}

function detailDigest(value: unknown): string | null {
  if (!isObject(value) || !isObject(value.snapshot)) return null;
  const integrity = value.snapshot.integrity;
  if (
    !isObject(integrity) ||
    integrity.algorithm !== "sha256" ||
    Object.keys(integrity).length !== 2
  ) {
    return null;
  }
  return typeof integrity.evidence_digest === "string" &&
    /^[0-9a-f]{64}$/.test(integrity.evidence_digest)
    ? integrity.evidence_digest
    : null;
}

async function responseErrorCode(response: Response): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (
      isObject(body) &&
      typeof body.code === "string"
    ) {
      return body.code;
    }
  } catch {
    // Dashboard authentication can return a non-JSON response.
  }
  if (response.status === 401) return "dashboard_authentication_required";
  if (response.status === 403) return "snapshot_access_forbidden";
  if (response.status === 404) return "snapshot_not_found";
  if (response.status === 409) return "snapshot_integrity_failed";
  return "snapshot_detail_unavailable";
}

function integrityErrorState(
  response: Response,
  code: string,
): IntegrityFailureState {
  if (response.status === 409 || code === "snapshot_integrity_failed") {
    return "failed";
  }
  if (response.status === 401 || code === "dashboard_authentication_required") {
    return "unauthorized";
  }
  if (
    response.status === 403 ||
    code === "snapshot_upstream_authorization_failed"
  ) {
    return "forbidden";
  }
  if (response.status === 404 || code === "snapshot_not_found") {
    return "not_found";
  }
  if (response.status === 504 || code === "snapshot_upstream_timeout") {
    return "timeout";
  }
  if (
    code === "unexpected_snapshot_response" ||
    code === "snapshot_response_too_large"
  ) {
    return "malformed_response";
  }
  return "unavailable";
}

export function useSnapshotDetail(snapshotId: string): {
  readonly state: SnapshotDetailState;
  readonly refresh: () => void;
} {
  const [state, setState] = useState<SnapshotDetailState>({
    status: "integrity_loading",
    snapshotId,
  });
  const [revision, setRevision] = useState(0);

  const refresh = useCallback(() => {
    setState({ status: "integrity_loading", snapshotId });
    setRevision((current) => current + 1);
  }, [snapshotId]);

  useEffect(() => {
    const controller = new AbortController();
    let current = true;
    const load = async () => {
      if (!isSnapshotId(snapshotId)) {
        setState({
          status: "integrity_error",
          snapshotId,
          integrityState: "malformed_response",
        });
        return;
      }
      setState({ status: "integrity_loading", snapshotId });
      try {
        const [detailResponse, metadataResponse, integrityResponse] =
          await Promise.all([
            fetch(`/api/evidence/snapshots/${snapshotId}`, {
              method: "GET",
              headers: { Accept: "application/json" },
              cache: "no-store",
              signal: controller.signal,
            }),
            fetch(`/api/evidence/snapshots/${snapshotId}/metadata`, {
              method: "GET",
              headers: { Accept: "application/json" },
              cache: "no-store",
              signal: controller.signal,
            }),
            fetch(`/api/evidence/snapshots/${snapshotId}/integrity`, {
              method: "GET",
              headers: { Accept: "application/json" },
              cache: "no-store",
              signal: controller.signal,
            }),
          ]);
        if (!current) return;
        if (
          !detailResponse.ok ||
          !metadataResponse.ok ||
          !integrityResponse.ok
        ) {
          const [detailCode, metadataCode, integrityCode] = await Promise.all([
            responseErrorCode(detailResponse),
            responseErrorCode(metadataResponse),
            responseErrorCode(integrityResponse),
          ]);
          if (!current) return;
          const failedResponse = !integrityResponse.ok
            ? integrityResponse
            : !detailResponse.ok
              ? detailResponse
              : metadataResponse;
          const failedCode = !integrityResponse.ok
            ? integrityCode
            : !detailResponse.ok
              ? detailCode
              : metadataCode;
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState: integrityErrorState(failedResponse, failedCode),
          });
          return;
        }
        const [detailBody, metadataBody, integrityBody]: [
          unknown,
          unknown,
          unknown,
        ] = await Promise.all([
          detailResponse.json(),
          metadataResponse.json(),
          integrityResponse.json(),
        ]);
        if (!current) return;
        if (
          isObject(metadataBody) &&
          typeof metadataBody.snapshot_id === "string" &&
          metadataBody.snapshot_id !== snapshotId
        ) {
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState: "metadata_disagreement",
          });
          return;
        }
        const metadata = metadataFrom(metadataBody, snapshotId);
        const integrity = integrityFrom(integrityBody, snapshotId);
        if (!metadata || !integrity) {
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState: "malformed_response",
          });
          return;
        }
        let semantic;
        try {
          semantic = projectSemanticSnapshot(detailBody, snapshotId);
        } catch (error) {
          const code =
            error instanceof SemanticProjectionError
              ? error.code
              : "invalid_semantic_response";
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState:
              code === "unsupported_snapshot_schema"
                ? "unsupported_schema"
                : "malformed_response",
          });
          return;
        }
        if (!metadataMatchesEvidence(metadata, semantic.evidence)) {
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState: "metadata_disagreement",
          });
          return;
        }
        const semanticDigest = detailDigest(detailBody);
        if (!semanticDigest || semanticDigest !== integrity.evidence_digest) {
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState: "failed",
          });
          return;
        }
        if (metadata.evidence_digest !== integrity.evidence_digest) {
          setState({
            status: "integrity_error",
            snapshotId,
            integrityState: "metadata_disagreement",
          });
          return;
        }
        setState({
          status: "verified",
          snapshotId,
          header: {
            snapshotId: semantic.snapshotId,
            snapshotSchemaVersion: semantic.snapshotSchemaVersion,
          },
          metadata,
          integrity,
          semanticEvidence: semantic.evidence,
          formattedJson: semantic.formattedJson,
        });
      } catch (error) {
        if (
          !current ||
          (error instanceof DOMException && error.name === "AbortError")
        ) {
          return;
        }
        setState({
          status: "integrity_error",
          snapshotId,
          integrityState: "unavailable",
        });
      }
    };
    const initialLoad = window.setTimeout(() => void load(), 0);
    return () => {
      current = false;
      window.clearTimeout(initialLoad);
      controller.abort();
    };
  }, [revision, snapshotId]);

  return {
    state:
      state.snapshotId === snapshotId
        ? state
        : { status: "integrity_loading", snapshotId },
    refresh,
  };
}
