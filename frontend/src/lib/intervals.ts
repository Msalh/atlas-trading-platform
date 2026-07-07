// Base poll intervals (ms) used when SSE is not connected - unchanged from Sprint 2.
// When SSE *is* connected, intervals are multiplied by SSE_SAFETY_FACTOR: SSE pushes
// invalidations the instant something happens, so polling only needs to run
// infrequently as a safety net (covering a missed/dropped SSE event, not as the
// primary update path). Polling never stops entirely - see
// docs/sprint3/architecture-decisions.md for why "keep polling fallback" means "also
// keep polling while connected," not "disable polling."
const SSE_SAFETY_FACTOR = 6;

export function pollInterval(sseConnected: boolean, baseMs: number): number {
  return sseConnected ? baseMs * SSE_SAFETY_FACTOR : baseMs;
}
