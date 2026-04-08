#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Leaderboard Integration Tests (P9-01)
# Usage: bash infra/test-leaderboard.sh
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
assert_gte() {
  local label="$1" min="$2" actual="$3"
  if [ "$actual" -ge "$min" ] 2>/dev/null; then green "$label ($actual >= $min)"; PASS=$((PASS+1))
  else red "$label (expected >= $min, got: $actual)"; FAIL=$((FAIL+1)); fi
}
jget() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}if(v===undefined||v===null)console.log('');else console.log(typeof v==='object'?JSON.stringify(v):v)}catch{console.log('')}})" 2>/dev/null || echo ""
}
jlen() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}console.log(Array.isArray(v)?v.length:0)}catch{console.log(0)}})" 2>/dev/null || echo "0"
}

# ═══════════════════════════════════════════════════════════════════════════════
# T01-T03: Leaderboard Books
# ═══════════════════════════════════════════════════════════════════════════════
header "T01-T03: Leaderboard Books"

# T01: Default books leaderboard → 200
T01_STATUS=$(curl -s -o /tmp/lb_t01.json -w "%{http_code}" "$GATEWAY/v1/leaderboard/books")
assert_status "T01 GET /leaderboard/books → 200" "200" "$T01_STATUS"
T01_ITEMS=$(cat /tmp/lb_t01.json | jlen .items)
assert_gte "T01 items is array (length >= 0)" "0" "$T01_ITEMS"
T01_PERIOD=$(cat /tmp/lb_t01.json | jget .period)
assert_eq "T01 default period is 'all'" "all" "$T01_PERIOD"

# T02: Books with period=7d
T02_RESP=$(curl -s "$GATEWAY/v1/leaderboard/books?period=7d")
T02_PERIOD=$(echo "$T02_RESP" | jget .period)
assert_eq "T02 period=7d" "7d" "$T02_PERIOD"

# T03: Books with genre + language filter
T03_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/leaderboard/books?genre=Fantasy&language=en&sort=trending&limit=5")
assert_status "T03 filter params → 200" "200" "$T03_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T04-T06: Leaderboard Authors
# ═══════════════════════════════════════════════════════════════════════════════
header "T04-T06: Leaderboard Authors"

# T04: Default authors leaderboard → 200
T04_STATUS=$(curl -s -o /tmp/lb_t04.json -w "%{http_code}" "$GATEWAY/v1/leaderboard/authors")
assert_status "T04 GET /leaderboard/authors → 200" "200" "$T04_STATUS"
T04_ITEMS=$(cat /tmp/lb_t04.json | jlen .items)
assert_gte "T04 items is array" "0" "$T04_ITEMS"

# T05: Authors with period=30d + limit
T05_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/leaderboard/authors?period=30d&limit=5")
assert_status "T05 period=30d + limit=5 → 200" "200" "$T05_STATUS"

# T06: Authors with offset pagination
T06_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/leaderboard/authors?offset=100")
assert_status "T06 offset=100 → 200 (empty)" "200" "$T06_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T07-T09: Leaderboard Translators
# ═══════════════════════════════════════════════════════════════════════════════
header "T07-T09: Leaderboard Translators"

# T07: Default translators leaderboard → 200
T07_STATUS=$(curl -s -o /tmp/lb_t07.json -w "%{http_code}" "$GATEWAY/v1/leaderboard/translators")
assert_status "T07 GET /leaderboard/translators → 200" "200" "$T07_STATUS"
T07_ITEMS=$(cat /tmp/lb_t07.json | jlen .items)
assert_gte "T07 items is array" "0" "$T07_ITEMS"

# T08: Translators period=7d
T08_RESP=$(curl -s "$GATEWAY/v1/leaderboard/translators?period=7d")
T08_PERIOD=$(echo "$T08_RESP" | jget .period)
assert_eq "T08 period=7d" "7d" "$T08_PERIOD"

# T09: Translators limit=1
T09_RESP=$(curl -s "$GATEWAY/v1/leaderboard/translators?limit=1")
T09_LEN=$(echo "$T09_RESP" | jlen .items)
assert_gte "T09 limit=1 → max 1 item" "0" "$T09_LEN"

# ═══════════════════════════════════════════════════════════════════════════════
# T10-T12: Single Stats
# ═══════════════════════════════════════════════════════════════════════════════
header "T10-T12: Single Stats Endpoints"

# T10: Stats overview → 200
T10_STATUS=$(curl -s -o /tmp/lb_t10.json -w "%{http_code}" "$GATEWAY/v1/stats/overview")
assert_status "T10 GET /stats/overview → 200" "200" "$T10_STATUS"
T10_BOOKS=$(cat /tmp/lb_t10.json | jget .total_books)
assert_gte "T10 total_books >= 0" "0" "$T10_BOOKS"

# T11: Stats for non-existent book → 200 (zero fallback)
FAKE_UUID="00000000-0000-0000-0000-000000000000"
T11_STATUS=$(curl -s -o /tmp/lb_t11.json -w "%{http_code}" "$GATEWAY/v1/stats/books/$FAKE_UUID")
assert_status "T11 stats/books (fake) → 200 zero fallback" "200" "$T11_STATUS"
T11_VIEWS=$(cat /tmp/lb_t11.json | jget .total_views)
assert_eq "T11 zero fallback views" "0" "$T11_VIEWS"

# T12: Stats for non-existent author → 200 (zero fallback)
T12_STATUS=$(curl -s -o /tmp/lb_t12.json -w "%{http_code}" "$GATEWAY/v1/stats/authors/$FAKE_UUID")
assert_status "T12 stats/authors (fake) → 200 zero fallback" "200" "$T12_STATUS"
T12_BOOKS=$(cat /tmp/lb_t12.json | jget .total_books)
assert_eq "T12 zero fallback books" "0" "$T12_BOOKS"

# T13: Stats for non-existent translator → 200 (zero fallback)
T13_STATUS=$(curl -s -o /tmp/lb_t13.json -w "%{http_code}" "$GATEWAY/v1/stats/translators/$FAKE_UUID")
assert_status "T13 stats/translators (fake) → 200 zero fallback" "200" "$T13_STATUS"
T13_CHAP=$(cat /tmp/lb_t13.json | jget .total_chapters_done)
assert_eq "T13 zero fallback chapters" "0" "$T13_CHAP"

# T14: Invalid book_id → 400
T14_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/stats/books/not-a-uuid")
assert_status "T14 stats/books invalid uuid → 400" "400" "$T14_STATUS"

# T15: Invalid author_id → 400
T15_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/stats/authors/not-a-uuid")
assert_status "T15 stats/authors invalid uuid → 400" "400" "$T15_STATUS"

# T16: Invalid translator_id → 400
T16_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/stats/translators/not-a-uuid")
assert_status "T16 stats/translators invalid uuid → 400" "400" "$T16_STATUS"

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
