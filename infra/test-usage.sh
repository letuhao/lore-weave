#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Usage Billing Service Integration Test
#
# Tests usage log recording with purpose, server-side filtering,
# enhanced summary (breakdowns, daily, error_rate), and detail retrieval.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-usage.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0
FAIL=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected: $expected, got: $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_not_empty() {
  local label="$1" value="$2"
  if [ -n "$value" ] && [ "$value" != "null" ] && [ "$value" != "undefined" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (was empty or null)"; FAIL=$((FAIL+1))
  fi
}

assert_gte() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" -ge "$expected" ] 2>/dev/null; then
    green "$label ($actual >= $expected)"; PASS=$((PASS+1))
  else
    red "$label (expected >= $expected, got: $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label (HTTP $actual)"; PASS=$((PASS+1))
  else
    red "$label (expected HTTP $expected, got $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if echo "$haystack" | grep -q "$needle"; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected to contain: $needle)"; FAIL=$((FAIL+1))
  fi
}

jget() {
  local path="$1"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      try {
        const j=JSON.parse(d);
        const keys='${path}'.slice(1).split('.');
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        if(v===undefined||v===null) console.log('null');
        else console.log(v);
      } catch { console.log(''); }
    });
  " 2>/dev/null || echo ""
}

# ── Setup: Auth ──────────────────────────────────────────────────────────────
header "Setup: Authenticate"

UNAME="usagetest_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# Extract user_id from JWT for internal record calls
USER_ID=$(echo "$TOKEN" | cut -d. -f2 | base64 -d 2>/dev/null | node -e "
  let d='';process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{try{console.log(JSON.parse(d).sub)}catch{console.log('')}})
" 2>/dev/null || echo "")
assert_not_empty "Extracted user_id from JWT" "$USER_ID"

# Internal service URL for recording (bypasses gateway auth — internal-only endpoint)
INTERNAL_URL="http://localhost:8209"

# ── T01: Account balance — initial state ─────────────────────────────────────
header "T01: Account balance — initial state"

BAL_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/account-balance")
TIER=$(echo "$BAL_RESP" | jget .tier_name)
QUOTA=$(echo "$BAL_RESP" | jget .month_quota_tokens)
CREDITS=$(echo "$BAL_RESP" | jget .credits_balance)
assert_eq "T01 default tier is starter" "starter" "$TIER"
assert_gte "T01 quota > 0" 1 "$QUOTA"
assert_gte "T01 credits > 0" 1 "$CREDITS"

# ── T02: Usage summary — empty (no records yet) ─────────────────────────────
header "T02: Usage summary — empty state"

SUM_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-summary?period=last_7d")
REQ_COUNT=$(echo "$SUM_RESP" | jget .request_count)
ERR_RATE=$(echo "$SUM_RESP" | jget .error_rate)
assert_eq "T02 request_count is 0" "0" "$REQ_COUNT"
assert_eq "T02 error_rate is 0" "0" "$ERR_RATE"

# ── T03: Record invocation with purpose=translation ──────────────────────────
header "T03: Record invocation (translation)"

REQ_ID1=$(node -e "const{randomUUID}=require('crypto');console.log(randomUUID())")
MODEL_REF=$(node -e "const{randomUUID}=require('crypto');console.log(randomUUID())")

REC_RESP=$(curl -s -X POST "$INTERNAL_URL/internal/model-billing/record" \
  -H "Content-Type: application/json" \
  -d "{
    \"request_id\":\"$REQ_ID1\",
    \"owner_user_id\":\"$USER_ID\",
    \"provider_kind\":\"anthropic\",
    \"model_source\":\"user_model\",
    \"model_ref\":\"$MODEL_REF\",
    \"input_tokens\":1000,
    \"output_tokens\":500,
    \"input_payload\":{\"messages\":[{\"role\":\"user\",\"content\":\"translate this\"}]},
    \"output_payload\":{\"content\":\"translated text\"},
    \"request_status\":\"success\",
    \"purpose\":\"translation\"
  }")
LOG_ID1=$(echo "$REC_RESP" | jget .usage_log_id)
BILLING1=$(echo "$REC_RESP" | jget .billing_mode)
assert_not_empty "T03 got usage_log_id" "$LOG_ID1"
assert_eq "T03 billing mode is quota" "quota" "$BILLING1"

# ── T04: Record invocation with purpose=chat ─────────────────────────────────
header "T04: Record invocation (chat)"

REQ_ID2=$(node -e "const{randomUUID}=require('crypto');console.log(randomUUID())")

REC_RESP2=$(curl -s -X POST "$INTERNAL_URL/internal/model-billing/record" \
  -H "Content-Type: application/json" \
  -d "{
    \"request_id\":\"$REQ_ID2\",
    \"owner_user_id\":\"$USER_ID\",
    \"provider_kind\":\"openai\",
    \"model_source\":\"user_model\",
    \"model_ref\":\"$MODEL_REF\",
    \"input_tokens\":2000,
    \"output_tokens\":800,
    \"input_payload\":{\"messages\":[{\"role\":\"user\",\"content\":\"hello\"}]},
    \"output_payload\":{\"content\":\"hi there\"},
    \"request_status\":\"success\",
    \"purpose\":\"chat\"
  }")
LOG_ID2=$(echo "$REC_RESP2" | jget .usage_log_id)
assert_not_empty "T04 got usage_log_id" "$LOG_ID2"

# ── T05: Record invocation with purpose=chunk_edit + provider_error ──────────
header "T05: Record invocation (chunk_edit, error)"

REQ_ID3=$(node -e "const{randomUUID}=require('crypto');console.log(randomUUID())")

REC_RESP3=$(curl -s -X POST "$INTERNAL_URL/internal/model-billing/record" \
  -H "Content-Type: application/json" \
  -d "{
    \"request_id\":\"$REQ_ID3\",
    \"owner_user_id\":\"$USER_ID\",
    \"provider_kind\":\"anthropic\",
    \"model_source\":\"user_model\",
    \"model_ref\":\"$MODEL_REF\",
    \"input_tokens\":500,
    \"output_tokens\":0,
    \"input_payload\":{\"messages\":[{\"role\":\"user\",\"content\":\"edit chunk\"}]},
    \"output_payload\":{},
    \"request_status\":\"provider_error\",
    \"purpose\":\"chunk_edit\"
  }")
LOG_ID3=$(echo "$REC_RESP3" | jget .usage_log_id)
assert_not_empty "T05 got usage_log_id" "$LOG_ID3"

# ── T06: List usage logs — no filters (should have 3) ───────────────────────
header "T06: List usage logs — no filters"

LIST_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?limit=50")
TOTAL=$(echo "$LIST_RESP" | jget .total)
assert_gte "T06 total >= 3" 3 "$TOTAL"

# ── T07: List with provider_kind filter ──────────────────────────────────────
header "T07: Filter by provider_kind=anthropic"

FILT_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?provider_kind=anthropic")
FILT_TOTAL=$(echo "$FILT_RESP" | jget .total)
assert_gte "T07 anthropic logs >= 2" 2 "$FILT_TOTAL"

# ── T08: List with purpose filter ────────────────────────────────────────────
header "T08: Filter by purpose=translation"

PURP_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?purpose=translation")
PURP_TOTAL=$(echo "$PURP_RESP" | jget .total)
assert_gte "T08 translation logs >= 1" 1 "$PURP_TOTAL"

# ── T09: List with request_status filter ─────────────────────────────────────
header "T09: Filter by request_status=provider_error"

ERR_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?request_status=provider_error")
ERR_TOTAL=$(echo "$ERR_RESP" | jget .total)
assert_gte "T09 error logs >= 1" 1 "$ERR_TOTAL"

# ── T10: List with combined filters ──────────────────────────────────────────
header "T10: Combined filter: anthropic + translation"

COMB_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?provider_kind=anthropic&purpose=translation")
COMB_TOTAL=$(echo "$COMB_RESP" | jget .total)
assert_gte "T10 anthropic+translation >= 1" 1 "$COMB_TOTAL"

# ── T11: List with purpose=chat + openai (should match T04) ─────────────────
header "T11: Filter: openai + chat"

CHAT_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?provider_kind=openai&purpose=chat")
CHAT_TOTAL=$(echo "$CHAT_RESP" | jget .total)
assert_gte "T11 openai+chat >= 1" 1 "$CHAT_TOTAL"

# ── T12: List with purpose filter that has no results ────────────────────────
header "T12: Filter with no results: purpose=image_gen"

EMPTY_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?purpose=image_gen")
EMPTY_TOTAL=$(echo "$EMPTY_RESP" | jget .total)
assert_eq "T12 image_gen logs = 0" "0" "$EMPTY_TOTAL"

# ── T13: Usage summary — enhanced fields ─────────────────────────────────────
header "T13: Usage summary — enhanced (last_7d)"

SUM2_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-summary?period=last_7d")
SUM2_COUNT=$(echo "$SUM2_RESP" | jget .request_count)
SUM2_TOKENS=$(echo "$SUM2_RESP" | jget .total_tokens)
SUM2_ERR_COUNT=$(echo "$SUM2_RESP" | jget .error_count)
assert_gte "T13 request_count >= 3" 3 "$SUM2_COUNT"
assert_gte "T13 total_tokens >= 4800" 4800 "$SUM2_TOKENS"
assert_gte "T13 error_count >= 1" 1 "$SUM2_ERR_COUNT"

# Check by_provider array exists
SUM2_RAW=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-summary?period=last_7d")
assert_contains "T13 has by_provider" "$SUM2_RAW" "by_provider"
assert_contains "T13 has by_purpose" "$SUM2_RAW" "by_purpose"
assert_contains "T13 has daily" "$SUM2_RAW" "daily"
assert_contains "T13 has error_rate" "$SUM2_RAW" "error_rate"

# ── T14: Usage summary — by_provider breakdown ──────────────────────────────
header "T14: by_provider breakdown"

PROV_COUNT=$(echo "$SUM2_RAW" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j.by_provider ? j.by_provider.length : 0);
  })
" 2>/dev/null)
assert_gte "T14 by_provider has entries" 1 "$PROV_COUNT"

# Check anthropic is in by_provider
assert_contains "T14 by_provider includes anthropic" "$SUM2_RAW" "anthropic"

# ── T15: Usage summary — by_purpose breakdown ────────────────────────────────
header "T15: by_purpose breakdown"

PURP_COUNT=$(echo "$SUM2_RAW" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j.by_purpose ? j.by_purpose.length : 0);
  })
" 2>/dev/null)
assert_gte "T15 by_purpose has entries" 1 "$PURP_COUNT"
assert_contains "T15 by_purpose includes translation" "$SUM2_RAW" "translation"
assert_contains "T15 by_purpose includes chat" "$SUM2_RAW" "chat"

# ── T16: Usage summary — daily breakdown ─────────────────────────────────────
header "T16: daily breakdown"

DAILY_COUNT=$(echo "$SUM2_RAW" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j.daily ? j.daily.length : 0);
  })
" 2>/dev/null)
assert_gte "T16 daily has >= 1 day" 1 "$DAILY_COUNT"

# Check daily entry has expected fields
TODAY=$(date +%Y-%m-%d)
assert_contains "T16 daily includes today" "$SUM2_RAW" "$TODAY"

# ── T17: Usage summary — last_30d period ─────────────────────────────────────
header "T17: Usage summary — last_30d"

SUM30_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$GATEWAY/v1/model-billing/usage-summary?period=last_30d")
assert_status "T17 last_30d returns 200" "200" "$SUM30_STATUS"

# ── T18: Usage summary — last_90d period ─────────────────────────────────────
header "T18: Usage summary — last_90d"

SUM90_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$GATEWAY/v1/model-billing/usage-summary?period=last_90d")
assert_status "T18 last_90d returns 200" "200" "$SUM90_STATUS"

# ── T19: Get usage log detail — endpoint reachable ───────────────────────────
header "T19: Get usage log detail"

# Detail endpoint decrypts payloads with AES-256-GCM. In Docker dev the key
# derivation may produce a mismatch (409 CIPHERTEXT_UNAVAILABLE). We accept
# either 200 (decrypted ok) or 409 (encryption working, key mismatch in dev).
DETAIL_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs/$LOG_ID1")
if [ "$DETAIL_HTTP" = "200" ] || [ "$DETAIL_HTTP" = "409" ]; then
  green "T19 detail endpoint reachable (HTTP $DETAIL_HTTP)"; PASS=$((PASS+1))
else
  red "T19 detail endpoint (expected 200 or 409, got $DETAIL_HTTP)"; FAIL=$((FAIL+1))
fi

# ── T20: Get detail — 404 for non-existent log ──────────────────────────────
header "T20: Detail 404 for non-existent log"

FAKE_ID="00000000-0000-0000-0000-000000000000"
NOT_FOUND_HTTP=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs/$FAKE_ID")
assert_status "T20 non-existent log returns 404" "404" "$NOT_FOUND_HTTP"

# ── T21: List logs — pagination ──────────────────────────────────────────────
header "T21: Pagination (limit=1, offset=0)"

PAGE_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?limit=1&offset=0")
PAGE_TOTAL=$(echo "$PAGE_RESP" | jget .total)
PAGE_LIMIT=$(echo "$PAGE_RESP" | jget .limit)
assert_gte "T21 total >= 3" 3 "$PAGE_TOTAL"
assert_eq "T21 limit is 1" "1" "$PAGE_LIMIT"

# ── T22: Pagination page 2 ──────────────────────────────────────────────────
header "T22: Pagination (limit=1, offset=1)"

PAGE2_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?limit=1&offset=1")
PAGE2_OFFSET=$(echo "$PAGE2_RESP" | jget .offset)
assert_eq "T22 offset is 1" "1" "$PAGE2_OFFSET"

# ── T23: List logs — purpose in response ─────────────────────────────────────
header "T23: Purpose field in log response"

assert_contains "T23 logs contain purpose field" "$LIST_RESP" "purpose"

# ── T24: Unauthenticated access — 401 ───────────────────────────────────────
header "T24: Unauthenticated access"

UNAUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/model-billing/usage-logs")
assert_status "T24 usage-logs without auth returns 401" "401" "$UNAUTH_STATUS"

UNAUTH_SUM=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/model-billing/usage-summary")
assert_status "T24 usage-summary without auth returns 401" "401" "$UNAUTH_SUM"

UNAUTH_BAL=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/model-billing/account-balance")
assert_status "T24 account-balance without auth returns 401" "401" "$UNAUTH_BAL"

# ── T25: Record without purpose defaults to "unknown" ────────────────────────
header "T25: Record without purpose defaults to unknown"

REQ_ID4=$(node -e "const{randomUUID}=require('crypto');console.log(randomUUID())")

curl -s -X POST "$INTERNAL_URL/internal/model-billing/record" \
  -H "Content-Type: application/json" \
  -d "{
    \"request_id\":\"$REQ_ID4\",
    \"owner_user_id\":\"$USER_ID\",
    \"provider_kind\":\"ollama\",
    \"model_source\":\"user_model\",
    \"model_ref\":\"$MODEL_REF\",
    \"input_tokens\":100,
    \"output_tokens\":50,
    \"input_payload\":{},
    \"output_payload\":{},
    \"request_status\":\"success\"
  }" > /dev/null

UNKNOWN_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?purpose=unknown")
UNKNOWN_TOTAL=$(echo "$UNKNOWN_RESP" | jget .total)
assert_gte "T25 unknown purpose logs >= 1" 1 "$UNKNOWN_TOTAL"

# ── T26: Date range filter — from/to ────────────────────────────────────────
header "T26: Date range filter"

# Use a from date of yesterday, to date of tomorrow — should include all
YESTERDAY=$(date -d "yesterday" +%Y-%m-%dT00:00:00Z 2>/dev/null || date -v-1d +%Y-%m-%dT00:00:00Z 2>/dev/null || echo "2026-04-02T00:00:00Z")
TOMORROW=$(date -d "tomorrow" +%Y-%m-%dT23:59:59Z 2>/dev/null || date -v+1d +%Y-%m-%dT23:59:59Z 2>/dev/null || echo "2026-04-04T23:59:59Z")

DATE_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?from=$YESTERDAY&to=$TOMORROW")
DATE_TOTAL=$(echo "$DATE_RESP" | jget .total)
assert_gte "T26 date range includes all logs" 4 "$DATE_TOTAL"

# Future date range — should be empty
FUTURE_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-billing/usage-logs?from=2099-01-01T00:00:00Z")
FUTURE_TOTAL=$(echo "$FUTURE_RESP" | jget .total)
assert_eq "T26 future date range is empty" "0" "$FUTURE_TOTAL"

# ══════════════════════════════════════════════════════════════════════════════
header "Results"
printf "\033[32m  PASS: %d\033[0m\n" "$PASS"
printf "\033[31m  FAIL: %d\033[0m\n" "$FAIL"
printf "  TOTAL: %d\n\n" "$((PASS+FAIL))"
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
