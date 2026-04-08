#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Notification Service Integration Tests (P9-03)
# Usage: bash infra/test-notifications.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
NOTIF_DIRECT="http://localhost:8215"
INTERNAL_TOKEN="dev_internal_token"
PASS=0
FAIL=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then green "$label"; PASS=$((PASS+1))
  else red "$label (expected: $expected, got: $actual)"; FAIL=$((FAIL+1)); fi
}
assert_not_empty() {
  local label="$1" value="$2"
  if [ -n "$value" ] && [ "$value" != "null" ]; then green "$label"; PASS=$((PASS+1))
  else red "$label (was empty or null)"; FAIL=$((FAIL+1)); fi
}
assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then green "$label (HTTP $actual)"; PASS=$((PASS+1))
  else red "$label (expected HTTP $expected, got $actual)"; FAIL=$((FAIL+1)); fi
}
jget() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}if(v===undefined||v===null)console.log('');else console.log(typeof v==='object'?JSON.stringify(v):v)}catch{console.log('')}})" 2>/dev/null || echo ""
}
jlen() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}console.log(Array.isArray(v)?v.length:0)}catch{console.log(0)}})" 2>/dev/null || echo "0"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Setup
# ═══════════════════════════════════════════════════════════════════════════════
header "Setup: Health + Auth"

# T01: Health check (direct)
T01_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$NOTIF_DIRECT/health")
assert_status "T01 notification-service health → 200" "200" "$T01_STATUS"

# T02: Ready check
T02_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$NOTIF_DIRECT/health/ready")
assert_status "T02 notification-service ready → 200" "200" "$T02_STATUS"

# Create test user
TS=$(date +%s)
EMAIL="notif_test_${TS}@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"Notif Tester\"}" > /dev/null
LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
USER_ID=$(echo "$LOGIN_RESP" | jget .user_profile.user_id)
assert_not_empty "Setup: got token" "$TOKEN"
assert_not_empty "Setup: got user_id" "$USER_ID"
AUTH="Authorization: Bearer $TOKEN"

# ═══════════════════════════════════════════════════════════════════════════════
# T03-T06: Internal Create
# ═══════════════════════════════════════════════════════════════════════════════
header "T03-T06: Internal Create Notification"

# T03: Create single notification
T03_STATUS=$(curl -s -o /tmp/notif_t03.json -w "%{http_code}" -X POST \
  "$NOTIF_DIRECT/internal/notifications" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_TOKEN" \
  -d "{\"user_id\":\"$USER_ID\",\"category\":\"translation\",\"title\":\"Translation complete\",\"body\":\"5 chapters done\",\"metadata\":{\"job_id\":\"test-job-1\"}}")
assert_status "T03 internal create → 201" "201" "$T03_STATUS"
NOTIF_ID_1=$(cat /tmp/notif_t03.json | jget .id)
assert_not_empty "T03 got notification id" "$NOTIF_ID_1"

# T04: Create without auth → 401
T04_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$NOTIF_DIRECT/internal/notifications" \
  -H "Content-Type: application/json" \
  -d "{\"user_id\":\"$USER_ID\",\"category\":\"system\",\"title\":\"test\"}")
assert_status "T04 internal create without token → 401" "401" "$T04_STATUS"

# T05: Create missing title → 400
T05_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$NOTIF_DIRECT/internal/notifications" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_TOKEN" \
  -d "{\"user_id\":\"$USER_ID\",\"category\":\"system\"}")
assert_status "T05 missing title → 400" "400" "$T05_STATUS"

# T06: Batch create
T06_STATUS=$(curl -s -o /tmp/notif_t06.json -w "%{http_code}" -X POST \
  "$NOTIF_DIRECT/internal/notifications/batch" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_TOKEN" \
  -d "{\"notifications\":[{\"user_id\":\"$USER_ID\",\"category\":\"social\",\"title\":\"New follower\"},{\"user_id\":\"$USER_ID\",\"category\":\"system\",\"title\":\"Welcome!\"}]}")
assert_status "T06 batch create → 201" "201" "$T06_STATUS"
T06_CREATED=$(cat /tmp/notif_t06.json | jget .created)
assert_eq "T06 batch created 2" "2" "$T06_CREATED"

# ═══════════════════════════════════════════════════════════════════════════════
# T07-T12: Public API (via Gateway)
# ═══════════════════════════════════════════════════════════════════════════════
header "T07-T12: Public API"

# T07: Unread count
T07_RESP=$(curl -s "$GATEWAY/v1/notifications/unread-count" -H "$AUTH")
T07_COUNT=$(echo "$T07_RESP" | jget .count)
assert_eq "T07 unread count = 3" "3" "$T07_COUNT"

# T08: List all
T08_RESP=$(curl -s "$GATEWAY/v1/notifications" -H "$AUTH")
T08_LEN=$(echo "$T08_RESP" | jlen .items)
T08_TOTAL=$(echo "$T08_RESP" | jget .total)
assert_eq "T08 items length = 3" "3" "$T08_LEN"
assert_eq "T08 total = 3" "3" "$T08_TOTAL"

# T09: Filter by category
T09_RESP=$(curl -s "$GATEWAY/v1/notifications?category=translation" -H "$AUTH")
T09_LEN=$(echo "$T09_RESP" | jlen .items)
assert_eq "T09 translation category = 1" "1" "$T09_LEN"

# T10: List without auth → 401
T10_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/notifications")
assert_status "T10 list without auth → 401" "401" "$T10_STATUS"

# T11: Mark single read
T11_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/notifications/$NOTIF_ID_1/read" -H "$AUTH")
assert_status "T11 mark read → 204" "204" "$T11_STATUS"

# T12: Unread count after mark read
T12_RESP=$(curl -s "$GATEWAY/v1/notifications/unread-count" -H "$AUTH")
T12_COUNT=$(echo "$T12_RESP" | jget .count)
assert_eq "T12 unread count = 2" "2" "$T12_COUNT"

# ═══════════════════════════════════════════════════════════════════════════════
# T13-T17: Mark All Read + Delete
# ═══════════════════════════════════════════════════════════════════════════════
header "T13-T17: Mark All Read + Delete"

# T13: Mark all read
T13_STATUS=$(curl -s -o /tmp/notif_t13.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/notifications/read-all" -H "$AUTH")
assert_status "T13 mark all read → 200" "200" "$T13_STATUS"
T13_MARKED=$(cat /tmp/notif_t13.json | jget .marked)
assert_eq "T13 marked 2 remaining" "2" "$T13_MARKED"

# T14: Unread count = 0
T14_RESP=$(curl -s "$GATEWAY/v1/notifications/unread-count" -H "$AUTH")
T14_COUNT=$(echo "$T14_RESP" | jget .count)
assert_eq "T14 unread count = 0" "0" "$T14_COUNT"

# T15: Delete notification
T15_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/notifications/$NOTIF_ID_1" -H "$AUTH")
assert_status "T15 delete → 204" "204" "$T15_STATUS"

# T16: Total after delete = 2
T16_RESP=$(curl -s "$GATEWAY/v1/notifications" -H "$AUTH")
T16_TOTAL=$(echo "$T16_RESP" | jget .total)
assert_eq "T16 total after delete = 2" "2" "$T16_TOTAL"

# T17: Delete non-existent → 404
T17_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/notifications/00000000-0000-0000-0000-000000000000" -H "$AUTH")
assert_status "T17 delete non-existent → 404" "404" "$T17_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T18-T20: Validation
# ═══════════════════════════════════════════════════════════════════════════════
header "T18-T20: Validation"

# T18: Mark read invalid UUID → 400
T18_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/notifications/not-a-uuid/read" -H "$AUTH")
assert_status "T18 mark read invalid id → 400" "400" "$T18_STATUS"

# T19: Delete invalid UUID → 400
T19_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/notifications/not-a-uuid" -H "$AUTH")
assert_status "T19 delete invalid id → 400" "400" "$T19_STATUS"

# T20: Unread-only filter
curl -s -X POST "$NOTIF_DIRECT/internal/notifications" \
  -H "Content-Type: application/json" \
  -H "X-Internal-Token: $INTERNAL_TOKEN" \
  -d "{\"user_id\":\"$USER_ID\",\"category\":\"system\",\"title\":\"Unread test\"}" > /dev/null
T20_RESP=$(curl -s "$GATEWAY/v1/notifications?unread=true" -H "$AUTH")
T20_LEN=$(echo "$T20_RESP" | jlen .items)
assert_eq "T20 unread-only filter = 1" "1" "$T20_LEN"

# ═══════════════════════════════════════════════════════════════════════════════
# T21-T22: Follow Notification Producer
# ═══════════════════════════════════════════════════════════════════════════════
header "T21-T22: Follow Notification Producer"

# Create second user
EMAIL_B="notif_b_${TS}@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\",\"display_name\":\"Follower Bob\"}" > /dev/null
TOKEN_B=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\"}" | jget .access_token)
assert_not_empty "Setup: user B token" "$TOKEN_B"

# T21: B follows A → should create notification for A
curl -s -o /dev/null -X POST "$GATEWAY/v1/users/$USER_ID/follow" \
  -H "Authorization: Bearer $TOKEN_B"
# Wait for fire-and-forget to complete
sleep 1
T21_RESP=$(curl -s "$GATEWAY/v1/notifications?category=social" -H "$AUTH")
T21_LEN=$(echo "$T21_RESP" | jlen .items)
# Should have at least 1 social notification (the follow from batch + the new follow)
T21_HAS=$(echo "$T21_RESP" | jget .items.0.title)
assert_not_empty "T21 follow created social notification" "$T21_HAS"

# T22: Check the notification title contains follower name
T22_TITLE=$(echo "$T21_RESP" | jget .items.0.title)
echo "  → Notification title: $T22_TITLE"
T22_HAS_FOLLOW=$(echo "$T22_TITLE" | grep -c "follow" || true)
if [ "$T22_HAS_FOLLOW" -ge "1" ]; then green "T22 title contains 'follow'"; PASS=$((PASS+1))
else red "T22 title should contain 'follow' (got: $T22_TITLE)"; FAIL=$((FAIL+1)); fi

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
header "Summary"
TOTAL=$((PASS + FAIL))
printf "Passed: %d / %d\n" "$PASS" "$TOTAL"
if [ "$FAIL" -gt 0 ]; then
  printf "\033[31mFailed: %d\033[0m\n" "$FAIL"
  exit 1
else
  printf "\033[32mAll %d tests passed!\033[0m\n" "$TOTAL"
fi
