#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Glossary Service Integration Test
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-glossary.sh
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
  if [ -n "$value" ] && [ "$value" != "null" ] && [ "$value" != "None" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (was empty or null)"; FAIL=$((FAIL+1))
  fi
}

# Pipe-safe JSON extraction: echo "$JSON" | jv '.get("key","")'
jv() { python3 -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null || echo ""; }

# ── Setup: Auth ─────────────────────────────────────────────────────────────
header "Setup: Authenticate"

REG_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"glosstest2","email":"glosstest2@test.com","password":"Test1234!"}')
TOKEN=$(echo "$REG_RESP" | jv 'd.get("access_token","")')

if [ -z "$TOKEN" ]; then
  LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"glosstest2@test.com","password":"Test1234!"}')
  TOKEN=$(echo "$LOGIN_RESP" | jv 'd.get("access_token","")')
fi

assert_not_empty "Got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# ── Setup: Create book ──────────────────────────────────────────────────────
header "Setup: Create book"

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Glossary Test Book","original_language":"en","target_language":"vi"}')
BOOK_ID=$(echo "$BOOK_RESP" | jv 'd.get("book_id","")')
assert_not_empty "Created book" "$BOOK_ID"

# ── T1: List Kinds ──────────────────────────────────────────────────────────
header "T1: List Kinds"

KINDS_RESP=$(curl -s "$GATEWAY/v1/glossary/kinds" -H "$AUTH")
KIND_COUNT=$(echo "$KINDS_RESP" | jv 'len(d)')
assert_not_empty "T1: Got kinds ($KIND_COUNT)" "$KIND_COUNT"

KIND_ID=$(echo "$KINDS_RESP" | jv 'd[0]["kind_id"] if d else ""')
KIND_NAME=$(echo "$KINDS_RESP" | jv 'd[0]["name"] if d else ""')
ATTR_COUNT=$(echo "$KINDS_RESP" | jv 'len(d[0].get("default_attributes",[])) if d else 0')
assert_not_empty "T1: First kind ID" "$KIND_ID"
echo "    Using kind: $KIND_NAME ($KIND_ID) with $ATTR_COUNT attributes"

# ── T2: Create Entity ──────────────────────────────────────────────────────
header "T2: Create Entity"

CREATE_RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"kind_id\":\"$KIND_ID\"}")
CREATE_STATUS=$(echo "$CREATE_RESP" | tail -1)
CREATE_BODY=$(echo "$CREATE_RESP" | sed '$d')

assert_eq "T2: Create returns 201" "201" "$CREATE_STATUS"

ENTITY_ID=$(echo "$CREATE_BODY" | jv 'd.get("entity_id","")')
assert_not_empty "T2: Got entity_id" "$ENTITY_ID"

ENTITY_KIND=$(echo "$CREATE_BODY" | jv 'd.get("kind",{}).get("name","")')
assert_eq "T2: Entity kind = $KIND_NAME" "$KIND_NAME" "$ENTITY_KIND"

ENTITY_ATTRS=$(echo "$CREATE_BODY" | jv 'len(d.get("attribute_values",[]))')
assert_eq "T2: Entity has $ATTR_COUNT attributes" "$ATTR_COUNT" "$ENTITY_ATTRS"

# ── T3: Get Entity Detail ──────────────────────────────────────────────────
header "T3: Get Entity Detail"

DETAIL_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID" -H "$AUTH")
DETAIL_ID=$(echo "$DETAIL_RESP" | jv 'd.get("entity_id","")')
assert_eq "T3: Detail returns correct entity" "$ENTITY_ID" "$DETAIL_ID"

DETAIL_STATUS=$(echo "$DETAIL_RESP" | jv 'd.get("status","")')
assert_eq "T3: Default status is draft" "draft" "$DETAIL_STATUS"

ATTR_VALUE_ID=$(echo "$DETAIL_RESP" | python3 -c "import sys,json; avs=json.load(sys.stdin).get('attribute_values',[]); print(avs[0]['attr_value_id'] if avs else '')" 2>/dev/null || echo "")
ATTR_NAME=$(echo "$DETAIL_RESP" | python3 -c "import sys,json; avs=json.load(sys.stdin).get('attribute_values',[]); print(avs[0]['attribute_def']['name'] if avs else '')" 2>/dev/null || echo "")
assert_not_empty "T3: Got first attr_value_id" "$ATTR_VALUE_ID"
echo "    First attribute: $ATTR_NAME ($ATTR_VALUE_ID)"

# ── T4: Patch Attribute Value ──────────────────────────────────────────────
header "T4: Patch Attribute Value"

PATCH_RESP=$(curl -s -w "\n%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID/attributes/$ATTR_VALUE_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"original_value":"Aldric the Hero"}')
PATCH_STATUS=$(echo "$PATCH_RESP" | tail -1)
assert_eq "T4: Patch returns 200" "200" "$PATCH_STATUS"

# Verify persisted
VERIFY_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID" -H "$AUTH")
SAVED_VAL=$(echo "$VERIFY_RESP" | python3 -c "import sys,json; avs=json.load(sys.stdin).get('attribute_values',[]); print(next((a['original_value'] for a in avs if a['attr_value_id']=='$ATTR_VALUE_ID'),''))" 2>/dev/null || echo "")
assert_eq "T4: Value persisted" "Aldric the Hero" "$SAVED_VAL"

# ── T5: Patch Entity Status ───────────────────────────────────────────────
header "T5: Patch Entity Status"

STATUS_RESP=$(curl -s -w "\n%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"status":"active"}')
STATUS_CODE=$(echo "$STATUS_RESP" | tail -1)
assert_eq "T5: Patch status returns 200" "200" "$STATUS_CODE"

VERIFY_STATUS=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID" -H "$AUTH" | jv 'd.get("status","")')
assert_eq "T5: Status = active" "active" "$VERIFY_STATUS"

# ── T6: List + Search + Filter ─────────────────────────────────────────────
header "T6: List + Search + Filter"

LIST_TOTAL=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "$AUTH" | jv 'd.get("total",0)')
assert_eq "T6: List shows 1 entity" "1" "$LIST_TOTAL"

# Create second entity
curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"kind_id\":\"$KIND_ID\"}" > /dev/null

LIST2_TOTAL=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "$AUTH" | jv 'd.get("total",0)')
assert_eq "T6: List shows 2 entities" "2" "$LIST2_TOTAL"

SEARCH_TOTAL=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities?search=Aldric" -H "$AUTH" | jv 'd.get("total",0)')
assert_eq "T6: Search 'Aldric' finds 1" "1" "$SEARCH_TOTAL"

FILTER_TOTAL=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities?status=active" -H "$AUTH" | jv 'd.get("total",0)')
assert_eq "T6: Filter status=active finds 1" "1" "$FILTER_TOTAL"

# ── T7: Delete Entity ─────────────────────────────────────────────────────
header "T7: Delete Entity"

DEL_RESP=$(curl -s -w "\n%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID" -H "$AUTH")
DEL_STATUS=$(echo "$DEL_RESP" | tail -1)
assert_eq "T7: Delete returns 204" "204" "$DEL_STATUS"

LIST3_TOTAL=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" -H "$AUTH" | jv 'd.get("total",0)')
assert_eq "T7: List shows 1 after delete" "1" "$LIST3_TOTAL"

# ── Summary ─────────────────────────────────────────────────────────────────
header "RESULTS"
printf "\033[32m  PASS: %d\033[0m\n" "$PASS"
printf "\033[31m  FAIL: %d\033[0m\n" "$FAIL"
echo ""

if [ "$FAIL" -gt 0 ]; then
  printf "\033[1;31mGLOSSARY TEST: FAILED\033[0m\n"
  exit 1
else
  printf "\033[1;32mGLOSSARY TEST: PASSED\033[0m\n"
  exit 0
fi
