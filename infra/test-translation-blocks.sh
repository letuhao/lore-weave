#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Block Translation Integration Tests (TF-15 + TF-16)
#
# Tests: block mode translate-text, backward compat, format detection
#
# Prerequisites: all services running via docker compose, Ollama with gemma3
# Usage: bash infra/test-translation-blocks.sh
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

# ── Setup: Auth ──────────────────────────────────────────────────────────────
header "Setup: Auth"
UNAME="blocktr_integ_$(date +%s)"
EMAIL="$UNAME@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\",\"display_name\":\"Block Translate Test\"}" > /dev/null

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Setup: got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# ═══════════════════════════════════════════════════════════════════════════════
# T01-T03: Text mode still works (backward compat — TF-16)
# ═══════════════════════════════════════════════════════════════════════════════
header "T01-T03: Text mode backward compat"

# T01: Text mode translate (no model → 422)
T01_RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"text":"Hello world","target_language":"vi"}')
T01_STATUS=$(echo "$T01_RESP" | tail -1)
assert_status "T01 text mode no model → 422" "422" "$T01_STATUS"

# T02: Empty text + no blocks → 422
T02_RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"target_language":"vi"}')
T02_STATUS=$(echo "$T02_RESP" | tail -1)
assert_status "T02 empty text no blocks → 422" "422" "$T02_STATUS"

# T03: Empty blocks array → 422
T03_RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"blocks":[],"target_language":"vi"}')
T03_STATUS=$(echo "$T03_RESP" | tail -1)
assert_status "T03 empty blocks → 422" "422" "$T03_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T04-T06: Block mode validation
# ═══════════════════════════════════════════════════════════════════════════════
header "T04-T06: Block mode validation"

# T04: Block mode also needs model → 422
T04_RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"blocks":[{"type":"paragraph","content":[{"type":"text","text":"Hello"}]}],"target_language":"vi"}')
T04_STATUS=$(echo "$T04_RESP" | tail -1)
assert_status "T04 block mode no model → 422" "422" "$T04_STATUS"

# T05: All passthrough blocks → returns as-is
# First set up a provider + model (create Ollama credential)
CRED_RESP=$(curl -s -X POST "$GATEWAY/v1/model-registry/providers" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"provider_kind":"ollama","display_name":"Test Ollama","api_key":"unused","base_url":"http://host.docker.internal:11434"}')
CRED_ID=$(echo "$CRED_RESP" | jget .provider_credential_id)

MODEL_RESP=$(curl -s -X POST "$GATEWAY/v1/model-registry/user-models" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"provider_credential_id\":\"$CRED_ID\",\"provider_model_name\":\"gemma3:12b\",\"context_length\":8192,\"capability_flags\":{\"chat\":true}}")
MODEL_ID=$(echo "$MODEL_RESP" | jget .user_model_id)
assert_not_empty "T05a created model" "$MODEL_ID"

# Set translation preferences
curl -s -X PUT "$GATEWAY/v1/translation/preferences" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"target_language\":\"vi\",\"model_source\":\"user_model\",\"model_ref\":\"$MODEL_ID\",\"system_prompt\":\"You are a translator.\",\"user_prompt_tpl\":\"Translate to {target_language}:\\n\\n{chapter_text}\"}" > /dev/null

T05_RESP=$(curl -s -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"blocks":[{"type":"codeBlock","content":[{"type":"text","text":"let x = 1;"}]},{"type":"horizontalRule"}],"target_language":"vi"}')
T05_FORMAT=$(echo "$T05_RESP" | jget .translated_body_format)
T05_BLOCKS=$(echo "$T05_RESP" | jlen .translated_blocks)
assert_eq "T05 all passthrough → json format" "json" "$T05_FORMAT"
assert_eq "T05 all passthrough → 2 blocks returned" "2" "$T05_BLOCKS"

# T06: No auth → 401
T06_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "Content-Type: application/json" \
  -d '{"blocks":[{"type":"paragraph","content":[{"type":"text","text":"Hello"}]}],"target_language":"vi"}')
assert_status "T06 no auth → 401" "401" "$T06_STATUS"

# ═══════════════════════════════════════════════════════════════════════════════
# T07-T12: Block mode with real AI model
# ═══════════════════════════════════════════════════════════════════════════════
header "T07-T12: Block mode with AI model (gemma3:12b)"

T07_RESP=$(curl -s -X POST "$GATEWAY/v1/translation/translate-text" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "blocks": [
      {"type":"heading","attrs":{"level":1},"content":[{"type":"text","text":"The Beginning"}]},
      {"type":"paragraph","content":[{"type":"text","text":"The throne room was silent."}]},
      {"type":"codeBlock","content":[{"type":"text","text":"const magic = true;"}]},
      {"type":"paragraph","content":[{"type":"text","text":"A scroll lay on the table."}]},
      {"type":"imageBlock","attrs":{"src":"map.png","caption":"Map of the realm"}}
    ],
    "target_language": "vi",
    "source_language": "en"
  }')

T07_FORMAT=$(echo "$T07_RESP" | jget .translated_body_format)
T07_BLOCKS=$(echo "$T07_RESP" | jlen .translated_blocks)

# T07: format is json
assert_eq "T07 format is json" "json" "$T07_FORMAT"

# T08: block count matches (5 blocks)
assert_eq "T08 block count is 5" "5" "$T07_BLOCKS"

# T09: codeBlock unchanged (index 2)
T09_CODE=$(echo "$T07_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const b=JSON.parse(d).translated_blocks[2];console.log(b.content[0].text)})")
assert_eq "T09 codeBlock unchanged" "const magic = true;" "$T09_CODE"

# T10: heading translated (index 0)
T10_TYPE=$(echo "$T07_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d).translated_blocks[0].type))")
assert_eq "T10 heading type preserved" "heading" "$T10_TYPE"

# T11: heading text exists and has content
T11_TEXT=$(echo "$T07_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>console.log(JSON.parse(d).translated_blocks[0].content[0].text))")
assert_not_empty "T11 heading has translated text" "$T11_TEXT"

# T12: imageBlock caption translated
T12_CAPTION=$(echo "$T07_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const b=JSON.parse(d).translated_blocks[4];console.log(b.attrs.caption)})")
T12_SRC=$(echo "$T07_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const b=JSON.parse(d).translated_blocks[4];console.log(b.attrs.src)})")
assert_not_empty "T12a imageBlock caption translated" "$T12_CAPTION"
assert_eq "T12b imageBlock src preserved" "map.png" "$T12_SRC"

# ═══════════════════════════════════════════════════════════════════════════════
# T13: DB migration columns exist (TF-16)
# ═══════════════════════════════════════════════════════════════════════════════
header "T13: DB migration check"

T13_COLS=$(docker compose exec -T postgres psql -U loreweave -d loreweave_translation -tA -c "
  SELECT column_name FROM information_schema.columns
  WHERE table_name='chapter_translations' AND column_name IN ('translated_body_json','translated_body_format')
  ORDER BY column_name;
")
T13_HAS_FORMAT=$(echo "$T13_COLS" | grep -c "translated_body_format" || true)
T13_HAS_JSON=$(echo "$T13_COLS" | grep -c "translated_body_json" || true)
assert_eq "T13a translated_body_format exists" "1" "$T13_HAS_FORMAT"
assert_eq "T13b translated_body_json exists" "1" "$T13_HAS_JSON"

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
