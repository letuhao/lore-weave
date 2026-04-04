#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Kind Editor Enhancement Integration Test (BE-KE-01)
#
# Tests description field on entity_kinds and attribute_definitions
# through the gateway.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-kind-editor-enhance.sh
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

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -q "$needle"; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected to contain: $needle)"; FAIL=$((FAIL+1))
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
        const keys='${path}'.slice(1).split('.').filter(Boolean);
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        if(v===undefined||v===null) console.log('');
        else console.log(typeof v==='object'?JSON.stringify(v):v);
      } catch { console.log(''); }
    });
  " 2>/dev/null || echo ""
}

# JSON array length
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

# ── Setup: Auth ──────────────────────────────────────────────────────────────
header "Setup: Register + Login"

UNAME="ke_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null 2>&1 || true

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# ═══════════════════════════════════════════════════════════════════════════════
# BE-KE-01: Description field on kinds
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-01a: listKinds returns description field"

# T01: List kinds — system kinds should have description=null (not set in seed)
KINDS_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
KIND_COUNT=$(echo "$KINDS_RESP" | jlen .)
assert_not_empty "T01 list kinds returns items" "$KIND_COUNT"

# T02: First kind (Character) should have description key in response
T02_DESC=$(echo "$KINDS_RESP" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log('description' in j[0] ? 'HAS_KEY' : 'MISSING');
  });" 2>/dev/null)
assert_eq "T02 listKinds includes description key" "HAS_KEY" "$T02_DESC"

# T03: System kind description should be null (seed doesn't set it)
T03_VAL=$(echo "$KINDS_RESP" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j[0].description === null ? 'null' : j[0].description);
  });" 2>/dev/null)
assert_eq "T03 system kind description is null" "null" "$T03_VAL"

# T04: Attributes also have description key
T04_ATTR_DESC=$(echo "$KINDS_RESP" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const attrs=j[0].default_attributes;
    console.log(attrs.length>0 && 'description' in attrs[0] ? 'HAS_KEY' : 'MISSING');
  });" 2>/dev/null)
assert_eq "T04 attr has description key" "HAS_KEY" "$T04_ATTR_DESC"

# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-01b: createKind with description"

# T05: Create kind with description
C1=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"test_spell","name":"Spell","description":"A magical ability or incantation"}')
NEW_KIND_ID=$(echo "$C1" | jget .kind_id)
assert_not_empty "T05 create kind with description (got id)" "$NEW_KIND_ID"
assert_eq "T05 create kind description" "A magical ability or incantation" "$(echo "$C1" | jget .description)"

# T06: Create kind without description — should be null
C2=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"test_nodesc","name":"No Desc Kind"}')
NEW_KIND_ID2=$(echo "$C2" | jget .kind_id)
assert_not_empty "T06 create kind without description (got id)" "$NEW_KIND_ID2"
T06_DESC=$(echo "$C2" | jget .description)
assert_empty_or_null "T06 description is null when not provided" "$T06_DESC"

# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-01c: patchKind description"

# T07: Patch kind to set description
PATCH1_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID2" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"description":"Now has a description"}')
assert_status "T07 patch kind set description" "200" "$PATCH1_STATUS"

# T08: Verify patched description persists
PATCH1_RESP=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID2" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"No Desc Kind"}')
assert_eq "T08 patched description persists" "Now has a description" "$(echo "$PATCH1_RESP" | jget .description)"

# T09: Patch kind to clear description (set to null)
PATCH2=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID2" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"description":null}')
T09_DESC=$(echo "$PATCH2" | jget .description)
assert_empty_or_null "T09 patch clear description to null" "$T09_DESC"

# T10: Patch kind description doesn't affect other fields
assert_eq "T10 name unchanged after description patch" "No Desc Kind" "$(echo "$PATCH2" | jget .name)"

# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-01d: createAttrDef with description"

# T11: Create attribute with description
A1=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"mana_cost","name":"Mana Cost","field_type":"number","description":"Energy required to cast"}')
ATTR_ID=$(echo "$A1" | jget .attr_def_id)
assert_not_empty "T11 create attr with description (got id)" "$ATTR_ID"
assert_eq "T11 attr description" "Energy required to cast" "$(echo "$A1" | jget .description)"

# T12: Create attribute without description — should be null
A2=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"cooldown","name":"Cooldown","field_type":"number"}')
ATTR_ID2=$(echo "$A2" | jget .attr_def_id)
assert_not_empty "T12 create attr without description (got id)" "$ATTR_ID2"
T12_DESC=$(echo "$A2" | jget .description)
assert_empty_or_null "T12 attr description null when not provided" "$T12_DESC"

# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-01e: patchAttrDef description"

# T13: Patch attribute to set description
APATCH1=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID2" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"description":"Time between uses in seconds"}')
assert_eq "T13 patch attr set description" "Time between uses in seconds" "$(echo "$APATCH1" | jget .description)"

# T14: Patch attribute to clear description
APATCH2=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID2" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"description":null}')
T14_DESC=$(echo "$APATCH2" | jget .description)
assert_empty_or_null "T14 patch attr clear description" "$T14_DESC"

# T15: Patch attr description doesn't affect other fields
assert_eq "T15 attr name unchanged" "Cooldown" "$(echo "$APATCH2" | jget .name)"
assert_eq "T15 attr field_type unchanged" "number" "$(echo "$APATCH2" | jget .field_type)"

# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-01f: listKinds reflects created kinds + descriptions"

# T16: List kinds includes our new kinds with descriptions
KINDS2=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T16_SPELL_DESC=$(echo "$KINDS2" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    console.log(spell ? spell.description||'' : 'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T16 listKinds shows Spell description" "A magical ability or incantation" "$T16_SPELL_DESC"

# T17: Attributes in listKinds show description
T17_ATTR_DESC=$(echo "$KINDS2" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    if(!spell) { console.log('NOT_FOUND'); return; }
    const mc=spell.default_attributes.find(a=>a.code==='mana_cost');
    console.log(mc ? mc.description||'' : 'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T17 listKinds attr description" "Energy required to cast" "$T17_ATTR_DESC"

# ═══════════════════════════════════════════════════════════════════════════════
# BE-KE-02: Entity count per kind
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-02a: entity_count in listKinds"

# Create a book for entity creation
BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"KE Test Book","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Setup: created book for entity tests" "$BOOK_ID"

# T18: listKinds includes entity_count key
KINDS3=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T18_HAS_KEY=$(echo "$KINDS3" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log('entity_count' in j[0] ? 'HAS_KEY' : 'MISSING');
  });" 2>/dev/null)
assert_eq "T18 listKinds has entity_count key" "HAS_KEY" "$T18_HAS_KEY"

# T19: test_spell kind (custom, no entities) should have entity_count=0
T19_COUNT=$(echo "$KINDS3" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    console.log(spell ? spell.entity_count : 'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T19 test_spell entity_count=0" "0" "$T19_COUNT"

# T20: Get Character kind_id for entity creation
CHAR_KIND_ID=$(echo "$KINDS3" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    console.log(ch ? ch.kind_id : '');
  });" 2>/dev/null)
assert_not_empty "T20 found character kind_id" "$CHAR_KIND_ID"

# T21: Get current Character entity_count before creating
T21_BEFORE=$(echo "$KINDS3" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    console.log(ch ? ch.entity_count : -1);
  });" 2>/dev/null)

# Create an entity of type Character
E1=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/entities" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"kind_id\":\"$CHAR_KIND_ID\"}")
ENTITY_ID=$(echo "$E1" | jget .entity_id)
assert_not_empty "T21 created character entity" "$ENTITY_ID"

# T22: listKinds now shows entity_count incremented by 1
KINDS4=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T22_AFTER=$(echo "$KINDS4" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    console.log(ch ? ch.entity_count : -1);
  });" 2>/dev/null)
T22_EXPECTED=$((T21_BEFORE + 1))
assert_eq "T22 character entity_count incremented" "$T22_EXPECTED" "$T22_AFTER"

# T23: Soft-delete the entity, count should go back down
curl -s -X DELETE "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$ENTITY_ID" \
  -H "$AUTH" > /dev/null 2>&1

KINDS5=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T23_AFTER_DEL=$(echo "$KINDS5" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    console.log(ch ? ch.entity_count : -1);
  });" 2>/dev/null)
assert_eq "T23 entity_count decremented after soft-delete" "$T21_BEFORE" "$T23_AFTER_DEL"

# T24: System kinds with no entities return entity_count=0 (or >= 0, not null/undefined)
T24_TERM_COUNT=$(echo "$KINDS5" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const t=j.find(k=>k.code==='terminology');
    console.log(t ? (typeof t.entity_count === 'number' ? 'NUMBER' : typeof t.entity_count) : 'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T24 entity_count is a number (not null)" "NUMBER" "$T24_TERM_COUNT"

# ═══════════════════════════════════════════════════════════════════════════════
# BE-KE-03: Attribute is_active toggle
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-03a: is_active in listKinds"

# T25: listKinds attrs have is_active key
KINDS6=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T25_HAS_KEY=$(echo "$KINDS6" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const attrs=j[0].default_attributes;
    console.log(attrs.length>0 && 'is_active' in attrs[0] ? 'HAS_KEY' : 'MISSING');
  });" 2>/dev/null)
assert_eq "T25 attr has is_active key" "HAS_KEY" "$T25_HAS_KEY"

# T26: Existing attrs default to is_active=true
T26_VAL=$(echo "$KINDS6" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const attrs=j[0].default_attributes;
    console.log(attrs.length>0 && attrs[0].is_active === true ? 'true' : 'false');
  });" 2>/dev/null)
assert_eq "T26 existing attr is_active defaults true" "true" "$T26_VAL"

header "BE-KE-03b: createAttrDef returns is_active=true"

# T27: Create attr — response has is_active=true
A3=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"toggle_test","name":"Toggle Test","field_type":"text"}')
ATTR_ID3=$(echo "$A3" | jget .attr_def_id)
assert_not_empty "T27 create attr (got id)" "$ATTR_ID3"
T27_ACTIVE=$(echo "$A3" | jget .is_active)
assert_eq "T27 new attr is_active=true" "true" "$T27_ACTIVE"

header "BE-KE-03c: patchAttrDef toggle is_active"

# T28: Patch attr to deactivate (is_active=false)
APATCH3=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"is_active":false}')
assert_eq "T28 patch is_active=false" "false" "$(echo "$APATCH3" | jget .is_active)"

# T29: Verify deactivated attr persists in listKinds
KINDS7=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T29_VAL=$(echo "$KINDS7" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    if(!spell){console.log('NOT_FOUND');return;}
    const a=spell.default_attributes.find(a=>a.code==='toggle_test');
    console.log(a ? String(a.is_active) : 'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T29 listKinds shows is_active=false" "false" "$T29_VAL"

# T30: Patch attr back to active (is_active=true)
APATCH4=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"is_active":true}')
assert_eq "T30 patch is_active=true" "true" "$(echo "$APATCH4" | jget .is_active)"

# T31: Toggle doesn't affect other fields
assert_eq "T31 name unchanged after toggle" "Toggle Test" "$(echo "$APATCH4" | jget .name)"
assert_eq "T31 field_type unchanged after toggle" "text" "$(echo "$APATCH4" | jget .field_type)"

# T32: Deactivating system attr is allowed
SYS_ATTR_ID=$(echo "$KINDS6" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    if(!ch){console.log('');return;}
    const a=ch.default_attributes.find(a=>a.is_system && a.code!=='name');
    console.log(a ? a.attr_def_id : '');
  });" 2>/dev/null)

if [ -n "$SYS_ATTR_ID" ]; then
  APATCH5_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$CHAR_KIND_ID/attributes/$SYS_ATTR_ID" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d '{"is_active":false}')
  assert_status "T32 deactivate system attr allowed" "200" "$APATCH5_STATUS"

  # Restore it back
  curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$CHAR_KIND_ID/attributes/$SYS_ATTR_ID" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d '{"is_active":true}' > /dev/null 2>&1
else
  red "T32 could not find system attr to test"; FAIL=$((FAIL+1))
fi

# ═══════════════════════════════════════════════════════════════════════════════
# BE-KE-04: Attribute inline edit — PATCH name, field_type, is_required
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-04a: patch attr name + field_type + is_required"

# T33: Patch attr name
APATCH6=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Renamed Toggle"}')
assert_eq "T33 patch attr name" "Renamed Toggle" "$(echo "$APATCH6" | jget .name)"

# T34: Patch attr field_type
APATCH7=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"field_type":"textarea"}')
assert_eq "T34 patch attr field_type" "textarea" "$(echo "$APATCH7" | jget .field_type)"

# T35: Patch attr is_required
APATCH8=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"is_required":true}')
assert_eq "T35 patch attr is_required=true" "true" "$(echo "$APATCH8" | jget .is_required)"

# T36: Patch multiple fields at once
APATCH9=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Multi Update","field_type":"number","is_required":false}')
assert_eq "T36 multi-patch name" "Multi Update" "$(echo "$APATCH9" | jget .name)"
assert_eq "T36 multi-patch field_type" "number" "$(echo "$APATCH9" | jget .field_type)"
assert_eq "T36 multi-patch is_required" "false" "$(echo "$APATCH9" | jget .is_required)"

header "BE-KE-04b: validation — invalid field_type + empty name"

# T37: Invalid field_type returns 400
T37_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"field_type":"invalid_type"}')
assert_status "T37 invalid field_type returns 400" "400" "$T37_STATUS"

# T38: Empty name returns 400
T38_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":""}')
assert_status "T38 empty name returns 400" "400" "$T38_STATUS"

# T39: Attr unchanged after rejected patches
KINDS8=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T39_NAME=$(echo "$KINDS8" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    if(!spell){console.log('NOT_FOUND');return;}
    const a=spell.default_attributes.find(a=>a.code==='toggle_test');
    console.log(a ? a.name : 'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T39 attr unchanged after rejected patches" "Multi Update" "$T39_NAME"

header "BE-KE-04c: system attr name customization"

# T40: Patch system attr name (allowed)
SYS_ATTR_NAME_BEFORE=$(echo "$KINDS8" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    if(!ch){console.log('');return;}
    const a=ch.default_attributes.find(a=>a.is_system && a.code==='aliases');
    console.log(a ? a.name : '');
  });" 2>/dev/null)
SYS_ALIASES_ID=$(echo "$KINDS8" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const ch=j.find(k=>k.code==='character');
    if(!ch){console.log('');return;}
    const a=ch.default_attributes.find(a=>a.is_system && a.code==='aliases');
    console.log(a ? a.attr_def_id : '');
  });" 2>/dev/null)

if [ -n "$SYS_ALIASES_ID" ]; then
  APATCH10=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$CHAR_KIND_ID/attributes/$SYS_ALIASES_ID" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d '{"name":"Also Known As"}')
  assert_eq "T40 system attr rename allowed" "Also Known As" "$(echo "$APATCH10" | jget .name)"

  # Restore original name
  curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$CHAR_KIND_ID/attributes/$SYS_ALIASES_ID" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"name\":\"$SYS_ATTR_NAME_BEFORE\"}" > /dev/null 2>&1
else
  red "T40 could not find aliases attr to test"; FAIL=$((FAIL+1))
fi

# T41: All valid field_types accepted
for ft in text textarea select number date tags url boolean; do
  T41_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID/attributes/$ATTR_ID3" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"field_type\":\"$ft\"}")
  assert_status "T41 field_type=$ft accepted" "200" "$T41_STATUS"
done

# ═══════════════════════════════════════════════════════════════════════════════
# BE-KE-06: Sort order reorder endpoints
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-KE-06a: reorder kinds"

# Get current kind order
KINDS_BEFORE=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
FIRST_TWO_IDS=$(echo "$KINDS_BEFORE" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    // Get test_spell and test_nodesc IDs (our custom kinds)
    const spell=j.find(k=>k.code==='test_spell');
    const nodesc=j.find(k=>k.code==='test_nodesc');
    if(spell&&nodesc) console.log(spell.kind_id+','+nodesc.kind_id);
    else console.log('');
  });" 2>/dev/null)

SPELL_ID=$(echo "$FIRST_TWO_IDS" | cut -d, -f1)
NODESC_ID=$(echo "$FIRST_TWO_IDS" | cut -d, -f2)

# T42: Reorder kinds — swap test_spell and test_nodesc
# Put nodesc before spell (reversed)
ALL_KIND_IDS=$(echo "$KINDS_BEFORE" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    // Swap our two custom kinds, keep system kinds in original order
    const ids=j.map(k=>k.kind_id);
    const si=ids.indexOf('$SPELL_ID');
    const ni=ids.indexOf('$NODESC_ID');
    if(si>=0&&ni>=0){[ids[si],ids[ni]]=[ids[ni],ids[si]];}
    console.log(JSON.stringify(ids));
  });" 2>/dev/null)

REORDER_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/reorder" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"kind_ids\":$ALL_KIND_IDS}")
assert_status "T42 reorder kinds" "200" "$REORDER_STATUS"

# T43: Verify new order in listKinds
KINDS_AFTER=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
T43_ORDER=$(echo "$KINDS_AFTER" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const si=j.findIndex(k=>k.kind_id==='$SPELL_ID');
    const ni=j.findIndex(k=>k.kind_id==='$NODESC_ID');
    console.log(ni < si ? 'SWAPPED' : 'NOT_SWAPPED');
  });" 2>/dev/null)
assert_eq "T43 kinds order swapped" "SWAPPED" "$T43_ORDER"

# T44: Empty array returns 400
T44_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/reorder" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"kind_ids":[]}')
assert_status "T44 empty kind_ids returns 400" "400" "$T44_STATUS"

header "BE-KE-06b: reorder attributes"

# Get attrs for test_spell kind
SPELL_ATTRS=$(echo "$KINDS_AFTER" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    if(!spell||spell.default_attributes.length<2){console.log('');return;}
    const ids=spell.default_attributes.map(a=>a.attr_def_id);
    console.log(JSON.stringify(ids));
  });" 2>/dev/null)

ATTR_FIRST=$(echo "$KINDS_AFTER" | node -e "
  let d=''; process.stdin.on('data',c=>d+=c);
  process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const spell=j.find(k=>k.code==='test_spell');
    if(!spell||spell.default_attributes.length<2){console.log('');return;}
    console.log(spell.default_attributes[0].code);
  });" 2>/dev/null)

if [ -n "$SPELL_ATTRS" ] && [ "$SPELL_ATTRS" != "[]" ]; then
  # T45: Reorder attrs — reverse order
  REVERSED_ATTRS=$(echo "$SPELL_ATTRS" | node -e "
    let d=''; process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      console.log(JSON.stringify(JSON.parse(d).reverse()));
    });" 2>/dev/null)

  T45_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$SPELL_ID/attributes/reorder" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d "{\"attr_def_ids\":$REVERSED_ATTRS}")
  assert_status "T45 reorder attrs" "200" "$T45_STATUS"

  # T46: Verify new attr order in listKinds
  KINDS_AFTER2=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
  ATTR_FIRST_AFTER=$(echo "$KINDS_AFTER2" | node -e "
    let d=''; process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const j=JSON.parse(d);
      const spell=j.find(k=>k.code==='test_spell');
      if(!spell||spell.default_attributes.length<2){console.log('');return;}
      console.log(spell.default_attributes[0].code);
    });" 2>/dev/null)

  if [ "$ATTR_FIRST" != "$ATTR_FIRST_AFTER" ]; then
    green "T46 attr order changed after reorder"; PASS=$((PASS+1))
  else
    red "T46 attr order did not change (was: $ATTR_FIRST, still: $ATTR_FIRST_AFTER)"; FAIL=$((FAIL+1))
  fi
else
  red "T45 skip — test_spell has < 2 attrs"; FAIL=$((FAIL+1))
  red "T46 skip — test_spell has < 2 attrs"; FAIL=$((FAIL+1))
fi

# T47: Empty attr_def_ids returns 400
T47_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$SPELL_ID/attributes/reorder" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"attr_def_ids":[]}')
assert_status "T47 empty attr_def_ids returns 400" "400" "$T47_STATUS"

# T48: Reorder with non-existent IDs doesn't error (no-op for unknown IDs)
T48_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/kinds/$SPELL_ID/attributes/reorder" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"attr_def_ids":["00000000-0000-0000-0000-000000000000"]}')
assert_status "T48 reorder with unknown ID succeeds (no-op)" "200" "$T48_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# Cleanup: delete test kinds + book
# ═══════════════════════════════════════════════════════════════════════════════
header "Cleanup"

curl -s -X DELETE "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID" -H "$AUTH" > /dev/null 2>&1
curl -s -X DELETE "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID2" -H "$AUTH" > /dev/null 2>&1
curl -s -X DELETE "$GATEWAY/v1/books/$BOOK_ID" -H "$AUTH" > /dev/null 2>&1
green "Cleanup: deleted test kinds + book"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1m═══ Results ═══\033[0m\n"
printf "\033[32m  PASS: %d\033[0m\n" "$PASS"
if [ "$FAIL" -gt 0 ]; then
  printf "\033[31m  FAIL: %d\033[0m\n" "$FAIL"
  exit 1
else
  printf "\033[32m  FAIL: 0\033[0m\n"
  printf "\033[1;32m  All tests passed!\033[0m\n"
fi
