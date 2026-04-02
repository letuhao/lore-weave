#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Sharing Service Integration Test
#
# Tests visibility CRUD, unlisted token lifecycle, and access guards.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-sharing.sh
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

assert_empty_or_null() {
  local label="$1" value="$2"
  if [ -z "$value" ] || [ "$value" = "null" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected empty/null, got: $value)"; FAIL=$((FAIL+1))
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

# JSON field extractor using node
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

# ── Setup: Auth + Book ────────────────────────────────────────────────────────
header "Setup: Authenticate + Create book"

UNAME="sharetest_$(date +%s)"
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

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Sharing Test Book","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Created book" "$BOOK_ID"

# ── T01: Default visibility is private ────────────────────────────────────────
header "T01: Default visibility"

GET_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/sharing/books/$BOOK_ID")
VIS=$(echo "$GET_RESP" | jget .visibility)
TKN=$(echo "$GET_RESP" | jget .unlisted_access_token)
assert_eq "T01 default visibility is private" "private" "$VIS"
assert_empty_or_null "T01 no unlisted token" "$TKN"

# ── T02: Change to unlisted ──────────────────────────────────────────────────
header "T02: Set unlisted"

PATCH_RESP=$(curl -s -X PATCH "$GATEWAY/v1/sharing/books/$BOOK_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"visibility":"unlisted"}')
VIS=$(echo "$PATCH_RESP" | jget .visibility)
TKN=$(echo "$PATCH_RESP" | jget .unlisted_access_token)
assert_eq "T02 visibility is unlisted" "unlisted" "$VIS"
assert_not_empty "T02 unlisted token generated" "$TKN"

# Save token for later tests
UNLISTED_TOKEN="$TKN"

# ── T03: Access unlisted book via token ──────────────────────────────────────
header "T03: Access unlisted book (no auth)"

UNLISTED_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/sharing/unlisted/$UNLISTED_TOKEN")
assert_status "T03 unlisted access 200" "200" "$UNLISTED_STATUS"

UNLISTED_BOOK=$(curl -s "$GATEWAY/v1/sharing/unlisted/$UNLISTED_TOKEN")
UNLISTED_TITLE=$(echo "$UNLISTED_BOOK" | jget .title)
assert_eq "T03 unlisted book title" "Sharing Test Book" "$UNLISTED_TITLE"

# ── T04: Rotate token ───────────────────────────────────────────────────────
header "T04: Rotate unlisted token"

ROTATE_RESP=$(curl -s -X PATCH "$GATEWAY/v1/sharing/books/$BOOK_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"visibility":"unlisted","rotate_unlisted_token":true}')
NEW_TKN=$(echo "$ROTATE_RESP" | jget .unlisted_access_token)
assert_not_empty "T04 new token generated" "$NEW_TKN"

# Old token should no longer work
OLD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/sharing/unlisted/$UNLISTED_TOKEN")
assert_status "T04 old token rejected" "404" "$OLD_STATUS"

# New token works
NEW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/sharing/unlisted/$NEW_TKN")
assert_status "T04 new token works" "200" "$NEW_STATUS"

# ── T05: Change to public ───────────────────────────────────────────────────
header "T05: Set public"

PUB_RESP=$(curl -s -X PATCH "$GATEWAY/v1/sharing/books/$BOOK_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"visibility":"public"}')
VIS=$(echo "$PUB_RESP" | jget .visibility)
TKN=$(echo "$PUB_RESP" | jget .unlisted_access_token)
assert_eq "T05 visibility is public" "public" "$VIS"
assert_empty_or_null "T05 token cleared on public" "$TKN"

# ── T06: Public book in catalog ──────────────────────────────────────────────
header "T06: Public catalog"

CATALOG_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books/$BOOK_ID")
assert_status "T06 book in catalog" "200" "$CATALOG_STATUS"

# ── T07: Change back to private ─────────────────────────────────────────────
header "T07: Set private"

PRIV_RESP=$(curl -s -X PATCH "$GATEWAY/v1/sharing/books/$BOOK_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"visibility":"private"}')
VIS=$(echo "$PRIV_RESP" | jget .visibility)
assert_eq "T07 visibility is private" "private" "$VIS"

# Rotated token should no longer work
DEAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/sharing/unlisted/$NEW_TKN")
assert_status "T07 unlisted token dead after private" "404" "$DEAD_STATUS"

# ── T08: Auth guard — no token ───────────────────────────────────────────────
header "T08: Auth guard"

NOAUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/sharing/books/$BOOK_ID")
if [ "$NOAUTH_STATUS" = "401" ] || [ "$NOAUTH_STATUS" = "403" ]; then
  green "T08 no-token rejected (HTTP $NOAUTH_STATUS)"; PASS=$((PASS+1))
else
  red "T08 no-token should be 401/403 (got $NOAUTH_STATUS)"; FAIL=$((FAIL+1))
fi

# ── T09: 404 on unknown book ────────────────────────────────────────────────
header "T09: 404 on unknown book"

UNKNOWN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "$AUTH" "$GATEWAY/v1/sharing/books/00000000-0000-0000-0000-000000000099")
assert_status "T09 unknown book 404" "404" "$UNKNOWN_STATUS"

# ── T10: Invalid token 404 ──────────────────────────────────────────────────
header "T10: Invalid unlisted token"

BOGUS_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/sharing/unlisted/bogus_token_12345")
assert_status "T10 bogus token 404" "404" "$BOGUS_STATUS"

# ── Cleanup ──────────────────────────────────────────────────────────────────
header "Cleanup"

CLEAN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE -H "$AUTH" "$GATEWAY/v1/books/$BOOK_ID")
if [ "$CLEAN_STATUS" = "204" ] || [ "$CLEAN_STATUS" = "200" ]; then
  green "Cleanup: book deleted"
else
  # Book might use trash lifecycle — just note it
  green "Cleanup: book trash response ($CLEAN_STATUS)"
fi

# ── Summary ──────────────────────────────────────────────────────────────────
header "Summary"
TOTAL=$((PASS + FAIL))
printf "  Pass: %d / %d\n" "$PASS" "$TOTAL"
if [ "$FAIL" -gt 0 ]; then
  printf "  \033[31mFail: %d\033[0m\n" "$FAIL"
  exit 1
else
  printf "  \033[32mAll tests passed!\033[0m\n"
fi
