// UI v2. Shared fetch helper for every UI v2 typed client (setupEngineApi.ts,
// researchApi.ts) - always calls the same-origin BFF proxy
// (src/app/api/proxy/[...path]/route.ts), never the Atlas API directly, so
// no API key ever needs to reach the browser for these endpoints
// (implementation plan §5.2/§5.3 - a deliberate departure from
// src/lib/api.ts and src/lib/ruleEngineApi.ts's older patterns).
//
// Also the one place lightweight runtime validation happens: every response
// body is checked against a caller-supplied type guard before being trusted
// as T. A backend shape drift then fails loudly as an ApiFetchError instead
// of an unchecked `as T` cast silently propagating a wrong shape into a
// page - "consider lightweight runtime validation... without a large new
// dependency" from the approved requirements, done here with plain
// hand-written guards rather than a schema-validation library.

export type ApiFetchErrorKind =
  | "not_found"
  | "invalid_request"
  | "upstream_error"
  | "network_error"
  | "invalid_response";

export class ApiFetchError extends Error {
  kind: ApiFetchErrorKind;
  constructor(kind: ApiFetchErrorKind, message: string) {
    super(message);
    this.name = "ApiFetchError";
    this.kind = kind;
  }
}

function isErrorBody(value: unknown): value is { ok: false; error: string } {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return v.ok === false && typeof v.error === "string";
}

export async function proxyGet<T>(
  path: string,
  params: Record<string, string>,
  isValid: (body: unknown) => body is T,
): Promise<T> {
  const qs = new URLSearchParams(params);
  const query = qs.toString();

  let res: Response;
  try {
    res = await fetch(`/api/proxy/${path}${query ? `?${query}` : ""}`, { cache: "no-store" });
  } catch {
    // fetch() itself threw - offline, DNS failure, etc. Never logs the raw
    // error object, only this generic, non-secret message.
    throw new ApiFetchError("network_error", "Could not reach the backend.");
  }

  let body: unknown;
  try {
    body = await res.json();
  } catch {
    throw new ApiFetchError("invalid_response", "The server returned a non-JSON response.");
  }

  if (!res.ok) {
    const message = isErrorBody(body) ? body.error : `Unexpected response: HTTP ${res.status}`;
    if (res.status === 404) throw new ApiFetchError("not_found", message);
    if (res.status === 422) throw new ApiFetchError("invalid_request", message);
    throw new ApiFetchError("upstream_error", message);
  }

  if (!isValid(body)) {
    throw new ApiFetchError("invalid_response", "The server returned an unexpected response shape.");
  }

  return body;
}
