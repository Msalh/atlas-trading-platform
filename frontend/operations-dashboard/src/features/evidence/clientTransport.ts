export const LOCAL_RESPONSE_LIMITS = {
  list: 512 * 1024,
  detail: 5 * 1024 * 1024,
  metadata: 256 * 1024,
  integrity: 64 * 1024,
  error: 64 * 1024,
} as const;

export class LocalResponseError extends Error {}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function hasErrorEnvelopeMarkers(value: unknown): boolean {
  return (
    isObject(value) &&
    ["ok", "code", "message", "correlation_id"].some((key) => key in value)
  );
}

export async function readBoundedJson(
  response: Response,
  maximumBytes: number,
): Promise<unknown> {
  const contentType = response.headers.get("content-type")?.toLowerCase() ?? "";
  if (!contentType.startsWith("application/json")) {
    throw new LocalResponseError("unexpected_content_type");
  }
  const declaredLength = response.headers.get("content-length");
  if (
    declaredLength !== null &&
    (!/^\d+$/.test(declaredLength) || Number(declaredLength) > maximumBytes)
  ) {
    throw new LocalResponseError("response_too_large");
  }
  const body = await response.arrayBuffer();
  if (body.byteLength > maximumBytes) {
    throw new LocalResponseError("response_too_large");
  }
  try {
    return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(body));
  } catch {
    throw new LocalResponseError("malformed_json");
  }
}

export async function safeErrorCode(
  response: Response,
  fallback: string,
): Promise<string> {
  if (response.status === 401) return "dashboard_authentication_required";
  try {
    const value = await readBoundedJson(response, LOCAL_RESPONSE_LIMITS.error);
    if (!isObject(value)) return fallback;
    const keys = Object.keys(value);
    if (
      keys.length !== 3 ||
      value.ok !== false ||
      typeof value.code !== "string" ||
      !/^[a-z][a-z0-9_]{0,127}$/.test(value.code) ||
      typeof value.correlation_id !== "string" ||
      !/^[A-Za-z0-9._:-]{1,128}$/.test(value.correlation_id)
    ) {
      return fallback;
    }
    return value.code;
  } catch {
    return fallback;
  }
}
