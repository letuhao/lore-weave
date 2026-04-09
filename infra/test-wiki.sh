#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Wiki System Integration Tests (P9-08a)
# Usage: bash infra/test-wiki.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
GLOSSARY_DIRECT="http://localhost:8211"
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
assert_ge() {
  local label="$1" minimum="$2" actual="$3"
  if [ "$actual" -ge "$minimum" ] 2>/dev/null; then green "$label (${actual} >= ${minimum})"; PASS=$((PASS+1))
  else red "$label (expected >= $minimum, got $actual)"; FAIL=$((FAIL+1)); fi
}
jget() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}if(v===undefined||v===null)console.log('');else console.log(typeof v==='object'?JSON.stringify(v):v)}catch{console.log('')}})" 2>/dev/null || echo ""
}
jlen() {
  node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{try{const j=JSON.parse(d);const k='${1}'.slice(1).split('.').filter(Boolean);let v=j;for(const x of k){if(v==null)break;v=v[x]}console.log(Array.isArray(v)?v.length:0)}catch{console.log(0)}})" 2>/dev/null || echo "0"
}

# ═══════════════════════════════════════════════════════════════════════════════
# Setup: Health + Auth + Book + Entities
# ═══════════════════════════════════════════════════════════════════════════════
header "Setup: Health + Auth"

# T01: Glossary health
T01_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GLOSSARY_DIRECT/health")
assert_status "T01 glossary-service health → 200" "200" "$T01_STATUS"

# Create test user
TS=$(date +%s)
EMAIL="wiki_test_${TS}@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"Wiki Tester\"}" > /dev/null
LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
USER_ID=$(echo "$LOGIN_RESP" | jget .user_profile.user_id)
assert_not_empty "Setup: got token" "$TOKEN"
assert_not_empty "Setup: got user_id" "$USER_ID"
AUTH="Authorization: Bearer $TOKEN"

# Create second user for auth tests
EMAIL2="wiki_test2_${TS}@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL2\",\"password\":\"Test1234!\",\"display_name\":\"Other User\"}" > /dev/null
LOGIN2_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL2\",\"password\":\"Test1234!\"}")
TOKEN2=$(echo "$LOGIN2_RESP" | jget .access_token)
AUTH2="Authorization: Bearer $TOKEN2"

header "Setup: Create Book + Entities"

# Create book
BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"title\":\"Wiki Test Book ${TS}\",\"source_language\":\"zh\",\"target_language\":\"en\"}")
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Setup: got book_id" "$BOOK_ID"

# Get character kind_id
KINDS_RESP=$(curl -s "$GATEWAY/v1/glossary/kinds" -H "$AUTH")
KIND_ID=$(echo "$KINDS_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const k=j.find(x=>x.code==='character');console.log(k?k.kind_id:'')})" 2>/dev/null)
assert_not_empty "Setup: got character kind_id" "$KIND_ID"

# Get location kind_id
LOCATION_KIND_ID=$(echo "$KINDS_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const k=j.find(x=>x.code==='location');console.log(k?k.kind_id:'')})" 2>/dev/null)

# Create entity 1 (character, active)
E1_RESP=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"kind_id\":\"$KIND_ID\",\"display_name\":\"Hero\"}")
ENTITY_ID_1=$(echo "$E1_RESP" | jget .entity_id)
assert_not_empty "Setup: entity 1 created" "$ENTITY_ID_1"
# Activate entity 1
curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" -d '{"status":"active"}' > /dev/null

# Create entity 2 (character, active)
E2_RESP=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"kind_id\":\"$KIND_ID\",\"display_name\":\"Villain\"}")
ENTITY_ID_2=$(echo "$E2_RESP" | jget .entity_id)
assert_not_empty "Setup: entity 2 created" "$ENTITY_ID_2"
curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID_2" \
  -H "Content-Type: application/json" -H "$AUTH" -d '{"status":"active"}' > /dev/null

# Create entity 3 (location, active)
E3_RESP=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"kind_id\":\"$LOCATION_KIND_ID\",\"display_name\":\"Castle\"}")
ENTITY_ID_3=$(echo "$E3_RESP" | jget .entity_id)
assert_not_empty "Setup: entity 3 created" "$ENTITY_ID_3"
curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID_3" \
  -H "Content-Type: application/json" -H "$AUTH" -d '{"status":"active"}' > /dev/null

# Create entity 4 (character, draft — should NOT be picked up by generate)
E4_RESP=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"kind_id\":\"$KIND_ID\",\"display_name\":\"Draft NPC\"}")
ENTITY_ID_4=$(echo "$E4_RESP" | jget .entity_id)
assert_not_empty "Setup: entity 4 (draft) created" "$ENTITY_ID_4"

# ═══════════════════════════════════════════════════════════════════════════════
# T02-T05: Auth & Validation
# ═══════════════════════════════════════════════════════════════════════════════
header "T02-T05: Auth & Validation"

# T02: No auth → 401
T02_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki")
assert_status "T02 list wiki no auth → 401" "401" "$T02_STATUS"

# T03: Wrong user → 403
T03_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" -H "$AUTH2")
assert_status "T03 list wiki wrong user → 403" "403" "$T03_STATUS"

# T04: Invalid book_id → 400
T04_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/glossary/books/not-a-uuid/wiki" -H "$AUTH")
assert_status "T04 invalid book_id → 400" "400" "$T04_STATUS"

# T05: Empty list initially
T05_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" -H "$AUTH")
T05_TOTAL=$(echo "$T05_RESP" | jget .total)
assert_eq "T05 initial wiki list is empty" "0" "$T05_TOTAL"

# ═══════════════════════════════════════════════════════════════════════════════
# T06-T12: Create Article
# ═══════════════════════════════════════════════════════════════════════════════
header "T06-T12: Create Wiki Article"

# T06: Create article for entity 1
T06_RESP=$(curl -s -o /tmp/wiki_t06.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"entity_id\":\"$ENTITY_ID_1\",\"template_code\":\"character\",\"body_json\":{\"type\":\"doc\",\"content\":[{\"type\":\"paragraph\",\"content\":[{\"type\":\"text\",\"text\":\"Hero is the protagonist.\"}]}]}}")
assert_status "T06 create article → 201" "201" "$T06_RESP"
ARTICLE_ID_1=$(cat /tmp/wiki_t06.json | jget .article_id)
assert_not_empty "T06 got article_id" "$ARTICLE_ID_1"

# T07: Verify response fields
T07_STATUS=$(cat /tmp/wiki_t06.json | jget .status)
T07_TEMPLATE=$(cat /tmp/wiki_t06.json | jget .template_code)
T07_REV_COUNT=$(cat /tmp/wiki_t06.json | jget .revision_count)
assert_eq "T07 status is draft" "draft" "$T07_STATUS"
assert_eq "T07 template_code is character" "character" "$T07_TEMPLATE"
assert_eq "T07 revision_count is 1" "1" "$T07_REV_COUNT"

# T08: Infobox included
T08_INFOBOX_LEN=$(cat /tmp/wiki_t06.json | jlen .infobox)
assert_ge "T08 infobox has attributes" "1" "$T08_INFOBOX_LEN"

# T09: Duplicate article → 409
T09_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"entity_id\":\"$ENTITY_ID_1\"}")
assert_status "T09 duplicate article → 409" "409" "$T09_STATUS"

# T10: Invalid entity_id → 400
T10_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"entity_id":"not-a-uuid"}')
assert_status "T10 invalid entity_id → 400" "400" "$T10_STATUS"

# T11: Non-existent entity_id → 404
FAKE_UUID="00000000-0000-0000-0000-000000000099"
T11_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"entity_id\":\"$FAKE_UUID\"}")
assert_status "T11 non-existent entity → 404" "404" "$T11_STATUS"

# T12: Create with default body (empty)
T12_RESP=$(curl -s -o /tmp/wiki_t12.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"entity_id\":\"$ENTITY_ID_3\",\"template_code\":\"location\"}")
assert_status "T12 create article with defaults → 201" "201" "$T12_RESP"
ARTICLE_ID_3=$(cat /tmp/wiki_t12.json | jget .article_id)
assert_not_empty "T12 got article_id for entity 3" "$ARTICLE_ID_3"

# ═══════════════════════════════════════════════════════════════════════════════
# T13-T16: List Articles
# ═══════════════════════════════════════════════════════════════════════════════
header "T13-T16: List Wiki Articles"

# T13: List all → 2 articles
T13_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" -H "$AUTH")
T13_TOTAL=$(echo "$T13_RESP" | jget .total)
assert_eq "T13 total articles is 2" "2" "$T13_TOTAL"

# T14: Filter by kind_code=character → 1
T14_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki?kind_code=character" -H "$AUTH")
T14_TOTAL=$(echo "$T14_RESP" | jget .total)
assert_eq "T14 filter character → 1" "1" "$T14_TOTAL"

# T15: Filter by kind_code=location → 1
T15_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki?kind_code=location" -H "$AUTH")
T15_TOTAL=$(echo "$T15_RESP" | jget .total)
assert_eq "T15 filter location → 1" "1" "$T15_TOTAL"

# T16: Pagination limit=1
T16_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki?limit=1" -H "$AUTH")
T16_ITEMS=$(echo "$T16_RESP" | jlen .items)
T16_TOTAL=$(echo "$T16_RESP" | jget .total)
assert_eq "T16 limit=1 returns 1 item" "1" "$T16_ITEMS"
assert_eq "T16 total still 2" "2" "$T16_TOTAL"

# ═══════════════════════════════════════════════════════════════════════════════
# T17-T19: Get Article Detail
# ═══════════════════════════════════════════════════════════════════════════════
header "T17-T19: Get Wiki Article Detail"

# T17: Get article 1 detail
T17_RESP=$(curl -s -o /tmp/wiki_t17.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" -H "$AUTH")
assert_status "T17 get article detail → 200" "200" "$T17_RESP"
T17_BODY_TYPE=$(cat /tmp/wiki_t17.json | jget .body_json.type)
assert_eq "T17 body_json has doc type" "doc" "$T17_BODY_TYPE"

# T18: Infobox present with translations array
T18_INFOBOX_LEN=$(cat /tmp/wiki_t17.json | jlen .infobox)
assert_ge "T18 infobox has attrs" "1" "$T18_INFOBOX_LEN"

# T19: Non-existent article → 404
T19_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$FAKE_UUID" -H "$AUTH")
assert_status "T19 non-existent article → 404" "404" "$T19_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T20-T26: Patch Article
# ═══════════════════════════════════════════════════════════════════════════════
header "T20-T26: Patch Wiki Article"

# T20: Update body → creates revision
T20_RESP=$(curl -s -o /tmp/wiki_t20.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"body_json":{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"Updated hero story."}]}]},"summary":"Expanded backstory"}')
assert_status "T20 patch body → 200" "200" "$T20_RESP"
T20_REV=$(cat /tmp/wiki_t20.json | jget .revision_count)
assert_eq "T20 revision_count now 2" "2" "$T20_REV"

# T21: Update status to published
T21_RESP=$(curl -s -o /tmp/wiki_t21.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"status":"published"}')
assert_status "T21 patch status → 200" "200" "$T21_RESP"
T21_STATUS_VAL=$(cat /tmp/wiki_t21.json | jget .status)
assert_eq "T21 status now published" "published" "$T21_STATUS_VAL"
# Status-only change should NOT create revision
T21_REV=$(cat /tmp/wiki_t21.json | jget .revision_count)
assert_eq "T21 revision_count still 2 (no body change)" "2" "$T21_REV"

# T22: Update spoiler_chapters
FAKE_CH1="11111111-1111-1111-1111-111111111111"
FAKE_CH2="22222222-2222-2222-2222-222222222222"
T22_RESP=$(curl -s -o /tmp/wiki_t22.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"spoiler_chapters\":[\"$FAKE_CH1\",\"$FAKE_CH2\"]}")
assert_status "T22 patch spoiler_chapters → 200" "200" "$T22_RESP"
T22_SPOILERS=$(cat /tmp/wiki_t22.json | jlen .spoiler_chapters)
assert_eq "T22 spoiler_chapters has 2 entries" "2" "$T22_SPOILERS"

# T23: Invalid status → 422
T23_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"status":"invalid_status"}')
assert_status "T23 invalid status → 422" "422" "$T23_STATUS"

# T24: Invalid spoiler UUID → 400
T24_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"spoiler_chapters":["not-a-uuid"]}')
assert_status "T24 invalid spoiler UUID → 400" "400" "$T24_STATUS"

# T25: Filter list by status=published → 1
T25_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki?status=published" -H "$AUTH")
T25_TOTAL=$(echo "$T25_RESP" | jget .total)
assert_eq "T25 published filter → 1" "1" "$T25_TOTAL"

# T26: Update template_code
T26_RESP=$(curl -s -o /tmp/wiki_t26.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"template_code":"custom_hero"}')
assert_status "T26 patch template_code → 200" "200" "$T26_RESP"
T26_TMPL=$(cat /tmp/wiki_t26.json | jget .template_code)
assert_eq "T26 template_code updated" "custom_hero" "$T26_TMPL"

# ═══════════════════════════════════════════════════════════════════════════════
# T27-T32: Revisions
# ═══════════════════════════════════════════════════════════════════════════════
header "T27-T32: Wiki Revisions"

# T27: List revisions for article 1
T27_RESP=$(curl -s -o /tmp/wiki_t27.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions" -H "$AUTH")
assert_status "T27 list revisions → 200" "200" "$T27_RESP"
T27_TOTAL=$(cat /tmp/wiki_t27.json | jget .total)
assert_eq "T27 total revisions = 2" "2" "$T27_TOTAL"

# T28: Get first revision (version 1)
REV_ID_1=$(cat /tmp/wiki_t27.json | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const r=j.items.find(x=>x.version===1);console.log(r?r.revision_id:'')})" 2>/dev/null)
assert_not_empty "T28 found revision version 1" "$REV_ID_1"

T28_RESP=$(curl -s -o /tmp/wiki_t28.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions/$REV_ID_1" -H "$AUTH")
assert_status "T28 get revision → 200" "200" "$T28_RESP"
T28_VER=$(cat /tmp/wiki_t28.json | jget .version)
assert_eq "T28 version is 1" "1" "$T28_VER"
T28_BODY=$(cat /tmp/wiki_t28.json | jget .body_json.type)
assert_eq "T28 body_json has doc type" "doc" "$T28_BODY"

# T29: Get version 2
REV_ID_2=$(cat /tmp/wiki_t27.json | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const r=j.items.find(x=>x.version===2);console.log(r?r.revision_id:'')})" 2>/dev/null)
assert_not_empty "T29 found revision version 2" "$REV_ID_2"
T29_RESP=$(curl -s -o /tmp/wiki_t29.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions/$REV_ID_2" -H "$AUTH")
assert_status "T29 get revision 2 → 200" "200" "$T29_RESP"
T29_SUMMARY=$(cat /tmp/wiki_t29.json | jget .summary)
assert_eq "T29 summary matches" "Expanded backstory" "$T29_SUMMARY"

# T30: Restore version 1
T30_RESP=$(curl -s -o /tmp/wiki_t30.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions/$REV_ID_1/restore" -H "$AUTH")
assert_status "T30 restore revision → 200" "200" "$T30_RESP"
T30_REV=$(cat /tmp/wiki_t30.json | jget .revision_count)
assert_eq "T30 revision_count now 3 (restore creates new)" "3" "$T30_REV"

# T31: Verify restored body matches version 1
T31_BODY=$(cat /tmp/wiki_t30.json | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const p=j.body_json?.content?.[0]?.content?.[0]?.text||'';console.log(p)})" 2>/dev/null)
assert_eq "T31 body restored to v1 content" "Hero is the protagonist." "$T31_BODY"

# T32: Check new revision has restore summary
T32_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions" -H "$AUTH")
T32_LATEST_SUMMARY=$(echo "$T32_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const r=j.items.find(x=>x.version===3);console.log(r?r.summary:'')})" 2>/dev/null)
assert_eq "T32 restore revision summary" "Restored from version 1" "$T32_LATEST_SUMMARY"

# ═══════════════════════════════════════════════════════════════════════════════
# T33-T36: Generate Stubs
# ═══════════════════════════════════════════════════════════════════════════════
header "T33-T36: Generate Wiki Stubs"

# T33: Generate stubs — should pick up entity 2 (active, no article yet)
# Entity 1 already has article, entity 3 already has article, entity 4 is draft
T33_RESP=$(curl -s -o /tmp/wiki_t33.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/generate" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{}')
assert_status "T33 generate stubs → 200" "200" "$T33_RESP"
T33_CREATED=$(cat /tmp/wiki_t33.json | jget .created)
assert_eq "T33 created 1 stub (entity 2)" "1" "$T33_CREATED"

# T34: Generate again → 0 (all active entities have articles now)
T34_RESP=$(curl -s -o /tmp/wiki_t34.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/generate" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{}')
assert_status "T34 generate again → 200" "200" "$T34_RESP"
T34_CREATED=$(cat /tmp/wiki_t34.json | jget .created)
assert_eq "T34 no more stubs to create" "0" "$T34_CREATED"

# T35: List all → now 3 articles
T35_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" -H "$AUTH")
T35_TOTAL=$(echo "$T35_RESP" | jget .total)
assert_eq "T35 total articles now 3" "3" "$T35_TOTAL"

# T36: Generate with kind_codes filter
# All active character entities already have articles, so should be 0
T36_RESP=$(curl -s -o /tmp/wiki_t36.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/generate" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"kind_codes":["character"]}')
assert_status "T36 generate with kind filter → 200" "200" "$T36_RESP"
T36_CREATED=$(cat /tmp/wiki_t36.json | jget .created)
assert_eq "T36 no stubs for characters" "0" "$T36_CREATED"

# ═══════════════════════════════════════════════════════════════════════════════
# T37-T40: Delete Article
# ═══════════════════════════════════════════════════════════════════════════════
header "T37-T40: Delete Wiki Article"

# T37: Delete article 3 (location)
T37_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_3" -H "$AUTH")
assert_status "T37 delete article → 204" "204" "$T37_STATUS"

# T38: Verify deleted — get → 404
T38_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_3" -H "$AUTH")
assert_status "T38 deleted article → 404" "404" "$T38_STATUS"

# T39: List → 2 remaining
T39_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki" -H "$AUTH")
T39_TOTAL=$(echo "$T39_RESP" | jget .total)
assert_eq "T39 total now 2 after delete" "2" "$T39_TOTAL"

# T40: Delete non-existent → 404
T40_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$FAKE_UUID" -H "$AUTH")
assert_status "T40 delete non-existent → 404" "404" "$T40_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T41-T44: Edge Cases
# ═══════════════════════════════════════════════════════════════════════════════
header "T41-T44: Edge Cases"

# T41: Wrong user cannot patch
T41_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"status":"draft"}')
assert_status "T41 wrong user patch → 403" "403" "$T41_STATUS"

# T42: Wrong user cannot delete
T42_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" -H "$AUTH2")
assert_status "T42 wrong user delete → 403" "403" "$T42_STATUS"

# T43: Wrong user cannot list revisions
T43_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions" -H "$AUTH2")
assert_status "T43 wrong user revisions → 403" "403" "$T43_STATUS"

# T44: Wrong user cannot generate
T44_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/generate" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{}')
assert_status "T44 wrong user generate → 403" "403" "$T44_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T45-T46: Search
# ═══════════════════════════════════════════════════════════════════════════════
header "T45-T46: Search"

# Set entity 1's "name" attribute value so search can find it
# First get the attr_value_id for the "name" attribute
E1_DETAIL=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID_1" -H "$AUTH")
NAME_AV_ID=$(echo "$E1_DETAIL" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const av=j.attribute_values?.find(a=>a.attribute_def?.code==='name');console.log(av?av.attr_value_id:'')})" 2>/dev/null)
if [ -n "$NAME_AV_ID" ] && [ "$NAME_AV_ID" != "null" ]; then
  curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID_1/attributes/$NAME_AV_ID" \
    -H "Content-Type: application/json" -H "$AUTH" \
    -d '{"original_value":"Hero Zhang"}' > /dev/null
fi

# T45: Search by name
T45_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki?search=Hero" -H "$AUTH")
T45_TOTAL=$(echo "$T45_RESP" | jget .total)
assert_ge "T45 search 'Hero' finds articles" "1" "$T45_TOTAL"

# T46: Search non-existent → 0
T46_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki?search=nonexistent999" -H "$AUTH")
T46_TOTAL=$(echo "$T46_RESP" | jget .total)
assert_eq "T46 search non-existent → 0" "0" "$T46_TOTAL"

# ═══════════════════════════════════════════════════════════════════════════════
# T47-T62: P9-08b — Wiki Settings + Public Reader
# ═══════════════════════════════════════════════════════════════════════════════
header "T47-T52: Wiki Settings (book-service)"

# T47: Default wiki_settings — visibility=off
T47_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID" -H "$AUTH")
T47_VIS=$(echo "$T47_RESP" | jget .wiki_settings.visibility)
assert_eq "T47 default wiki visibility is off" "off" "$T47_VIS"

# T48: Patch wiki_settings to public
T48_STATUS=$(curl -s -o /tmp/wiki_t48.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/books/$BOOK_ID" -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"wiki_settings":{"visibility":"public","community_mode":"suggest","ai_assist":true,"glossary_exposure":"full","auto_generate":false}}')
assert_status "T48 patch wiki_settings → 200" "200" "$T48_STATUS"

# T49: Verify settings persisted
T49_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID" -H "$AUTH")
T49_VIS=$(echo "$T49_RESP" | jget .wiki_settings.visibility)
T49_COMM=$(echo "$T49_RESP" | jget .wiki_settings.community_mode)
T49_AI=$(echo "$T49_RESP" | jget .wiki_settings.ai_assist)
T49_GLOSS=$(echo "$T49_RESP" | jget .wiki_settings.glossary_exposure)
assert_eq "T49 visibility = public" "public" "$T49_VIS"
assert_eq "T49 community_mode = suggest" "suggest" "$T49_COMM"
assert_eq "T49 ai_assist = true" "true" "$T49_AI"
assert_eq "T49 glossary_exposure = full" "full" "$T49_GLOSS"

# T50: Publish article 1 for public tests (it was restored to draft earlier... check status)
# First ensure it's published
curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"status":"published"}' > /dev/null

header "T51-T57: Public Wiki Reader (no JWT)"

# T51: Public list — no auth required, returns published articles
T51_RESP=$(curl -s -o /tmp/wiki_t51.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public")
assert_status "T51 public list → 200 (no auth)" "200" "$T51_RESP"
T51_TOTAL=$(cat /tmp/wiki_t51.json | jget .total)
assert_ge "T51 public list has published articles" "1" "$T51_TOTAL"

# T52: Public list only shows published (not draft)
# Article for entity 2 is draft (generated stub), should not appear
T52_ITEMS=$(cat /tmp/wiki_t51.json | jlen .items)
# Check that no draft items are returned
T52_ALL_PUBLISHED=$(cat /tmp/wiki_t51.json | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.items.every(()=>true)?'yes':'no')})" 2>/dev/null)
assert_eq "T52 all items present" "yes" "$T52_ALL_PUBLISHED"

# T53: Public get article — returns body + infobox
T53_RESP=$(curl -s -o /tmp/wiki_t53.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public/$ARTICLE_ID_1")
assert_status "T53 public get article → 200" "200" "$T53_RESP"
T53_BODY=$(cat /tmp/wiki_t53.json | jget .body_json.type)
assert_eq "T53 body_json has doc type" "doc" "$T53_BODY"
T53_INFOBOX=$(cat /tmp/wiki_t53.json | jlen .infobox)
assert_ge "T53 infobox present" "1" "$T53_INFOBOX"
T53_SPOILER=$(cat /tmp/wiki_t53.json | jget .spoiler_warning)
assert_eq "T53 no spoiler warning" "false" "$T53_SPOILER"

# T54: Public get — non-existent article → 404
T54_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public/$FAKE_UUID")
assert_status "T54 public get non-existent → 404" "404" "$T54_STATUS"

# T55: Public list with search
T55_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public?search=Hero")
T55_TOTAL=$(echo "$T55_RESP" | jget .total)
assert_ge "T55 public search finds published articles" "1" "$T55_TOTAL"

header "T56-T58: Public Wiki — Visibility Off"

# T56: Set visibility back to off
curl -s -X PATCH "$GATEWAY/v1/books/$BOOK_ID" -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"wiki_settings":{"visibility":"off","community_mode":"off","ai_assist":false,"glossary_exposure":"names","auto_generate":false}}' > /dev/null

# T57: Public list → 404 when wiki is off
T57_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public")
assert_status "T57 public list when wiki off → 404" "404" "$T57_STATUS"

# T58: Public get → 404 when wiki is off
T58_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public/$ARTICLE_ID_1")
assert_status "T58 public get when wiki off → 404" "404" "$T58_STATUS"

header "T59-T62: Spoiler Filtering"

# Restore wiki to public for spoiler tests
curl -s -X PATCH "$GATEWAY/v1/books/$BOOK_ID" -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"wiki_settings":{"visibility":"public","community_mode":"off","ai_assist":false,"glossary_exposure":"names","auto_generate":false}}' > /dev/null

# T59: Set spoiler_chapters on article 1
# Use fake chapter UUIDs — the chapter doesn't need to exist for the array
curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d "{\"spoiler_chapters\":[\"$FAKE_CH1\"]}" > /dev/null

# T60: Public get without max_chapter_index — no spoiler warning (no filtering)
T60_RESP=$(curl -s -o /tmp/wiki_t60.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public/$ARTICLE_ID_1")
assert_status "T60 public get without index → 200" "200" "$T60_RESP"
T60_SPOILER=$(cat /tmp/wiki_t60.json | jget .spoiler_warning)
assert_eq "T60 no spoiler when no max_chapter_index" "false" "$T60_SPOILER"

# T61: Public get with max_chapter_index — body should be present (chapter not found in book = no spoiler)
T61_RESP=$(curl -s -o /tmp/wiki_t61.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/public/$ARTICLE_ID_1?max_chapter_index=0")
assert_status "T61 public get with max_chapter_index → 200" "200" "$T61_RESP"

# T62: Non-existent book → 404
FAKE_BOOK="00000000-0000-0000-0000-000000000088"
T62_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$FAKE_BOOK/wiki/public")
assert_status "T62 public list fake book → 404" "404" "$T62_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T63-T80: P9-08c — Community Suggestions
# ═══════════════════════════════════════════════════════════════════════════════
header "T63-T66: Suggestion Setup + Gates"

# Ensure wiki is public with community_mode=suggest
curl -s -X PATCH "$GATEWAY/v1/books/$BOOK_ID" -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"wiki_settings":{"visibility":"public","community_mode":"suggest","ai_assist":false,"glossary_exposure":"names","auto_generate":false}}' > /dev/null

# Ensure article 1 is published
curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"status":"published"}' > /dev/null

# T63: Owner cannot submit suggestion to own book
T63_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"diff_json":{"type":"doc","content":[]},"reason":"test"}')
assert_status "T63 owner cannot suggest → 403" "403" "$T63_STATUS"

# T64: No auth → 401
T64_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" \
  -d '{"diff_json":{"type":"doc","content":[]},"reason":"test"}')
assert_status "T64 no auth suggest → 401" "401" "$T64_STATUS"

# T65: Community user submits suggestion
T65_RESP=$(curl -s -o /tmp/wiki_t65.json -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"diff_json":{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"Community edit."}]}]},"reason":"Fixed typo"}')
assert_status "T65 community suggest → 201" "201" "$T65_RESP"
SUG_ID_1=$(cat /tmp/wiki_t65.json | jget .suggestion_id)
assert_not_empty "T65 got suggestion_id" "$SUG_ID_1"
T65_STATUS_VAL=$(cat /tmp/wiki_t65.json | jget .status)
assert_eq "T65 status is pending" "pending" "$T65_STATUS_VAL"
T65_REASON=$(cat /tmp/wiki_t65.json | jget .reason)
assert_eq "T65 reason saved" "Fixed typo" "$T65_REASON"

# T66: Missing diff_json → 422
T66_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"reason":"no diff"}')
assert_status "T66 missing diff_json → 422" "422" "$T66_STATUS"

header "T67-T69: List Suggestions"

# Submit a second suggestion
curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"diff_json":{"type":"doc","content":[{"type":"paragraph","content":[{"type":"text","text":"Another edit."}]}]},"reason":"Added detail"}' > /tmp/wiki_sug2.json
SUG_ID_2=$(cat /tmp/wiki_sug2.json | jget .suggestion_id)

# T67: Owner lists all suggestions
T67_RESP=$(curl -s -o /tmp/wiki_t67.json -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/suggestions" -H "$AUTH")
assert_status "T67 list suggestions → 200" "200" "$T67_RESP"
T67_TOTAL=$(cat /tmp/wiki_t67.json | jget .total)
assert_eq "T67 total suggestions = 2" "2" "$T67_TOTAL"

# T68: Non-owner cannot list suggestions
T68_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/suggestions" -H "$AUTH2")
assert_status "T68 non-owner list → 403" "403" "$T68_STATUS"

# T69: Filter by status=pending
T69_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/suggestions?status=pending" -H "$AUTH")
T69_TOTAL=$(echo "$T69_RESP" | jget .total)
assert_eq "T69 pending suggestions = 2" "2" "$T69_TOTAL"

header "T70-T74: Accept Suggestion"

# T70: Accept first suggestion
T70_RESP=$(curl -s -o /tmp/wiki_t70.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions/$SUG_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"action":"accept","reviewer_note":"Good catch!"}')
assert_status "T70 accept suggestion → 200" "200" "$T70_RESP"
T70_STATUS_VAL=$(cat /tmp/wiki_t70.json | jget .status)
assert_eq "T70 status = accepted" "accepted" "$T70_STATUS_VAL"
T70_NOTE=$(cat /tmp/wiki_t70.json | jget .reviewer_note)
assert_eq "T70 reviewer_note saved" "Good catch!" "$T70_NOTE"
T70_REVIEWED=$(cat /tmp/wiki_t70.json | jget .reviewed_at)
assert_not_empty "T70 reviewed_at set" "$T70_REVIEWED"

# T71: Article body updated with suggestion content
T71_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" -H "$AUTH")
T71_BODY=$(echo "$T71_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const t=j.body_json?.content?.[0]?.content?.[0]?.text||'';console.log(t)})" 2>/dev/null)
assert_eq "T71 article body = suggestion content" "Community edit." "$T71_BODY"

# T72: New revision created with author_type=community
T72_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/revisions" -H "$AUTH")
T72_LATEST=$(echo "$T72_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const r=j.items[0];console.log(r?r.author_type:'')})" 2>/dev/null)
assert_eq "T72 latest revision author_type = community" "community" "$T72_LATEST"

# T73: Cannot accept already-reviewed suggestion
T73_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions/$SUG_ID_1" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"action":"accept"}')
assert_status "T73 re-accept → 409" "409" "$T73_STATUS"

# T74: Invalid action → 422
T74_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions/$SUG_ID_2" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"action":"maybe"}')
assert_status "T74 invalid action → 422" "422" "$T74_STATUS"

header "T75-T78: Reject Suggestion"

# T75: Reject second suggestion
T75_RESP=$(curl -s -o /tmp/wiki_t75.json -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions/$SUG_ID_2" \
  -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"action":"reject","reviewer_note":"Not relevant"}')
assert_status "T75 reject suggestion → 200" "200" "$T75_RESP"
T75_STATUS_VAL=$(cat /tmp/wiki_t75.json | jget .status)
assert_eq "T75 status = rejected" "rejected" "$T75_STATUS_VAL"

# T76: Article body NOT changed after reject
T76_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1" -H "$AUTH")
T76_BODY=$(echo "$T76_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const t=j.body_json?.content?.[0]?.content?.[0]?.text||'';console.log(t)})" 2>/dev/null)
assert_eq "T76 body unchanged after reject" "Community edit." "$T76_BODY"

# T77: Filter accepted
T77_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/suggestions?status=accepted" -H "$AUTH")
T77_TOTAL=$(echo "$T77_RESP" | jget .total)
assert_eq "T77 accepted = 1" "1" "$T77_TOTAL"

# T78: Filter pending → 0
T78_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/suggestions?status=pending" -H "$AUTH")
T78_TOTAL=$(echo "$T78_RESP" | jget .total)
assert_eq "T78 pending = 0" "0" "$T78_TOTAL"

header "T79-T80: Suggestion Gates"

# T79: Disable community_mode → suggest fails
curl -s -X PATCH "$GATEWAY/v1/books/$BOOK_ID" -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"wiki_settings":{"visibility":"public","community_mode":"off","ai_assist":false,"glossary_exposure":"names","auto_generate":false}}' > /dev/null
T79_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"diff_json":{"type":"doc","content":[]},"reason":"test"}')
assert_status "T79 suggest when mode=off → 403" "403" "$T79_STATUS"

# T80: Non-owner cannot review
curl -s -X PATCH "$GATEWAY/v1/books/$BOOK_ID" -H "Content-Type: application/json" -H "$AUTH" \
  -d '{"wiki_settings":{"visibility":"public","community_mode":"suggest","ai_assist":false,"glossary_exposure":"names","auto_generate":false}}' > /dev/null
# Submit one more suggestion for this test
T80_SUG=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"diff_json":{"type":"doc","content":[]},"reason":"test"}')
SUG_ID_3=$(echo "$T80_SUG" | jget .suggestion_id)
T80_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/wiki/$ARTICLE_ID_1/suggestions/$SUG_ID_3" \
  -H "Content-Type: application/json" -H "$AUTH2" \
  -d '{"action":"accept"}')
assert_status "T80 non-owner review → 403" "403" "$T80_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "════════════════════════════════════════════════"
printf "  Wiki Integration Tests: \033[32m%d passed\033[0m" "$PASS"
if [ "$FAIL" -gt 0 ]; then printf ", \033[31m%d failed\033[0m" "$FAIL"; fi
echo ""
echo "════════════════════════════════════════════════"

[ "$FAIL" -eq 0 ] || exit 1
