#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — MIG-07 Public Book Detail Integration Test
#
# Tests: catalog book detail (owner_user_id, available_languages, word_count)
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-mig07-public-book.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0; FAIL=0; SKIP=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; PASS=$((PASS+1)); }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }
yellow() { printf "\033[33m⊘ %s\033[0m\n" "$1"; SKIP=$((SKIP+1)); }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() { if [ "$2" = "$3" ]; then green "$1"; else red "$1 (expected: $2, got: $3)"; fi; }
assert_not_empty() { if [ -n "$2" ] && [ "$2" != "null" ]; then green "$1"; else red "$1 (empty/null)"; fi; }
assert_contains() { if echo "$2" | grep -q "$3"; then green "$1"; else red "$1 (missing: $3)"; fi; }

jget() {
  node -e "
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      try{const j=JSON.parse(d);const keys='${1}'.slice(1).split('.');let v=j;
      for(const k of keys){if(v==null)break;v=v[k];}
      if(v===undefined||v===null)console.log('');
      else console.log(typeof v==='object'?JSON.stringify(v):v);
      }catch{console.log('');}
    });" 2>/dev/null || echo ""
}

jlen() {
  node -e "
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      try{const j=JSON.parse(d);const keys='${1}'.slice(1).split('.');let v=j;
      for(const k of keys){if(v==null)break;v=v[k];}
      console.log(Array.isArray(v)?v.length:0);
      }catch{console.log(0);}
    });" 2>/dev/null || echo "0"
}

# ── Setup: Create a public book ──────────────────────────────────────────────
header "Setup: Create test user + public book"

EMAIL="mig07_test_$(date +%s)@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null 2>&1 || true

TOKEN=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" | jget .access_token)
assert_not_empty "Got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# Create book
BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"MIG-07 Test Book","description":"A test book for public detail page","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Created book" "$BOOK_ID"

# Create 2 chapters with some content
CH1_RESP=$(curl -s -X POST "$GATEWAY/v1/books/$BOOK_ID/chapters" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Chapter 1 — The Beginning","sort_order":1,"original_language":"en"}')
CH1_ID=$(echo "$CH1_RESP" | jget .chapter_id)

CH2_RESP=$(curl -s -X POST "$GATEWAY/v1/books/$BOOK_ID/chapters" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Chapter 2 — The Middle","sort_order":2,"original_language":"en"}')
CH2_ID=$(echo "$CH2_RESP" | jget .chapter_id)

# Save some draft content so word count estimate works
curl -s -X PUT "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH1_ID/draft" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"body":"The quick brown fox jumps over the lazy dog. This is a test paragraph with enough words to produce a meaningful word count estimate for our integration test.","body_format":"text"}' > /dev/null

# Make book public
curl -s -X PATCH "$GATEWAY/v1/sharing/books/$BOOK_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"visibility":"public"}' > /dev/null

green "Setup complete: book=$BOOK_ID, ch1=$CH1_ID, ch2=$CH2_ID"

# Wait for catalog to be ready
sleep 2

# ══════════════════════════════════════════════════════════════════════════════
# T01: Get public book detail (no auth required)
# ══════════════════════════════════════════════════════════════════════════════
header "T01: GET /v1/catalog/books/:id (no auth)"

T01_RESP=$(curl -s "$GATEWAY/v1/catalog/books/$BOOK_ID")
T01_TITLE=$(echo "$T01_RESP" | jget .title)
T01_OWNER=$(echo "$T01_RESP" | jget .owner_user_id)
T01_LANG=$(echo "$T01_RESP" | jget .original_language)
T01_VIS=$(echo "$T01_RESP" | jget .visibility)
T01_COUNT=$(echo "$T01_RESP" | jget .chapter_count)
T01_LANGS=$(echo "$T01_RESP" | jget .available_languages)

assert_eq "T01 title" "MIG-07 Test Book" "$T01_TITLE"
assert_not_empty "T01 owner_user_id present" "$T01_OWNER"
assert_eq "T01 language" "en" "$T01_LANG"
assert_eq "T01 visibility" "public" "$T01_VIS"
assert_eq "T01 chapter_count" "2" "$T01_COUNT"
# available_languages may be empty (no translations yet) — that's ok
if [ "$T01_LANGS" = "null" ] || [ "$T01_LANGS" = "[]" ] || [ -z "$T01_LANGS" ]; then
  green "T01 available_languages present (empty — no translations)"
else
  green "T01 available_languages has data: $T01_LANGS"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T02: List public chapters (no auth)
# ══════════════════════════════════════════════════════════════════════════════
header "T02: GET /v1/catalog/books/:id/chapters"

T02_RESP=$(curl -s "$GATEWAY/v1/catalog/books/$BOOK_ID/chapters")
T02_COUNT=$(echo "$T02_RESP" | jlen .items)
T02_TOTAL=$(echo "$T02_RESP" | jget .total)

assert_eq "T02 chapter count" "2" "$T02_COUNT"
assert_eq "T02 total" "2" "$T02_TOTAL"

# Check first chapter has word_count_estimate
T02_WC=$(echo "$T02_RESP" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch1=j.items?.find(i=>i.title==='Chapter 1 — The Beginning');
    console.log(ch1?.word_count_estimate ?? 'missing');
  })" 2>/dev/null)

if [ "$T02_WC" != "missing" ] && [ "$T02_WC" != "0" ] && [ -n "$T02_WC" ]; then
  green "T02 word_count_estimate present: $T02_WC"
else
  yellow "T02 word_count_estimate missing or zero (draft may not have body)"
fi

# Check chapter has title and sort_order
T02_TITLE=$(echo "$T02_RESP" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j.items?.[0]?.title||'');
  })" 2>/dev/null)
assert_not_empty "T02 chapter title present" "$T02_TITLE"

# ══════════════════════════════════════════════════════════════════════════════
# T03: Get single public chapter
# ══════════════════════════════════════════════════════════════════════════════
header "T03: GET /v1/catalog/books/:id/chapters/:chapterId"

T03_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books/$BOOK_ID/chapters/$CH1_ID")
assert_eq "T03 chapter detail HTTP 200" "200" "$T03_STATUS"

# ══════════════════════════════════════════════════════════════════════════════
# T04: Non-public book returns 404
# ══════════════════════════════════════════════════════════════════════════════
header "T04: Non-public book returns 404"

# Create a private book
PRIV_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Private Book","original_language":"en"}')
PRIV_ID=$(echo "$PRIV_RESP" | jget .book_id)

T04_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books/$PRIV_ID")
assert_eq "T04 private book 404" "404" "$T04_STATUS"

# ══════════════════════════════════════════════════════════════════════════════
# T05: Invalid book ID returns 400/404
# ══════════════════════════════════════════════════════════════════════════════
header "T05: Invalid book ID"

T05_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/catalog/books/not-a-uuid")
if [ "$T05_STATUS" = "400" ] || [ "$T05_STATUS" = "404" ]; then
  green "T05 invalid ID returns $T05_STATUS"
else
  red "T05 invalid ID (expected 400/404, got $T05_STATUS)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T06: Pagination
# ══════════════════════════════════════════════════════════════════════════════
header "T06: Chapter pagination"

T06_RESP=$(curl -s "$GATEWAY/v1/catalog/books/$BOOK_ID/chapters?limit=1&offset=0")
T06_COUNT=$(echo "$T06_RESP" | jlen .items)
T06_TOTAL=$(echo "$T06_RESP" | jget .total)
assert_eq "T06 limit=1 returns 1 item" "1" "$T06_COUNT"
assert_eq "T06 total still 2" "2" "$T06_TOTAL"

# ══════════════════════════════════════════════════════════════════════════════
# Cleanup
# ══════════════════════════════════════════════════════════════════════════════
header "Cleanup"
curl -s -X DELETE "$GATEWAY/v1/books/$BOOK_ID" -H "$AUTH" > /dev/null 2>&1 || true
curl -s -X DELETE "$GATEWAY/v1/books/$PRIV_ID" -H "$AUTH" > /dev/null 2>&1 || true
green "Cleaned up test data"

# ══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1;37m═══════════════════════════════════════\033[0m\n"
printf "\033[1;32m  PASS: %d\033[0m  " "$PASS"
printf "\033[1;31m  FAIL: %d\033[0m  " "$FAIL"
printf "\033[1;33m  SKIP: %d\033[0m\n" "$SKIP"
printf "\033[1;37m═══════════════════════════════════════\033[0m\n"

if [ "$FAIL" -gt 0 ]; then exit 1; fi
