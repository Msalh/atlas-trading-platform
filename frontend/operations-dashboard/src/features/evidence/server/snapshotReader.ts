import { NextResponse } from "next/server";
import {
  SNAPSHOT_API_SCHEMA_VERSION,
  SNAPSHOT_CORRELATION_HEADER,
  SNAPSHOT_DEFAULT_PAGE_SIZE,
  isSnapshotId,
  SNAPSHOT_MAX_CURSOR_LENGTH,
  SNAPSHOT_PAGE_SIZES,
  SNAPSHOT_READER_ROUTES,
  type SnapshotDetailResponse,
  type SnapshotIntegrityResponse,
  type SnapshotListResponse,
  type SnapshotMetadata,
} from "../contract";

const CORRELATION_ID = /^[A-Za-z0-9._:-]{1,128}$/;
const ALLOWED_LIST_PARAMETERS = new Set(["limit", "cursor"]);
const PAGE_SIZES = new Set<number>(SNAPSHOT_PAGE_SIZES);

type ReaderOperation =
  | { readonly kind: "list"; readonly limit: number; readonly cursor: string | null }
  | { readonly kind: "detail"; readonly snapshotId: string }
  | { readonly kind: "metadata"; readonly snapshotId: string }
  | { readonly kind: "integrity"; readonly snapshotId: string };

interface OperationPolicy {
  readonly timeoutMs: number;
  readonly maximumBytes: number;
}

const POLICIES: Readonly<Record<ReaderOperation["kind"], OperationPolicy>> = {
  list: { timeoutMs: 3_000, maximumBytes: 512 * 1024 },
  detail: { timeoutMs: 5_000, maximumBytes: 5 * 1024 * 1024 },
  metadata: { timeoutMs: 3_000, maximumBytes: 256 * 1024 },
  integrity: { timeoutMs: 3_000, maximumBytes: 64 * 1024 },
};

interface BffError {
  readonly ok: false;
  readonly code: string;
  readonly correlation_id: string;
}

class ResponseTooLargeError extends Error {}
class UnexpectedResponseError extends Error {}

function responseHeaders(correlationId: string): HeadersInit {
  return {
    "Cache-Control": "no-store",
    "Content-Type": "application/json",
    "X-Content-Type-Options": "nosniff",
    [SNAPSHOT_CORRELATION_HEADER]: correlationId,
  };
}

function errorResponse(
  status: number,
  code: string,
  correlationId: string,
): NextResponse<BffError> {
  return NextResponse.json(
    { ok: false, code, correlation_id: correlationId },
    { status, headers: responseHeaders(correlationId) },
  );
}

function requestCorrelationId(request: Request): string {
  const supplied = request.headers.get(SNAPSHOT_CORRELATION_HEADER) ?? "";
  return CORRELATION_ID.test(supplied) ? supplied : crypto.randomUUID();
}

function snapshotApiConfiguration():
  | { readonly baseUrl: string; readonly token: string }
  | null {
  const configuredUrl = process.env.SNAPSHOT_API_INTERNAL_URL;
  const token = process.env.SNAPSHOT_READER_API_TOKEN;
  if (!configuredUrl || !token) return null;
  try {
    const url = new URL(configuredUrl);
    if (
      !["http:", "https:"].includes(url.protocol) ||
      url.username ||
      url.password ||
      url.search ||
      url.hash ||
      !url.hostname ||
      !["", "/"].includes(url.pathname)
    ) {
      return null;
    }
    return { baseUrl: url.origin, token };
  } catch {
    return null;
  }
}

function operationPath(operation: ReaderOperation): string {
  switch (operation.kind) {
    case "list": {
      const query = new URLSearchParams({ limit: String(operation.limit) });
      if (operation.cursor !== null) query.set("cursor", operation.cursor);
      return `${SNAPSHOT_READER_ROUTES.list}?${query}`;
    }
    case "detail":
      return SNAPSHOT_READER_ROUTES.detail(operation.snapshotId);
    case "metadata":
      return SNAPSHOT_READER_ROUTES.metadata(operation.snapshotId);
    case "integrity":
      return SNAPSHOT_READER_ROUTES.integrity(operation.snapshotId);
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function hasApiSchema(value: Record<string, unknown>): boolean {
  return value.schema_version === SNAPSHOT_API_SCHEMA_VERSION;
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string";
}

function isMetadata(value: unknown): value is SnapshotMetadata {
  if (!isObject(value) || !hasApiSchema(value)) return false;
  return (
    typeof value.snapshot_id === "string" &&
    isSnapshotId(value.snapshot_id) &&
    typeof value.evidence_digest === "string" &&
    /^[0-9a-f]{64}$/.test(value.evidence_digest) &&
    typeof value.created_at === "string" &&
    isNullableString(value.evaluated_at) &&
    isNullableString(value.latest_closed_at) &&
    isNullableString(value.economic_instrument) &&
    isNullableString(value.market_data_provider) &&
    isNullableString(value.market_data_series_symbol) &&
    isNullableString(value.market_data_series_type) &&
    typeof value.timeframe === "string" &&
    typeof value.strategy_id === "string" &&
    typeof value.strategy_version === "string" &&
    typeof value.trust_status === "string" &&
    isNullableString(value.supersedes_snapshot_id)
  );
}

function isExpectedResponse(
  operation: ReaderOperation,
  value: unknown,
): value is
  | SnapshotListResponse
  | SnapshotDetailResponse
  | SnapshotMetadata
  | SnapshotIntegrityResponse {
  if (!isObject(value) || !hasApiSchema(value)) return false;
  switch (operation.kind) {
    case "list": {
      const nextCursor = value.next_cursor;
      return (
        Array.isArray(value.items) &&
        value.items.every(isMetadata) &&
        (nextCursor === null ||
          (typeof nextCursor === "string" &&
            nextCursor.length <= SNAPSHOT_MAX_CURSOR_LENGTH))
      );
    }
    case "detail":
      return (
        isObject(value.snapshot) &&
        typeof value.snapshot.snapshot_schema_version === "string" &&
        value.snapshot.snapshot_id === operation.snapshotId
      );
    case "metadata":
      return isMetadata(value) && value.snapshot_id === operation.snapshotId;
    case "integrity":
      return (
        value.snapshot_id === operation.snapshotId &&
        typeof value.evidence_digest === "string" &&
        /^[0-9a-f]{64}$/.test(value.evidence_digest) &&
        value.valid === true
      );
  }
}

function translatedUpstreamError(
  status: number,
  correlationId: string,
  retryAfter: string | null,
): NextResponse<BffError> {
  let translatedStatus = 502;
  let code = "snapshot_upstream_failure";
  if (status === 400 || status === 422) {
    translatedStatus = 400;
    code = "invalid_snapshot_request";
  } else if (status === 401) {
    code = "snapshot_upstream_authentication_failed";
  } else if (status === 403) {
    code = "snapshot_upstream_authorization_failed";
  } else if (status === 404) {
    translatedStatus = 404;
    code = "snapshot_not_found";
  } else if (status === 409) {
    translatedStatus = 409;
    code = "snapshot_integrity_failed";
  } else if (status === 429) {
    translatedStatus = 429;
    code = "snapshot_rate_limited";
  } else if (status >= 500) {
    translatedStatus = 503;
    code = "snapshot_service_unavailable";
  }
  const response = errorResponse(translatedStatus, code, correlationId);
  if (translatedStatus === 429 && retryAfter && /^\d{1,5}$/.test(retryAfter)) {
    response.headers.set("Retry-After", retryAfter);
  }
  return response;
}

async function readBody(
  response: Response,
  maximumBytes: number,
): Promise<unknown> {
  const declaredLength = response.headers.get("content-length");
  if (
    declaredLength &&
    (!/^\d+$/.test(declaredLength) || Number(declaredLength) > maximumBytes)
  ) {
    throw new ResponseTooLargeError();
  }
  const body = await response.arrayBuffer();
  if (body.byteLength > maximumBytes) {
    throw new ResponseTooLargeError();
  }
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.startsWith("application/json")) {
    throw new UnexpectedResponseError();
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
  } catch {
    throw new UnexpectedResponseError();
  }
}

async function readSnapshotApi(
  request: Request,
  operation: ReaderOperation,
): Promise<NextResponse> {
  const correlationId = requestCorrelationId(request);
  if (process.env.EVIDENCE_BROWSER_ENABLED !== "true") {
    return errorResponse(404, "evidence_browser_disabled", correlationId);
  }
  const configuration = snapshotApiConfiguration();
  if (!configuration) {
    return errorResponse(
      503,
      "evidence_configuration_unavailable",
      correlationId,
    );
  }
  const policy = POLICIES[operation.kind];
  try {
    const response = await fetch(
      `${configuration.baseUrl}${operationPath(operation)}`,
      {
        method: "GET",
        headers: {
          Accept: "application/json",
          Authorization: `Bearer ${configuration.token}`,
          [SNAPSHOT_CORRELATION_HEADER]: correlationId,
        },
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(policy.timeoutMs),
      },
    );
    const upstreamCorrelation =
      response.headers.get(SNAPSHOT_CORRELATION_HEADER) ?? correlationId;
    const safeCorrelation = CORRELATION_ID.test(upstreamCorrelation)
      ? upstreamCorrelation
      : correlationId;
    if (!response.ok) {
      return translatedUpstreamError(
        response.status,
        safeCorrelation,
        response.headers.get("retry-after"),
      );
    }
    const body = await readBody(response, policy.maximumBytes);
    if (!isExpectedResponse(operation, body)) {
      return errorResponse(
        502,
        "unexpected_snapshot_response",
        safeCorrelation,
      );
    }
    return NextResponse.json(body, {
      status: 200,
      headers: responseHeaders(safeCorrelation),
    });
  } catch (error) {
    if (error instanceof ResponseTooLargeError) {
      return errorResponse(502, "snapshot_response_too_large", correlationId);
    }
    if (error instanceof UnexpectedResponseError) {
      return errorResponse(502, "unexpected_snapshot_response", correlationId);
    }
    if (
      error instanceof DOMException &&
      (error.name === "TimeoutError" || error.name === "AbortError")
    ) {
      return errorResponse(504, "snapshot_upstream_timeout", correlationId);
    }
    return errorResponse(503, "snapshot_service_unavailable", correlationId);
  }
}

export async function readSnapshotList(request: Request): Promise<NextResponse> {
  const url = new URL(request.url);
  const correlationId = requestCorrelationId(request);
  if ([...url.searchParams.keys()].some((key) => !ALLOWED_LIST_PARAMETERS.has(key))) {
    return errorResponse(400, "invalid_snapshot_request", correlationId);
  }
  const limits = url.searchParams.getAll("limit");
  if (limits.length > 1) {
    return errorResponse(400, "invalid_snapshot_request", correlationId);
  }
  const limitValue = limits[0] ?? String(SNAPSHOT_DEFAULT_PAGE_SIZE);
  if (!/^\d+$/.test(limitValue) || !PAGE_SIZES.has(Number(limitValue))) {
    return errorResponse(400, "invalid_snapshot_request", correlationId);
  }
  const cursors = url.searchParams.getAll("cursor");
  if (
    cursors.length > 1 ||
    (cursors[0] !== undefined &&
      (cursors[0].length === 0 ||
        cursors[0].length > SNAPSHOT_MAX_CURSOR_LENGTH))
  ) {
    return errorResponse(400, "invalid_snapshot_request", correlationId);
  }
  return readSnapshotApi(request, {
    kind: "list",
    limit: Number(limitValue),
    cursor: cursors[0] ?? null,
  });
}

export async function readSnapshotDetail(
  request: Request,
  snapshotId: string,
): Promise<NextResponse> {
  if (!isSnapshotId(snapshotId)) {
    return errorResponse(
      400,
      "invalid_snapshot_id",
      requestCorrelationId(request),
    );
  }
  return readSnapshotApi(request, { kind: "detail", snapshotId });
}

export async function readSnapshotMetadata(
  request: Request,
  snapshotId: string,
): Promise<NextResponse> {
  if (!isSnapshotId(snapshotId)) {
    return errorResponse(
      400,
      "invalid_snapshot_id",
      requestCorrelationId(request),
    );
  }
  return readSnapshotApi(request, { kind: "metadata", snapshotId });
}

export async function readSnapshotIntegrity(
  request: Request,
  snapshotId: string,
): Promise<NextResponse> {
  if (!isSnapshotId(snapshotId)) {
    return errorResponse(
      400,
      "invalid_snapshot_id",
      requestCorrelationId(request),
    );
  }
  return readSnapshotApi(request, { kind: "integrity", snapshotId });
}
