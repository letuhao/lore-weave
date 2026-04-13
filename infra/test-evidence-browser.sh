#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Evidence Browser Integration Test (G-EV-1)
#
# Tests: entity-level evidence list endpoint with pagination, filters, sort,
#        language fallback, plus create/patch/delete CRUD.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-evidence-browser.sh
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

assert_gte() {
  local label="$1" min="$2" actual="$3"
  if [ "$actual" -ge "$min" ] 2>/dev/null; then
    green "$label ($actual >= $min)"; PASS=$((PASS+1))
  else
    red "$label (expected >= $min, got: $actual)"; FAIL=$((FAIL+1))
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
        console.log(v===null||v===undefined?'null':typeof v==='object'?JSON.stringify(v):v);
      } catch { console.log('PARSE_ERROR'); }
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
      } catch { console.log('0'); }
    });
  " 2>/dev/null || echo "0"
}

# ══════════════════════════════════════════════════════════════════════════════
# Setup
# ══════════════════════════════════════════════════════════════════════════════
header "Setup: Register + Login + Create Book + Entity"

UNAME="ev_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"EV Test\"}" > /dev/null

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Evidence Test Book","original_language":"zh"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Setup: created book" "$BOOK_ID"

# Get first kind (character)
KINDS=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
KIND_ID=$(echo "$KINDS" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const k=JSON.parse(d).find(k=>k.code==='character');
    console.log(k?k.kind_id:'');
  });" 2>/dev/null)
assert_not_empty "Setup: got character kind_id" "$KIND_ID"

# Create entity
ENTITY_RESP=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"kind_id\":\"$KIND_ID\"}")
ENTITY_ID=$(echo "$ENTITY_RESP" | jget .entity_id)
assert_not_empty "Setup: created entity" "$ENTITY_ID"

# Get entity detail to find attr_value_ids
DETAIL=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID")
ATTR1_ID=$(echo "$DETAIL" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const e=JSON.parse(d);
    const av=e.attribute_values[0];
    console.log(av?av.attr_value_id:'');
  });" 2>/dev/null)
ATTR2_ID=$(echo "$DETAIL" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const e=JSON.parse(d);
    const av=e.attribute_values[1];
    console.log(av?av.attr_value_id:'');
  });" 2>/dev/null)
assert_not_empty "Setup: got attr_value_id 1" "$ATTR1_ID"
assert_not_empty "Setup: got attr_value_id 2" "$ATTR2_ID"

# ══════════════════════════════════════════════════════════════════════════════
# T01: List evidences (empty)
# ══════════════════════════════════════════════════════════════════════════════
header "T01: List evidences (empty)"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences")
T01_TOTAL=$(echo "$RESP" | jget .total)
T01_ITEMS=$(echo "$RESP" | jlen .items)
assert_eq "T01a total=0" "0" "$T01_TOTAL"
assert_eq "T01b items=0" "0" "$T01_ITEMS"

# ══════════════════════════════════════════════════════════════════════════════
# T02: Create evidences
# ══════════════════════════════════════════════════════════════════════════════
header "T02: Create evidences"

# Evidence 1: quote on attr1
EV1_RESP=$(curl -s -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/attributes/$ATTR1_ID/evidences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"evidence_type":"quote","original_text":"他是天下第一剑客","original_language":"zh","chapter_title":"Chapter 1","chapter_index":1,"block_or_line":"p.5"}')
EV1_ID=$(echo "$EV1_RESP" | jget .evidence_id)
assert_not_empty "T02a created quote evidence" "$EV1_ID"
EV1_TYPE=$(echo "$EV1_RESP" | jget .evidence_type)
assert_eq "T02b type=quote" "quote" "$EV1_TYPE"

# Evidence 2: summary on attr1
EV2_RESP=$(curl -s -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/attributes/$ATTR1_ID/evidences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"evidence_type":"summary","original_text":"主角是一位武林高手","original_language":"zh","chapter_title":"Chapter 2","chapter_index":2,"block_or_line":"p.12"}')
EV2_ID=$(echo "$EV2_RESP" | jget .evidence_id)
assert_not_empty "T02c created summary evidence" "$EV2_ID"

# Evidence 3: reference on attr2
EV3_RESP=$(curl -s -X POST \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/attributes/$ATTR2_ID/evidences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"evidence_type":"reference","original_text":"参见第一章描述","original_language":"zh","chapter_title":"Chapter 3","chapter_index":3,"block_or_line":"p.20","note":"cross-reference"}')
EV3_ID=$(echo "$EV3_RESP" | jget .evidence_id)
assert_not_empty "T02d created reference evidence" "$EV3_ID"

# ══════════════════════════════════════════════════════════════════════════════
# T03: List evidences (all)
# ══════════════════════════════════════════════════════════════════════════════
header "T03: List evidences (all 3)"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences")
T03_TOTAL=$(echo "$RESP" | jget .total)
T03_ITEMS=$(echo "$RESP" | jlen .items)
assert_eq "T03a total=3" "3" "$T03_TOTAL"
assert_eq "T03b items=3" "3" "$T03_ITEMS"

# Check first item has attribute_name
T03_ATTR_NAME=$(echo "$RESP" | jget .items.0.attribute_name)
assert_not_empty "T03c has attribute_name" "$T03_ATTR_NAME"

# Check available_attributes
T03_AVAIL_ATTRS=$(echo "$RESP" | jlen .available_attributes)
assert_gte "T03d available_attributes >= 1" "1" "$T03_AVAIL_ATTRS"

# Check available_chapters
T03_AVAIL_CH=$(echo "$RESP" | jlen .available_chapters)
assert_eq "T03e available_chapters=3" "3" "$T03_AVAIL_CH"

# ══════════════════════════════════════════════════════════════════════════════
# T04: Filter by evidence_type
# ══════════════════════════════════════════════════════════════════════════════
header "T04: Filter by evidence_type"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?evidence_type=quote")
T04_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T04a filter type=quote → 1" "1" "$T04_TOTAL"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?evidence_type=summary")
T04B_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T04b filter type=summary → 1" "1" "$T04B_TOTAL"

# ══════════════════════════════════════════════════════════════════════════════
# T05: Filter by attr_value_id
# ══════════════════════════════════════════════════════════════════════════════
header "T05: Filter by attr_value_id"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?attr_value_id=$ATTR1_ID")
T05_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T05a filter attr1 → 2" "2" "$T05_TOTAL"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?attr_value_id=$ATTR2_ID")
T05B_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T05b filter attr2 → 1" "1" "$T05B_TOTAL"

# ══════════════════════════════════════════════════════════════════════════════
# T06: Sort
# ══════════════════════════════════════════════════════════════════════════════
header "T06: Sort"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?sort_by=chapter_index&sort_dir=asc")
T06_FIRST_CH=$(echo "$RESP" | jget .items.0.chapter_title)
assert_eq "T06a sort chapter asc → Ch1 first" "Chapter 1" "$T06_FIRST_CH"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?sort_by=chapter_index&sort_dir=desc")
T06_FIRST_DESC=$(echo "$RESP" | jget .items.0.chapter_title)
assert_eq "T06b sort chapter desc → Ch3 first" "Chapter 3" "$T06_FIRST_DESC"

# ══════════════════════════════════════════════════════════════════════════════
# T07: Pagination
# ══════════════════════════════════════════════════════════════════════════════
header "T07: Pagination"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?limit=2&offset=0")
T07_ITEMS=$(echo "$RESP" | jlen .items)
T07_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T07a limit=2 → 2 items" "2" "$T07_ITEMS"
assert_eq "T07b total still 3" "3" "$T07_TOTAL"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?limit=2&offset=2")
T07C_ITEMS=$(echo "$RESP" | jlen .items)
assert_eq "T07c offset=2 → 1 item" "1" "$T07C_ITEMS"

# ══════════════════════════════════════════════════════════════════════════════
# T08: Language fallback
# ══════════════════════════════════════════════════════════════════════════════
header "T08: Language fallback"

# Request English — no translations exist, should fallback to original
RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?language=en")
T08_DISPLAY=$(echo "$RESP" | jget .items.0.display_text)
T08_LANG=$(echo "$RESP" | jget .items.0.display_language)
assert_not_empty "T08a display_text present (fallback)" "$T08_DISPLAY"
assert_eq "T08b display_language=zh (fallback)" "zh" "$T08_LANG"

# Without language param — should return original
RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences")
T08C_LANG=$(echo "$RESP" | jget .items.0.display_language)
assert_eq "T08c no lang param → original_language" "zh" "$T08C_LANG"

# ══════════════════════════════════════════════════════════════════════════════
# T09: Patch evidence
# ══════════════════════════════════════════════════════════════════════════════
header "T09: Patch evidence"

PATCH_RESP=$(curl -s -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/attributes/$ATTR1_ID/evidences/$EV1_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"original_text":"他是天下第一剑客也是最强的","note":"updated note","evidence_type":"summary"}')
T09_TEXT=$(echo "$PATCH_RESP" | jget .original_text)
assert_eq "T09a text updated" "他是天下第一剑客也是最强的" "$T09_TEXT"

# Verify in list
RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?evidence_type=summary")
T09_SUMMARY_COUNT=$(echo "$RESP" | jget .total)
assert_eq "T09b now 2 summaries" "2" "$T09_SUMMARY_COUNT"

# ══════════════════════════════════════════════════════════════════════════════
# T10: Delete evidence
# ══════════════════════════════════════════════════════════════════════════════
header "T10: Delete evidence"

DEL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/attributes/$ATTR2_ID/evidences/$EV3_ID" \
  -H "$AUTH")
assert_status "T10a delete returns 204" "204" "$DEL_STATUS"

RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences")
T10_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T10b total now 2" "2" "$T10_TOTAL"

# ══════════════════════════════════════════════════════════════════════════════
# T11: Validation
# ══════════════════════════════════════════════════════════════════════════════
header "T11: Validation"

# Invalid evidence_type filter
V1_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?evidence_type=invalid")
assert_status "T11a invalid evidence_type → 400" "400" "$V1_STATUS"

# Invalid attr_value_id filter
V2_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?attr_value_id=not-a-uuid")
assert_status "T11b invalid attr_value_id → 400" "400" "$V2_STATUS"

# Invalid chapter_id filter
V3_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?chapter_id=bad")
assert_status "T11c invalid chapter_id → 400" "400" "$V3_STATUS"

# ══════════════════════════════════════════════════════════════════════════════
# T12: Combined filters
# ══════════════════════════════════════════════════════════════════════════════
header "T12: Combined filters"

RESP=$(curl -s -H "$AUTH" \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/evidences?evidence_type=summary&attr_value_id=$ATTR1_ID")
T12_TOTAL=$(echo "$RESP" | jget .total)
assert_eq "T12a summary+attr1 → 2" "2" "$T12_TOTAL"

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════

echo ""
echo "═══════════════════════════════════════════════════════════════"
printf "  Evidence Browser: \033[32m%d passed\033[0m" "$PASS"
if [ "$FAIL" -gt 0 ]; then
  printf ", \033[31m%d failed\033[0m" "$FAIL"
fi
echo ""
echo "═══════════════════════════════════════════════════════════════"
exit "$FAIL"
