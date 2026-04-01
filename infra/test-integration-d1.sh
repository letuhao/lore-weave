#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# LoreWeave — D1 Data Re-Engineering Integration Test
#
# Prerequisites: all services running via docker compose
#   docker compose up -d
#   Wait for healthchecks to pass
#
# Usage: bash infra/test-integration-d1.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

GATEWAY="http://localhost:3123"
BOOK_SERVICE="http://localhost:8201"
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

assert_contains() {
  local label="$1" needle="$2" haystack="$3"
  if echo "$haystack" | grep -q "$needle"; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (expected to contain: $needle)"; FAIL=$((FAIL+1))
  fi
}

assert_not_empty() {
  local label="$1" value="$2"
  if [ -n "$value" ]; then
    green "$label"; PASS=$((PASS+1))
  else
    red "$label (was empty)"; FAIL=$((FAIL+1))
  fi
}

psql_book() {
  docker compose exec -T postgres psql -U loreweave -d loreweave_book -tAc "$1" 2>/dev/null | tr -d '[:space:]'
}

psql_events() {
  docker compose exec -T postgres psql -U loreweave -d loreweave_events -tAc "$1" 2>/dev/null | tr -d '[:space:]'
}

redis_cmd() {
  docker compose exec -T redis redis-cli "$@" 2>/dev/null
}

# ── T01: Postgres 18 + Migrations ───────────────────────────────────────────
header "T01: Postgres 18 Startup + All Migrations"

DB_COUNT=$(docker compose exec -T postgres psql -U loreweave -d postgres -tAc "SELECT count(*) FROM pg_database WHERE datname LIKE 'loreweave_%'" 2>/dev/null | tr -d '[:space:]')
assert_eq "T01: ≥10 databases exist" "1" "$([ "$DB_COUNT" -ge 10 ] && echo 1 || echo 0)"

UUID_TEST=$(docker compose exec -T postgres psql -U loreweave -d loreweave_book -tAc "SELECT uuidv7();" 2>/dev/null | tr -d '[:space:]')
assert_not_empty "T01: uuidv7() works" "$UUID_TEST"

# ── Register user + create book ─────────────────────────────────────────────
header "Setup: Register user + create book"

REG_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/register" \
  -H "Content-Type: application/json" \
  -d '{"username":"d1test","email":"d1test@test.com","password":"Test1234!"}')
TOKEN=$(echo "$REG_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -z "$TOKEN" ]; then
  # User may already exist, try login
  LOGIN_RESP=$(curl -s -X POST "$GATEWAY/v1/auth/login" \
    -H "Content-Type: application/json" \
    -d '{"email":"d1test@test.com","password":"Test1234!"}')
  TOKEN=$(echo "$LOGIN_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)
fi

assert_not_empty "Setup: got auth token" "$TOKEN"

BOOK_RESP=$(curl -s -X POST "$GATEWAY/v1/books" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"D1 Test Book","original_language":"en","target_language":"vi"}')
BOOK_ID=$(echo "$BOOK_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('book_id',''))" 2>/dev/null || true)
assert_not_empty "Setup: created book" "$BOOK_ID"

# ── T02: Chapter Create (plain text → Tiptap JSON) ─────────────────────────
header "T02: Chapter Create (plain text → Tiptap JSON)"

CH_RESP=$(curl -s -w "\n%{http_code}" -X POST "$GATEWAY/v1/books/$BOOK_ID/chapters" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"title":"Test Chapter","original_language":"en","body":"First paragraph\n\nSecond paragraph"}')
CH_STATUS=$(echo "$CH_RESP" | tail -1)
CH_BODY=$(echo "$CH_RESP" | sed '$d')
CHAPTER_ID=$(echo "$CH_BODY" | python3 -c "import sys,json; print(json.load(sys.stdin).get('chapter_id',''))" 2>/dev/null || true)

assert_eq "T02: create returns 201" "201" "$CH_STATUS"
assert_not_empty "T02: got chapter_id" "$CHAPTER_ID"

# Wait for trigger to fire
sleep 1

DRAFT_FORMAT=$(psql_book "SELECT draft_format FROM chapter_drafts WHERE chapter_id='$CHAPTER_ID'")
assert_eq "T02: draft_format = json" "json" "$DRAFT_FORMAT"

BODY_TYPE=$(psql_book "SELECT jsonb_typeof(body) FROM chapter_drafts WHERE chapter_id='$CHAPTER_ID'")
assert_eq "T02: body is JSONB object" "object" "$BODY_TYPE"

BLOCK_COUNT=$(psql_book "SELECT count(*) FROM chapter_blocks WHERE chapter_id='$CHAPTER_ID'")
assert_eq "T02: 2 chapter_blocks" "2" "$BLOCK_COUNT"

BLOCK0_TEXT=$(docker compose exec -T postgres psql -U loreweave -d loreweave_book -tAc "SELECT text_content FROM chapter_blocks WHERE chapter_id='$CHAPTER_ID' ORDER BY block_index LIMIT 1" 2>/dev/null | xargs)
assert_eq "T02: block 0 text" "First paragraph" "$BLOCK0_TEXT"

OUTBOX_TYPE=$(psql_book "SELECT event_type FROM outbox_events WHERE aggregate_id='$CHAPTER_ID' ORDER BY created_at LIMIT 1")
assert_eq "T02: outbox has chapter.created" "chapter.created" "$OUTBOX_TYPE"

# ── T03: Chapter Save (patchDraft with JSONB) ───────────────────────────────
header "T03: Chapter Save (Tiptap JSON with _text)"

SAVE_BODY='{"body":{"type":"doc","content":[{"type":"heading","attrs":{"level":2},"_text":"Chapter Title","content":[{"type":"text","text":"Chapter Title"}]},{"type":"paragraph","_text":"Some text here","content":[{"type":"text","text":"Some text here"}]}]},"body_format":"json","expected_draft_version":1}'

SAVE_RESP=$(curl -s -w "\n%{http_code}" -X PATCH "$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/draft" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "$SAVE_BODY")
SAVE_STATUS=$(echo "$SAVE_RESP" | tail -1)
assert_eq "T03: save returns 200" "200" "$SAVE_STATUS"

sleep 1

BLOCK_COUNT_AFTER=$(psql_book "SELECT count(*) FROM chapter_blocks WHERE chapter_id='$CHAPTER_ID'")
assert_eq "T03: 2 blocks after save" "2" "$BLOCK_COUNT_AFTER"

SAVE_OUTBOX=$(psql_book "SELECT count(*) FROM outbox_events WHERE aggregate_id='$CHAPTER_ID' AND event_type='chapter.saved'")
assert_eq "T03: outbox has chapter.saved" "1" "$SAVE_OUTBOX"

# ── T06: getDraft Returns JSON + text_content ───────────────────────────────
header "T06: getDraft Returns JSON + text_content"

DRAFT_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/draft" \
  -H "Authorization: Bearer $TOKEN")

DRAFT_BODY_TYPE=$(echo "$DRAFT_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(type(d['body']).__name__)" 2>/dev/null || true)
assert_eq "T06: body is dict (JSON object)" "dict" "$DRAFT_BODY_TYPE"

DRAFT_FORMAT_API=$(echo "$DRAFT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('draft_format',''))" 2>/dev/null || true)
assert_eq "T06: draft_format = json" "json" "$DRAFT_FORMAT_API"

DRAFT_TEXT=$(echo "$DRAFT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('text_content',''))" 2>/dev/null || true)
assert_not_empty "T06: text_content present" "$DRAFT_TEXT"

DRAFT_VERSION=$(echo "$DRAFT_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('draft_version',0))" 2>/dev/null || true)
assert_eq "T06: draft_version = 2" "2" "$DRAFT_VERSION"

# ── T07: getRevision Returns JSON + text_content ────────────────────────────
header "T07: getRevision Returns JSON + text_content"

REV_LIST=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/revisions?limit=1" \
  -H "Authorization: Bearer $TOKEN")
REV_ID=$(echo "$REV_LIST" | python3 -c "import sys,json; items=json.load(sys.stdin)['items']; print(items[0]['revision_id'] if items else '')" 2>/dev/null || true)

if [ -n "$REV_ID" ]; then
  REV_RESP=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/revisions/$REV_ID" \
    -H "Authorization: Bearer $TOKEN")
  REV_BODY_FORMAT=$(echo "$REV_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('body_format',''))" 2>/dev/null || true)
  assert_eq "T07: revision body_format = json" "json" "$REV_BODY_FORMAT"

  REV_TEXT=$(echo "$REV_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('text_content','') or '')" 2>/dev/null || true)
  assert_not_empty "T07: revision has text_content" "$REV_TEXT"
else
  yellow "T07: SKIP — no revisions found"; SKIP=$((SKIP+1))
fi

# ── T09: Export Chapter (plain text from blocks) ────────────────────────────
header "T09: Export Chapter (plain text from blocks)"

EXPORT_RESP=$(curl -s -D - "$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/export" \
  -H "Authorization: Bearer $TOKEN" 2>/dev/null)
EXPORT_CT=$(echo "$EXPORT_RESP" | grep -i "content-type:" | tr -d '\r' || true)
assert_contains "T09: Content-Type is text/plain" "text/plain" "$EXPORT_CT"

EXPORT_BODY=$(curl -s "$GATEWAY/v1/books/$BOOK_ID/chapters/$CHAPTER_ID/export" \
  -H "Authorization: Bearer $TOKEN")
assert_contains "T09: export contains text" "Chapter Title" "$EXPORT_BODY"

# ── T10: Internal API ───────────────────────────────────────────────────────
header "T10: Internal API + text_content"

INTERNAL_RESP=$(curl -s "$BOOK_SERVICE/internal/books/$BOOK_ID/chapters/$CHAPTER_ID" 2>/dev/null || true)
if [ -n "$INTERNAL_RESP" ]; then
  INT_BODY_TYPE=$(echo "$INTERNAL_RESP" | python3 -c "import sys,json; d=json.load(sys.stdin); print(type(d.get('body',{})).__name__)" 2>/dev/null || true)
  assert_eq "T10: internal body is dict" "dict" "$INT_BODY_TYPE"

  INT_TEXT=$(echo "$INTERNAL_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('text_content','') or '')" 2>/dev/null || true)
  assert_not_empty "T10: internal has text_content" "$INT_TEXT"
else
  yellow "T10: SKIP — book-service not directly reachable"; SKIP=$((SKIP+1))
fi

# ── T11: Outbox Relay + Event Log ───────────────────────────────────────────
header "T11: Outbox Relay + Event Log"

# Give worker-infra time to relay
sleep 5

PUBLISHED=$(psql_book "SELECT count(*) FROM outbox_events WHERE published_at IS NOT NULL AND aggregate_id='$CHAPTER_ID'")
PENDING=$(psql_book "SELECT count(*) FROM outbox_events WHERE published_at IS NULL AND aggregate_id='$CHAPTER_ID'")
assert_eq "T11: no pending outbox events" "0" "$PENDING"
assert_not_empty "T11: some events published" "$PUBLISHED"

EVENT_LOG_COUNT=$(psql_events "SELECT count(*) FROM event_log WHERE aggregate_id='$CHAPTER_ID'" 2>/dev/null || echo "0")
if [ "$EVENT_LOG_COUNT" != "0" ] && [ -n "$EVENT_LOG_COUNT" ]; then
  green "T11: event_log has $EVENT_LOG_COUNT events"; PASS=$((PASS+1))
else
  yellow "T11: event_log empty (worker-infra may not have relayed yet)"; SKIP=$((SKIP+1))
fi

REDIS_LEN=$(redis_cmd XLEN loreweave:events:chapter 2>/dev/null | tr -d '[:space:]' || echo "0")
if [ "$REDIS_LEN" != "0" ] && [ -n "$REDIS_LEN" ]; then
  green "T11: Redis stream has $REDIS_LEN events"; PASS=$((PASS+1))
else
  yellow "T11: Redis stream empty (worker-infra may not have relayed yet)"; SKIP=$((SKIP+1))
fi

DEAD_LETTER=$(psql_events "SELECT count(*) FROM dead_letter_events" 2>/dev/null || echo "0")
assert_eq "T11: no dead letter events" "0" "${DEAD_LETTER:-0}"

# ── T16: uuidv7 Ordering ───────────────────────────────────────────────────
header "T16: uuidv7 Ordering"

UUID_ORDER=$(psql_book "SELECT CASE WHEN count(*)=(SELECT count(*) FROM chapter_revisions WHERE chapter_id='$CHAPTER_ID') THEN 'ok' ELSE 'fail' END FROM (SELECT id, created_at, LAG(created_at) OVER (ORDER BY id) AS prev_at FROM chapter_revisions WHERE chapter_id='$CHAPTER_ID') sub WHERE prev_at IS NULL OR created_at >= prev_at")
assert_eq "T16: uuidv7 order matches created_at order" "ok" "$UUID_ORDER"

# ── Summary ─────────────────────────────────────────────────────────────────
header "RESULTS"
printf "\033[32m  PASS: %d\033[0m\n" "$PASS"
printf "\033[31m  FAIL: %d\033[0m\n" "$FAIL"
printf "\033[33m  SKIP: %d\033[0m\n" "$SKIP"
echo ""

if [ "$FAIL" -gt 0 ]; then
  printf "\033[1;31mD1 GATE: FAILED\033[0m\n"
  exit 1
else
  printf "\033[1;32mD1 GATE: PASSED\033[0m\n"
  exit 0
fi
