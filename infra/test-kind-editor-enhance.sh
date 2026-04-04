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
# Cleanup: delete test kinds
# ═══════════════════════════════════════════════════════════════════════════════
header "Cleanup"

curl -s -X DELETE "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID" -H "$AUTH" > /dev/null 2>&1
curl -s -X DELETE "$GATEWAY/v1/glossary/kinds/$NEW_KIND_ID2" -H "$AUTH" > /dev/null 2>&1
green "Cleanup: deleted test kinds"

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
