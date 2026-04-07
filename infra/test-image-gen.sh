#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Image Generation Integration Tests (PE-04 + PE-05)
#
# Tests: validation, auth, image generation endpoint, capability filter
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-image-gen.sh
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

UNAME="imagegen_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"Image Gen Test\"}" > /dev/null

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"
USER_ID=$(echo "$LOGIN_RESP" | jget .user_profile.user_id)

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Image Gen Test Book","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Setup: created book" "$BOOK_ID"

CHAPTER_ID=$(docker compose exec -T postgres psql -U loreweave -d loreweave_book -tA -c "
  INSERT INTO chapters(book_id, title, original_filename, original_language, content_type, sort_order, storage_key)
  VALUES ('$BOOK_ID', 'Image Gen Chapter', 'ch1.txt', 'en', 'text/plain', 1, 'test/ch1.txt')
  RETURNING id;
" | head -1 | tr -d '[:space:]')
assert_not_empty "Setup: created chapter" "$CHAPTER_ID"

BASE="$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID"

# ═══════════════════════════════════════════════════════════════════════════════
# T01-T04: Validation tests — generate-image
# ═══════════════════════════════════════════════════════════════════════════════
header "T01-T04: Image generation validation"

# T01: Missing auth → 401
T01_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/media-generate" \
  -H "Content-Type: application/json" \
  -d '{"block_id":"b1","prompt":"a cat","model_ref":"fake-id"}')
assert_status "T01 missing auth → 401" "401" "$T01_STATUS"

# T02: Missing required fields → 400
T02_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE/media-generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"block_id":"b1"}')
T02_STATUS=$(echo "$T02_RESP" | tail -1)
assert_status "T02 missing prompt+model_ref → 400" "400" "$T02_STATUS"

# T03: Missing block_id → 400
T03_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE/media-generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"prompt":"a cat","model_ref":"fake-id"}')
T03_STATUS=$(echo "$T03_RESP" | tail -1)
assert_status "T03 missing block_id → 400" "400" "$T03_STATUS"

# T04: Non-existent model_ref → 402 (no provider)
T04_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE/media-generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"block_id":"b1","prompt":"a cat","model_ref":"00000000-0000-0000-0000-000000000000"}')
T04_STATUS=$(echo "$T04_RESP" | tail -1)
T04_CODE=$(echo "$T04_RESP" | head -1 | jget .code)
assert_status "T04 fake model_ref → 402" "402" "$T04_STATUS"
assert_eq "T04 error code NO_PROVIDER" "NO_PROVIDER" "$T04_CODE"

# ═══════════════════════════════════════════════════════════════════════════════
# T05-T07: Auth / ownership tests
# ═══════════════════════════════════════════════════════════════════════════════
header "T05-T07: Auth and ownership"

# T05: Other user can't access book → 404
UNAME2="imagegen_other_$(date +%s)"
EMAIL2="$UNAME2@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL2\",\"password\":\"Test1234!\",\"display_name\":\"Other User\"}" > /dev/null
LOGIN2=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL2\",\"password\":\"Test1234!\"}")
TOKEN2=$(echo "$LOGIN2" | jget .access_token)
AUTH2="Authorization: Bearer $TOKEN2"

T05_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/media-generate" \
  -H "$AUTH2" -H "Content-Type: application/json" \
  -d '{"block_id":"b1","prompt":"a cat","model_ref":"00000000-0000-0000-0000-000000000000"}')
assert_status "T05 other user → 404 (not owner)" "404" "$T05_STATUS"

# T06: Non-existent book → 404
T06_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$GATEWAY/v1/books/00000000-0000-0000-0000-000000000000/chapters/$CHAPTER_ID/media-generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"block_id":"b1","prompt":"a cat","model_ref":"00000000-0000-0000-0000-000000000000"}')
assert_status "T06 non-existent book → 404" "404" "$T06_STATUS"

# T07: Invalid book_id format → 400
T07_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$GATEWAY/v1/books/not-a-uuid/chapters/$CHAPTER_ID/media-generate" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"block_id":"b1","prompt":"a cat","model_ref":"00000000-0000-0000-0000-000000000000"}')
assert_status "T07 invalid book UUID → 400" "400" "$T07_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T08-T10: Media upload tests
# ═══════════════════════════════════════════════════════════════════════════════
header "T08-T10: Media upload"

# T08: Upload image (create temp PNG)
TEMP_IMG=$(mktemp /tmp/test_XXXX.png)
printf '\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82' > "$TEMP_IMG"

T08_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE/media" \
  -H "$AUTH" \
  -F "file=@$TEMP_IMG;type=image/png" \
  -F "block_id=block_test_1")
T08_STATUS=$(echo "$T08_RESP" | tail -1)
T08_BODY=$(echo "$T08_RESP" | head -1)
T08_URL=$(echo "$T08_BODY" | jget .url)
assert_status "T08 upload PNG → 201" "201" "$T08_STATUS"
assert_not_empty "T08 upload returns URL" "$T08_URL"
rm -f "$TEMP_IMG"

# T09: Upload unsupported type → 415
TEMP_TXT=$(mktemp /tmp/test_XXXX.txt)
echo "not an image" > "$TEMP_TXT"
T09_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/media" \
  -H "$AUTH" \
  -F "file=@$TEMP_TXT;type=text/plain")
assert_status "T09 upload text/plain → 415" "415" "$T09_STATUS"
rm -f "$TEMP_TXT"

# T10: Upload missing file → 400
T10_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X POST "$BASE/media" \
  -H "$AUTH" \
  -H "Content-Type: multipart/form-data")
assert_status "T10 upload missing file → 400" "400" "$T10_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T11-T14: Version history tests
# ═══════════════════════════════════════════════════════════════════════════════
header "T11-T14: Version history"

# T11: List versions for block_test_1
T11_RESP=$(curl -s "$BASE/media/versions?block_id=block_test_1" -H "$AUTH")
T11_LEN=$(echo "$T11_RESP" | jlen .items)
assert_eq "T11 version count for block_test_1" "1" "$T11_LEN"

# T12: Create manual version record
T12_RESP=$(curl -s -w "\n%{http_code}" \
  -X POST "$BASE/media/versions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"block_id":"block_test_1","action":"edit","changes":["caption"],"caption_snapshot":"A cat photo"}')
T12_STATUS=$(echo "$T12_RESP" | tail -1)
assert_status "T12 create version record → 201" "201" "$T12_STATUS"

# T13: Verify version count incremented
T13_RESP=$(curl -s "$BASE/media/versions?block_id=block_test_1" -H "$AUTH")
T13_LEN=$(echo "$T13_RESP" | jlen .items)
assert_eq "T13 version count now 2" "2" "$T13_LEN"

# T14: Missing block_id in version query → 400
T14_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/media/versions" -H "$AUTH")
assert_status "T14 missing block_id → 400" "400" "$T14_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T15-T17: Capability filter tests (PE-01)
# ═══════════════════════════════════════════════════════════════════════════════
header "T15-T17: Capability filter on user models"

# T15: List all models (no filter) — should return 0 for new user
T15_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models" -H "$AUTH")
T15_LEN=$(echo "$T15_RESP" | jlen .items)
assert_eq "T15 new user has 0 models" "0" "$T15_LEN"

# T16: List with capability=tts — still 0
T16_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=tts" -H "$AUTH")
T16_LEN=$(echo "$T16_RESP" | jlen .items)
assert_eq "T16 capability=tts returns 0" "0" "$T16_LEN"

# T17: List with capability=image_gen — still 0
T17_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=image_gen" -H "$AUTH")
T17_LEN=$(echo "$T17_RESP" | jlen .items)
assert_eq "T17 capability=image_gen returns 0" "0" "$T17_LEN"

# ═══════════════════════════════════════════════════════════════════════════════
# T18-T22: Capability filter with real models
# ═══════════════════════════════════════════════════════════════════════════════
header "T18-T22: Capability filter with provider + models"

# Create a provider credential first
CRED_RESP=$(curl -s -X POST "$GATEWAY/v1/model-registry/credentials" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"provider_kind":"openai","api_key":"sk-test-fake-key","base_url":"http://localhost:9999"}')
CRED_ID=$(echo "$CRED_RESP" | jget .credential_id)
assert_not_empty "T18 created provider credential" "$CRED_ID"

# T19: Add a chat model
M1_RESP=$(curl -s -X POST "$GATEWAY/v1/model-registry/user-models" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"provider_credential_id\":\"$CRED_ID\",\"provider_model_name\":\"gpt-4o\",\"capability_flags\":{\"chat\":true,\"vision\":true}}")
M1_ID=$(echo "$M1_RESP" | jget .user_model_id)
assert_not_empty "T19 created chat model" "$M1_ID"

# T20: Add a TTS model
M2_RESP=$(curl -s -X POST "$GATEWAY/v1/model-registry/user-models" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"provider_credential_id\":\"$CRED_ID\",\"provider_model_name\":\"tts-1\",\"capability_flags\":{\"tts\":true}}")
M2_ID=$(echo "$M2_RESP" | jget .user_model_id)
assert_not_empty "T20 created TTS model" "$M2_ID"

# T21: Add an image_gen model
M3_RESP=$(curl -s -X POST "$GATEWAY/v1/model-registry/user-models" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"provider_credential_id\":\"$CRED_ID\",\"provider_model_name\":\"dall-e-3\",\"capability_flags\":{\"image_gen\":true}}")
M3_ID=$(echo "$M3_RESP" | jget .user_model_id)
assert_not_empty "T21 created image_gen model" "$M3_ID"

# T22: Filter by capability=tts → only TTS model
T22_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=tts" -H "$AUTH")
T22_LEN=$(echo "$T22_RESP" | jlen .items)
assert_eq "T22 capability=tts returns 1" "1" "$T22_LEN"

# T23: Filter by capability=image_gen → only image model
T23_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=image_gen" -H "$AUTH")
T23_LEN=$(echo "$T23_RESP" | jlen .items)
assert_eq "T23 capability=image_gen returns 1" "1" "$T23_LEN"

# T24: Filter by capability=chat → only chat model
T24_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=chat" -H "$AUTH")
T24_LEN=$(echo "$T24_RESP" | jlen .items)
assert_eq "T24 capability=chat returns 1" "1" "$T24_LEN"

# T25: Filter by capability=video_gen → 0
T25_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=video_gen" -H "$AUTH")
T25_LEN=$(echo "$T25_RESP" | jlen .items)
assert_eq "T25 capability=video_gen returns 0" "0" "$T25_LEN"

# T26: No filter → all 3
T26_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models" -H "$AUTH")
T26_LEN=$(echo "$T26_RESP" | jlen .items)
assert_eq "T26 no filter returns 3" "3" "$T26_LEN"

# T27: Combine capability + provider_kind
T27_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models?capability=tts&provider_kind=openai" -H "$AUTH")
T27_LEN=$(echo "$T27_RESP" | jlen .items)
assert_eq "T27 tts+openai returns 1" "1" "$T27_LEN"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "════════════════════════════════════════════════════════════════════════"
printf "  \033[32mPassed: %d\033[0m  |  \033[31mFailed: %d\033[0m  |  Total: %d\n" "$PASS" "$FAIL" $((PASS+FAIL))
echo "════════════════════════════════════════════════════════════════════════"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
