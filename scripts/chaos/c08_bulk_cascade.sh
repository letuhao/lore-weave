#!/usr/bin/env bash
# T2-close-3 / C08 — Bulk chapter cascade (KSA §9.10)
#
# Chaos hypothesis:
#   If 1000 chapters are deleted in a single bulk operation, the
#   knowledge-service cascade path (`handle_chapter_deleted` →
#   `delete_source_cascade` + passage cleanup) must drain the
#   backlog without:
#     - running a 1000-statement Cypher transaction that stalls
#       Neo4j
#     - blocking extraction for other projects / users
#     - tripping the chapter.deleted consumer into the DLQ after
#       the default 3 retries
#
# What this script does NOT do:
#   - it does NOT go through the real book-service chapter-delete
#     HTTP path (that requires auth, a real book, cover assets,
#     etc.) — the compressed proxy is to seed the Neo4j side
#     directly and emit N `chapter.deleted` events into the Redis
#     stream. The knowledge-service consumer treats those events
#     identically to ones from book-service's outbox.
#
# Flow:
#   1. Seed 1000 fake :ExtractionSource nodes for a test user +
#      project, each attached to one orphan :Entity so
#      delete_source_cascade has real work to do.
#   2. Capture baseline: row count in dead_letter_events,
#      cascade duration metric (if exposed).
#   3. Emit 1000 chapter.deleted events onto the Redis stream in
#      a tight loop. No rate-limiting on the producer side — this
#      is a worst-case burst.
#   4. Poll Neo4j until the :ExtractionSource count for our test
#      user hits 0, or fail after 120 s.
#   5. Assert:
#      - All 1000 sources drained (ExtractionSource == 0)
#      - The cascade did not crash the consumer
#        (dead_letter_events unchanged AND new events still
#        process — we fire one post-burst probe and wait for ack)
#      - Total drain time in a sane window (not a hard assertion —
#        we log it and expect the user to eyeball it against the
#        K14.7 SLA; "1000 cascades / 120 s" = 8.3 evt/s is the
#        floor we'd want to beat)
#
# Caveats:
#   - This test does NOT validate rate-limiting in detail — the
#     K11.9 reconciler batching (D-K11.9-01 limit_per_label) and
#     the K15.10 quarantine sweep both have LIMIT clauses but
#     neither is on the cascade path. The cascade itself uses
#     `DETACH DELETE` per source_id which is naturally O(1) per
#     source. If you see per-source time climbing during the burst,
#     that's a Neo4j lock-contention issue, not a missing LIMIT.

set -euo pipefail
CHAOS_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$CHAOS_DIR/lib.sh"

log_step "C08 — Bulk chapter cascade (1000 chapters)"
require_infra

TEST_USER="00000000-0000-0000-c008-000000000001"
TEST_PROJECT="00000000-0000-0000-c008-000000000002"
BOOK_ID="00000000-0000-0000-c008-000000000003"
BATCH_SIZE=1000
STREAM="loreweave:events:chapter"
GROUP="knowledge-extractor"

cleanup() {
    log_step "cleanup — removing chaos-c08 test nodes + project row"
    cypher_q "
MATCH (n {user_id: '$TEST_USER'})
DETACH DELETE n
" >/dev/null || log_warn "cleanup cypher failed (non-fatal)"
    psql_exec loreweave_knowledge "
DELETE FROM extraction_pending WHERE user_id = '$TEST_USER';
DELETE FROM knowledge_projects WHERE user_id = '$TEST_USER';
" >/dev/null 2>&1 || true
}
trap cleanup EXIT

# ── Seed the knowledge_projects row ───────────────────────────────
# handle_chapter_deleted early-returns unless it can resolve book_id
# → (project_id, user_id) via `SELECT ... FROM knowledge_projects
# WHERE book_id = $1`. Without this seed the chaos never exercises
# the cascade — a trap the first author of this script stepped in
# (caught by review-impl HIGH).
log_step "seeding matching knowledge_projects row"
PROJECT_UUID="$TEST_PROJECT"
psql_exec loreweave_knowledge "
INSERT INTO knowledge_projects (project_id, user_id, name, project_type, book_id)
VALUES ('$PROJECT_UUID', '$TEST_USER', 'Chaos C08', 'book', '$BOOK_ID')
ON CONFLICT (project_id) DO NOTHING;
" >/dev/null

baseline_dlq=$(psql_q loreweave_knowledge "SELECT count(*) FROM dead_letter_events" | tr -d '[:space:]')
log_ts "baseline dead_letter_events = $baseline_dlq"

# chapter_uuid for i builds a valid UUID with the iteration index
# in the last segment — the handler's `_uuid()` parse tolerates
# non-UUID strings but uses None for downstream DELETEs; using real
# UUIDs exercises the same code path a real book-service delete
# would. `c0080000-0000-0000-0000-$(printf %012d)` yields
# c0080000-0000-0000-0000-000000000001 … -000000001000.
chapter_uuid() {
    printf 'c0080000-0000-0000-0000-%012d' "$1"
}

# ── Seed: 1000 :ExtractionSource nodes + orphan :Entity each ──────
log_step "seeding $BATCH_SIZE :ExtractionSource + :Entity pairs (one UNWIND)"
# Use one Cypher call with UNWIND range — writing 1000 creates in
# 1000 round trips would itself take a minute. source_id is built
# in-query with the same printf pattern so it matches the UUIDs the
# emit phase sends as aggregate_id.
cypher_q "
UNWIND range(1, $BATCH_SIZE) AS i
WITH i, 'c0080000-0000-0000-0000-' + substring('000000000000' + toString(i), size(toString(i))) AS uuid_suffix
CREATE (s:ExtractionSource {
  source_id: uuid_suffix,
  user_id: '$TEST_USER',
  project_id: '$TEST_PROJECT',
  book_id: '$BOOK_ID'
})
CREATE (e:Entity {
  entity_id: 'c08-entity-' + toString(i),
  user_id: '$TEST_USER',
  project_id: '$TEST_PROJECT',
  name: 'Chaos C08 entity ' + toString(i),
  evidence_count: 1
})
CREATE (e)-[:EVIDENCED_BY]->(s)
" >/dev/null

seeded=$(cypher_count_scalar "
MATCH (s:ExtractionSource {user_id: '$TEST_USER'}) RETURN count(s)
")
assert_eq "seeded ExtractionSource count" "$BATCH_SIZE" "$seeded"

# ── Inject: emit 1000 chapter.deleted events ──────────────────────
# Review-impl HIGH catch: a per-event `docker exec redis-cli XADD`
# costs ~240ms of docker-exec overhead, so 1000 iterations would
# take ~4 min BEFORE any cascade work starts — blowing past the
# 120 s drain budget and producing a false FAIL. Batch everything
# through a single `docker exec -i ... redis-cli` that reads XADD
# commands from stdin; measured ~2 s for 1000 emits.
log_step "emitting $BATCH_SIZE chapter.deleted events onto $STREAM (batched)"
t0=$(date +%s)
{
    for i in $(seq 1 $BATCH_SIZE); do
        chid=$(chapter_uuid "$i")
        # Each redis-cli stdin command is one line, space-separated
        # args. Our values contain no spaces — {} is treated as a
        # literal arg. If that ever changes, wrap the offending arg
        # in quotes the way redis-cli docs spec out.
        echo "XADD $STREAM * event_type chapter.deleted aggregate_type chapter aggregate_id $chid user_id $TEST_USER project_id $TEST_PROJECT book_id $BOOK_ID payload {}"
    done
} | docker exec -i "$REDIS_CONTAINER" redis-cli >/dev/null
t_emit=$(($(date +%s) - t0))
log_ts "emit phase done in ${t_emit}s"

# ── Observe: drain ────────────────────────────────────────────────
log_step "waiting for cascade to drain (120 s budget)"
t1=$(date +%s)
check_drained() {
    local remaining
    remaining=$(cypher_count_scalar "
MATCH (s:ExtractionSource {user_id: '$TEST_USER'}) RETURN count(s)
")
    [ "${remaining:-$BATCH_SIZE}" = "0" ]
}
wait_until 120 "ExtractionSource drain to 0" check_drained
t_drain=$(($(date +%s) - t1))
log_pass "drain complete in ${t_drain}s (throughput ≈ $((BATCH_SIZE / (t_drain == 0 ? 1 : t_drain))) evt/s)"

# ── Assertions ────────────────────────────────────────────────────
final_dlq=$(psql_q loreweave_knowledge "SELECT count(*) FROM dead_letter_events" | tr -d '[:space:]')
assert_eq "dead_letter_events unchanged (no crashes)" "$baseline_dlq" "$final_dlq"

orphan_entities=$(cypher_count_scalar "
MATCH (e:Entity {user_id: '$TEST_USER'})-[:EVIDENCED_BY]->()
RETURN count(e)
")
assert_eq "orphan Entity with stale edges" "0" "$orphan_entities"

# ── Post-burst probe: system still responsive ─────────────────────
log_step "post-burst probe — verifying consumer still responsive"
probe_id="c08-post-probe-$(date +%s)"
baseline_pending=$(redis_pending_count "$STREAM" "$GROUP")
redis_cmd XADD "$STREAM" '*' \
    event_type "chapter.probe" \
    aggregate_id "$probe_id" \
    payload '{}' >/dev/null

check_probe_acked() {
    local pending
    pending=$(redis_pending_count "$STREAM" "$GROUP")
    [ "${pending:-0}" = "${baseline_pending:-0}" ]
}
wait_until 15 "post-burst probe acked" check_probe_acked
log_pass "post-burst probe processed — consumer still healthy"

log_pass "C08 — Bulk chapter cascade drained ${BATCH_SIZE} events without overload"
echo "C08:PASS"
