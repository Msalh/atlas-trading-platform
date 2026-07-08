#!/usr/bin/env bash
# Staging deployment smoke test - see docs/staging/deployment-checklist.md.
#
# Usage:
#   BASE_URL=https://your-app.up.railway.app \
#   API_KEY=<the API_KEY you set in Railway> \
#   WEBHOOK_SECRET=<the WEBHOOK_SECRET you set in Railway> \
#   ./smoke_test.sh
#
# WEBHOOK_SECRET is optional - without it, step 6 (webhook secret rejection) is
# skipped, but everything else still runs.
#
# Never sends a real trade entry by default - see step 10, which is opt-in only
# (SEND_TEST_ENTRY=true) and refuses to run at all unless step 5 has already
# confirmed PickMyTrade forwarding is not configured on the target deployment. This
# script never enables or disables anything on the server - it only ever reads.
#
# Requires: bash, curl, timeout (coreutils). No other dependencies - deliberately
# avoids writing to /tmp or shelling out to python3 for JSON parsing (both curl and a
# separately-invoked interpreter agreeing on the same /tmp path is not something this
# script can assume across every environment it might run in - grep is enough for the
# one boolean field this needs).
set -uo pipefail

BASE_URL="${BASE_URL:?Set BASE_URL to your deployed backend URL, e.g. https://your-app.up.railway.app}"
API_KEY="${API_KEY:?Set API_KEY to match the backend deployment API_KEY variable}"
WEBHOOK_SECRET="${WEBHOOK_SECRET:-}"
BASE_URL="${BASE_URL%/}"

PASS=0
FAIL=0

check() {
  local desc="$1" actual="$2" expected="$3"
  if [[ "$actual" == "$expected" ]]; then
    echo "  PASS: $desc"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: $desc (expected $expected, got $actual)"
    FAIL=$((FAIL + 1))
  fi
}

# Fetches $1 with any extra curl args in $2..., prints "<body>\n<http_status>" so
# callers can split the two without ever touching a temp file.
fetch() {
  local url="$1"
  shift
  curl -s -w $'\n%{http_code}' "$@" "$url"
}

echo "== 1. Health =="
RESPONSE=$(fetch "$BASE_URL/api/v1/health")
HEALTH_STATUS=$(echo "$RESPONSE" | tail -n1)
HEALTH_BODY=$(echo "$RESPONSE" | sed '$d')
check "GET /api/v1/health returns 200" "$HEALTH_STATUS" "200"
echo "$HEALTH_BODY"

echo "== 2. Auth: protected endpoint rejects a missing key =="
STATUS=$(fetch "$BASE_URL/api/v1/status" -o /dev/null | tail -n1)
check "GET /api/v1/status without a key returns 401" "$STATUS" "401"

echo "== 3. Auth: protected endpoint rejects a wrong key =="
STATUS=$(fetch "$BASE_URL/api/v1/status" -H "Authorization: Bearer wrong-key" -o /dev/null | tail -n1)
check "GET /api/v1/status with a wrong key returns 401" "$STATUS" "401"

echo "== 4. Auth: protected endpoint accepts the real key =="
RESPONSE=$(fetch "$BASE_URL/api/v1/status" -H "Authorization: Bearer $API_KEY")
STATUS_STATUS=$(echo "$RESPONSE" | tail -n1)
STATUS_BODY=$(echo "$RESPONSE" | sed '$d')
check "GET /api/v1/status with the real key returns 200" "$STATUS_STATUS" "200"

echo "== 5. No real orders possible (the most important check on this list) =="
if echo "$STATUS_BODY" | grep -q '"pickmytrade":{"configured":false'; then
  echo "  PASS: PickMyTrade forwarding is NOT configured - no real order can be placed by this deployment."
  PASS=$((PASS + 1))
  PMT_CONFIGURED="False"
elif echo "$STATUS_BODY" | grep -q '"pickmytrade":{"configured":true'; then
  echo "  WARNING: PickMyTrade forwarding IS configured on this deployment."
  echo "           If this is meant to be staging, unset PICKMYTRADE_WEBHOOK_URL in Railway now."
  FAIL=$((FAIL + 1))
  PMT_CONFIGURED="True"
else
  echo "  FAIL: could not determine pickmytrade.configured from the /status response"
  echo "  $STATUS_BODY"
  FAIL=$((FAIL + 1))
  PMT_CONFIGURED="unknown"
fi

echo "== 6. Webhook secret rejection =="
if [[ -n "$WEBHOOK_SECRET" ]]; then
  STATUS=$(fetch "$BASE_URL/webhook" -o /dev/null -X POST \
    -H "Content-Type: application/json" \
    -d '{"type":"entry","correlation_id":"smoke-test-bad-secret","secret":"definitely-wrong"}' | tail -n1)
  check "POST /webhook with the wrong secret returns 401" "$STATUS" "401"
else
  echo "  SKIPPED (set WEBHOOK_SECRET to also run this check)"
fi

echo "== 7. Interactive docs disabled in production =="
STATUS=$(fetch "$BASE_URL/docs" -o /dev/null | tail -n1)
check "GET /docs returns 404 (disabled when ENVIRONMENT=production)" "$STATUS" "404"

echo "== 8. Security headers present =="
HEADERS=$(curl -s -D - -o /dev/null "$BASE_URL/api/v1/health")
if echo "$HEADERS" | grep -qi "x-content-type-options: *nosniff"; then
  echo "  PASS: X-Content-Type-Options header present"
  PASS=$((PASS + 1))
else
  echo "  FAIL: X-Content-Type-Options header missing"
  FAIL=$((FAIL + 1))
fi

echo "== 9. SSE stream connects =="
SSE_OUTPUT=$(timeout 5 curl -s -N -H "Authorization: Bearer $API_KEY" "$BASE_URL/api/v1/stream" 2>/dev/null | head -n 3 || true)
if echo "$SSE_OUTPUT" | grep -q "event: connected"; then
  echo "  PASS: SSE stream sent the initial 'connected' event"
  PASS=$((PASS + 1))
else
  echo "  FAIL: SSE stream did not send 'connected' within 5s"
  echo "$SSE_OUTPUT"
  FAIL=$((FAIL + 1))
fi

echo "== 10. OPTIONAL: send one test trade entry (opt-in only) =="
if [[ "${SEND_TEST_ENTRY:-false}" == "true" ]]; then
  if [[ -z "$WEBHOOK_SECRET" ]]; then
    echo "  ABORTED: SEND_TEST_ENTRY=true but WEBHOOK_SECRET is not set - can't authenticate the entry."
    FAIL=$((FAIL + 1))
  elif [[ "$PMT_CONFIGURED" != "False" ]]; then
    echo "  ABORTED: refusing to send a test entry - step 5 above did not confirm PickMyTrade"
    echo "           forwarding is disabled on this deployment. Sending an entry right now"
    echo "           could place a REAL order. Unset PICKMYTRADE_WEBHOOK_URL first if this"
    echo "           is meant to be staging, then re-run this script."
    FAIL=$((FAIL + 1))
  else
    CORR_ID="smoke-test-$(date +%s)"
    STATUS=$(fetch "$BASE_URL/webhook" -o /dev/null -X POST \
      -H "Content-Type: application/json" \
      -d "{\"type\":\"entry\",\"correlation_id\":\"$CORR_ID\",\"secret\":\"$WEBHOOK_SECRET\",\"direction\":\"long\",\"setup_tag\":\"SMOKE\",\"entry_price\":100,\"sl\":90,\"tp\":110,\"quantity\":1}" | tail -n1)
    check "POST /webhook test entry returns 207 (stored, correctly NOT forwarded)" "$STATUS" "207"
    echo "  Test trade correlation_id: $CORR_ID - safe to leave in the staging DB, or delete manually."
  fi
else
  echo "  SKIPPED (default). Set SEND_TEST_ENTRY=true to opt in - only meaningful after"
  echo "           step 5 has already confirmed PickMyTrade forwarding is disabled."
fi

echo
echo "== Summary: $PASS passed, $FAIL failed =="
if [[ $FAIL -gt 0 ]]; then
  exit 1
fi
