#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Audio Segments Integration Test (AU-01)
#
# Tests chapter_audio_segments CRUD through the gateway:
#   - List segments (GET with language+voice)
#   - Get single segment (GET by segment_id)
#   - Delete segments (DELETE with language+voice)
#   - Auth, validation, edge cases
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-audio.sh
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

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label (HTTP $actual)"; PASS=$((PASS+1))
  else
    red "$label (expected HTTP $expected, got $actual)"; FAIL=$((FAIL+1))
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
        const keys='${path}'.slice(1).split('.').filter(Boolean);
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        if(v===undefined||v===null) console.log('');
        else console.log(typeof v==='object'?JSON.stringify(v):v);
      } catch { console.log(''); }
    });
  " 2>/dev/null || echo ""
}

jlen() {
  local path="$1"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      try {
        const j=JSON.parse(d);
        const keys='${path}'.slice(1).split('.').filter(Boolean);
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        console.log(Array.isArray(v)?v.length:0);
      } catch { console.log(0); }
    });
  " 2>/dev/null || echo "0"
}

# ── T00: Health check ────────────────────────────────────────────────────────
header "T00: Health check"

GW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/health")
assert_status "T00 gateway health" "200" "$GW_STATUS"

# ── Setup: Auth + Book + Chapter ─────────────────────────────────────────────
header "Setup: Register + Login + Book + Chapter"

UNAME="audio_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"Audio Test\"}" > /dev/null

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"
USER_ID=$(echo "$LOGIN_RESP" | jget .user_profile.user_id)

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Audio Test Book","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Setup: created book" "$BOOK_ID"

# Insert chapter directly via psql (avoids MinIO bucket dependency for chapter creation)
CHAPTER_ID=$(docker compose exec -T postgres psql -U loreweave -d loreweave_book -tA -c "
  INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, sort_order, storage_key)
  VALUES ('$BOOK_ID', 'Audio Test Chapter', 'ch1.txt', 'en', 'text/plain', 1, 'test/ch1.txt')
  RETURNING id;
" | head -1 | tr -d '[:space:]')
assert_not_empty "Setup: created chapter" "$CHAPTER_ID"

# Insert test audio segments directly (AU-01 has no create endpoint — AU-03 adds generation)
docker compose exec -T postgres psql -U loreweave -d loreweave_book -c "
  INSERT INTO chapter_audio_segments(chapter_id, block_index, source_text, source_text_hash, voice, provider, language, media_key, duration_ms)
  VALUES
    ('$CHAPTER_ID', 0, 'First paragraph of the chapter.', encode(sha256('First paragraph of the chapter.'::bytea),'hex'), 'alloy', 'openai', 'en', 'audio/$CHAPTER_ID/tts/en_alloy_0.mp3', 3200),
    ('$CHAPTER_ID', 1, 'Second paragraph continues here.', encode(sha256('Second paragraph continues here.'::bytea),'hex'), 'alloy', 'openai', 'en', 'audio/$CHAPTER_ID/tts/en_alloy_1.mp3', 2800),
    ('$CHAPTER_ID', 2, 'Final block of text.', encode(sha256('Final block of text.'::bytea),'hex'), 'alloy', 'openai', 'en', 'audio/$CHAPTER_ID/tts/en_alloy_2.mp3', 1500),
    ('$CHAPTER_ID', 0, 'Đoạn văn đầu tiên.', encode(sha256('Đoạn văn đầu tiên.'::bytea),'hex'), 'nova', 'openai', 'vi', 'audio/$CHAPTER_ID/tts/vi_nova_0.mp3', 2900),
    ('$CHAPTER_ID', 1, 'Đoạn văn thứ hai.', encode(sha256('Đoạn văn thứ hai.'::bytea),'hex'), 'nova', 'openai', 'vi', 'audio/$CHAPTER_ID/tts/vi_nova_1.mp3', 2100);
" > /dev/null
green "Setup: inserted 5 audio segments (3 en/alloy + 2 vi/nova)"
PASS=$((PASS+1))

BASE="$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/audio"

# ═══════════════════════════════════════════════════════════════════════════════
# AU-01: List audio segments
# ═══════════════════════════════════════════════════════════════════════════════
header "AU-01a: List audio segments"

# T01: List en/alloy — should return 3 segments
LIST_EN=$(curl -s -H "$AUTH" "$BASE?language=en&voice=alloy")
LEN_EN=$(echo "$LIST_EN" | jlen .segments)
assert_eq "T01 list en/alloy count" "3" "$LEN_EN"

# T02: Verify ordering by block_index (0, 1, 2)
BI_0=$(echo "$LIST_EN" | jget .segments.0.block_index)
BI_1=$(echo "$LIST_EN" | jget .segments.1.block_index)
BI_2=$(echo "$LIST_EN" | jget .segments.2.block_index)
assert_eq "T02a block_index[0]" "0" "$BI_0"
assert_eq "T02b block_index[1]" "1" "$BI_1"
assert_eq "T02c block_index[2]" "2" "$BI_2"

# T03: Verify source_text is NOT in list response
HAS_SOURCE=$(echo "$LIST_EN" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j.segments[0].hasOwnProperty('source_text'));
  });
" 2>/dev/null)
assert_eq "T03 source_text excluded from list" "false" "$HAS_SOURCE"

# T04: Verify fields present
SEG0_ID=$(echo "$LIST_EN" | jget .segments.0.segment_id)
SEG0_VOICE=$(echo "$LIST_EN" | jget .segments.0.voice)
SEG0_PROVIDER=$(echo "$LIST_EN" | jget .segments.0.provider)
SEG0_LANG=$(echo "$LIST_EN" | jget .segments.0.language)
SEG0_KEY=$(echo "$LIST_EN" | jget .segments.0.media_key)
SEG0_DUR=$(echo "$LIST_EN" | jget .segments.0.duration_ms)
SEG0_HASH=$(echo "$LIST_EN" | jget .segments.0.source_text_hash)
SEG0_CREATED=$(echo "$LIST_EN" | jget .segments.0.created_at)
assert_not_empty "T04a segment_id" "$SEG0_ID"
assert_eq "T04b voice" "alloy" "$SEG0_VOICE"
assert_eq "T04c provider" "openai" "$SEG0_PROVIDER"
assert_eq "T04d language" "en" "$SEG0_LANG"
assert_not_empty "T04e media_key" "$SEG0_KEY"
assert_eq "T04f duration_ms" "3200" "$SEG0_DUR"
assert_not_empty "T04g source_text_hash" "$SEG0_HASH"
assert_not_empty "T04h created_at" "$SEG0_CREATED"

# T05: List vi/nova — should return 2 segments
LIST_VI=$(curl -s -H "$AUTH" "$BASE?language=vi&voice=nova")
LEN_VI=$(echo "$LIST_VI" | jlen .segments)
assert_eq "T05 list vi/nova count" "2" "$LEN_VI"

# T06: List non-existent language — empty array
LIST_EMPTY=$(curl -s -H "$AUTH" "$BASE?language=jp&voice=alloy")
LEN_EMPTY=$(echo "$LIST_EMPTY" | jlen .segments)
assert_eq "T06 list non-existent lang (empty)" "0" "$LEN_EMPTY"

# T07: Missing query params → 400
S_NO_LANG=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE?voice=alloy")
assert_status "T07a missing language" "400" "$S_NO_LANG"

S_NO_VOICE=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE?language=en")
assert_status "T07b missing voice" "400" "$S_NO_VOICE"

S_NO_PARAMS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE")
assert_status "T07c no params" "400" "$S_NO_PARAMS"

# ═══════════════════════════════════════════════════════════════════════════════
# AU-01: Get single segment
# ═══════════════════════════════════════════════════════════════════════════════
header "AU-01b: Get single segment"

# T08: Get single — includes source_text
SINGLE=$(curl -s -H "$AUTH" "$BASE/$SEG0_ID")
S_TEXT=$(echo "$SINGLE" | jget .source_text)
assert_eq "T08 source_text present" "First paragraph of the chapter." "$S_TEXT"

# T09: All fields match list
S_BI=$(echo "$SINGLE" | jget .block_index)
S_VOICE=$(echo "$SINGLE" | jget .voice)
S_DUR=$(echo "$SINGLE" | jget .duration_ms)
assert_eq "T09a block_index" "0" "$S_BI"
assert_eq "T09b voice" "alloy" "$S_VOICE"
assert_eq "T09c duration_ms" "3200" "$S_DUR"

# T10: Get non-existent segment → 404
S_404=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/00000000-0000-0000-0000-000000000000")
assert_status "T10 non-existent segment" "404" "$S_404"

# T11: Invalid UUID → 400
S_BAD=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/not-a-uuid")
assert_status "T11 invalid UUID" "400" "$S_BAD"

# ═══════════════════════════════════════════════════════════════════════════════
# AU-01: Auth checks
# ═══════════════════════════════════════════════════════════════════════════════
header "AU-01c: Auth checks"

# T12: No auth token → 401
S_NOAUTH=$(curl -s -o /dev/null -w "%{http_code}" "$BASE?language=en&voice=alloy")
assert_status "T12a list without auth" "401" "$S_NOAUTH"

S_NOAUTH2=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/$SEG0_ID")
assert_status "T12b get without auth" "401" "$S_NOAUTH2"

S_NOAUTH3=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE "$BASE?language=en&voice=alloy")
assert_status "T12c delete without auth" "401" "$S_NOAUTH3"

# T13: Different user cannot access
UNAME2="audio_integ2_$(date +%s)"
EMAIL2="$UNAME2@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL2\",\"password\":\"Test1234!\"}" > /dev/null
LOGIN2=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL2\",\"password\":\"Test1234!\"}")
TOKEN2=$(echo "$LOGIN2" | jget .access_token)
AUTH2="Authorization: Bearer $TOKEN2"

S_OTHER=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH2" "$BASE?language=en&voice=alloy")
assert_status "T13 other user gets 404" "404" "$S_OTHER"

# ═══════════════════════════════════════════════════════════════════════════════
# AU-01: Delete segments
# ═══════════════════════════════════════════════════════════════════════════════
header "AU-01d: Delete segments"

# T14: Delete vi/nova
DEL_VI=$(curl -s -X DELETE -H "$AUTH" "$BASE?language=vi&voice=nova")
DEL_COUNT=$(echo "$DEL_VI" | jget .deleted)
assert_eq "T14 delete vi/nova count" "2" "$DEL_COUNT"

# T15: Verify vi/nova gone
LIST_VI2=$(curl -s -H "$AUTH" "$BASE?language=vi&voice=nova")
LEN_VI2=$(echo "$LIST_VI2" | jlen .segments)
assert_eq "T15 vi/nova empty after delete" "0" "$LEN_VI2"

# T16: en/alloy still intact
LIST_EN2=$(curl -s -H "$AUTH" "$BASE?language=en&voice=alloy")
LEN_EN2=$(echo "$LIST_EN2" | jlen .segments)
assert_eq "T16 en/alloy still has 3" "3" "$LEN_EN2"

# T17: Delete en/alloy
DEL_EN=$(curl -s -X DELETE -H "$AUTH" "$BASE?language=en&voice=alloy")
DEL_EN_CT=$(echo "$DEL_EN" | jget .deleted)
assert_eq "T17 delete en/alloy count" "3" "$DEL_EN_CT"

# T18: Everything gone
LIST_EN3=$(curl -s -H "$AUTH" "$BASE?language=en&voice=alloy")
LEN_EN3=$(echo "$LIST_EN3" | jlen .segments)
assert_eq "T18 en/alloy empty after delete" "0" "$LEN_EN3"

# T19: Get previously fetched segment → 404
S_GONE=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$BASE/$SEG0_ID")
assert_status "T19 segment gone after delete" "404" "$S_GONE"

# T20: Delete already empty → returns 0 (idempotent)
DEL_EMPTY=$(curl -s -X DELETE -H "$AUTH" "$BASE?language=en&voice=alloy")
DEL_EMPTY_CT=$(echo "$DEL_EMPTY" | jget .deleted)
assert_eq "T20 delete empty is idempotent" "0" "$DEL_EMPTY_CT"

# T21: Delete missing params → 400
S_DEL_BAD=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE -H "$AUTH" "$BASE")
assert_status "T21 delete without params" "400" "$S_DEL_BAD"

# ═══════════════════════════════════════════════════════════════════════════════
# Cleanup
# ═══════════════════════════════════════════════════════════════════════════════
header "Cleanup"
docker compose exec -T postgres psql -U loreweave -d loreweave_book -c "
  DELETE FROM chapters WHERE id = '$CHAPTER_ID';
  DELETE FROM books WHERE id = '$BOOK_ID';
" > /dev/null
green "Cleanup: test data removed"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1;35m════════════════════════════════════════\033[0m\n"
printf "\033[1;35m  PASS: %d   FAIL: %d   TOTAL: %d\033[0m\n" "$PASS" "$FAIL" "$((PASS+FAIL))"
printf "\033[1;35m════════════════════════════════════════\033[0m\n"

if [ "$FAIL" -gt 0 ]; then exit 1; fi
