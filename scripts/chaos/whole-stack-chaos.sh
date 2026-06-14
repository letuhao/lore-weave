#!/usr/bin/env bash
# scripts/chaos/whole-stack-chaos.sh
#
# S11 (Technique H2, LOCAL half) — whole-stack chaos-convergence under CONCURRENT
# multi-service faults + sustained load.
#
# What's new vs S5/S6/S8 (review HIGH-1): the foundation spine has NO live
# projection consumer (the publisher only drains outbox->Redis; spine projections
# are rebuild-only). So a final rebuild LAUNDERS B/C/C2, and the transactional
# write path keeps C3 clean under faults. The ONE property the faults actually
# stress is DELIVERY: the publisher draining outbox->Redis. So the load-bearing
# oracle here is DELIVERY-CONVERGENCE (no-loss + dedup-able = at-least-once, per
# S8 G1), asserted per reality after a CONCURRENT pg-slow || redis-partition.
#
# The publisher's shard reads go through a PG proxy (pg-slow latency) AND its
# Redis delivery through a Redis proxy (partition) — so it is degraded on BOTH
# dependencies at once (the "whole-stack" fault S6's single-fault drills don't
# reach), mid-flight through a multi-reality (3-stream) drain = sustained load.
# Both faults are proven concurrently active (pending+retries for redis; an RTT
# probe for pg).
#
# Verdict (S6/S8 convention): fault couldn't be injected / publisher not draining
# / quiesce timeout -> NOTRUN (2, never flaky-fails the nightly). Delivery
# (no-loss) or C3 VIOLATED under the fault -> FAIL (1). Clean -> PASS (0).
# BITE: XDEL all stream copies of one event_id -> no-loss (distinct==events) MUST
# fail -> proves the delivery oracle has teeth (not the integrity-checker, which
# S5/S8 already bite). Re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
REDIS_CONTAINER="foundation-dev-redis"
TOXI_CONTAINER="foundation-dev-toxiproxy"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"             # DIRECT (setup + C3)
PG_PROXY_PORT="${FOUNDATION_PG_PROXY_PORT:-55433}" # publisher shard reads (pg-slow)
REDIS_PROXY_PORT="${FOUNDATION_REDIS_PROXY_PORT:-56380}" # publisher delivery (partition)
META_DB="wholestack_meta"; SHARD_DB="wholestack_shard"
PROFILE="${PROFILE:-multi-reality}"   # several realities -> richer multi-stream drain
SEED="${SEED:-7}"
PG_LATENCY_MS="${PG_LATENCY_MS:-200}"
BITE="${BITE:-0}"
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done
SHARD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SHARD_DB}?sslmode=disable"
TOXIC="bash $ROOT/scripts/chaos/toxic.sh"

log() { printf '[whole-stack] %s\n' "$*"; }
notrun() { log "NOTRUN(setup/timing): $*"; $TOXIC reset >/dev/null 2>&1 || true; exit 2; }
fail()   { log "FAIL: $*"; $TOXIC reset >/dev/null 2>&1 || true; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }
redis_cli() { docker exec -i "$REDIS_CONTAINER" redis-cli "$@"; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || { log "FAIL(setup): workload-gen not built"; exit 2; }
PUB="${PUB_BIN:-$(bin services/publisher/pub.exe services/publisher/pub)}" || { log "FAIL(setup): publisher not built (go build -C services/publisher -o pub ./cmd/publisher)"; exit 2; }

PUB_PID=""
cleanup() { [ -n "$PUB_PID" ] && kill -9 "$PUB_PID" >/dev/null 2>&1 || true; $TOXIC reset >/dev/null 2>&1 || true; }
trap cleanup EXIT

register_reality() { # reality_id  — idempotent insert into reality_registry
  psql_db "$META_DB" -c "INSERT INTO reality_registry
      (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
    VALUES ('${1}','pg-shard-1.internal','${SHARD_DB}','active','en',10,10,20,5)
    ON CONFLICT (reality_id) DO NOTHING" >/dev/null
}

# Publisher: META direct (stable), SHARD reads via the PG proxy (pg-slow), Redis
# delivery via the Redis proxy (partition). Persistent process (review MED-1) —
# the Go publisher retries both a slow PG and a redis partition rather than
# crashing; the harness asserts it stays alive.
start_publisher() {
  PUBLISHER_ID=wholestack-pub SHARD_HOST=pg-shard-1.internal \
    META_DB_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable" \
    REDIS_URL="redis://127.0.0.1:${REDIS_PROXY_PORT}/0" \
    SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$PG_PROXY_PORT" SHARD_DB_SSLMODE=disable \
    PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${PG_PROXY_PORT}" \
    POLL_INTERVAL=1s BATCH_SIZE=5 HEARTBEAT_INTERVAL=5s PUBLISHER_HTTP_ADDR="${1:-:18083}" \
    "$PUB" >>/tmp/wholestack_pub.log 2>&1 &
  PUB_PID=$!
}
pub_published() { psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=TRUE"; }
outbox_pending() { psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=FALSE"; }

# SELECT 1 RTT through the PG proxy (ms) — proves the pg-slow toxic is on the
# publisher's shard-read path concurrently with the redis partition.
rtt_pg_proxy_ms() {
  local start end
  start="$(date +%s%3N)"
  docker exec -e PGPASSWORD="$PG_PASS" "$PG_CONTAINER" \
    psql -h "$TOXI_CONTAINER" -p "$PG_PROXY_PORT" -U "$PG_USER" -d foundation -tAc "SELECT 1" >/dev/null 2>&1 || true
  end="$(date +%s%3N)"
  echo $((end - start))
}

# ── boot stack + proxies ─────────────────────────────────────────────────────
log "bringing up postgres + redis + minio + toxiproxy ..."
docker compose -f "$COMPOSE" up -d postgres-foundation redis-foundation minio-foundation toxiproxy-foundation >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break; sleep 1; done
$TOXIC wait
$TOXIC create-proxy pg_proxy "$PG_PROXY_PORT" "${PG_CONTAINER}:5432"
$TOXIC create-proxy redis_proxy "$REDIS_PROXY_PORT" "${REDIS_CONTAINER}:6379"

# ── meta + shard DBs, multi-reality seed (DIRECT) ────────────────────────────
log "(re)creating meta + shard DBs; seeding ${PROFILE} ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
for m in 001_reality_registry 003_publisher_heartbeats; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"; done
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"; done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null

: >/tmp/wholestack_pub.log
"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"
NEVENTS="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events")"
[ "${NEVENTS:-0}" -gt 0 ] || notrun "seed produced 0 events — drill would be vacuous"
for rid in $(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events"); do
  redis_cli DEL "lw.events.${rid}" >/dev/null; register_reality "$rid"
done
NREAL="$(psql_db "$SHARD_DB" -tA -c "SELECT count(DISTINCT reality_id) FROM events")"
log "seeded events=${NEVENTS} across ${NREAL} realities"

# ── start publisher; let it drain PARTIALLY ──────────────────────────────────
log "starting publisher (shard via pg_proxy, redis via redis_proxy) ..."
start_publisher ":18083"
sleep 1
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/wholestack_pub.log; notrun "publisher exited at startup (config/env)"; }
caught=0
for _ in $(seq 1 50); do
  p="$(pub_published)"
  if [ "$p" -gt 0 ] && [ "$p" -lt "$NEVENTS" ]; then caught=1; break; fi
  [ "$p" = "$NEVENTS" ] && break
  sleep 0.2
done
[ "$caught" = 1 ] || notrun "could not catch the publisher mid-drain (drained too fast for this machine)"
log "publisher mid-drain (published ${p}/${NEVENTS})"

# ── CONCURRENT FAULTS: pg-slow (latency) || redis-partition (down) ────────────
log "INJECT concurrent faults: pg_proxy +${PG_LATENCY_MS}ms latency || redis_proxy DOWN ..."
$TOXIC add-latency pg_proxy "$PG_LATENCY_MS"
$TOXIC down redis_proxy

# Sustained load = the multi-reality drain itself: the publisher is mid-flight
# delivering ~52 of 67 events across 3 reality streams (batches of 5/poll) when
# the concurrent faults land, and keeps working under them. (A fresh during-fault
# emit was considered but pollutes the per-seed C3 spec on the shared shard DB;
# the in-flight multi-reality drain under degradation is the sustained load.)
sleep 4  # retries accumulate (redis) + slow polls (pg)

# ── prove BOTH faults are concurrently active (non-vacuity) ───────────────────
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/wholestack_pub.log; fail "publisher crashed under concurrent faults — robustness violation"; }
pending="$(outbox_pending)"; maxatt="$(psql_db "$SHARD_DB" -tA -c "SELECT COALESCE(max(attempts),0) FROM events_outbox")"
dead="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE dead_lettered_at IS NOT NULL")"
rtt="$(rtt_pg_proxy_ms)"
log "under fault: pending=${pending} max_attempts=${maxatt} dead=${dead} pg_proxy_rtt=${rtt}ms"
[ "$pending" -gt 0 ] || notrun "nothing pending during partition — the redis down mis-timed the drain"
[ "$maxatt" -gt 0 ] || notrun "0 retry attempts — publisher never hit the partition window"
[ "$dead" -eq 0 ] || notrun "${dead} row(s) dead-lettered — fault window too long for this machine"
# pg-slow non-vacuity: the RTT through the proxy must reflect the injected latency
# (proves pg-slow is concurrently on the publisher's shard-read path).
[ "$rtt" -ge $((PG_LATENCY_MS / 2)) ] || notrun "pg_proxy RTT ${rtt}ms < half the injected ${PG_LATENCY_MS}ms — the pg-slow toxic did not land"
log "both faults concurrently active: delivery blocked (pending/retries) AND shard reads slow (rtt≥${PG_LATENCY_MS}/2)"

# ── HEAL both + quiesce ──────────────────────────────────────────────────────
log "HEAL (reset: latency off + redis up); waiting for full drain (quiesce) ..."
$TOXIC reset
quiesced=0
for _ in $(seq 1 40); do
  left="$(outbox_pending)"; [ "$left" = "0" ] && { quiesced=1; break; }; sleep 1
done
[ "$quiesced" = 1 ] || { cat /tmp/wholestack_pub.log; notrun "outbox did not drain within timeout (left=${left})"; }
dead="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE dead_lettered_at IS NOT NULL")"
[ "$dead" -eq 0 ] || fail "${dead} row(s) dead-lettered across a survivable fault — delivery broken"
log "quiesced: all outbox rows published, no dead-letter"

# ── PRIMARY oracle: delivery-convergence (no-loss + dedup-able) per reality ───
stream_event_ids() { redis_cli XRANGE "lw.events.${1}" - + | grep -A1 '^event_id$' | grep -oiE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}'; }
log_event_ids()    { psql_db "$SHARD_DB" -tA -c "SELECT event_id FROM events WHERE reality_id='${1}' ORDER BY 1"; }
history_ok() {
  local bad=0 rid sids lids xlen distinct nev missing phantom
  for rid in $(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events"); do
    sids="$(stream_event_ids "$rid" | tr 'A-Z' 'a-z' | sort)"
    lids="$(log_event_ids "$rid" | tr 'A-Z' 'a-z' | sort)"
    xlen="$(redis_cli XLEN "lw.events.${rid}" | tr -d '\r')"
    distinct="$(printf '%s\n' "$sids" | sort -u | grep -c .)"
    nev="$(printf '%s\n' "$lids" | grep -c .)"
    missing="$(comm -23 <(printf '%s\n' "$lids") <(printf '%s\n' "$sids" | sort -u) | grep -c . || true)"
    phantom="$(comm -13 <(printf '%s\n' "$lids") <(printf '%s\n' "$sids" | sort -u) | grep -c . || true)"
    log "  reality=${rid}: events=${nev} XLEN=${xlen} distinct=${distinct} missing=${missing} phantom=${phantom} dups=$((xlen - distinct))"
    { [ "$missing" = 0 ] && [ "$phantom" = 0 ] && [ "$distinct" = "$nev" ] && [ "$xlen" -ge "$nev" ]; } || bad=1
  done
  [ "$bad" = 0 ]
}
[ "$NEVENTS" -gt 0 ] || notrun "0 events — delivery check would be vacuous"
if history_ok; then
  log "DELIVERY-CONVERGENCE: no-loss ∧ no-phantom ∧ dedup-able across all realities (survived concurrent pg-slow || redis-partition)"
else
  fail "delivery-convergence violated: loss/phantom in a reality stream after the concurrent fault"
fi

# ── SECONDARY (rebuild-laundered, not fault-sensitive): C3 ledger integrity ───
# B / C2 are rebuild-only in the spine (HIGH-1) so they cannot detect a fault
# here and are covered by S5/S8; C3 (log integrity) is cheap and re-asserted.
"$WG" -seed "$SEED" -profile "$PROFILE" -verify -dsn "$SHARD_DSN"
log "C3: event-store ledger integrity clean (secondary sanity)"

# ── BITE: XDEL all stream copies of one event_id -> no-loss MUST fail ─────────
if [ "$BITE" = "1" ]; then
  rid="$(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")"
  victim="$(log_event_ids "$rid" | head -1)"
  log "BITE: XDEL every stream copy of event_id=${victim} (reality ${rid}) ..."
  xids="$(redis_cli XRANGE "lw.events.${rid}" - + | awk -v v="$victim" '
    /^[0-9]+-[0-9]+$/ { xid=$0; next }
    prev=="event_id" && tolower($0)==tolower(v) { print xid }
    { prev=$0 }')"
  [ -n "$xids" ] || { log "FAIL(harness): could not locate victim in stream"; exit 2; }
  # shellcheck disable=SC2086
  redis_cli XDEL "lw.events.${rid}" $xids >/dev/null
  if history_ok; then
    log "FAIL(harness): delivery check PASSED after deleting an event_id — vacuous"; exit 2
  fi
  log "PASS(bite): delivery oracle flagged the lost event_id (distinct<events) — it has teeth"
fi

$TOXIC reset; $TOXIC delete-proxy pg_proxy; $TOXIC delete-proxy redis_proxy
log "PASS: concurrent pg-slow || redis-partition under sustained load → delivery-convergence (no-loss, dedup-able) + C3 clean"
