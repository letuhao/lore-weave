#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Setup LM Studio test model for Chat Enhancement tests
#
# Inserts a provider credential + user model for Qwen3-1.7B on LM Studio
# into the provider-registry DB. Idempotent — safe to run multiple times.
#
# Prerequisites: Postgres running via docker compose, LM Studio running
# Usage: bash infra/setup-chat-test-model.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PG_URL="postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_provider_registry"

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

# JSON field extractor
jget() {
  local path="$1"
  node -e "
    let d='';
    process.stdin.on('data',c=>d+=c);
    process.stdin.on('end',()=>{
      try {
        const j=JSON.parse(d);
        const keys='${path}'.slice(1).split('.');
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        if(v===undefined||v===null) console.log('');
        else console.log(v);
      } catch { console.log(''); }
    });
  " 2>/dev/null || echo ""
}

# ── Step 1: Register + Login test user ────────────────────────────────────────
header "Step 1: Auth — register/login test user"

UNAME="chatenhance_test"
EMAIL="${UNAME}@test.com"

# Register (may already exist — that's fine)
curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null 2>&1 || true

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
USER_ID=$(echo "$LOGIN_RESP" | jget .user_id)

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  red "Failed to get auth token"
  echo "$LOGIN_RESP"
  exit 1
fi
green "Logged in as $EMAIL (user_id: $USER_ID)"
AUTH="Authorization: Bearer $TOKEN"

# ── Step 2: Create LM Studio provider credential ─────────────────────────────
header "Step 2: Create LM Studio provider credential"

# Check if already exists
EXISTING=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-registry/providers" | jget .items)

# Create provider credential pointing to LM Studio on Docker host
CREATE_PROV=$(curl -s -X POST "$GATEWAY/v1/model-registry/providers" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{
    "provider_kind": "lm_studio",
    "display_name": "LM Studio (Local)",
    "endpoint_base_url": "http://host.docker.internal:1234",
    "secret": "",
    "api_standard": "lm_studio"
  }')
PROV_ID=$(echo "$CREATE_PROV" | jget .provider_credential_id)

if [ -z "$PROV_ID" ] || [ "$PROV_ID" = "null" ]; then
  red "Failed to create provider credential"
  echo "$CREATE_PROV"
  # Try to get existing one
  PROV_ID=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-registry/providers" \
    | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const lm=j.items?.find(i=>i.provider_kind==='lm_studio');console.log(lm?.provider_credential_id||'')})" 2>/dev/null)
  if [ -z "$PROV_ID" ]; then
    red "No existing LM Studio credential found either"
    exit 1
  fi
  green "Using existing provider credential: $PROV_ID"
else
  green "Created provider credential: $PROV_ID"
fi

# ── Step 3: Create user model for Qwen3-1.7B ─────────────────────────────────
header "Step 3: Create user model — qwen/qwen3-1.7b"

CREATE_MODEL=$(curl -s -X POST "$GATEWAY/v1/model-registry/user-models" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"provider_credential_id\": \"$PROV_ID\",
    \"provider_model_name\": \"qwen/qwen3-1.7b\",
    \"context_length\": 32768,
    \"alias\": \"Qwen3-1.7B (Test)\",
    \"capability_flags\": {\"thinking\": true, \"chat\": true}
  }")
MODEL_ID=$(echo "$CREATE_MODEL" | jget .user_model_id)

if [ -z "$MODEL_ID" ] || [ "$MODEL_ID" = "null" ]; then
  red "Failed to create user model"
  echo "$CREATE_MODEL"
  # Try to get existing
  MODEL_ID=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-registry/user-models" \
    | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const m=j.items?.find(i=>i.provider_model_name==='qwen/qwen3-1.7b');console.log(m?.user_model_id||'')})" 2>/dev/null)
  if [ -z "$MODEL_ID" ]; then
    red "No existing qwen3 model found"
    exit 1
  fi
  green "Using existing model: $MODEL_ID"
else
  green "Created user model: $MODEL_ID"
fi

# ── Summary ───────────────────────────────────────────────────────────────────
header "Setup Complete"
echo ""
echo "  User:       $EMAIL / Test1234!"
echo "  User ID:    $USER_ID"
echo "  Token:      ${TOKEN:0:20}..."
echo "  Provider:   $PROV_ID (LM Studio @ host.docker.internal:1234)"
echo "  Model:      $MODEL_ID (qwen/qwen3-1.7b)"
echo ""
echo "  Export for test script:"
echo "    export CHAT_TEST_TOKEN=\"$TOKEN\""
echo "    export CHAT_TEST_MODEL_ID=\"$MODEL_ID\""
echo "    export CHAT_TEST_PROV_ID=\"$PROV_ID\""
echo ""
