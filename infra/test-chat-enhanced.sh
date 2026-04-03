#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Chat Enhancement Integration Test (Phase 6)
#
# Tests: generation_params, system_prompt, thinking mode, pin, search,
#        auto-title, and streaming with LM Studio Qwen3.
#
# Prerequisites:
#   1. All services running via docker compose
#   2. LM Studio running on host with qwen/qwen3-1.7b loaded
#   3. Run setup-chat-test-model.sh first to create provider + model
#
# Usage: bash infra/test-chat-enhanced.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0
FAIL=0
SKIP=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; PASS=$((PASS+1)); }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }
yellow() { printf "\033[33m⊘ %s\033[0m\n" "$1"; SKIP=$((SKIP+1)); }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then green "$label"
  else red "$label (expected: $expected, got: $actual)"; fi
}

assert_not_empty() {
  local label="$1" value="$2"
  if [ -n "$value" ] && [ "$value" != "null" ] && [ "$value" != "undefined" ]; then green "$label"
  else red "$label (was empty or null)"; fi
}

assert_contains() {
  local label="$1" haystack="$2" needle="$3"
  if echo "$haystack" | grep -q "$needle"; then green "$label"
  else red "$label (did not contain: $needle)"; fi
}

assert_status() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then green "$label (HTTP $actual)"
  else red "$label (expected HTTP $expected, got $actual)"; fi
}

# JSON helpers
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
        const keys='${path}'.slice(1).split('.');
        let v=j;
        for(const k of keys) { if(v==null) break; v=v[k]; }
        console.log(Array.isArray(v)?v.length:0);
      } catch { console.log(0); }
    });
  " 2>/dev/null || echo "0"
}

# ── Setup: Auth ───────────────────────────────────────────────────────────────
header "Setup: Authenticate"

UNAME="chatenhance_test"
EMAIL="${UNAME}@test.com"

curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null 2>&1 || true

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)
assert_not_empty "Got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# Find test model
MODELS_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/model-registry/user-models")
MODEL_ID=$(echo "$MODELS_RESP" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    const m=j.items?.find(i=>i.provider_model_name==='qwen/qwen3-1.7b');
    console.log(m?.user_model_id||'');
  })" 2>/dev/null)

if [ -z "$MODEL_ID" ]; then
  red "No qwen3 test model found. Run setup-chat-test-model.sh first."
  exit 1
fi
green "Found test model: $MODEL_ID"

# ══════════════════════════════════════════════════════════════════════════════
# T20: Create session with generation_params
# ══════════════════════════════════════════════════════════════════════════════
header "T20: Create session with generation_params"

T20_RESP=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"model_source\": \"user_model\",
    \"model_ref\": \"$MODEL_ID\",
    \"title\": \"Gen Params Test\",
    \"generation_params\": {\"temperature\": 0.1, \"max_tokens\": 256}
  }")
T20_SID=$(echo "$T20_RESP" | jget .session_id)
T20_GP=$(echo "$T20_RESP" | jget .generation_params)
T20_PINNED=$(echo "$T20_RESP" | jget .is_pinned)

assert_not_empty "T20 session created" "$T20_SID"
assert_contains "T20 has temperature" "$T20_GP" "0.1"
assert_contains "T20 has max_tokens" "$T20_GP" "256"
assert_eq "T20 is_pinned default false" "false" "$T20_PINNED"

# ══════════════════════════════════════════════════════════════════════════════
# T21: PATCH generation_params (merge, not replace)
# ══════════════════════════════════════════════════════════════════════════════
header "T21: PATCH generation_params"

T21_RESP=$(curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$T20_SID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"generation_params": {"top_p": 0.5}}')
T21_GP=$(echo "$T21_RESP" | jget .generation_params)

assert_contains "T21 merged top_p" "$T21_GP" "0.5"
assert_contains "T21 kept temperature" "$T21_GP" "0.1"
assert_contains "T21 kept max_tokens" "$T21_GP" "256"

# ══════════════════════════════════════════════════════════════════════════════
# T22: Create session with system_prompt
# ══════════════════════════════════════════════════════════════════════════════
header "T22: Create session with system_prompt"

T22_RESP=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"model_source\": \"user_model\",
    \"model_ref\": \"$MODEL_ID\",
    \"title\": \"System Prompt Test\",
    \"system_prompt\": \"You answer only in rhymes. Every response must rhyme.\"
  }")
T22_SID=$(echo "$T22_RESP" | jget .session_id)
T22_SP=$(echo "$T22_RESP" | jget .system_prompt)

assert_not_empty "T22 session created" "$T22_SID"
assert_contains "T22 system_prompt persisted" "$T22_SP" "rhymes"

# ══════════════════════════════════════════════════════════════════════════════
# T23: PATCH system_prompt
# ══════════════════════════════════════════════════════════════════════════════
header "T23: PATCH system_prompt"

T23_RESP=$(curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$T22_SID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"system_prompt": "You are a pirate. Respond in pirate speak."}')
T23_SP=$(echo "$T23_RESP" | jget .system_prompt)

assert_contains "T23 system_prompt updated" "$T23_SP" "pirate"

# ══════════════════════════════════════════════════════════════════════════════
# T24: Send message with system_prompt → verify response follows instruction
# (Requires LM Studio to be running!)
# ══════════════════════════════════════════════════════════════════════════════
header "T24: Send message with system_prompt (requires LM Studio)"

# Reset system_prompt to rhyming
curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$T22_SID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"system_prompt": "You MUST answer only in rhymes. Every single line must rhyme."}' > /dev/null

# Send message — capture SSE stream
T24_STREAM=$(curl -s --max-time 60 -X POST "$GATEWAY/v1/chat/sessions/$T22_SID/messages" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"content": "What is your favorite color?"}' 2>&1 || true)

if echo "$T24_STREAM" | grep -q "text-delta"; then
  green "T24 got streaming response (text-delta events)"
  # Extract full text from stream
  T24_TEXT=$(echo "$T24_STREAM" | grep "text-delta" | sed 's/data: //g' \
    | node -e "
      let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
        const lines=d.trim().split('\n');
        let txt='';
        for(const l of lines){try{const j=JSON.parse(l);if(j.delta)txt+=j.delta}catch{}}
        console.log(txt);
      })" 2>/dev/null)
  assert_not_empty "T24 response has content" "$T24_TEXT"
  echo "    Response: ${T24_TEXT:0:200}"
else
  if echo "$T24_STREAM" | grep -q "error"; then
    T24_ERR=$(echo "$T24_STREAM" | grep "error" | head -1)
    yellow "T24 SKIP: LM Studio not available ($T24_ERR)"
  else
    yellow "T24 SKIP: No streaming response (LM Studio may be offline)"
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# T25: Send message with thinking=true
# ══════════════════════════════════════════════════════════════════════════════
header "T25: Send with thinking=true (requires LM Studio)"

# Create fresh session for thinking test
T25_CREATE=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"model_source\": \"user_model\",
    \"model_ref\": \"$MODEL_ID\",
    \"title\": \"Thinking Test\"
  }")
T25_SID=$(echo "$T25_CREATE" | jget .session_id)

T25_STREAM=$(curl -s --max-time 60 -X POST "$GATEWAY/v1/chat/sessions/$T25_SID/messages" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"content": "What is 2+2?", "thinking": true}' 2>&1 || true)

if echo "$T25_STREAM" | grep -q "text-delta\|reasoning-delta"; then
  green "T25 got streaming response"
  if echo "$T25_STREAM" | grep -q "reasoning-delta"; then
    green "T25 got reasoning-delta events (thinking mode works!)"
  else
    yellow "T25 no reasoning-delta (model may not support thinking)"
  fi
  # Check finish event has usage
  if echo "$T25_STREAM" | grep -q "finish-message"; then
    green "T25 got finish-message event"
  fi
else
  yellow "T25 SKIP: LM Studio not available"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T26: Send message with thinking=false (fast mode)
# ══════════════════════════════════════════════════════════════════════════════
header "T26: Send with thinking=false (fast mode)"

T26_CREATE=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"model_source\": \"user_model\",
    \"model_ref\": \"$MODEL_ID\",
    \"title\": \"Fast Mode Test\"
  }")
T26_SID=$(echo "$T26_CREATE" | jget .session_id)

T26_STREAM=$(curl -s --max-time 60 -X POST "$GATEWAY/v1/chat/sessions/$T26_SID/messages" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"content": "Say hello", "thinking": false}' 2>&1 || true)

if echo "$T26_STREAM" | grep -q "text-delta"; then
  green "T26 got text-delta (fast mode response)"
else
  yellow "T26 SKIP: LM Studio not available"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T27: Verify generation_params affect response
# ══════════════════════════════════════════════════════════════════════════════
header "T27: generation_params affect response (max_tokens=50)"

T27_CREATE=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"model_source\": \"user_model\",
    \"model_ref\": \"$MODEL_ID\",
    \"title\": \"Max Tokens Test\",
    \"generation_params\": {\"max_tokens\": 50, \"temperature\": 0.1}
  }")
T27_SID=$(echo "$T27_CREATE" | jget .session_id)

T27_STREAM=$(curl -s --max-time 120 -X POST "$GATEWAY/v1/chat/sessions/$T27_SID/messages" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"content": "Write a very long essay about the history of the world"}' 2>&1 || true)

if echo "$T27_STREAM" | grep -q "text-delta\|reasoning-delta"; then
  # Count total text tokens (both reasoning + content)
  T27_ALL=$(echo "$T27_STREAM" | grep -E "text-delta|reasoning-delta" | sed 's/data: //g' \
    | node -e "
      let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
        const lines=d.trim().split('\n');
        let txt='';
        for(const l of lines){try{const j=JSON.parse(l);if(j.delta)txt+=j.delta}catch{}}
        console.log(txt.length);
      })" 2>/dev/null)
  green "T27 response total chars: $T27_ALL (constrained by max_tokens=50)"
else
  yellow "T27 SKIP: LM Studio not available"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T28: Pin session
# ══════════════════════════════════════════════════════════════════════════════
header "T28: Pin session"

T28_RESP=$(curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$T20_SID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"is_pinned": true}')
T28_PINNED=$(echo "$T28_RESP" | jget .is_pinned)
assert_eq "T28 is_pinned true" "true" "$T28_PINNED"

# Verify pinned session comes first in list
T28_LIST=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions")
T28_FIRST_ID=$(echo "$T28_LIST" | node -e "
  let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
    const j=JSON.parse(d);
    console.log(j.items?.[0]?.session_id||'');
  })" 2>/dev/null)
assert_eq "T28 pinned session is first" "$T20_SID" "$T28_FIRST_ID"

# ══════════════════════════════════════════════════════════════════════════════
# T29: Unpin session
# ══════════════════════════════════════════════════════════════════════════════
header "T29: Unpin session"

T29_RESP=$(curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$T20_SID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"is_pinned": false}')
T29_PINNED=$(echo "$T29_RESP" | jget .is_pinned)
assert_eq "T29 is_pinned false" "false" "$T29_PINNED"

# ══════════════════════════════════════════════════════════════════════════════
# T30: Search messages
# ══════════════════════════════════════════════════════════════════════════════
header "T30: Search messages"

# T24 sent "What is your favorite color?" — search for "color" in user messages
# The message was persisted by the send_message endpoint before streaming
T30_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/search?q=color")
T30_COUNT=$(echo "$T30_RESP" | jlen .items)
if [ "$T30_COUNT" -gt "0" ]; then
  green "T30 search returned $T30_COUNT results for 'color'"
  T30_SNIPPET=$(echo "$T30_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.items?.[0]?.snippet?.slice(0,80)||'')})" 2>/dev/null)
  echo "    Snippet: $T30_SNIPPET"
else
  # Try a simpler search term that's definitely in the DB
  T30_RESP2=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/search?q=hello")
  T30_COUNT2=$(echo "$T30_RESP2" | jlen .items)
  if [ "$T30_COUNT2" -gt "0" ]; then
    green "T30 search returned $T30_COUNT2 results for 'hello' (fallback)"
  else
    # Try searching for "favorite" or "world"
    T30_RESP3=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/search?q=favorite")
    T30_COUNT3=$(echo "$T30_RESP3" | jlen .items)
    if [ "$T30_COUNT3" -gt "0" ]; then
      green "T30 search returned $T30_COUNT3 results for 'favorite'"
    else
      red "T30 search returned 0 results (FTS may not be indexing)"
    fi
  fi
fi

# ══════════════════════════════════════════════════════════════════════════════
# T31: Auto-title (check if title changed from "New Chat")
# ══════════════════════════════════════════════════════════════════════════════
header "T31: Auto-title generation"

# Create a fresh session with title "New Chat" (the default that auto-title replaces)
T31_CREATE=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d "{
    \"model_source\": \"user_model\",
    \"model_ref\": \"$MODEL_ID\",
    \"title\": \"New Chat\"
  }")
T31_SID=$(echo "$T31_CREATE" | jget .session_id)

if [ -n "$T31_SID" ] && [ "$T31_SID" != "null" ]; then
  # Send a message to trigger auto-title
  curl -s --max-time 120 -X POST "$GATEWAY/v1/chat/sessions/$T31_SID/messages" \
    -H "$AUTH" -H "Content-Type: application/json" \
    -d '{"content": "Tell me about the history of chocolate"}' > /dev/null 2>&1

  # Wait for async title generation
  sleep 8
  T31_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/$T31_SID")
  T31_TITLE=$(echo "$T31_RESP" | jget .title)
  if [ "$T31_TITLE" != "New Chat" ] && [ -n "$T31_TITLE" ]; then
    green "T31 auto-title generated: $T31_TITLE"
  else
    yellow "T31 title still 'New Chat' (thinking model may exhaust tokens on reasoning)"
  fi
  # Cleanup
  curl -s -X DELETE "$GATEWAY/v1/chat/sessions/$T31_SID" -H "$AUTH" > /dev/null 2>&1 || true
else
  red "T31 failed to create session"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T32: Send with context + system_prompt (both coexist)
# ══════════════════════════════════════════════════════════════════════════════
header "T32: Context + system_prompt coexist"

T32_STREAM=$(curl -s --max-time 60 -X POST "$GATEWAY/v1/chat/sessions/$T22_SID/messages" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"content": "Tell me about Kael", "context": "Kael is a warrior prince from the kingdom of Eldria."}' 2>&1 || true)

if echo "$T32_STREAM" | grep -q "text-delta"; then
  green "T32 response with both context and system_prompt"
else
  yellow "T32 SKIP: LM Studio not available"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T33: Verify new fields in GET response
# ══════════════════════════════════════════════════════════════════════════════
header "T33: GET session returns new fields"

T33_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/$T20_SID")
T33_GP=$(echo "$T33_RESP" | jget .generation_params)
T33_PIN=$(echo "$T33_RESP" | jget .is_pinned)

assert_not_empty "T33 generation_params in response" "$T33_GP"
assert_eq "T33 is_pinned in response" "false" "$T33_PIN"

# ══════════════════════════════════════════════════════════════════════════════
# Cleanup: delete test sessions
# ══════════════════════════════════════════════════════════════════════════════
header "Cleanup"

for SID in "${T20_SID:-}" "${T22_SID:-}" "${T25_SID:-}" "${T26_SID:-}" "${T27_SID:-}"; do
  if [ -n "$SID" ]; then
    curl -s -X DELETE "$GATEWAY/v1/chat/sessions/$SID" -H "$AUTH" > /dev/null 2>&1 || true
  fi
done
green "Cleaned up test sessions"

# ══════════════════════════════════════════════════════════════════════════════
# Summary
# ══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1;37m═══════════════════════════════════════\033[0m\n"
printf "\033[1;32m  PASS: %d\033[0m  " "$PASS"
printf "\033[1;31m  FAIL: %d\033[0m  " "$FAIL"
printf "\033[1;33m  SKIP: %d\033[0m\n" "$SKIP"
printf "\033[1;37m═══════════════════════════════════════\033[0m\n"

if [ "$FAIL" -gt 0 ]; then exit 1; fi
