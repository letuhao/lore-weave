#!/usr/bin/env bash
# scripts/perf/w3-generator.sh
#
# W3.1 — generator completeness, LIVE: the workload generator now emits
# npc.relationship_changed + pc.relationship_changed + npc.memory_embedded + a
# PERSISTENT world.kv_set, so projection arms that previously got 0 coverage
# (npc_pc_relationship_projection, pc_relationship_projection,
# npc_session_memory_embedding, world_kv_projection — the latter net-zeroed by
# set+unset) actually carry data. Closes D-WORKLOAD-GEN-NPC-REL-EMBED +
# D-S5-WORLDKV-NETS-EMPTY; the relationship arms also live-exercise the Upsert
# rebuild path (D-W3-NPC-REL-PROJECTION-UPSERT).
#
#   smoke   emit → rebuild → assert the new arms each have >=1 row (the rebuilder
#           projects the new events end-to-end, incl. the pgvector embedding + the
#           ON CONFLICT upserts) → no-orphan clean. BITE: corrupt one
#           npc_session_memory_embedding row's event_id to a non-existent id → the
#           no-orphan sweep CATCHES it, proving a now-populated arm is actually
#           checked (before W3.1 these tables were EMPTY so the oracle ran
#           vacuously over them).
#
# Verdict: NOTRUN(2) setup; FAIL(1) an arm empty after rebuild / a rebuild failed
# / the bite not caught; PASS(0). Reuses the S12 scale rig (shard-0).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
# The embedding arm needs pgvector — the scale rig's plain postgres:16 lacks it,
# so use the foundation-dev postgres image (which ships pgvector, like the S3
# pipeline smoke). Bring it up if needed.
COMPOSE="infra/foundation-dev/docker-compose.yml"
SHARD_C="foundation-dev-postgres"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
DB="w3_gen"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${DB}?sslmode=disable"
SEED="${W3_SEED:-3}"; PROFILE="${W3_PROFILE:-single-reality}"

log()    { printf '[w3-generator] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
require() {
  docker compose -f "$COMPOSE" up -d postgres-foundation >/dev/null 2>&1 || notrun "could not start foundation-dev postgres"
  local i
  for i in $(seq 1 30); do
    docker exec "$SHARD_C" pg_isready -U "$PG_USER" >/dev/null 2>&1 && return 0
    sleep 2
  done
  notrun "foundation-dev postgres not ready"
}
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db()  { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }
scalar()   { docker exec -i "$SHARD_C" psql -tA -U "$PG_USER" -d "$DB" -c "$1" | tr -d '[:space:]'; }

setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256 0006_projections 0008_pgvector_setup 0009_canon_projection; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
      < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null || notrun "default partition"
  log "w3_gen ready (events + projections + pgvector)"
}

build_bins() {
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build wg failed"
  WG="tests/workload-gen/wg.exe"
  REB="target/debug/rebuilder.exe"; [ -x "$REB" ] || REB="target/debug/rebuilder"
  if [ ! -x "$REB" ]; then
    log "building rebuilder ..."
    cargo build -p world-service --bin rebuilder || notrun "build rebuilder failed"
    REB="target/debug/rebuilder.exe"; [ -x "$REB" ] || REB="target/debug/rebuilder"
  fi
}

# Arms that materialize rows end-to-end (now incl npc_pc_relationship_projection).
# D-W3-NPC-REL-PROJECTION-UPSERT is FIXED: the relationship projections emit
# ProjectionUpdate::Upsert and the rebuild writer does INSERT … ON CONFLICT (pk)
# DO UPDATE, so the row created on the FIRST npc.relationship_changed now
# materializes (it previously stayed 0 rows because a plain UPDATE hit no row).
NEW_ARMS="npc_session_memory_embedding world_kv_projection npc_pc_relationship_projection pc_relationship_projection"
TABLES="region_projection npc_projection npc_session_memory_projection pc_projection pc_inventory_projection session_participants world_kv_projection npc_pc_relationship_projection pc_relationship_projection npc_session_memory_embedding"

main() {
  require; setup; build_bins

  log "emit seed=${SEED} profile=${PROFILE}"
  "$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$DSN" >/dev/null 2>&1 || notrun "emit failed"
  local rid; rid="$(scalar "SELECT DISTINCT reality_id FROM events LIMIT 1")"
  [ -n "$rid" ] || notrun "no events emitted"

  export REALITY_DB_URL="$DSN"
  local t out failed
  for t in $TABLES; do
    out="$("$REB" --reality-id "$rid" --projection "$t" 2>&1)" || true
    failed="$(printf '%s' "$out" | grep -o '"aggregates_failed":[0-9]*' | grep -o '[0-9]*' || true)"
    [ -n "$failed" ] || fail "rebuild ${t} produced no stats: ${out}"
    [ "$failed" = "0" ] || fail "rebuild ${t} had ${failed} failed aggregate(s)"
  done
  log "rebuild: all ${TABLES// /, } clean (0 failed)"

  # Generator side (the W3.1 deliverable): all three new events are emitted +
  # causally valid (gen.Validate ran in -emit). Confirm the events landed.
  local rel mem
  rel="$(scalar "SELECT count(*) FROM events WHERE event_type='npc.relationship_changed'")"
  mem="$(scalar "SELECT count(*) FROM events WHERE event_type='npc.memory_embedded'")"
  [ "${rel:-0}" -ge 1 ] && [ "${mem:-0}" -ge 1 ] \
    || fail "generator did not emit the new npc events (rel=${rel} mem=${mem})"
  log "  generator emitted: npc.relationship_changed=${rel} npc.memory_embedded=${mem}"

  # The arms that materialize rows end-to-end now carry data (were 0 before W3.1).
  local arm n
  for arm in $NEW_ARMS; do
    n="$(scalar "SELECT count(*) FROM ${arm}")"
    [ "${n:-0}" -ge 1 ] || fail "arm ${arm} has ${n} rows after rebuild — generator did not populate it (still vacuous)"
    log "  ${arm}: ${n} rows"
  done
  log "PASS(arms): npc_session_memory_embedding + world_kv_projection + npc_pc_relationship_projection all populated (were 0 before W3.1; the relationship row now materializes via the Upsert fix — D-W3-NPC-REL-PROJECTION-UPSERT)"

  # no-orphan clean over the freshly-rebuilt projections.
  "$WG" -check-projections -dsn "$DSN" >/dev/null 2>&1 || fail "no-orphan sweep failed on a clean rebuild"
  log "PASS(no-orphan): clean"

  # BITE: orphan one npc_session_memory_embedding row (point its event_id at a
  # non-existent event) → the no-orphan sweep MUST now flag it. Before W3.1 this
  # table was EMPTY, so the sweep covered it vacuously; now it actually checks it.
  psql_db -c "UPDATE npc_session_memory_embedding SET event_id = gen_random_uuid()
              WHERE ctid = (SELECT ctid FROM npc_session_memory_embedding LIMIT 1)" >/dev/null \
    || notrun "bite setup: could not orphan an embedding row"
  if "$WG" -check-projections -dsn "$DSN" >/dev/null 2>&1; then
    fail "bite VACUOUS: no-orphan PASSED after orphaning an npc_session_memory_embedding row — the arm is not actually covered by the sweep"
  fi
  log "PASS(bite): no-orphan CAUGHT the orphaned embedding row — the newly-populated arm is genuinely checked (non-vacuous)"
}
main "$@"
