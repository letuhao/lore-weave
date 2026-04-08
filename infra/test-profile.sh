#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — User Profile Integration Tests (P9-02)
# Usage: bash infra/test-profile.sh
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
# Setup: Create two test users
# ═══════════════════════════════════════════════════════════════════════════════
header "Setup: Create Users"

TS=$(date +%s)
EMAIL_A="proftest_a_${TS}@test.com"
EMAIL_B="proftest_b_${TS}@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_A\",\"password\":\"Test1234!\",\"display_name\":\"Alice Profile\"}" > /dev/null
TOKEN_A=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_A\",\"password\":\"Test1234!\"}" | jget .access_token)
USER_A=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_A\",\"password\":\"Test1234!\"}" | jget .user_profile.user_id)
assert_not_empty "Setup: user A token" "$TOKEN_A"
assert_not_empty "Setup: user A id" "$USER_A"
AUTH_A="Authorization: Bearer $TOKEN_A"

curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\",\"display_name\":\"Bob Profile\"}" > /dev/null
TOKEN_B=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\"}" | jget .access_token)
USER_B=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL_B\",\"password\":\"Test1234!\"}" | jget .user_profile.user_id)
assert_not_empty "Setup: user B token" "$TOKEN_B"
assert_not_empty "Setup: user B id" "$USER_B"
AUTH_B="Authorization: Bearer $TOKEN_B"

# ═══════════════════════════════════════════════════════════════════════════════
# T01-T04: Profile Bio & Languages (PATCH + GET)
# ═══════════════════════════════════════════════════════════════════════════════
header "T01-T04: Bio & Languages"

# T01: Update bio + languages
T01_STATUS=$(curl -s -o /tmp/prof_t01.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/account/profile" -H "$AUTH_A" -H "Content-Type: application/json" \
  -d '{"bio":"Fantasy writer and translator","languages":["en","ja","vi"]}')
assert_status "T01 PATCH profile bio+langs → 200" "200" "$T01_STATUS"
T01_BIO=$(cat /tmp/prof_t01.json | jget .bio)
assert_eq "T01 bio saved" "Fantasy writer and translator" "$T01_BIO"
T01_LANGS=$(cat /tmp/prof_t01.json | jget .languages)
assert_eq "T01 languages saved" '["en","ja","vi"]' "$T01_LANGS"

# T02: Bio too long (>1000 chars) → 400
LONG_BIO=$(python3 -c "print('x' * 1001)" 2>/dev/null || node -e "console.log('x'.repeat(1001))")
T02_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/account/profile" -H "$AUTH_A" -H "Content-Type: application/json" \
  -d "{\"bio\":\"$LONG_BIO\"}")
assert_status "T02 bio > 1000 chars → 400" "400" "$T02_STATUS"

# T03: Languages > 20 items → 400
MANY_LANGS=$(node -e "console.log(JSON.stringify(Array.from({length:21},(_,i)=>'lang'+i)))")
T03_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/account/profile" -H "$AUTH_A" -H "Content-Type: application/json" \
  -d "{\"languages\":$MANY_LANGS}")
assert_status "T03 languages > 20 items → 400" "400" "$T03_STATUS"

# T04: GET profile includes bio + languages
T04_RESP=$(curl -s "$GATEWAY/v1/account/profile" -H "$AUTH_A")
T04_BIO=$(echo "$T04_RESP" | jget .bio)
T04_LANGS=$(echo "$T04_RESP" | jget .languages)
assert_eq "T04 GET profile has bio" "Fantasy writer and translator" "$T04_BIO"
assert_eq "T04 GET profile has languages" '["en","ja","vi"]' "$T04_LANGS"

# ═══════════════════════════════════════════════════════════════════════════════
# T05-T08: Public Profile
# ═══════════════════════════════════════════════════════════════════════════════
header "T05-T08: Public Profile"

# T05: GET public profile without auth → 200
T05_STATUS=$(curl -s -o /tmp/prof_t05.json -w "%{http_code}" "$GATEWAY/v1/users/$USER_A")
assert_status "T05 GET /users/{id} no auth → 200" "200" "$T05_STATUS"
T05_NAME=$(cat /tmp/prof_t05.json | jget .display_name)
assert_eq "T05 display_name" "Alice Profile" "$T05_NAME"
T05_BIO=$(cat /tmp/prof_t05.json | jget .bio)
assert_eq "T05 bio visible" "Fantasy writer and translator" "$T05_BIO"
T05_FOLLOWING=$(cat /tmp/prof_t05.json | jget .is_following)
assert_eq "T05 is_following=false (no auth)" "false" "$T05_FOLLOWING"

# T06: GET public profile with auth → shows is_following
T06_RESP=$(curl -s "$GATEWAY/v1/users/$USER_A" -H "$AUTH_B")
T06_FOLLOWING=$(echo "$T06_RESP" | jget .is_following)
assert_eq "T06 is_following=false (not yet)" "false" "$T06_FOLLOWING"

# T07: Non-existent user → 404
T07_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/users/00000000-0000-0000-0000-000000000000")
assert_status "T07 non-existent user → 404" "404" "$T07_STATUS"

# T08: Invalid UUID → 400
T08_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/users/not-a-uuid")
assert_status "T08 invalid uuid → 400" "400" "$T08_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T09-T18: Follow System
# ═══════════════════════════════════════════════════════════════════════════════
header "T09-T18: Follow System"

# T09: B follows A → 204
T09_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/users/$USER_A/follow" -H "$AUTH_B")
assert_status "T09 B follows A → 204" "204" "$T09_STATUS"

# T10: is_following now true
T10_RESP=$(curl -s "$GATEWAY/v1/users/$USER_A" -H "$AUTH_B")
T10_FOLLOWING=$(echo "$T10_RESP" | jget .is_following)
T10_FOLLOWERS=$(echo "$T10_RESP" | jget .follower_count)
assert_eq "T10 is_following=true" "true" "$T10_FOLLOWING"
assert_eq "T10 follower_count=1" "1" "$T10_FOLLOWERS"

# T11: Duplicate follow → 204 (idempotent)
T11_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/users/$USER_A/follow" -H "$AUTH_B")
assert_status "T11 duplicate follow → 204 (idempotent)" "204" "$T11_STATUS"

# T12: Follower count still 1 after duplicate
T12_RESP=$(curl -s "$GATEWAY/v1/users/$USER_A" -H "$AUTH_B")
T12_FOLLOWERS=$(echo "$T12_RESP" | jget .follower_count)
assert_eq "T12 follower_count still 1" "1" "$T12_FOLLOWERS"

# T13: Self-follow → 400
T13_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/users/$USER_A/follow" -H "$AUTH_A")
assert_status "T13 self-follow → 400" "400" "$T13_STATUS"

# T14: Follow without auth → 401
T14_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/users/$USER_A/follow")
assert_status "T14 follow without auth → 401" "401" "$T14_STATUS"

# T15: List followers of A
T15_RESP=$(curl -s "$GATEWAY/v1/users/$USER_A/followers")
T15_LEN=$(echo "$T15_RESP" | jlen .items)
T15_TOTAL=$(echo "$T15_RESP" | jget .total)
T15_UID=$(echo "$T15_RESP" | jget .items.0.user_id)
assert_eq "T15 followers count" "1" "$T15_LEN"
assert_eq "T15 followers total" "1" "$T15_TOTAL"
assert_eq "T15 follower is B" "$USER_B" "$T15_UID"

# T16: List following of B
T16_RESP=$(curl -s "$GATEWAY/v1/users/$USER_B/following")
T16_LEN=$(echo "$T16_RESP" | jlen .items)
T16_UID=$(echo "$T16_RESP" | jget .items.0.user_id)
assert_eq "T16 following count" "1" "$T16_LEN"
assert_eq "T16 following is A" "$USER_A" "$T16_UID"

# T17: B unfollows A → 204
T17_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/users/$USER_A/follow" -H "$AUTH_B")
assert_status "T17 B unfollows A → 204" "204" "$T17_STATUS"

# T18: Follower count back to 0
T18_RESP=$(curl -s "$GATEWAY/v1/users/$USER_A" -H "$AUTH_B")
T18_FOLLOWING=$(echo "$T18_RESP" | jget .is_following)
T18_FOLLOWERS=$(echo "$T18_RESP" | jget .follower_count)
assert_eq "T18 is_following=false" "false" "$T18_FOLLOWING"
assert_eq "T18 follower_count=0" "0" "$T18_FOLLOWERS"

# ═══════════════════════════════════════════════════════════════════════════════
# T19-T25: Favorites System
# ═══════════════════════════════════════════════════════════════════════════════
header "T19-T25: Favorites System"

# Setup: Create a book as user A
BOOK_ID=$(curl -s -X POST "$GATEWAY/v1/books" -H "$AUTH_A" -H "Content-Type: application/json" \
  -d '{"title":"Fav Test Book","original_language":"en"}' | jget .book_id)
assert_not_empty "Setup: created book" "$BOOK_ID"

# T19: Check favorite → false
T19_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/favorite" -H "$AUTH_B")
T19_FAV=$(echo "$T19_RESP" | jget .is_favorited)
assert_eq "T19 not favorited" "false" "$T19_FAV"

# T20: Add favorite → 204
T20_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/favorite" -H "$AUTH_B")
assert_status "T20 add favorite → 204" "204" "$T20_STATUS"

# T21: Check favorite → true
T21_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/favorite" -H "$AUTH_B")
T21_FAV=$(echo "$T21_RESP" | jget .is_favorited)
assert_eq "T21 now favorited" "true" "$T21_FAV"

# T22: Duplicate favorite → 204 (idempotent)
T22_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/books/$BOOK_ID/favorite" -H "$AUTH_B")
assert_status "T22 duplicate favorite → 204" "204" "$T22_STATUS"

# T23: List favorites → includes the book
T23_RESP=$(curl -s "$GATEWAY/v1/books/favorites" -H "$AUTH_B")
T23_LEN=$(echo "$T23_RESP" | jlen .items)
T23_BID=$(echo "$T23_RESP" | jget .items.0.book_id)
assert_eq "T23 favorites count" "1" "$T23_LEN"
assert_eq "T23 favorite book_id" "$BOOK_ID" "$T23_BID"

# T24: Remove favorite → 204
T24_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/books/$BOOK_ID/favorite" -H "$AUTH_B")
assert_status "T24 remove favorite → 204" "204" "$T24_STATUS"

# T25: List favorites → empty
T25_RESP=$(curl -s "$GATEWAY/v1/books/favorites" -H "$AUTH_B")
T25_LEN=$(echo "$T25_RESP" | jlen .items)
assert_eq "T25 favorites now empty" "0" "$T25_LEN"

# ═══════════════════════════════════════════════════════════════════════════════
# T26-T28: Catalog Author Filter
# ═══════════════════════════════════════════════════════════════════════════════
header "T26-T28: Catalog Author Filter"

# T26: Catalog books with valid author → 200
T26_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books?author=$USER_A")
assert_status "T26 catalog ?author=valid → 200" "200" "$T26_STATUS"

# T27: Catalog books with invalid author → 400
T27_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books?author=not-a-uuid")
assert_status "T27 catalog ?author=invalid → 400" "400" "$T27_STATUS"

# T28: Catalog books without author → 200 (no filter)
T28_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books")
assert_status "T28 catalog no author → 200" "200" "$T28_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T29-T30: Translator Stats by User
# ═══════════════════════════════════════════════════════════════════════════════
header "T29-T30: Translator Stats by User"

# T29: Translator stats for user → 200 (zero fallback)
T29_STATUS=$(curl -s -o /tmp/prof_t29.json -w "%{http_code}" "$GATEWAY/v1/stats/translators/$USER_A")
assert_status "T29 stats/translators/{id} → 200" "200" "$T29_STATUS"
T29_CHAP=$(cat /tmp/prof_t29.json | jget .total_chapters_done)
assert_eq "T29 zero fallback chapters" "0" "$T29_CHAP"

# T30: Invalid user_id → 400
T30_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/stats/translators/not-a-uuid")
assert_status "T30 invalid uuid → 400" "400" "$T30_STATUS"

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
