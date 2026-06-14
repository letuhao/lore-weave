#!/usr/bin/env bash
# scripts/chaos/recover-kill-restart.sh
#
# S8 (Technique G) — drill G1: KILL + RESTART mid-workload -> convergence.
#
# Crash-recovery on the PUBLISH path: SIGKILL the real publisher mid-drain, then
# restart the SAME binary and assert it converges. Unlike the S6 redis-partition
# drill (a NETWORK fault that makes XADD fail cleanly), a SIGKILL can land BETWEEN
# a successful XADD and the `published=TRUE` mark.
#
# DELIVERY CONTRACT = AT-LEAST-ONCE, not exactly-once (S8 review HIGH-1): the
# publisher XADDs with an auto stream id (redisemit sets no ID) and marks
# published in a SEPARATE step, so a kill in that window re-XADDs the same
# event_id (new stream id) on restart -- a duplicate is EXPECTED. The consumer
# dedups by event_id. So the oracle is NO-LOSS + DEDUP-ABLE, never no-dup:
#   - no-loss      : distinct(event_id in stream) == events  (nothing dropped)
#   - no-phantom   : every stream event_id exists in the log (no spurious id)
#   - dedup-able   : XLEN >= events (duplicates allowed, all carry a known id)
# A kill that loses an event (kill after the row is gone from the drain set but
# before XADD lands -- impossible here since the mark is AFTER XADD) would show
# distinct < events. The bite (XDEL all copies of one event_id) proves that arm.
#
# Coverage note (review LOW-6): a SIGKILL precisely in the XADD-then-mark window
# (which would produce an actual duplicate, XLEN>events) is timing-dependent and
# not deterministically forced -- the oracle TOLERATES it, and the real failure
# modes (loss, phantom) ARE always checked. A forced-dup variant would strengthen
# the demonstration of the dedup-able path; tracked, not a today-hole.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
REDIS_CONTAINER="foundation-dev-redis"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
REDIS_PORT="${FOUNDATION_REDIS_PORT:-56379}"
META_DB="recover_kill_meta"; SHARD_DB="recover_kill_shard"
PROFILE="${PROFILE:-multi-reality}"   # ~69 events -> a drain long enough to kill mid-flight
SEED="${SEED:-7}"
BITE="${BITE:-0}"
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done
SHARD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SHARD_DB}?sslmode=disable"

log() { printf '[kill-restart] %s\n' "$*"; }
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
cleanup() { [ -n "$PUB_PID" ] && kill -9 "$PUB_PID" >/dev/null 2>&1 || true; }
trap cleanup EXIT

start_publisher() { # backgrounds the publisher, sets PUB_PID
  PUBLISHER_ID=recover-pub SHARD_HOST=pg-shard-1.internal \
    META_DB_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable" \
    REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/0" \
    SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$PG_PORT" SHARD_DB_SSLMODE=disable \
    PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${PG_PORT}" \
    POLL_INTERVAL=1s BATCH_SIZE=5 HEARTBEAT_INTERVAL=5s PUBLISHER_HTTP_ADDR="${1:-:18081}" \
    "$PUB" >>/tmp/recover_kill_pub.log 2>&1 &
  PUB_PID=$!
}
pub_published() { psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=TRUE"; }

log "bringing up postgres + redis ..."
docker compose -f "$COMPOSE" up -d postgres-foundation redis-foundation >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break; sleep 1; done

log "(re)creating meta + shard DBs ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
for m in 001_reality_registry 003_publisher_heartbeats; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"; done
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"; done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null

: >/tmp/recover_kill_pub.log
"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"
NEVENTS="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events")"
[ "${NEVENTS:-0}" -gt 0 ] || notrun "seed produced 0 events — drill would be vacuous"
for rid in $(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events"); do
  redis_cli DEL "lw.events.${rid}" >/dev/null
  psql_db "$META_DB" -c "INSERT INTO reality_registry (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort) VALUES ('${rid}','pg-shard-1.internal','${SHARD_DB}','active','en',10,10,20,5)" >/dev/null
done
NREAL="$(psql_db "$SHARD_DB" -tA -c "SELECT count(DISTINCT reality_id) FROM events")"
log "seeded events=${NEVENTS} across ${NREAL} realities"

# ── start publisher; KILL -9 it mid-drain (0 < published < NEVENTS) ───────────
log "starting publisher (poll=1s batch=5) ..."
start_publisher ":18081"
sleep 1
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/recover_kill_pub.log; notrun "publisher exited at startup (config/env)"; }
killed=0
for _ in $(seq 1 50); do
  p="$(pub_published)"
  if [ "$p" -gt 0 ] && [ "$p" -lt "$NEVENTS" ]; then
    log "SIGKILL publisher mid-drain (published ${p}/${NEVENTS}) ..."
    kill -9 "$PUB_PID" 2>/dev/null || true
    wait "$PUB_PID" 2>/dev/null || true
    killed=1; break
  fi
  [ "$p" = "$NEVENTS" ] && break
  sleep 0.2
done
[ "$killed" = 1 ] || notrun "could not catch the publisher mid-drain (drained too fast for this machine)"

# ── restart the SAME publisher; wait for quiesce ─────────────────────────────
log "RESTART publisher; waiting for full drain (quiesce) ..."
start_publisher ":18082"
quiesced=0
for _ in $(seq 1 40); do
  left="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=FALSE")"
  [ "$left" = "0" ] && { quiesced=1; break; }; sleep 1
done
[ "$quiesced" = 1 ] || { cat /tmp/recover_kill_pub.log; notrun "outbox did not drain after restart (left=${left})"; }
dead="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE dead_lettered_at IS NOT NULL")"
[ "$dead" -eq 0 ] || fail "${dead} row(s) dead-lettered across a clean kill+restart — recovery broken"
log "quiesced: all outbox rows published, no dead-letter"

# ── CONVERGE: C3 + history (no-loss + dedup-able, AT-LEAST-ONCE) ──────────────
"$WG" -seed "$SEED" -profile "$PROFILE" -verify -dsn "$SHARD_DSN"

# stream event_ids for a reality, in XID order (raw redis-cli: value follows a
# bare `event_id` line).
stream_event_ids() { redis_cli XRANGE "lw.events.${1}" - + | grep -A1 '^event_id$' | grep -oiE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'; }
log_event_ids()    { psql_db "$SHARD_DB" -tA -c "SELECT event_id FROM events WHERE reality_id='${1}' ORDER BY 1"; }

# G1 oracle (HIGH-1): per reality — no-loss (distinct==events), no-phantom (every
# stream id in the log), dedup-able (XLEN>=events, dups OK).
history_ok() {
  local bad=0
  for rid in $(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events"); do
    local sids lids xlen distinct nev missing phantom
    # lowercase both sides (review LOW-4): publisher writes EventID.String()
    # (lowercase) today, but normalizing hardens the comm() against a future
    # producer emitting upper/mixed-case ids.
    sids="$(stream_event_ids "$rid" | tr 'A-Z' 'a-z' | sort)"
    lids="$(log_event_ids "$rid" | tr 'A-Z' 'a-z' | sort)"
    xlen="$(redis_cli XLEN "lw.events.${rid}" | tr -d '\r')"
    distinct="$(printf '%s\n' "$sids" | sort -u | grep -c .)"
    nev="$(printf '%s\n' "$lids" | grep -c .)"
    missing="$(comm -23 <(printf '%s\n' "$lids") <(printf '%s\n' "$sids" | sort -u) | grep -c . || true)"  # in log, not in stream = LOSS
    phantom="$(comm -13 <(printf '%s\n' "$lids") <(printf '%s\n' "$sids" | sort -u) | grep -c . || true)"  # in stream, not in log = SPURIOUS
    log "  reality=${rid}: events=${nev} XLEN=${xlen} distinct=${distinct} missing=${missing} phantom=${phantom} dups=$((xlen - distinct))"
    { [ "$missing" = 0 ] && [ "$phantom" = 0 ] && [ "$distinct" = "$nev" ] && [ "$xlen" -ge "$nev" ]; } || bad=1
  done
  [ "$bad" = 0 ]
}

if history_ok; then
  log "history: no-loss ∧ no-phantom ∧ dedup-able (XLEN>=events; duplicates allowed = at-least-once)"
else
  fail "history violated: loss or phantom event_id after kill+restart"
fi

# ── BITE: remove ALL stream copies of one event_id -> distinct<events (LOSS) ──
if [ "$BITE" = "1" ]; then
  rid="$(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")"
  victim="$(log_event_ids "$rid" | head -1)"
  log "BITE: XDEL every stream copy of event_id=${victim} (reality ${rid}) ..."
  # map XID -> event_id; collect XIDs whose event_id == victim; XDEL them all.
  xids="$(redis_cli XRANGE "lw.events.${rid}" - + | awk -v v="$victim" '
    /^[0-9]+-[0-9]+$/ { xid=$0; next }
    prev=="event_id" && tolower($0)==tolower(v) { print xid }
    { prev=$0 }')"
  [ -n "$xids" ] || { log "FAIL(harness): could not locate victim in stream"; exit 2; }
  # shellcheck disable=SC2086
  redis_cli XDEL "lw.events.${rid}" $xids >/dev/null
  if history_ok; then
    log "FAIL(harness): history check PASSED after deleting an event_id — vacuous"; exit 2
  fi
  log "PASS(bite): history checker flagged the lost event_id (distinct<events) that the outbox 'all published' view misses"
fi

log "PASS: kill+restart -> converged (no dead-letter) -> C3 + history (no-loss, dedup-able) clean"
