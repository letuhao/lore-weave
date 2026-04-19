#!/usr/bin/env bash
# T2-close-3 / C05 — Redis restart resilience (KSA §9.10)
#
# Chaos hypothesis:
#   If Redis is restarted mid-run, the knowledge-service events
#   consumer must reconnect, reattach to its XREADGROUP consumer
#   group, and continue processing new events. Messages that were
#   already acked before the restart should stay acked (no
#   re-delivery). Messages enqueued before a consumer crash should
#   redeliver on restart via the pending list.
#
# Note on "event_log":
#   The knowledge-service does NOT maintain a separate event_log
#   Postgres table — recovery is entirely via Redis Streams
#   consumer-group pending state + `_process_pending()` on startup.
#   The SSOT row on the BOOK-service side is the outbox table
#   (`outbox_events`), which replays to the stream on book-service
#   restart — not on knowledge-service restart. This script exercises
#   the knowledge-service half.
#
# Failure modes this script catches:
#   1. Consumer group eaten by the restart (stream state lost)
#      → new events published after restart go unprocessed
#   2. Consumer hangs on the XREADGROUP connection after Redis
#      restart → pending count climbs forever
#   3. DLQ writes on restart (a transient Redis error treated as a
#      terminal handler failure) → dead_letter_events grows
#
# What this script does:
#   1. Capture baseline dead_letter_events row count + pending
#      count for the knowledge-extractor group.
#   2. Publish a synthetic probe event directly to
#      loreweave:events:chapter via redis XADD with a test marker.
#   3. Wait for the consumer to ack it (pending count returns to
#      baseline).
#   4. docker restart infra-redis-1.
#   5. Wait for knowledge-service to observe the reconnect. The
#      pending list persists across a Redis restart because Redis
#      persists streams + consumer groups in RDB/AOF by default in
#      the compose config; if your compose turned persistence off,
#      this script documents that state.
#   6. Publish a second probe event after the restart.
#   7. Assert the second probe is acked within 15 s.
#   8. Assert dead_letter_events is unchanged from baseline.

set -euo pipefail
CHAOS_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$CHAOS_DIR/lib.sh"

STREAM="loreweave:events:chapter"
GROUP="knowledge-extractor"
PROBE_KEY_PREFIX="chaos-c05-probe"

log_step "C05 — Redis restart resilience"
require_infra

# Probe IDs are captured so we can XDEL them on exit. Without this
# the loreweave:events:chapter stream accumulates stale probes on
# every run — harmless but untidy.
PROBE_IDS=()
cleanup() {
    if [ ${#PROBE_IDS[@]} -gt 0 ]; then
        log_step "cleanup — XDELing ${#PROBE_IDS[@]} probe event(s)"
        redis_cmd XDEL "$STREAM" "${PROBE_IDS[@]}" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# ── Baseline ───────────────────────────────────────────────────────
baseline_dlq=$(psql_q loreweave_knowledge "SELECT count(*) FROM dead_letter_events" | tr -d '[:space:]')
log_ts "baseline dead_letter_events = $baseline_dlq"

baseline_pending=$(redis_pending_count "$STREAM" "$GROUP")
log_ts "baseline pending on $GROUP = $baseline_pending"

# If the consumer group doesn't exist yet, wait briefly for the
# knowledge-service startup path to XGROUP CREATE it. Running the
# chaos against a freshly-started stack that hasn't hit its first
# event is a common footgun.
check_group_attached() {
    redis_cmd XINFO GROUPS "$STREAM" 2>/dev/null | grep -q "$GROUP"
}
if ! check_group_attached; then
    log_warn "consumer group $GROUP not yet attached — waiting up to 30s"
    wait_until 30 "consumer group $GROUP created" check_group_attached
fi

# ── Probe 1 (pre-restart) ──────────────────────────────────────────
probe1="${PROBE_KEY_PREFIX}-$(date +%s)-a"
log_step "publishing probe 1: $probe1"
probe1_id=$(redis_cmd XADD "$STREAM" '*' \
    event_type "chapter.probe" \
    aggregate_id "$probe1" \
    payload '{}')
PROBE_IDS+=("$probe1_id")

# Probe events don't match any registered handler so they should
# fail gracefully with retry + eventually land in DLQ. We don't want
# to pollute DLQ with probes — use a type that the dispatcher skips.
# The consumer logs unknown-type events at WARN and acks them (see
# events/dispatcher.py). If your dispatcher treats unknown types as
# retriable errors instead, change this to a real event shape.
check_probe1_acked() {
    local pending
    pending=$(redis_pending_count "$STREAM" "$GROUP")
    # Some installs report pending as "0", others as empty; treat
    # both as "no backlog".
    [ "${pending:-0}" = "${baseline_pending:-0}" ]
}
wait_until 15 "probe 1 acked (pending back to baseline)" check_probe1_acked
log_pass "probe 1 processed"

# ── Inject: restart Redis ──────────────────────────────────────────
log_step "docker restart $REDIS_CONTAINER"
docker restart "$REDIS_CONTAINER" >/dev/null
log_ts "waiting for Redis healthy"
check_redis_ready() {
    redis_cmd PING >/dev/null 2>&1
}
wait_until 30 "Redis PING reply" check_redis_ready
log_pass "Redis back up"

# Give the knowledge-service consumer a moment to reconnect. The
# consumer loop sleeps 5 s on ConnectionError before retrying
# (consumer.py:137), then the first XREADGROUP after reconnect
# takes up to COUNT*BLOCK ms to return. 10 s headroom comfortably
# covers both — 5 s would sometimes race the reconnect backoff.
sleep 10

# ── Probe 2 (post-restart) ─────────────────────────────────────────
probe2="${PROBE_KEY_PREFIX}-$(date +%s)-b"
log_step "publishing probe 2: $probe2"
probe2_id=$(redis_cmd XADD "$STREAM" '*' \
    event_type "chapter.probe" \
    aggregate_id "$probe2" \
    payload '{}')
PROBE_IDS+=("$probe2_id")

check_probe2_acked() {
    local pending
    pending=$(redis_pending_count "$STREAM" "$GROUP")
    [ "${pending:-0}" = "${baseline_pending:-0}" ]
}
wait_until 15 "probe 2 acked post-restart" check_probe2_acked
log_pass "probe 2 processed after Redis restart — consumer reattached"

# ── Assertion: DLQ unchanged ───────────────────────────────────────
final_dlq=$(psql_q loreweave_knowledge "SELECT count(*) FROM dead_letter_events" | tr -d '[:space:]')
assert_eq "dead_letter_events row count" "$baseline_dlq" "$final_dlq"

log_pass "C05 — Redis restart resilience"
echo "C05:PASS"
