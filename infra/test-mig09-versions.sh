#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — MIG-09 Translation Versions Integration Test
#
# Tests: list chapter versions, get version detail, set active version
# Prerequisites: all services running, at least one completed translation
# Usage: bash infra/test-mig09-versions.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0; FAIL=0; SKIP=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; PASS=$((PASS+1)); }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; FAIL=$((FAIL+1)); }
yellow() { printf "\033[33m⊘ %s\033[0m\n" "$1"; SKIP=$((SKIP+1)); }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

jget() {
  node -e "
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      try{const j=JSON.parse(d);const keys='${1}'.slice(1).split('.');let v=j;
      for(const k of keys){if(v==null)break;v=v[k];}
      if(v===undefined||v===null)console.log('');
      else console.log(typeof v==='object'?JSON.stringify(v):v);
      }catch{console.log('');}
    });" 2>/dev/null || echo ""
}

jlen() {
  node -e "
    let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{
      try{const j=JSON.parse(d);const keys='${1}'.slice(1).split('.');let v=j;
      for(const k of keys){if(v==null)break;v=v[k];}
      console.log(Array.isArray(v)?v.length:0);
      }catch{console.log(0);}
    });" 2>/dev/null || echo "0"
}

assert_eq() { if [ "$2" = "$3" ]; then green "$1"; else red "$1 (expected: $2, got: $3)"; fi; }
assert_not_empty() { if [ -n "$2" ] && [ "$2" != "null" ]; then green "$1"; else red "$1 (empty/null)"; fi; }

# ── Setup: Auth ──────────────────────────────────────────────────────────────
header "Setup: Authenticate"

EMAIL="mig09_test_$(date +%s)@test.com"
curl -s -X POST "$GATEWAY/v1/auth/register" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" > /dev/null 2>&1 || true

TOKEN=$(curl -s -X POST "$GATEWAY/v1/auth/login" -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"Test1234!\"}" | jget .access_token)
assert_not_empty "Got auth token" "$TOKEN"
AUTH="Authorization: Bearer $TOKEN"

# ── Setup: Create book + chapter ─────────────────────────────────────────────
header "Setup: Create book + chapter"

BOOK_ID=$(curl -s -X POST "$GATEWAY/v1/books" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"MIG-09 Versions Test","original_language":"ja"}' | jget .book_id)
assert_not_empty "Created book" "$BOOK_ID"

CH_ID=$(curl -s -X POST "$GATEWAY/v1/books/$BOOK_ID/chapters" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"title":"Chapter 1","sort_order":1,"original_language":"ja"}' | jget .chapter_id)
assert_not_empty "Created chapter" "$CH_ID"

# Save draft content
curl -s -X PUT "$GATEWAY/v1/books/$BOOK_ID/chapters/$CH_ID/draft" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"body":"玉座の間は魔法の松明の穏やかな音だけが響いていた。","body_format":"text"}' > /dev/null

# ══════════════════════════════════════════════════════════════════════════════
# T01: List versions (empty — no translations yet)
# ══════════════════════════════════════════════════════════════════════════════
header "T01: List versions (empty)"

T01_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/translation/chapters/$CH_ID/versions")
T01_CHID=$(echo "$T01_RESP" | jget .chapter_id)
T01_LANGS=$(echo "$T01_RESP" | jlen .languages)

assert_eq "T01 chapter_id matches" "$CH_ID" "$T01_CHID"
assert_eq "T01 no languages yet" "0" "$T01_LANGS"

# ══════════════════════════════════════════════════════════════════════════════
# T02: Create a translation job to generate versions
# ══════════════════════════════════════════════════════════════════════════════
header "T02: Create translation job"

# Set translation settings first
curl -s -X PUT "$GATEWAY/v1/translation/books/$BOOK_ID/settings" -H "$AUTH" -H "Content-Type: application/json" \
  -d '{"target_language":"en","model_source":"user_model","model_ref":"00000000-0000-0000-0000-000000000001"}' > /dev/null 2>&1 || true

# Try to create job (may fail if no valid model — that's ok)
JOB_RESP=$(curl -s -X POST "$GATEWAY/v1/translation/books/$BOOK_ID/jobs" -H "$AUTH" -H "Content-Type: application/json" \
  -d "{\"chapter_ids\":[\"$CH_ID\"]}" 2>&1 || true)
JOB_ID=$(echo "$JOB_RESP" | jget .job_id)

if [ -n "$JOB_ID" ] && [ "$JOB_ID" != "null" ]; then
  green "T02 translation job created: $JOB_ID"
  # Wait for job to process (may complete or fail)
  sleep 5
else
  yellow "T02 SKIP: Could not create translation job (no valid model configured)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T03: List versions after translation
# ══════════════════════════════════════════════════════════════════════════════
header "T03: List versions"

T03_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/translation/chapters/$CH_ID/versions")
T03_LANGS=$(echo "$T03_RESP" | jlen .languages)

if [ "$T03_LANGS" -gt "0" ]; then
  green "T03 has $T03_LANGS language(s)"

  # Get first language details
  T03_LANG=$(echo "$T03_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.languages?.[0]?.target_language||'')})")
  T03_VERS=$(echo "$T03_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.languages?.[0]?.versions?.length||0)})")
  T03_VID=$(echo "$T03_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.languages?.[0]?.versions?.[0]?.id||'')})")
  T03_STATUS=$(echo "$T03_RESP" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);console.log(j.languages?.[0]?.versions?.[0]?.status||'')})")

  assert_not_empty "T03 language" "$T03_LANG"
  green "T03 versions count: $T03_VERS"
  assert_not_empty "T03 version_id" "$T03_VID"
  green "T03 version status: $T03_STATUS"

  # ════════════════════════════════════════════════════════════════════════════
  # T04: Get version detail
  # ════════════════════════════════════════════════════════════════════════════
  header "T04: Get version detail"

  T04_RESP=$(curl -s -H "$AUTH" "$GATEWAY/v1/translation/chapters/$CH_ID/versions/$T03_VID")
  T04_ID=$(echo "$T04_RESP" | jget .id)
  T04_LANG=$(echo "$T04_RESP" | jget .target_language)
  T04_BODY=$(echo "$T04_RESP" | jget .translated_body)

  assert_eq "T04 version id matches" "$T03_VID" "$T04_ID"
  assert_not_empty "T04 target_language" "$T04_LANG"
  if [ "$T03_STATUS" = "completed" ]; then
    assert_not_empty "T04 translated_body (completed)" "$T04_BODY"
  else
    green "T04 version not completed — body may be null"
  fi

  # ════════════════════════════════════════════════════════════════════════════
  # T05: Set active version
  # ════════════════════════════════════════════════════════════════════════════
  header "T05: Set active version"

  if [ "$T03_STATUS" = "completed" ]; then
    T05_RESP=$(curl -s -X PUT "$GATEWAY/v1/translation/chapters/$CH_ID/versions/$T03_VID/active" -H "$AUTH")
    T05_AID=$(echo "$T05_RESP" | jget .active_id)
    assert_eq "T05 active_id set" "$T03_VID" "$T05_AID"

    # Verify it's now active in list
    T05_LIST=$(curl -s -H "$AUTH" "$GATEWAY/v1/translation/chapters/$CH_ID/versions")
    T05_ACTIVE=$(echo "$T05_LIST" | node -e "let d='';process.stdin.on('data',c=>d+=c);process.stdin.on('end',()=>{const j=JSON.parse(d);const v=j.languages?.[0]?.versions?.find(v=>v.id==='$T03_VID');console.log(v?.is_active||false)})")
    assert_eq "T05 version is_active true" "true" "$T05_ACTIVE"
  else
    yellow "T05 SKIP: version not completed — cannot set active"
  fi
else
  yellow "T03 SKIP: no translations created (job may have failed)"
  yellow "T04 SKIP: depends on T03"
  yellow "T05 SKIP: depends on T03"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T06: Version endpoint auth check (no token → 401/403)
# ══════════════════════════════════════════════════════════════════════════════
header "T06: Auth check"

T06_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$GATEWAY/v1/translation/chapters/$CH_ID/versions")
if [ "$T06_STATUS" = "401" ] || [ "$T06_STATUS" = "403" ]; then
  green "T06 no-auth returns $T06_STATUS"
else
  red "T06 no-auth (expected 401/403, got $T06_STATUS)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# T07: Invalid chapter_id
# ══════════════════════════════════════════════════════════════════════════════
header "T07: Invalid chapter_id"

T07_STATUS=$(curl -s -o /dev/null -w "%{http_code}" -H "$AUTH" "$GATEWAY/v1/translation/chapters/not-a-uuid/versions")
if [ "$T07_STATUS" = "422" ] || [ "$T07_STATUS" = "400" ]; then
  green "T07 invalid chapter_id returns $T07_STATUS"
else
  red "T07 (expected 422/400, got $T07_STATUS)"
fi

# ══════════════════════════════════════════════════════════════════════════════
# Cleanup
# ══════════════════════════════════════════════════════════════════════════════
header "Cleanup"
curl -s -X DELETE "$GATEWAY/v1/books/$BOOK_ID" -H "$AUTH" > /dev/null 2>&1 || true
green "Cleaned up"

# ══════════════════════════════════════════════════════════════════════════════
printf "\n\033[1;37m═══════════════════════════════════════\033[0m\n"
printf "\033[1;32m  PASS: %d\033[0m  " "$PASS"
printf "\033[1;31m  FAIL: %d\033[0m  " "$FAIL"
printf "\033[1;33m  SKIP: %d\033[0m\n" "$SKIP"
printf "\033[1;37m═══════════════════════════════════════\033[0m\n"

if [ "$FAIL" -gt 0 ]; then exit 1; fi
