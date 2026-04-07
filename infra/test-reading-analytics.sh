#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Reading Analytics Integration Tests (TH-12)
# Usage: bash infra/test-reading-analytics.sh
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

# ── Setup ────────────────────────────────────────────────────────────────────
header "Setup: Auth + Book + Chapter"

UNAME="analytics_$(date +%s)"
EMAIL="$UNAME@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"Analytics Test\"}" > /dev/null
TOKEN=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" | jget .access_token)
assert_not_empty "Setup: got token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

BOOK_ID=$(curl -s -X POST "$GATEWAY/v1/books" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Analytics Test Book","original_language":"en"}' | jget .book_id)
assert_not_empty "Setup: created book" "$BOOK_ID"

CH_ID=$(docker compose exec -T postgres psql -U loreweave -d loreweave_book -tA -c "
  INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, sort_order, storage_key)
  VALUES ('$BOOK_ID', 'Ch1', 'ch1.txt', 'en', 'text/plain', 1, 'test/ch1.txt') RETURNING id;
" | head -1 | tr -d '[:space:]')
assert_not_empty "Setup: created chapter" "$CH_ID"

# ═══════════════════════════════════════════════════════════════════════════════
# T01-T05: Reading Progress UPSERT
# ═══════════════════════════════════════════════════════════════════════════════
header "T01-T05: Reading Progress"

# T01: First progress → creates row
T01_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH_ID/progress" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"time_spent_ms":5000,"scroll_depth":0.4}')
assert_status "T01 first progress → 204" "204" "$T01_STATUS"

# T02: List progress — 1 entry
T02_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/progress" -H "$AUTH")
T02_LEN=$(echo "$T02_RESP" | jlen .items)
T02_TIME=$(echo "$T02_RESP" | jget .items.0.time_spent_ms)
T02_DEPTH=$(echo "$T02_RESP" | jget .items.0.scroll_depth)
assert_eq "T02 progress count" "1" "$T02_LEN"
assert_eq "T02 time_spent_ms" "5000" "$T02_TIME"
assert_eq "T02 scroll_depth" "0.4" "$T02_DEPTH"

# T03: Second progress → accumulates time, keeps max depth
T03_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH_ID/progress" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"time_spent_ms":3000,"scroll_depth":0.8}')
assert_status "T03 second progress → 204" "204" "$T03_STATUS"

T03_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/progress" -H "$AUTH")
T03_TIME=$(echo "$T03_RESP" | jget .items.0.time_spent_ms)
T03_DEPTH=$(echo "$T03_RESP" | jget .items.0.scroll_depth)
T03_COUNT=$(echo "$T03_RESP" | jget .items.0.read_count)
assert_eq "T03 time accumulated" "8000" "$T03_TIME"
assert_eq "T03 scroll_depth max" "0.8" "$T03_DEPTH"
assert_eq "T03 read_count" "2" "$T03_COUNT"

# T04: Lower scroll_depth doesn't decrease
curl -s -o /dev/null -X POST "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH_ID/progress" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"time_spent_ms":1000,"scroll_depth":0.3}'
T04_DEPTH=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/progress" -H "$AUTH" | jget .items.0.scroll_depth)
assert_eq "T04 scroll_depth stays at max" "0.8" "$T04_DEPTH"

# T05: No auth → 401
T05_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH_ID/progress" \
  -H "Content-Type: application/json" \
  -d '{"time_spent_ms":1000,"scroll_depth":0.5}')
assert_status "T05 no auth → 401" "401" "$T05_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T06-T10: Book Views
# ═══════════════════════════════════════════════════════════════════════════════
header "T06-T10: Book Views"

# T06: Record authenticated view
T06_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/view" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"session_id":"test-session-1","referrer":"http://example.com"}')
assert_status "T06 auth view → 204" "204" "$T06_STATUS"

# T07: Record anonymous view (no auth)
T07_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/view" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"anon-session-1"}')
assert_status "T07 anon view → 204" "204" "$T07_STATUS"

# T08: Second anonymous view
curl -s -o /dev/null -X POST "$GATEWAY/v1/books/$BOOK_ID/view" \
  -H "Content-Type: application/json" \
  -d '{"session_id":"anon-session-2"}'

# T09: Stats
T09_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/stats" -H "$AUTH")
T09_VIEWS=$(echo "$T09_RESP" | jget .view_count)
T09_READERS=$(echo "$T09_RESP" | jget .total_readers)
assert_eq "T09 view_count is 3" "3" "$T09_VIEWS"
assert_eq "T09 total_readers is 1" "1" "$T09_READERS"

# T10: sendBeacon format (text/plain with JSON body)
T10_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH_ID/progress" \
  -H "$AUTH" -H "Content-Type: text/plain" \
  -d '{"time_spent_ms":2000,"scroll_depth":0.95}')
assert_status "T10 text/plain beacon → 204" "204" "$T10_STATUS"

T10_DEPTH=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/progress" -H "$AUTH" | jget .items.0.scroll_depth)
assert_eq "T10 scroll_depth updated to 0.95" "0.95" "$T10_DEPTH"

# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "════════════════════════════════════════════════════════════════════════"
printf "  \033[32mPassed: %d\033[0m  |  \033[31mFailed: %d\033[0m  |  Total: %d\n" "$PASS" "$FAIL" $((PASS+FAIL))
echo "════════════════════════════════════════════════════════════════════════"
[ "$FAIL" -gt 0 ] && exit 1 || true
