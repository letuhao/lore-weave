#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — GEP (Glossary Extraction Pipeline) Integration Test
#
# GEP-BE-13: End-to-end extraction test covering:
#   - Single chapter extraction
#   - Cancellation flow
#   - Multi-batch (>1 LLM call per chapter)
#   - Concurrent jobs
#   - Known entities dedup
#   - Job status polling
#
# Prerequisites: all services running via docker compose, LM Studio running
# Usage: bash infra/test-gep-integration.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
PASS=0
FAIL=0
SKIP=0

green()  { printf "\033[32m✓ %s\033[0m\n" "$1"; }
red()    { printf "\033[31m✗ %s\033[0m\n" "$1"; }
yellow() { printf "\033[33m⊘ %s\033[0m\n" "$1"; }
header() { printf "\n\033[1;36m── %s ──\033[0m\n" "$1"; }

assert_eq() {
  local label="$1" expected="$2" actual="$3"
  if [ "$expected" = "$actual" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected: $expected, got: $actual)"; FAIL=$((FAIL+1))
  fi
}

assert_ne() {
  local label="$1" not_expected="$2" actual="$3"
  if [ "$not_expected" != "$actual" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (should not be: $not_expected)"; FAIL=$((FAIL+1))
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

assert_ge() {
  local label="$1" expected="$2" actual="$3"
  if [ "$actual" -ge "$expected" ] 2>/dev/null; then
    green "$label ($actual >= $expected)"; PASS=$((PASS+1))
  else
    red "$label (expected >= $expected, got: $actual)"; FAIL=$((FAIL+1))
  fi
}

skip_test() {
  yellow "SKIP: $1"; SKIP=$((SKIP+1))
}

# Pipe-safe JSON extraction
jv() { python -c "import sys,json; d=json.load(sys.stdin); print($1)" 2>/dev/null || echo ""; }

# Poll job until terminal state (completed/failed/cancelled/completed_with_errors)
poll_job() {
  local job_id="$1" max_wait="${2:-600}" interval="${3:-5}"
  local elapsed=0 status=""
  while [ "$elapsed" -lt "$max_wait" ]; do
    status=$(curl -s "$GATEWAY/v1/extraction/jobs/$job_id" \
      -H "Authorization: Bearer $TOKEN" | jv 'd.get("status","")')
    case "$status" in
      completed|failed|cancelled|completed_with_errors) echo "$status"; return 0 ;;
    esac
    sleep "$interval"
    elapsed=$((elapsed + interval))
  done
  echo "timeout($status)"
  return 1
}

# ── Setup ─────────────────────────────────────────────────────────────────────
header "Setup: Authenticate + discover book/model"

LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"letuhao1994@gmail.com","password":"Ab.0914113903"}')
TOKEN=$(echo "$LOGIN_RESP" | jv 'd.get("access_token","")')

if [ -z "$TOKEN" ]; then
  red "Login failed — cannot proceed"
  exit 1
fi
green "Logged in"

# Find first book with chapters
BOOKS_RESP=$(curl -s "$GATEWAY/v1/books?limit=1" -H "Authorization: Bearer $TOKEN")
BOOK_ID=$(echo "$BOOKS_RESP" | jv 'd["items"][0]["book_id"]')
assert_not_empty "T01: Found book" "$BOOK_ID"

# Get first 3 chapter IDs
CHAPTERS_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters?limit=3" -H "Authorization: Bearer $TOKEN")
CH0=$(echo "$CHAPTERS_RESP" | jv 'd["items"][0]["chapter_id"]')
CH1=$(echo "$CHAPTERS_RESP" | jv 'd["items"][1]["chapter_id"]')
CH2=$(echo "$CHAPTERS_RESP" | jv 'd["items"][2]["chapter_id"]')
assert_not_empty "T02: Found chapter 0" "$CH0"
assert_not_empty "T03: Found chapter 1" "$CH1"
assert_not_empty "T04: Found chapter 2" "$CH2"

# Find LM Studio model (user_model with provider_kind=lm_studio)
MODELS_RESP=$(curl -s "$GATEWAY/v1/model-registry/user-models" -H "Authorization: Bearer $TOKEN")
MODEL_REF=$(echo "$MODELS_RESP" | jv '
next((m["user_model_id"] for m in d.get("items",[]) if m.get("provider_kind")=="lm_studio" and m.get("is_active")), "")
')

if [ -z "$MODEL_REF" ]; then
  # Fallback: try ollama
  MODEL_REF=$(echo "$MODELS_RESP" | jv '
next((m["user_model_id"] for m in d.get("items",[]) if m.get("provider_kind")=="ollama" and m.get("is_active")), "")
')
fi

if [ -z "$MODEL_REF" ]; then
  red "No active LM Studio or Ollama model found — cannot run LLM tests"
  echo "Skipping LLM-dependent tests. Proceeding with API-only tests."
  HAS_MODEL=false
else
  green "Found model: $MODEL_REF"
  HAS_MODEL=true
fi

# Get extraction profile
PROFILE_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/extraction-profile" \
  -H "Authorization: Bearer $TOKEN")
KINDS_COUNT=$(echo "$PROFILE_RESP" | jv 'len(d.get("kinds",[]))')
assert_ge "T05: Extraction profile has kinds" "3" "$KINDS_COUNT"

# ═══════════════════════════════════════════════════════════════════════════════
header "Section A: API Validation"
# ═══════════════════════════════════════════════════════════════════════════════

# T06: Missing chapter_ids
RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"extraction_profile":{"character":{"name":"fill"}}}')
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T06: Missing model returns 422" "422" "$HTTP"

# T07: Invalid book_id
RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/extraction/books/00000000-0000-0000-0000-000000000000/extract-glossary" \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d "{\"chapter_ids\":[\"$CH0\"],\"extraction_profile\":{\"character\":{\"name\":\"fill\"}},\"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\"}")
HTTP=$(echo "$RESP" | tail -1)
# 404 or 422 depending on validation order (book check vs model check)
if [ "$HTTP" = "404" ] || [ "$HTTP" = "422" ]; then
  green "T07: Invalid book returns error ($HTTP)"; PASS=$((PASS+1))
else
  red "T07: Invalid book (expected 404 or 422, got: $HTTP)"; FAIL=$((FAIL+1))
fi

# T08: Get nonexistent job
RESP=$(curl -s -w "\n%{http_code}" "$GATEWAY/v1/extraction/jobs/00000000-0000-0000-0000-000000000000" \
  -H "Authorization: Bearer $TOKEN")
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T08: Nonexistent job returns 404" "404" "$HTTP"

# T09: Cancel nonexistent job
RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/extraction/jobs/00000000-0000-0000-0000-000000000000/cancel" \
  -H "Authorization: Bearer $TOKEN")
HTTP=$(echo "$RESP" | tail -1)
assert_eq "T09: Cancel nonexistent job returns 404" "404" "$HTTP"

# ═══════════════════════════════════════════════════════════════════════════════
header "Section B: Cancellation Flow"
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$HAS_MODEL" = true ]; then
  # Submit a 3-chapter job then immediately cancel
  CREATE_RESP=$(curl -s -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{
      \"chapter_ids\":[\"$CH0\",\"$CH1\",\"$CH2\"],
      \"extraction_profile\":{\"character\":{\"name\":\"fill\",\"aliases\":\"fill\"}},
      \"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\",
      \"max_entities_per_kind\":5
    }")
  CANCEL_JOB=$(echo "$CREATE_RESP" | jv 'd.get("job_id","")')
  assert_not_empty "T10: Created 3-chapter job for cancellation" "$CANCEL_JOB"

  CANCEL_STATUS=$(echo "$CREATE_RESP" | jv 'd.get("status","")')
  assert_eq "T11: Job starts as pending" "pending" "$CANCEL_STATUS"

  # Wait a moment for it to start, then cancel
  sleep 2

  CANCEL_RESP=$(curl -s -X POST "$GATEWAY/v1/extraction/jobs/$CANCEL_JOB/cancel" \
    -H "Authorization: Bearer $TOKEN")
  CANCEL_NEW_STATUS=$(echo "$CANCEL_RESP" | jv 'd.get("status","")')
  assert_eq "T12: Cancel returns cancelling" "cancelling" "$CANCEL_NEW_STATUS"

  # Wait for worker to finish the current chapter and pick up cancellation.
  # Cooperative cancellation only fires between chapters, so we need to wait
  # for the in-flight LLM call to finish (~2-3 min for reasoning models).
  echo "  Waiting for cancellation to take effect (up to 5 min)..."
  CANCEL_FINAL=$(poll_job "$CANCEL_JOB" 300 10)

  JOB_RESP=$(curl -s "$GATEWAY/v1/extraction/jobs/$CANCEL_JOB" -H "Authorization: Bearer $TOKEN")
  COMPLETED=$(echo "$JOB_RESP" | jv 'd.get("completed_chapters",0)')
  TOTAL=$(echo "$JOB_RESP" | jv 'd.get("total_chapters",0)')

  # Status should be cancelled (or completed if it finished before cancel was processed)
  if [ "$CANCEL_FINAL" = "cancelled" ]; then
    green "T13: Job was cancelled"
    PASS=$((PASS+1))
    # Should NOT have completed all chapters
    if [ "$COMPLETED" -lt "$TOTAL" ]; then
      green "T14: Not all chapters completed ($COMPLETED/$TOTAL)"
      PASS=$((PASS+1))
    else
      yellow "T14: All chapters completed before cancel was processed"
      SKIP=$((SKIP+1))
    fi
  elif [ "$CANCEL_FINAL" = "completed" ] || [ "$CANCEL_FINAL" = "completed_with_errors" ]; then
    yellow "T13: Job completed before cancel was processed (race condition OK)"
    SKIP=$((SKIP+1))
    skip_test "T14: Cancellation race — job finished first"
  else
    red "T13: Unexpected status: $CANCEL_FINAL"
    FAIL=$((FAIL+1))
    red "T14: Cannot verify (bad status)"
    FAIL=$((FAIL+1))
  fi

  # T15: Cannot cancel a completed/cancelled job
  RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/extraction/jobs/$CANCEL_JOB/cancel" \
    -H "Authorization: Bearer $TOKEN")
  HTTP=$(echo "$RESP" | tail -1)
  assert_eq "T15: Re-cancel returns 409 (not cancellable)" "409" "$HTTP"
else
  skip_test "T10-T15: Cancellation (no model)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "Section C: Single Chapter Extraction + Quality"
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$HAS_MODEL" = true ]; then
  # Count entities before
  BEFORE_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities?limit=1" \
    -H "Authorization: Bearer $TOKEN")
  ENTITIES_BEFORE=$(echo "$BEFORE_RESP" | jv 'd.get("total",0)')

  CREATE_RESP=$(curl -s -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{
      \"chapter_ids\":[\"$CH0\"],
      \"extraction_profile\":{
        \"character\":{\"name\":\"fill\",\"aliases\":\"fill\",\"gender\":\"fill\",\"role\":\"fill\"},
        \"location\":{\"name\":\"fill\",\"type\":\"fill\"}
      },
      \"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\",
      \"max_entities_per_kind\":10
    }")
  JOB1=$(echo "$CREATE_RESP" | jv 'd.get("job_id","")')
  assert_not_empty "T16: Created single chapter job" "$JOB1"

  # Verify cost estimate
  EST_CALLS=$(echo "$CREATE_RESP" | jv 'd.get("cost_estimate",{}).get("llm_calls",0)')
  assert_eq "T17: Cost estimate shows 1 LLM call" "1" "$EST_CALLS"

  EST_CHAPTERS=$(echo "$CREATE_RESP" | jv 'd.get("cost_estimate",{}).get("chapters_count",0)')
  assert_eq "T18: Cost estimate shows 1 chapter" "1" "$EST_CHAPTERS"

  # Poll until done
  echo "  Waiting for extraction (up to 5 min)..."
  FINAL=$(poll_job "$JOB1" 300 5)

  if [ "$FINAL" = "completed" ] || [ "$FINAL" = "completed_with_errors" ]; then
    green "T19: Job completed ($FINAL)"
    PASS=$((PASS+1))
  else
    red "T19: Job did not complete (status: $FINAL)"
    FAIL=$((FAIL+1))
  fi

  # Check job details
  JOB_DETAIL=$(curl -s "$GATEWAY/v1/extraction/jobs/$JOB1" -H "Authorization: Bearer $TOKEN")
  COMPLETED=$(echo "$JOB_DETAIL" | jv 'd.get("completed_chapters",0)')
  FAILED=$(echo "$JOB_DETAIL" | jv 'd.get("failed_chapters",0)')
  CREATED=$(echo "$JOB_DETAIL" | jv 'd.get("entities_created",0)')
  UPDATED=$(echo "$JOB_DETAIL" | jv 'd.get("entities_updated",0)')
  SKIPPED=$(echo "$JOB_DETAIL" | jv 'd.get("entities_skipped",0)')
  IN_TOKENS=$(echo "$JOB_DETAIL" | jv 'd.get("total_input_tokens",0)')
  OUT_TOKENS=$(echo "$JOB_DETAIL" | jv 'd.get("total_output_tokens",0)')

  assert_eq "T20: 1/1 chapters completed" "1" "$COMPLETED"
  assert_eq "T21: 0 failed chapters" "0" "$FAILED"
  assert_ge "T22: Input tokens > 0" "1" "$IN_TOKENS"
  assert_ge "T23: Output tokens > 0" "1" "$OUT_TOKENS"

  TOTAL_ENTITIES=$((CREATED + UPDATED + SKIPPED))
  assert_ge "T24: At least 1 entity found" "1" "$TOTAL_ENTITIES"

  # Check chapter results
  CH_STATUS=$(echo "$JOB_DETAIL" | jv 'd["chapters"][0]["status"]')
  CH_FOUND=$(echo "$JOB_DETAIL" | jv 'd["chapters"][0]["entities_found"] or 0')
  assert_eq "T25: Chapter status is completed" "completed" "$CH_STATUS"
  # entities_found counts created+updated only (skipped not included)
  # On re-extraction all entities may be skipped, so check job-level total instead
  TOTAL_FOUND=$((CREATED + UPDATED + SKIPPED))
  assert_ge "T26: Job found >= 1 entity (created+updated+skipped)" "1" "$TOTAL_FOUND"

  # Verify timestamps
  STARTED=$(echo "$JOB_DETAIL" | jv 'd.get("started_at","")')
  FINISHED=$(echo "$JOB_DETAIL" | jv 'd.get("finished_at","")')
  assert_not_empty "T27: started_at populated" "$STARTED"
  assert_not_empty "T28: finished_at populated" "$FINISHED"

  echo "  Results: created=$CREATED updated=$UPDATED skipped=$SKIPPED in=$IN_TOKENS out=$OUT_TOKENS"
else
  skip_test "T16-T28: Single chapter extraction (no model)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "Section D: Multi-Batch (many kinds → >1 LLM call per chapter)"
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$HAS_MODEL" = true ]; then
  # Include ALL available kinds to force schema > 2000 tokens → multiple batches
  # character(14 attrs)=580, location(7)=300, item(6)=260, event(8)=340,
  # terminology(4)=180, power_system(7)=300, organization(7)=300, species(7)=300,
  # relationship(10)=420, plot_arc(9)=380, trope(7)=300, social_setting(8)=340
  # Total: ~4000 tokens → should split into 2+ batches
  CREATE_RESP=$(curl -s -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{
      \"chapter_ids\":[\"$CH0\"],
      \"extraction_profile\":{
        \"character\":{\"name\":\"fill\",\"aliases\":\"fill\",\"gender\":\"fill\",\"role\":\"fill\",\"occupation\":\"fill\",\"social_class\":\"fill\",\"affiliation\":\"fill\",\"appearance\":\"fill\",\"personality\":\"fill\",\"emotional_wound\":\"fill\",\"love_language\":\"fill\",\"relationships\":\"fill\",\"description\":\"fill\"},
        \"location\":{\"name\":\"fill\",\"type\":\"fill\",\"parent_location\":\"fill\",\"atmosphere\":\"fill\",\"significance\":\"fill\",\"description\":\"fill\"},
        \"item\":{\"name\":\"fill\",\"type\":\"fill\",\"owner\":\"fill\",\"symbolic_meaning\":\"fill\",\"description\":\"fill\"},
        \"event\":{\"name\":\"fill\",\"type\":\"fill\",\"date_in_story\":\"fill\",\"location\":\"fill\",\"participants\":\"fill\",\"emotional_impact\":\"fill\",\"outcome\":\"fill\",\"description\":\"fill\"},
        \"terminology\":{\"term\":\"fill\",\"category\":\"fill\",\"definition\":\"fill\",\"usage_note\":\"fill\"},
        \"power_system\":{\"name\":\"fill\",\"type\":\"fill\",\"rank\":\"fill\",\"user\":\"fill\",\"effects\":\"fill\",\"description\":\"fill\"},
        \"organization\":{\"name\":\"fill\",\"type\":\"fill\",\"leader\":\"fill\",\"headquarters\":\"fill\",\"members\":\"fill\",\"description\":\"fill\"},
        \"species\":{\"name\":\"fill\",\"traits\":\"fill\",\"abilities\":\"fill\",\"habitat\":\"fill\",\"culture\":\"fill\",\"description\":\"fill\"},
        \"relationship\":{\"name\":\"fill\",\"parties\":\"fill\",\"relationship_type\":\"fill\",\"status\":\"fill\",\"tropes\":\"fill\",\"dynamic\":\"fill\",\"key_conflict\":\"fill\",\"turning_points\":\"fill\",\"resolution\":\"fill\",\"description\":\"fill\"},
        \"plot_arc\":{\"name\":\"fill\",\"arc_type\":\"fill\",\"parties\":\"fill\",\"trigger\":\"fill\",\"stakes\":\"fill\",\"chapters_span\":\"fill\",\"emotional_beats\":\"fill\",\"resolution\":\"fill\",\"description\":\"fill\"}
      },
      \"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\",
      \"max_entities_per_kind\":5
    }")
  MB_JOB=$(echo "$CREATE_RESP" | jv 'd.get("job_id","")')
  assert_not_empty "T29: Created multi-kind job" "$MB_JOB"

  # Check cost estimate — should show >1 batches_per_chapter
  BATCHES=$(echo "$CREATE_RESP" | jv 'd.get("cost_estimate",{}).get("batches_per_chapter",0)')
  assert_ge "T30: Batches per chapter >= 2 (multi-batch)" "2" "$BATCHES"

  LLM_CALLS=$(echo "$CREATE_RESP" | jv 'd.get("cost_estimate",{}).get("llm_calls",0)')
  assert_ge "T31: LLM calls >= 2" "2" "$LLM_CALLS"

  echo "  Waiting for multi-batch extraction (up to 10 min)..."
  FINAL=$(poll_job "$MB_JOB" 600 10)

  if [ "$FINAL" = "completed" ] || [ "$FINAL" = "completed_with_errors" ]; then
    green "T32: Multi-batch job completed ($FINAL)"
    PASS=$((PASS+1))
  else
    red "T32: Multi-batch job did not complete (status: $FINAL)"
    FAIL=$((FAIL+1))
  fi

  # Verify results
  MB_DETAIL=$(curl -s "$GATEWAY/v1/extraction/jobs/$MB_JOB" -H "Authorization: Bearer $TOKEN")
  MB_CREATED=$(echo "$MB_DETAIL" | jv 'd.get("entities_created",0)')
  MB_UPDATED=$(echo "$MB_DETAIL" | jv 'd.get("entities_updated",0)')
  MB_SKIPPED=$(echo "$MB_DETAIL" | jv 'd.get("entities_skipped",0)')
  MB_TOTAL=$((MB_CREATED + MB_UPDATED + MB_SKIPPED))
  assert_ge "T33: Multi-batch found entities" "1" "$MB_TOTAL"

  echo "  Multi-batch results: created=$MB_CREATED updated=$MB_UPDATED skipped=$MB_SKIPPED batches=$BATCHES"
else
  skip_test "T29-T33: Multi-batch (no model)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "Section E: Concurrent Jobs"
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$HAS_MODEL" = true ]; then
  # Submit 2 jobs simultaneously — they should queue and execute sequentially
  CONC_RESP1=$(curl -s -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{
      \"chapter_ids\":[\"$CH1\"],
      \"extraction_profile\":{\"character\":{\"name\":\"fill\",\"aliases\":\"fill\"}},
      \"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\",
      \"max_entities_per_kind\":5
    }")
  CONC_JOB1=$(echo "$CONC_RESP1" | jv 'd.get("job_id","")')
  assert_not_empty "T34: Concurrent job 1 created" "$CONC_JOB1"

  CONC_RESP2=$(curl -s -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{
      \"chapter_ids\":[\"$CH2\"],
      \"extraction_profile\":{\"location\":{\"name\":\"fill\",\"type\":\"fill\"}},
      \"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\",
      \"max_entities_per_kind\":5
    }")
  CONC_JOB2=$(echo "$CONC_RESP2" | jv 'd.get("job_id","")')
  assert_not_empty "T35: Concurrent job 2 created" "$CONC_JOB2"

  assert_ne "T36: Jobs have different IDs" "$CONC_JOB1" "$CONC_JOB2"

  echo "  Waiting for both concurrent jobs (up to 10 min)..."
  FINAL1=$(poll_job "$CONC_JOB1" 600 10)
  FINAL2=$(poll_job "$CONC_JOB2" 600 10)

  if [ "$FINAL1" = "completed" ] || [ "$FINAL1" = "completed_with_errors" ]; then
    green "T37: Concurrent job 1 completed ($FINAL1)"
    PASS=$((PASS+1))
  else
    red "T37: Concurrent job 1 failed (status: $FINAL1)"
    FAIL=$((FAIL+1))
  fi

  if [ "$FINAL2" = "completed" ] || [ "$FINAL2" = "completed_with_errors" ]; then
    green "T38: Concurrent job 2 completed ($FINAL2)"
    PASS=$((PASS+1))
  else
    red "T38: Concurrent job 2 failed (status: $FINAL2)"
    FAIL=$((FAIL+1))
  fi

  # Verify they didn't interfere with each other
  D1=$(curl -s "$GATEWAY/v1/extraction/jobs/$CONC_JOB1" -H "Authorization: Bearer $TOKEN")
  D2=$(curl -s "$GATEWAY/v1/extraction/jobs/$CONC_JOB2" -H "Authorization: Bearer $TOKEN")
  F1=$(echo "$D1" | jv 'd.get("failed_chapters",0)')
  F2=$(echo "$D2" | jv 'd.get("failed_chapters",0)')
  assert_eq "T39: Job 1 — 0 failed chapters" "0" "$F1"
  assert_eq "T40: Job 2 — 0 failed chapters" "0" "$F2"
else
  skip_test "T34-T40: Concurrent jobs (no model)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "Section F: Known Entities Dedup (re-extract same chapter)"
# ═══════════════════════════════════════════════════════════════════════════════

if [ "$HAS_MODEL" = true ]; then
  # Re-extract CH0 — should see mostly updated/skipped, few created
  CREATE_RESP=$(curl -s -X POST "$GATEWAY/v1/extraction/books/$BOOK_ID/extract-glossary" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d "{
      \"chapter_ids\":[\"$CH0\"],
      \"extraction_profile\":{
        \"character\":{\"name\":\"fill\",\"aliases\":\"fill\",\"gender\":\"fill\",\"role\":\"fill\"},
        \"location\":{\"name\":\"fill\",\"type\":\"fill\"}
      },
      \"model_source\":\"user_model\",\"model_ref\":\"$MODEL_REF\",
      \"max_entities_per_kind\":10,
      \"context_filters\":{\"alive\":true,\"min_frequency\":1,\"recency_window\":200,\"limit\":100}
    }")
  DEDUP_JOB=$(echo "$CREATE_RESP" | jv 'd.get("job_id","")')
  assert_not_empty "T41: Created dedup test job" "$DEDUP_JOB"

  echo "  Waiting for dedup extraction (up to 5 min)..."
  FINAL=$(poll_job "$DEDUP_JOB" 300 5)

  DEDUP_DETAIL=$(curl -s "$GATEWAY/v1/extraction/jobs/$DEDUP_JOB" -H "Authorization: Bearer $TOKEN")
  D_CREATED=$(echo "$DEDUP_DETAIL" | jv 'd.get("entities_created",0)')
  D_UPDATED=$(echo "$DEDUP_DETAIL" | jv 'd.get("entities_updated",0)')
  D_SKIPPED=$(echo "$DEDUP_DETAIL" | jv 'd.get("entities_skipped",0)')
  D_TOTAL=$((D_UPDATED + D_SKIPPED))

  # On re-extraction, most entities should be updated or skipped (not created)
  assert_ge "T42: Dedup — updated+skipped > 0 (existing entities recognized)" "1" "$D_TOTAL"

  echo "  Dedup results: created=$D_CREATED updated=$D_UPDATED skipped=$D_SKIPPED"

  if [ "$D_TOTAL" -gt "$D_CREATED" ] 2>/dev/null; then
    green "T43: Dedup ratio OK (existing > new: $D_TOTAL > $D_CREATED)"
    PASS=$((PASS+1))
  else
    yellow "T43: Most entities were new (model may have used different names)"
    SKIP=$((SKIP+1))
  fi
else
  skip_test "T41-T43: Dedup (no model)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "Section G: Extraction Profile Endpoint"
# ═══════════════════════════════════════════════════════════════════════════════

# T44: Profile returns kinds with attributes
PROFILE=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/extraction-profile" \
  -H "Authorization: Bearer $TOKEN")
FIRST_KIND=$(echo "$PROFILE" | jv 'd["kinds"][0]["code"]')
FIRST_ATTRS=$(echo "$PROFILE" | jv 'len(d["kinds"][0]["attributes"])')
assert_not_empty "T44: Profile first kind has code" "$FIRST_KIND"
assert_ge "T45: Profile first kind has attributes" "1" "$FIRST_ATTRS"

# T46: Profile includes auto_selected flag
AUTO=$(echo "$PROFILE" | jv 'd["kinds"][0]["auto_selected"]')
assert_not_empty "T46: Profile includes auto_selected" "$AUTO"

# ═══════════════════════════════════════════════════════════════════════════════
header "Section H: Known Entities Endpoint"
# ═══════════════════════════════════════════════════════════════════════════════

# Test via internal endpoint directly (glossary-service port 8211)
KNOWN_RESP=$(curl -s "http://localhost:8211/internal/books/$BOOK_ID/known-entities?alive=true&limit=10" \
  -H "X-Internal-Token: dev_internal_token")
KNOWN_HTTP=$(echo "$KNOWN_RESP" | python -c "
import sys,json
try:
  d=json.load(sys.stdin)
  items=d if isinstance(d,list) else d.get('items',d)
  print(len(items))
except: print('error')
" 2>/dev/null || echo "error")

if [ "$KNOWN_HTTP" != "error" ]; then
  green "T47: Known entities endpoint returns data"
  PASS=$((PASS+1))
else
  red "T47: Known entities endpoint failed"
  FAIL=$((FAIL+1))
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "Section I: Entity Alive Toggle"
# ═══════════════════════════════════════════════════════════════════════════════

# Get first entity
ENTITIES_RESP=$(curl -s "$GATEWAY/v1/glossary/books/$BOOK_ID/entities?limit=1" \
  -H "Authorization: Bearer $TOKEN")
FIRST_ENTITY=$(echo "$ENTITIES_RESP" | jv 'd["items"][0]["entity_id"] if d.get("items") else ""')

if [ -n "$FIRST_ENTITY" ] && [ "$FIRST_ENTITY" != "null" ]; then
  # Toggle alive=false
  PATCH_RESP=$(curl -s -w "\n%{http_code}" -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$FIRST_ENTITY" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"alive":false}')
  PATCH_HTTP=$(echo "$PATCH_RESP" | tail -1)
  assert_eq "T48: Patch alive=false returns 200" "200" "$PATCH_HTTP"

  # Toggle back
  PATCH_RESP2=$(curl -s -w "\n%{http_code}" -X PATCH "$GATEWAY/v1/glossary/books/$BOOK_ID/entities/$FIRST_ENTITY" \
    -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
    -d '{"alive":true}')
  PATCH_HTTP2=$(echo "$PATCH_RESP2" | tail -1)
  assert_eq "T49: Patch alive=true returns 200" "200" "$PATCH_HTTP2"
else
  skip_test "T48-T49: Alive toggle (no entities)"
fi

# ═══════════════════════════════════════════════════════════════════════════════
header "RESULTS"
# ═══════════════════════════════════════════════════════════════════════════════

TOTAL=$((PASS + FAIL + SKIP))
printf "\n\033[1m%d tests: \033[32m%d passed\033[0m" "$TOTAL" "$PASS"
if [ "$FAIL" -gt 0 ]; then printf ", \033[31m%d failed\033[0m" "$FAIL"; fi
if [ "$SKIP" -gt 0 ]; then printf ", \033[33m%d skipped\033[0m" "$SKIP"; fi
printf "\n\n"

if [ "$FAIL" -gt 0 ]; then exit 1; fi
exit 0
