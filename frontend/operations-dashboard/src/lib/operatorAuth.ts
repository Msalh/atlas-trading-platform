import { timingSafeEqual } from "node:crypto";

function equal(left: string, right: string): boolean {
  const a = Buffer.from(left);
  const b = Buffer.from(right);
  return a.length === b.length && timingSafeEqual(a, b);
}

export function hasValidOperatorAuthorization(header: string | null): boolean {
  const username = process.env.OPERATOR_USERNAME;
  const password = process.env.OPERATOR_PASSWORD;
  if (!username || !password || !header?.startsWith("Basic ")) return false;
  try {
    const decoded = Buffer.from(header.slice(6), "base64").toString("utf8");
    const separator = decoded.indexOf(":");
    if (separator < 0) return false;
    return equal(decoded.slice(0, separator), username) &&
      equal(decoded.slice(separator + 1), password);
  } catch {
    return false;
  }
}
