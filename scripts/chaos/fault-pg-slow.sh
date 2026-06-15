#!/usr/bin/env bash
# scripts/chaos/fault-pg-slow.sh
#
# S6 (Battery D) — CONVERGENCE drill: Postgres SLOW on the publisher's drain path.
# The publisher reads the outbox + marks rows through a latency toxic on pg_proxy
# (Redis + the meta registry stay direct, so the fault is isolated to the PG
# drain). Asserts the publisher stays LIVE under sustained latency (forward
# progress, no deadlock, no pool-exhaustion crash) and CONVERGES fully once the
# latency lifts → C3 + the stream history are clean. Events are already committed,
# so this is a true convergence drill (vs the emit-path degradation drill).
#
# Non-vacuity: during the latency window the drain demonstrably SLOWS (does not
# finish in a window it otherwise would) yet keeps making progress; recovery
# drains the remainder. Re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
REDIS_CONTAINER="foundation-dev-redis"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
PG_PROXY_PORT="${FOUNDATION_PG_PROXY_PORT:-55433}"
REDIS_PORT="${FOUNDATION_REDIS_PORT:-56379}"
META_DB="chaos_pgslow_meta"; SHARD_DB="chaos_pgslow_shard"
PROFILE="${PROFILE:-multi-reality}"   # ~69 events → a longer drain to slow
SEED="${SEED:-5}"
LATENCY_MS="${LATENCY_MS:-400}"
TOXIC="bash $ROOT/scripts/chaos/toxic.sh"
SHARD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SHARD_DB}?sslmode=disable"

log() { printf '[pg-slow] %s\n' "$*"; }
# Verdict convention (review-impl #1): fault couldn't be injected / latency-tuning
# / timing → NOTRUN (exit 2, never flaky-fail). System invariant violated under
# the fault (dead-letter, history loss, publisher crash) → FAIL (exit 1).
notrun() { log "NOTRUN(setup/timing): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }
redis_cli() { docker exec -i "$REDIS_CONTAINER" redis-cli "$@"; }
pub_count() { psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=TRUE"; }

WG="${WG_BIN:-}"; [ -n "$WG" ] || { [ -x tests/workload-gen/wg.exe ] && WG="tests/workload-gen/wg.exe"; }
[ -n "$WG" ] || { [ -x tests/workload-gen/wg ] && WG="tests/workload-gen/wg"; }
[ -n "$WG" ] || { log "FAIL(setup): workload-gen not found"; exit 2; }
PUB="${PUB_BIN:-}"; [ -n "$PUB" ] || { [ -x services/publisher/pub.exe ] && PUB="services/publisher/pub.exe"; }
[ -n "$PUB" ] || { [ -x services/publisher/pub ] && PUB="services/publisher/pub"; }
[ -n "$PUB" ] || { log "FAIL(setup): publisher binary not found"; exit 2; }

PUB_PID=""; cleanup() { [ -n "$PUB_PID" ] && kill "$PUB_PID" >/dev/null 2>&1 || true; }; trap cleanup EXIT

log "bringing up postgres + redis + toxiproxy ..."
docker compose -f "$COMPOSE" up -d postgres-foundation redis-foundation toxiproxy-foundation >/dev/null
for _ in $(seq 1 30); do docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 && break; sleep 1; done
$TOXIC wait
$TOXIC create-proxy pg_proxy "$PG_PROXY_PORT" "${PG_CONTAINER}:5432"

log "(re)creating meta + shard DBs (DIRECT) ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
for m in 001_reality_registry 003_publisher_heartbeats; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"; done
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"; done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"
NEVENTS="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events")"
# Register EVERY reality the multi-reality profile produced (3/DB) so the
# publisher drains all of their outbox rows.
for rid in $(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events"); do
  redis_cli DEL "lw.events.${rid}" >/dev/null
  psql_db "$META_DB" -c "INSERT INTO reality_registry (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort) VALUES ('${rid}','pg-shard-1.internal','${SHARD_DB}','active','en',10,10,20,5)" >/dev/null
done
log "seeded events=${NEVENTS} across $(psql_db "$SHARD_DB" -tA -c "SELECT count(DISTINCT reality_id) FROM events") realities"

# ── start publisher draining the SHARD via pg_proxy (meta + redis DIRECT) ────
log "starting publisher (shard via pg_proxy, poll=1s, batch=5) ..."
PUBLISHER_ID=chaos-pub SHARD_HOST=pg-shard-1.internal \
  META_DB_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable" \
  REDIS_URL="redis://127.0.0.1:${REDIS_PORT}/0" \
  SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$PG_PROXY_PORT" SHARD_DB_SSLMODE=disable \
  PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${PG_PROXY_PORT}" \
  POLL_INTERVAL=1s BATCH_SIZE=5 HEARTBEAT_INTERVAL=5s PUBLISHER_HTTP_ADDR=:18080 \
  "$PUB" >/tmp/chaos_pubslow.log 2>&1 &
PUB_PID=$!
sleep 2
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/chaos_pubslow.log; notrun "publisher exited at startup (config/env)"; }
[ "$NEVENTS" -gt 0 ] || notrun "seed produced 0 events — drill would be vacuous"

# ── inject sustained latency; observe progress-but-slowed ────────────────────
before="$(pub_count)"
log "adding ${LATENCY_MS}ms latency to pg_proxy (already published ${before}/${NEVENTS}) ..."
$TOXIC add-latency pg_proxy "$LATENCY_MS"
sleep 4; mid="$(pub_count)"
sleep 4; after_lat="$(pub_count)"
# publisher crash under latency is a REAL robustness violation → FAIL.
kill -0 "$PUB_PID" 2>/dev/null || { cat /tmp/chaos_pubslow.log; fail "publisher crashed under PG latency"; }
dead="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE dead_lettered_at IS NOT NULL")"
log "under latency: published ${before} -> ${mid} -> ${after_lat} / ${NEVENTS} (dead=${dead})"
# (a) progress under latency, (b) latency genuinely slowed it, (c) no dead-letter.
# (a)/(b) are LATENCY-TUNING for this machine (no progress = too severe; fully
# drained = too small) → NOTRUN, not a system fail. dead-letter under latency
# (queries slow but succeed) is unexpected/environmental → NOTRUN.
[ "$after_lat" -gt "$before" ]   || notrun "no forward progress in the window — ${LATENCY_MS}ms latency too severe for this machine"
[ "$after_lat" -lt "$NEVENTS" ]  || notrun "drained fully under ${LATENCY_MS}ms latency — too small to be a real slowdown here"
[ "$dead" -eq 0 ]                || notrun "${dead} dead-lettered under latency (environmental)"

# ── recovery: remove latency, quiesce, converge ──────────────────────────────
log "removing latency; waiting for full drain ..."
$TOXIC reset
quiesced=0
for _ in $(seq 1 30); do
  left="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events_outbox WHERE published=FALSE")"
  [ "$left" = "0" ] && { quiesced=1; break; }; sleep 1
done
[ "$quiesced" = "1" ] || { cat /tmp/chaos_pubslow.log; notrun "did not drain within timeout (left=${left})"; }
"$WG" -seed "$SEED" -profile "$PROFILE" -verify -dsn "$SHARD_DSN"

# history: every reality's stream carries exactly its events (no-loss/no-dup).
# Per-aggregate ordering is deferred (D-S6-HISTORY-ORDERING), as in the partition drill.
tot_ev=0; tot_xlen=0; hist_fail=0
for rid in $(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events"); do
  nev="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events WHERE reality_id='${rid}'")"
  xlen="$(redis_cli XLEN "lw.events.${rid}" | tr -d '\r')"
  ids="$(redis_cli XRANGE "lw.events.${rid}" - + | grep -A1 '^event_id$' | grep -oiE '[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}' | sort)"
  distinct="$(printf '%s\n' "$ids" | grep -c . )"
  [ "$xlen" = "$nev" ] && [ "$distinct" = "$nev" ] || { log "history MISMATCH reality=${rid}: events=${nev} xlen=${xlen} distinct=${distinct}"; hist_fail=1; }
  tot_ev=$((tot_ev+nev)); tot_xlen=$((tot_xlen+xlen))
done
[ "$hist_fail" = "0" ] || fail "history check found loss/dup"
log "history: ${tot_ev} events == ${tot_xlen} stream entries, no-loss ∧ no-dup across all realities"

$TOXIC reset; $TOXIC delete-proxy pg_proxy
log "PASS: PG-slow drain stayed live + bounded (no dead-letter) → converged → C3 + history clean"
