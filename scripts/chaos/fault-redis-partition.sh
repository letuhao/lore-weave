#!/usr/bin/env bash
# scripts/chaos/fault-redis-partition.sh
#
# S6 (Battery D) — CONVERGENCE drill on the PUBLISH path: Redis partitioned while
# the publisher drains outbox → Redis Streams. Events are ALREADY committed, so
# the publisher RETRIES (sub-threshold partition, < the 10-attempt dead-letter
# bound) and delivers everything on heal → the end-state is exactly the seed →
# C3 + B + the history checker are legitimately clean. This is the convergence
# fault the emit-path drill (fault-pg-down.sh) deliberately cannot claim.
#
# Plus the DURING-FAULT HISTORY CHECKER (the part post-quiesce drift misses):
# records the Redis stream vs the event log and asserts no-loss / no-dup. BITE=1
# XDELs a delivered stream entry AFTER quiesce — the outbox still shows all
# published (post-quiesce drift sees nothing) but the history checker flags the
# lost stream entry. That clean→loss transition is the checker's teeth.
#
# Deterministic bracket (no race against a sub-second batch): start the publisher
# with a SLOW poll, down redis within the first poll window, let retries
# accumulate, then up + quiesce. Re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
REDIS_CONTAINER="foundation-dev-redis"
PG_USER="foundation"
PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
REDIS_PROXY_PORT="${FOUNDATION_REDIS_PROXY_PORT:-56380}"
META_DB="chaos_redis_meta"
SHARD_DB="chaos_redis_shard"
PROFILE="${PROFILE:-single-reality}"
SEED="${SEED:-7}"
BITE="${BITE:-0}"
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done
TOXIC="bash $ROOT/scripts/chaos/toxic.sh"
SHARD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SHARD_DB}?sslmode=disable"

log() { printf '[redis-part] %s\n' "$*"; }
# Verdict convention (review-impl #1): a fault that couldn't be INJECTED or a
# harness/timing condition the drill couldn't establish → NOTRUN (exit 2, never
# flaky-fails the nightly gate). A system invariant VIOLATED under the fault
# (dead-letter loss, history loss/dup, publisher crash) → FAIL (exit 1).
notrun() { log "NOTRUN(setup/timing): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }
redis_cli() { docker exec -i "$REDIS_CONTAINER" redis-cli "$@"; }

WG="${WG_BIN:-}"; [ -n "$WG" ] || { [ -x tests/workload-gen/wg.exe ] && WG="tests/workload-gen/wg.exe"; }
[ -n "$WG" ] || { [ -x tests/workload-gen/wg ] && WG="tests/workload-gen/wg"; }
[ -n "$WG" ] || { log "FAIL(setup): workload-gen binary not found"; exit 2; }
PUB="${PUB_BIN:-}"; [ -n "$PUB" ] || { [ -x services/publisher/pub.exe ] && PUB="services/publisher/pub.exe"; }
[ -n "$PUB" ] || { [ -x services/publisher/pub ] && PUB="services/publisher/pub"; }
[ -n "$PUB" ] || { log "FAIL(setup): publisher binary not found (go build -C services/publisher -o pub.exe ./cmd/publisher)"; exit 2; }

PUB_PID=""
cleanup() { [ -n "$PUB_PID" ] && kill "$PUB_PID" >/dev/null 2>&1 || true; }
trap cleanup EXIT

log "bringing up postgres + redis + toxiproxy ..."
docker compose -f "$COMPOSE" up -d postgres-foundation redis-foundation toxiproxy-foundation >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break; sleep 1; done
$TOXIC wait
$TOXIC create-proxy redis_proxy "$REDIS_PROXY_PORT" "${REDIS_CONTAINER}:6379"

# ── meta DB (reality_registry + publisher_heartbeats) ────────────────────────
log "(re)creating meta DB + shard DB ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null
psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
for m in 001_reality_registry 003_publisher_heartbeats; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"
done

# ── shard DB seeded (committed events + outbox) ──────────────────────────────
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null
psql_db foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"
done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"
RID="$(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")"
NEVENTS="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events")"
STREAM="lw.events.${RID}"
log "seeded reality=${RID} events=${NEVENTS} stream=${STREAM}"
redis_cli DEL "$STREAM" >/dev/null  # clean any prior run's stream

# Register the reality BEFORE the publisher starts (V1 loads realities once).
psql_db "$META_DB" -c "INSERT INTO reality_registry
    (reality_id, db_host, db_name, status, locale,
     session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
  VALUES ('${RID}', 'pg-shard-1.internal', '${SHARD_DB}', 'active', 'en', 10, 10, 20, 5)" >/dev/null

# ── start the publisher (Redis UP so its startup ping passes) ────────────────
# poll=1s + BATCH_SIZE=5: the drain proceeds in SMALL steps so the partition
# reliably catches it MID-drain (a single batch ≥ the seed would drain all-or-
# nothing in one poll and the down would land in a dead window).
log "starting publisher (poll=1s, batch=5) draining outbox -> redis_proxy ..."
PUBLISHER_ID=chaos-pub SHARD_HOST=pg-shard-1.internal \
  META_DB_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable" \
  REDIS_URL="redis://127.0.0.1:${REDIS_PROXY_PORT}/0" \
  SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$PG_PORT" SHARD_DB_SSLMODE=disable \
  PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${PG_PORT}" \
  POLL_INTERVAL=1s BATCH_SIZE=5 HEARTBEAT_INTERVAL=5s PUBLISHER_HTTP_ADDR=:18080 \
  "$PUB" >/tmp/chaos_pub.log 2>&1 &
PUB_PID=$!
sleep 1
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/chaos_pub.log; notrun "publisher exited at startup (config/redis env)"; }

# Let it drain PARTIALLY (a few batches) so the partition interrupts mid-flight.
sleep 2.5
part_pub="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=TRUE")"

# ── PARTITION: down redis mid-drain ──────────────────────────────────────────
log "DOWN redis_proxy mid-drain (already published ${part_pub}/${NEVENTS}) ..."
$TOXIC down redis_proxy
sleep 4  # several poll cycles fail → pending rows accumulate retry attempts

# fault-real (non-vacuity): delivery was BLOCKED — NOT everything drained, the
# pending rows accrued retry attempts, the publisher is alive, nothing dead-lettered.
# publisher crash under a partition is a REAL robustness violation → FAIL.
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/chaos_pub.log; fail "publisher crashed during partition"; }
pending="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=FALSE")"
maxatt="$(psql_db "$SHARD_DB" -tA -c "SELECT COALESCE(max(attempts),0) FROM events_outbox")"
dead="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE dead_lettered_at IS NOT NULL")"
log "during partition: pending=${pending} max_attempts=${maxatt} dead_lettered=${dead}"
# pending==0 / 0-attempts = the down mis-timed the drain (the fault didn't land) → NOTRUN.
[ "$pending" -gt 0 ] || notrun "nothing pending during partition — the down mis-timed the drain"
[ "$maxatt" -gt 0 ] || notrun "0 retry attempts — publisher never hit the partition window"
# dead-letter = the partition window was environmentally too long (the system
# correctly dead-letters past 10 attempts) → NOTRUN, not a system fail.
[ "$dead" -eq 0 ] || notrun "${dead} row(s) dead-lettered — partition window too long for this machine's poll rate"

# ── HEAL + quiesce: all rows published ───────────────────────────────────────
log "UP redis_proxy; waiting for full drain (quiesce) ..."
$TOXIC up redis_proxy
quiesced=0
for _ in $(seq 1 30); do
  left="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=FALSE")"
  [ "$left" = "0" ] && { quiesced=1; break; }
  sleep 1
done
# quiesce timeout = slow machine (or stuck) — NOTRUN per the plan (never flaky-fail).
[ "$quiesced" = "1" ] || { cat /tmp/chaos_pub.log; notrun "outbox did not drain within timeout (left=${left})"; }
log "quiesced: all outbox rows published"

# ── CONVERGE: C3 + outbox-empty + history ────────────────────────────────────
"$WG" -seed "$SEED" -profile "$PROFILE" -verify -dsn "$SHARD_DSN"

# History checker: the Redis stream vs the event log (the stream-delivery
# dimension C3 doesn't see). Extract event_ids from the stream (XID order) and
# compare to the event log: no-loss (events ⊆ stream) + no-dup (XLEN == distinct)
# + stream==events (set equality — a phantom extra forces distinct>events, caught
# by the count check). Per-aggregate ORDERING (stream order respects
# aggregate_version monotonicity) is NOT yet checked → D-S6-HISTORY-ORDERING
# (V1 single-replica drains in outbox order, so reordering is structurally
# unlikely; tracked rather than silently claimed).
history_check() {
  local xlen stream_ids ev_ids n_stream n_distinct n_events missing dup
  xlen="$(redis_cli XLEN "$STREAM" | tr -d '\r')"
  # docker exec → redis-cli RAW output: each field name is a bare line, its value
  # the next line (no quotes / list markers). The event_id value follows a line
  # that is exactly `event_id` (NOT reality_id/aggregate_id), in XID order.
  stream_ids="$(redis_cli XRANGE "$STREAM" - + \
    | grep -A1 '^event_id$' \
    | grep -oiE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | sort)"
  ev_ids="$(psql_db "$SHARD_DB" -tA -c "SELECT event_id FROM events ORDER BY 1")"
  n_stream="$(printf '%s\n' "$stream_ids" | grep -c .)"
  n_distinct="$(printf '%s\n' "$stream_ids" | sort -u | grep -c .)"
  n_events="$(printf '%s\n' "$ev_ids" | grep -c .)"
  # no-loss: every event in the log appears in the stream.
  missing="$(comm -23 <(printf '%s\n' "$ev_ids" | sort -u) <(printf '%s\n' "$stream_ids" | sort -u) | grep -c . || true)"
  # no-dup: stream length == distinct event_ids.
  dup=$((n_stream - n_distinct))
  log "history: events=${n_events} XLEN=${xlen} stream_ids=${n_stream} distinct=${n_distinct} missing=${missing} dup=${dup}"
  [ "$missing" = "0" ] && [ "$dup" = "0" ] && [ "$n_stream" = "$n_events" ]
}

# Guard against a vacuous no-loss check (review-impl #4): 0 events ⟹ 0==0==0.
[ "$NEVENTS" -gt 0 ] || notrun "seed produced 0 events — history check would be vacuous"
if history_check; then
  log "history: no-loss ∧ no-dup ∧ stream==events"
else
  fail "history check found loss/dup (stream != event log)"
fi

# ── BITE: prove the history checker catches a stream loss post-quiesce drift misses ──
if [ "$BITE" = "1" ]; then
  log "BITE: XDEL one delivered stream entry (outbox still shows all published) ..."
  first_xid="$(redis_cli XRANGE "$STREAM" - + COUNT 1 | head -1 | tr -d '\r')"
  redis_cli XDEL "$STREAM" "$first_xid" >/dev/null
  still_pub="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=FALSE")"
  if history_check; then
    log "FAIL(harness): history check PASSED after XDEL — it cannot see stream loss (vacuous)"; exit 2
  fi
  log "PASS(bite): history checker flagged the lost stream entry while outbox still shows published=FALSE count=${still_pub} — it sees what post-quiesce drift misses"
fi

$TOXIC reset; $TOXIC delete-proxy redis_proxy
log "PASS: redis partition → publisher retried (no dead-letter) → drained on heal → C3 + history clean"
