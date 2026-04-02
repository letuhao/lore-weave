#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — Chat Service Integration Test (No AI Provider Needed)
#
# Tests session CRUD, message listing, and export through the gateway.
# Streaming/send is NOT tested (requires AI provider credentials).
#
# Prerequisites: all services running via docker compose
# Usage: bash infra/test-chat.sh
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

# JSON field extractor using node
# Usage: echo '{"a":1}' | jget .a
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

# JSON array length
# Usage: echo '{"items":[1,2]}' | jlen .items
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

# ── T00: Health check ──────────────────────────────────────────────────────────
header "T00: Chat service health"

# Health goes direct to chat-service (not proxied through gateway)
HEALTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost:8212/health")
assert_status "T00 chat-service health (direct)" "200" "$HEALTH_STATUS"

# Gateway is alive
GW_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/health")
assert_status "T00 gateway health" "200" "$GW_STATUS"

# ── Setup: Auth ────────────────────────────────────────────────────────────────
header "Setup: Authenticate"

UNAME="chattest_$(date +%s)"
EMAIL="$UNAME@test.com"

# Register (may return user object without token if verification required)
curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null

# Login to get token
LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}")
TOKEN=$(echo "$LOGIN_RESP" | jget .access_token)

assert_not_empty "Got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# ── T01: List sessions (empty) ─────────────────────────────────────────────────
header "T01: List sessions (initially empty)"

LIST_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions")
ITEM_COUNT=$(echo "$LIST_RESP" | jlen .items)
assert_eq "T01 empty session list" "0" "$ITEM_COUNT"

# ── T02: Create session ───────────────────────────────────────────────────────
header "T02: Create session"

# We use a fake model_ref — it only matters when actually sending a message
CREATE_RESP=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"model_source":"user_model","model_ref":"00000000-0000-0000-0000-000000000001","title":"Integration Test Chat"}')
SESSION_ID=$(echo "$CREATE_RESP" | jget .session_id)
SESSION_TITLE=$(echo "$CREATE_RESP" | jget .title)
SESSION_STATUS=$(echo "$CREATE_RESP" | jget .status)

assert_not_empty "T02 session_id exists" "$SESSION_ID"
assert_eq "T02 title" "Integration Test Chat" "$SESSION_TITLE"
assert_eq "T02 status" "active" "$SESSION_STATUS"

# ── T03: Get session by ID ────────────────────────────────────────────────────
header "T03: Get session by ID"

GET_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION_ID")
GET_TITLE=$(echo "$GET_RESP" | jget .title)
assert_eq "T03 title matches" "Integration Test Chat" "$GET_TITLE"

# ── T04: List sessions (has one) ──────────────────────────────────────────────
header "T04: List sessions (one session)"

LIST2_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions")
LIST2_COUNT=$(echo "$LIST2_RESP" | jlen .items)
assert_eq "T04 session count" "1" "$LIST2_COUNT"

# ── T05: Rename session ──────────────────────────────────────────────────────
header "T05: Patch session (rename)"

PATCH_RESP=$(curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$SESSION_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Renamed Chat"}')
PATCHED_TITLE=$(echo "$PATCH_RESP" | jget .title)
assert_eq "T05 renamed title" "Renamed Chat" "$PATCHED_TITLE"

# ── T06: List messages (empty session) ────────────────────────────────────────
header "T06: List messages (empty)"

MSG_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION_ID/messages")
MSG_COUNT=$(echo "$MSG_RESP" | jlen .items)
assert_eq "T06 no messages yet" "0" "$MSG_COUNT"

# ── T07: List outputs (empty session) ─────────────────────────────────────────
header "T07: List outputs (empty)"

OUT_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION_ID/outputs")
OUT_COUNT=$(echo "$OUT_RESP" | jlen .items)
assert_eq "T07 no outputs yet" "0" "$OUT_COUNT"

# ── T08: Export session (markdown, empty) ─────────────────────────────────────
header "T08: Export session (markdown)"

EXPORT_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION_ID/export?format=markdown")
assert_status "T08 export markdown" "200" "$EXPORT_STATUS"

# ── T09: Export session (json) ────────────────────────────────────────────────
header "T09: Export session (json)"

EXPORT_JSON_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION_ID/export?format=json")
assert_status "T09 export json" "200" "$EXPORT_JSON_STATUS"

# ── T10: Create second session ────────────────────────────────────────────────
header "T10: Create second session"

CREATE2_RESP=$(curl -s -X POST "$GATEWAY/v1/chat/sessions" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"model_source":"user_model","model_ref":"00000000-0000-0000-0000-000000000002","title":"Second Chat"}')
SESSION2_ID=$(echo "$CREATE2_RESP" | jget .session_id)
assert_not_empty "T10 second session_id" "$SESSION2_ID"

LIST3_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions")
LIST3_COUNT=$(echo "$LIST3_RESP" | jlen .items)
assert_eq "T10 now 2 sessions" "2" "$LIST3_COUNT"

# ── T11: Archive session ─────────────────────────────────────────────────────
header "T11: Archive session"

ARCHIVE_RESP=$(curl -s -X PATCH "$GATEWAY/v1/chat/sessions/$SESSION2_ID" \
  -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"status":"archived"}')
ARCHIVE_STATUS=$(echo "$ARCHIVE_RESP" | jget .status)
assert_eq "T11 status archived" "archived" "$ARCHIVE_STATUS"

# Archived sessions don't appear in default list
LIST4_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions")
LIST4_COUNT=$(echo "$LIST4_RESP" | jlen .items)
assert_eq "T11 active list has 1" "1" "$LIST4_COUNT"

# But appear with status=archived filter
LIST5_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions?status=archived")
LIST5_COUNT=$(echo "$LIST5_RESP" | jlen .items)
assert_eq "T11 archived list has 1" "1" "$LIST5_COUNT"

# ── T12: Delete session ──────────────────────────────────────────────────────
header "T12: Delete session"

DEL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION2_ID")
assert_status "T12 delete returns 204" "204" "$DEL_STATUS"

# Verify gone
GET_DEL_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION2_ID")
assert_status "T12 deleted session returns 404" "404" "$GET_DEL_STATUS"

# ── T13: Auth guard — no token ────────────────────────────────────────────────
header "T13: Auth guard"

NOAUTH_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/chat/sessions")
# Should be 401 or 403
if [ "$NOAUTH_STATUS" = "401" ] || [ "$NOAUTH_STATUS" = "403" ]; then
  green "T13 no-token rejected (HTTP $NOAUTH_STATUS)"; PASS=$((PASS+1))
else
  red "T13 no-token should be 401/403 (got $NOAUTH_STATUS)"; FAIL=$((FAIL+1))
fi

# ── T14: 404 on unknown session ──────────────────────────────────────────────
header "T14: 404 on unknown session"

UNKNOWN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -H "$AUTH" "$GATEWAY/v1/chat/sessions/00000000-0000-0000-0000-000000000099")
assert_status "T14 unknown session 404" "404" "$UNKNOWN_STATUS"

# ── T16: Send message with context field (BE-C1) ─────────────────────────────
header "T16: Context field accepted"

# Context field should be accepted without 422 — will get 404 (fake model) or 502 but NOT 422
CTX_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
  -X POST -H "$AUTH" -H "Content-Type: application/json" \
  "$GATEWAY/v1/chat/sessions/$SESSION_ID/messages" \
  -d '{"content":"Analyze this","context":"Chapter 3: Aldric walked in..."}')
# Accept 404 (model not found) or 502 (cred resolution) — just not 422 (validation)
if [ "$CTX_STATUS" != "422" ]; then
  green "T16 context field accepted (HTTP $CTX_STATUS, not 422)"; PASS=$((PASS+1))
else
  red "T16 context field rejected with 422 — model needs context field"; FAIL=$((FAIL+1))
fi

# Without context (backwards compat)
NOCTX_STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
  -X POST -H "$AUTH" -H "Content-Type: application/json" \
  "$GATEWAY/v1/chat/sessions/$SESSION_ID/messages" \
  -d '{"content":"Hello"}')
if [ "$NOCTX_STATUS" != "422" ]; then
  green "T16 no-context backwards compat (HTTP $NOCTX_STATUS)"; PASS=$((PASS+1))
else
  red "T16 no-context broke backwards compat"; FAIL=$((FAIL+1))
fi

# ── T15: Cleanup — delete remaining session ──────────────────────────────────
header "T15: Cleanup"

CLEAN_STATUS=$(curl -s -o /dev/null -w "%{http_code}" \
  -X DELETE -H "$AUTH" "$GATEWAY/v1/chat/sessions/$SESSION_ID")
assert_status "T15 cleanup delete" "204" "$CLEAN_STATUS"

FINAL_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/chat/sessions")
FINAL_COUNT=$(echo "$FINAL_RESP" | jlen .items)
assert_eq "T15 no sessions remain" "0" "$FINAL_COUNT"

# ── Summary ──────────────────────────────────────────────────────────────────
header "Summary"
TOTAL=$((PASS + FAIL))
printf "  Pass: %d / %d\n" "$PASS" "$TOTAL"
if [ "$FAIL" -gt 0 ]; then
  printf "  \033[31mFail: %d\033[0m\n" "$FAIL"
  exit 1
else
  printf "  \033[32mAll tests passed!\033[0m\n"
fi
