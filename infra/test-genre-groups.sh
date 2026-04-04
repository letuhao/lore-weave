#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Genre Groups Integration Test (BE-G1..G4)
#
# Tests genre_groups CRUD, attribute genre_tags, book genre_tags,
# and catalog genre filter — all through the gateway.
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-genre-groups.sh
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

# JSON field extractor using node (handles nested paths, arrays, objects)
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

# JSON array length (supports top-level arrays with path ".")
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

# Check if items array contains a book_id
jhas() {
  local bid="$1"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const r=JSON.parse(d);
      console.log(r.items.some(b=>b.book_id===process.argv[1]));
    });
  " "$bid" 2>/dev/null || echo ""
}

# Extract a field from a specific item in kinds array by kind_id + attr code
jattr() {
  local kind_id="$1" attr_code="$2" field="$3"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      const kinds=JSON.parse(d);
      const k=kinds.find(k=>k.kind_id===process.argv[1]);
      if(!k){console.log('KIND_NOT_FOUND');return;}
      const a=k.default_attributes.find(a=>a.code===process.argv[2]);
      if(!a){console.log('ATTR_NOT_FOUND');return;}
      const v=a[process.argv[3]];
      console.log(typeof v==='object'?JSON.stringify(v):v);
    });
  " "$kind_id" "$attr_code" "$field" 2>/dev/null || echo ""
}

# ── T00: Health checks ────────────────────────────────────────────────────────
header "T00: Health checks"

GW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/health")
assert_status "T00a gateway health" "200" "$GW_STATUS"

# ── Setup: Auth + Books ──────────────────────────────────────────────────────
header "Setup: Register + Login + Create Books"

UNAME="genre_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Genre Test Book","original_language":"en"}')
BOOK_ID=$(echo "$BOOK_RESP" | jget .book_id)
assert_not_empty "Setup: created book" "$BOOK_ID"

# ═══════════════════════════════════════════════════════════════════════════════
# BE-G1: Genre Groups CRUD
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-G1: Genre Groups CRUD"

# T01: List genres (empty)
LIST1=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/genres")
LEN1=$(echo "$LIST1" | jlen .)
assert_eq "T01 list genres (empty)" "0" "$LEN1"

# T02: Create Fantasy
C1=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Fantasy","color":"#8b5cf6","description":"Magic and mythical creatures"}')
G1_ID=$(echo "$C1" | jget .id)
assert_not_empty "T02 create Fantasy (got id)" "$G1_ID"
assert_eq "T02 create Fantasy (name)" "Fantasy" "$(echo "$C1" | jget .name)"
assert_eq "T02 create Fantasy (color)" "#8b5cf6" "$(echo "$C1" | jget .color)"

# T03: Create Sci-Fi
C2=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"name":"Sci-Fi","color":"#06b6d4","sort_order":1}')
G2_ID=$(echo "$C2" | jget .id)
assert_eq "T03 create Sci-Fi" "Sci-Fi" "$(echo "$C2" | jget .name)"

# T04: Duplicate name → 409
DUP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Fantasy"}')
assert_status "T04 duplicate name" "409" "$DUP_STATUS"

# T05: Empty name → 400
BAD_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"  "}')
assert_status "T05 empty name" "400" "$BAD_STATUS"

# T06: List genres (2 items)
LIST2=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/genres")
LEN2=$(echo "$LIST2" | jlen .)
assert_eq "T06 list has 2 genres" "2" "$LEN2"

# T07: Patch name + color
PATCH1=$(curl -s -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/$G1_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Dark Fantasy","color":"#a855f7"}')
assert_eq "T07 patch name" "Dark Fantasy" "$(echo "$PATCH1" | jget .name)"
assert_eq "T07 patch color" "#a855f7" "$(echo "$PATCH1" | jget .color)"

# T08: Patch no fields → 400
S=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/$G1_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{}')
assert_status "T08 patch no fields" "400" "$S"

# T09: Patch non-existent → 404
S=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/00000000-0000-0000-0000-000000000000" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"X"}')
assert_status "T09 patch 404" "404" "$S"

# T10: Delete
S=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/$G1_ID" -H "$AUTH")
assert_status "T10 delete" "204" "$S"

# T11: List after delete (1 remaining)
LIST3=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK_ID/genres")
assert_eq "T11 1 remaining after delete" "1" "$(echo "$LIST3" | jlen .)"

# T12: Delete non-existent → 404
S=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/00000000-0000-0000-0000-000000000000" -H "$AUTH")
assert_status "T12 delete 404" "404" "$S"

# T13: No auth → 401
S=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/glossary/books/$BOOK_ID/genres")
assert_status "T13 no auth" "401" "$S"

# T14: Invalid UUID → 400
S=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$GATEWAY/v1/glossary/books/not-a-uuid/genres")
assert_status "T14 invalid book_id UUID" "400" "$S"

S=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/not-a-uuid" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"X"}')
assert_status "T14b invalid genre_id UUID" "400" "$S"

# T15: Cross-book isolation
BOOK2_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"title":"Other Book"}')
BOOK2_ID=$(echo "$BOOK2_RESP" | jget .book_id)

CROSS=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK2_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Sci-Fi","color":"#06b6d4"}')
CROSS_GID=$(echo "$CROSS" | jget .id)
assert_eq "T15a cross-book same name allowed" "Sci-Fi" "$(echo "$CROSS" | jget .name)"

assert_eq "T15b cross-book list isolation" "1" \
  "$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/books/$BOOK2_ID/genres" | jlen .)"

S=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/$CROSS_GID" -H "$AUTH")
assert_status "T15c cross-book delete blocked" "404" "$S"

S=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH \
  "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/$CROSS_GID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Hacked"}')
assert_status "T15d cross-book patch blocked" "404" "$S"

# T16: Name too long → 400
LONGNAME=$(python3 -c "print('A'*201)")
S=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" -d "{\"name\":\"$LONGNAME\"}")
assert_status "T16 name too long" "400" "$S"

# T17: Rename to existing name → 409
C3=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Temp Genre"}')
G3_ID=$(echo "$C3" | jget .id)
S=$(curl -s -o /dev/null -w "%{http_code}" -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/genres/$G3_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Sci-Fi"}')
assert_status "T17 rename to duplicate" "409" "$S"

# T18: Default color
C4=$(curl -s -X POST "$GATEWAY/v1/glossary/books/$BOOK_ID/genres" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"No Color"}')
assert_eq "T18 default color" "#8b5cf6" "$(echo "$C4" | jget .color)"

# T19: created_at ISO format
TS=$(echo "$C4" | jget .created_at)
echo "$TS" | grep -qE "^20[0-9]{2}-" && { green "T19 created_at ISO ($TS)"; PASS=$((PASS+1)); } \
  || { red "T19 created_at ($TS)"; FAIL=$((FAIL+1)); }

# ═══════════════════════════════════════════════════════════════════════════════
# BE-G2: Attribute genre_tags
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-G2: Attribute genre_tags"

# Create a test kind (unique code per run)
KIND_CODE="gtest_$(date +%s)"
KIND_RESP=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"code\":\"$KIND_CODE\",\"name\":\"Genre Test Kind\"}")
KIND_ID=$(echo "$KIND_RESP" | jget .kind_id)
assert_not_empty "Setup: created test kind" "$KIND_ID"

# T20: Create attr without genre_tags → default []
A1=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"plain","name":"Plain","field_type":"text"}')
A1_ID=$(echo "$A1" | jget .attr_def_id)
assert_eq "T20 create attr no tags → []" "[]" "$(echo "$A1" | jget .genre_tags)"

# T21: Create attr with genre_tags
A2=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"fan_attr","name":"Fantasy Attr","field_type":"number","genre_tags":["Fantasy"]}')
A2_ID=$(echo "$A2" | jget .attr_def_id)
assert_eq "T21 create attr with tags" '["Fantasy"]' "$(echo "$A2" | jget .genre_tags)"

# T22: Create attr with multiple genre_tags
A3=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"multi","name":"Multi","field_type":"text","genre_tags":["Fantasy","Sci-Fi"]}')
A3_ID=$(echo "$A3" | jget .attr_def_id)
assert_eq "T22 multi genre_tags" '["Fantasy","Sci-Fi"]' "$(echo "$A3" | jget .genre_tags)"

# T23: Patch genre_tags
P=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes/$A1_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":["Drama"]}')
assert_eq "T23 patch genre_tags" '["Drama"]' "$(echo "$P" | jget .genre_tags)"

# T24: Patch genre_tags to empty
P=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes/$A1_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":[]}')
assert_eq "T24 patch to empty" "[]" "$(echo "$P" | jget .genre_tags)"

# T25: listKinds returns genre_tags on attrs
KINDS=$(curl -s -H "$AUTH" "$GATEWAY/v1/glossary/kinds")
assert_eq "T25 listKinds attr genre_tags" '["Fantasy"]' "$(echo "$KINDS" | jattr "$KIND_ID" fan_attr genre_tags)"

# T26: System attrs default to []
SYS_TAGS=$(echo "$KINDS" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const k=JSON.parse(d).find(k=>k.code==='character');
    const a=k.default_attributes.find(a=>a.code==='name');
    console.log(JSON.stringify(a.genre_tags));
  });" 2>/dev/null)
assert_eq "T26 system attr default []" "[]" "$SYS_TAGS"

# T27: loadAttrDefs (via patchKind) includes genre_tags
PK=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$KIND_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Genre Test Kind v2"}')
PK_ATTR_TAGS=$(echo "$PK" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const k=JSON.parse(d);
    const a=k.default_attributes.find(a=>a.code==='fan_attr');
    console.log(a?JSON.stringify(a.genre_tags):'NOT_FOUND');
  });" 2>/dev/null)
assert_eq "T27 loadAttrDefs genre_tags" '["Fantasy"]' "$PK_ATTR_TAGS"

# T28: Patch name only preserves genre_tags
curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes/$A3_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":["Isekai"]}' > /dev/null
P=$(curl -s -X PATCH "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes/$A3_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"name":"Multi Renamed"}')
assert_eq "T28 name-only patch preserves tags" '["Isekai"]' "$(echo "$P" | jget .genre_tags)"

# T29: Delete attr with genre_tags
A4=$(curl -s -X POST "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"code":"del_me","name":"Delete Me","genre_tags":["Fantasy"]}')
A4_ID=$(echo "$A4" | jget .attr_def_id)
S=$(curl -s -o /dev/null -w "%{http_code}" -X DELETE \
  "$GATEWAY/v1/glossary/kinds/$KIND_ID/attributes/$A4_ID" -H "$AUTH")
assert_status "T29 delete attr with tags" "204" "$S"

# ═══════════════════════════════════════════════════════════════════════════════
# BE-G3: Book genre_tags
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-G3: Book genre_tags"

# T30: Create book without genre_tags → default []
B1=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"title":"No Genre Book"}')
assert_eq "T30 create no tags → []" "[]" "$(echo "$B1" | jget .genre_tags)"

# T31: Create book with genre_tags
B2=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Fantasy Drama","genre_tags":["Fantasy","Drama"],"original_language":"en"}')
B2_ID=$(echo "$B2" | jget .book_id)
assert_eq "T31 create with tags" '["Fantasy","Drama"]' "$(echo "$B2" | jget .genre_tags)"

# T32: GET returns genre_tags
G=$(curl -s -H "$AUTH" "$GATEWAY/v1/books/$B2_ID")
assert_eq "T32 GET roundtrip" '["Fantasy","Drama"]' "$(echo "$G" | jget .genre_tags)"

# T33: List returns genre_tags
LIST_TAGS=$(curl -s -H "$AUTH" "$GATEWAY/v1/books" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const r=JSON.parse(d);
    const b=r.items.find(b=>b.book_id===process.argv[1]);
    console.log(b?JSON.stringify(b.genre_tags):'NOT_FOUND');
  });" "$B2_ID" 2>/dev/null)
assert_eq "T33 list returns tags" '["Fantasy","Drama"]' "$LIST_TAGS"

# T34: PATCH genre_tags
P=$(curl -s -X PATCH "$GATEWAY/v1/books/$B2_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":["Sci-Fi"]}')
assert_eq "T34 patch genre_tags" '["Sci-Fi"]' "$(echo "$P" | jget .genre_tags)"

# T35: PATCH to empty
P=$(curl -s -X PATCH "$GATEWAY/v1/books/$B2_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":[]}')
assert_eq "T35 patch to empty" "[]" "$(echo "$P" | jget .genre_tags)"

# T36: Title-only patch preserves genre_tags
curl -s -X PATCH "$GATEWAY/v1/books/$B2_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":["Isekai"]}' > /dev/null
P=$(curl -s -X PATCH "$GATEWAY/v1/books/$B2_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"title":"Renamed"}')
assert_eq "T36 title-only preserves tags" '["Isekai"]' "$(echo "$P" | jget .genre_tags)"

# T37: PATCH null clears to []
P=$(curl -s -X PATCH "$GATEWAY/v1/books/$B2_ID" \
  -H "$AUTH" -H "Content-Type: application/json" -d '{"genre_tags":null}')
assert_eq "T37 null clears to []" "[]" "$(echo "$P" | jget .genre_tags)"

# ═══════════════════════════════════════════════════════════════════════════════
# BE-G4: Catalog genre filter
# ═══════════════════════════════════════════════════════════════════════════════
header "BE-G4: Catalog genre filter"

# Create 3 test books with distinct genres and make them public
BF_ID=$(curl -s -X POST "$GATEWAY/v1/books" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"CatFantasy","genre_tags":["Fantasy"],"original_language":"en"}' | jget .book_id)
BS_ID=$(curl -s -X POST "$GATEWAY/v1/books" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"CatSciFi","genre_tags":["Sci-Fi"],"original_language":"en"}' | jget .book_id)
BB_ID=$(curl -s -X POST "$GATEWAY/v1/books" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"CatBoth","genre_tags":["Fantasy","Sci-Fi"],"original_language":"ja"}' | jget .book_id)

for BID in $BF_ID $BS_ID $BB_ID; do
  curl -s -X PATCH "$GATEWAY/v1/sharing/books/$BID" \
    -H "$AUTH" -H "Content-Type: application/json" -d '{"visibility":"public"}' > /dev/null
done
sleep 1

# T38: getPublicBook returns genre_tags
PUB=$(curl -s "$GATEWAY/v1/catalog/books/$BB_ID")
assert_eq "T38 public book genre_tags" '["Fantasy","Sci-Fi"]' "$(echo "$PUB" | jget .genre_tags)"

# T39: genre=Fantasy → BF + BB, not BS
FANT=$(curl -s "$GATEWAY/v1/catalog/books?genre=Fantasy&limit=50")
assert_eq "T39a Fantasy includes CatFantasy" "true" "$(echo "$FANT" | jhas "$BF_ID")"
assert_eq "T39b Fantasy excludes CatSciFi" "false" "$(echo "$FANT" | jhas "$BS_ID")"
assert_eq "T39c Fantasy includes CatBoth" "true" "$(echo "$FANT" | jhas "$BB_ID")"

# T40: genre=Sci-Fi → BS + BB, not BF
SCIFI=$(curl -s "$GATEWAY/v1/catalog/books?genre=Sci-Fi&limit=50")
assert_eq "T40a Sci-Fi excludes CatFantasy" "false" "$(echo "$SCIFI" | jhas "$BF_ID")"
assert_eq "T40b Sci-Fi includes CatSciFi" "true" "$(echo "$SCIFI" | jhas "$BS_ID")"
assert_eq "T40c Sci-Fi includes CatBoth" "true" "$(echo "$SCIFI" | jhas "$BB_ID")"

# T41: genre=Drama → none of ours
DRAMA=$(curl -s "$GATEWAY/v1/catalog/books?genre=Drama&limit=50")
assert_eq "T41 Drama excludes all" "false" "$(echo "$DRAMA" | jhas "$BF_ID")"

# T42: Multi-genre OR (comma-separated)
MULTI=$(curl -s "$GATEWAY/v1/catalog/books?genre=Fantasy,Sci-Fi&limit=50")
assert_eq "T42a multi OR includes CatFantasy" "true" "$(echo "$MULTI" | jhas "$BF_ID")"
assert_eq "T42b multi OR includes CatSciFi" "true" "$(echo "$MULTI" | jhas "$BS_ID")"
assert_eq "T42c multi OR includes CatBoth" "true" "$(echo "$MULTI" | jhas "$BB_ID")"

# T43: genre + language combined
FANT_JA=$(curl -s "$GATEWAY/v1/catalog/books?genre=Fantasy&language=ja&limit=50")
assert_eq "T43a Fantasy+ja excludes CatFantasy (en)" "false" "$(echo "$FANT_JA" | jhas "$BF_ID")"
assert_eq "T43b Fantasy+ja includes CatBoth (ja)" "true" "$(echo "$FANT_JA" | jhas "$BB_ID")"

# T44: List items include genre_tags field
ITEM_TAGS=$(curl -s "$GATEWAY/v1/catalog/books?genre=Fantasy&limit=50" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const r=JSON.parse(d);
    const b=r.items.find(i=>i.book_id===process.argv[1]);
    console.log(b?JSON.stringify(b.genre_tags):'NOT_FOUND');
  });" "$BB_ID" 2>/dev/null)
assert_eq "T44 list items include genre_tags" '["Fantasy","Sci-Fi"]' "$ITEM_TAGS"

# T45: No genre filter returns all
ALL=$(curl -s "$GATEWAY/v1/catalog/books?limit=50")
assert_eq "T45a no filter has CatFantasy" "true" "$(echo "$ALL" | jhas "$BF_ID")"
assert_eq "T45b no filter has CatSciFi" "true" "$(echo "$ALL" | jhas "$BS_ID")"

# T46: Empty genre= returns all (same as no param)
EMPTY=$(curl -s "$GATEWAY/v1/catalog/books?genre=&limit=50")
assert_eq "T46 empty genre= has CatFantasy" "true" "$(echo "$EMPTY" | jhas "$BF_ID")"

# ═══════════════════════════════════════════════════════════════════════════════
# Summary
# ═══════════════════════════════════════════════════════════════════════════════
echo ""
echo "─────────────────────────────────────"
printf "  \033[32m%d passed\033[0m, \033[31m%d failed\033[0m\n" "$PASS" "$FAIL"
echo "─────────────────────────────────────"

if [ "$FAIL" -gt 0 ]; then
  exit 1
fi
