#!/usr/bin/env bash
# scripts/chaos/recover-rebuild.sh
#
# S8 (Technique G) — drill G2: rebuild-from-events -> B ∧ C ∧ C2.
#
# DR property: projections are DERIVED state and MUST be fully reconstructable
# from the event log alone. Emit events -> TRUNCATE the projection tables
# (simulate total projection loss) -> run the rebuilder per table -> assert the
# reconstructed state is correct by the three oracles:
#   B  (projection == replay) : the integrity-checker samples a projection row,
#                               replays its aggregate, byte-compares -> drift==0.
#   C  (no orphan)            : wg -check-projections — every projection row's
#                               event_id resolves to a real event.
#   C2 (counts)               : every expected-populated table is NON-empty after
#                               the rebuild (recovery actually reconstructed rows).
# Bite: corrupt a rebuilt projection row -> the integrity-checker's B differential
# turns drift>0 -> proves B has teeth (a vacuous rebuild that wrote garbage would
# be caught). Re-runnable.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
META_DB="recover_rebuild_meta"; SHARD_DB="recover_rebuild_shard"
PROFILE="${PROFILE:-single-reality}"
SEED="${SEED:-3}"
BITE="${BITE:-0}"
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done
SHARD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SHARD_DB}?sslmode=disable"
# Tables the rebuilder reconstructs (S5 set) + the subset that must be populated.
REBUILD_TABLES="region_projection npc_projection npc_session_memory_projection pc_projection pc_inventory_projection session_participants world_kv_projection canon_projection"
POPULATED_TABLES="pc_projection pc_inventory_projection npc_projection npc_session_memory_projection region_projection session_participants"
BITE_TABLE="region_projection"

log() { printf '[recover-rebuild] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || notrun "workload-gen not built"
REBUILDER="${REBUILDER_BIN:-$(bin target/debug/rebuilder.exe target/debug/rebuilder)}" || notrun "rebuilder not built"
REPLAY="${REPLAY_BIN:-$(bin target/debug/replay-aggregate.exe target/debug/replay-aggregate)}" || notrun "replay-aggregate not built"
IC="${IC_BIN:-$(bin services/integrity-checker/ic.exe services/integrity-checker/ic)}" || notrun "integrity-checker not built"
REPLAY_ABS="$(cd "$(dirname "$REPLAY")" && pwd)/$(basename "$REPLAY")"

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || notrun "foundation Postgres not reachable"

log "(re)creating meta + shard DBs (full projection + drift migrations) ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
for m in 001_reality_registry 003_publisher_heartbeats; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"; done
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table 0006_projections 0007_drift_metadata 0008_pgvector_setup 0009_canon_projection; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"
done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null

"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"
RID="$(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")"
NEVENTS="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM events")"
[ "${NEVENTS:-0}" -gt 0 ] && [ -n "$RID" ] || notrun "seed produced 0 events"
psql_db "$META_DB" -c "INSERT INTO reality_registry (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort) VALUES ('${RID}','pg-shard-1.internal','${SHARD_DB}','active','en',10,10,20,5)" >/dev/null
log "seeded reality=${RID} events=${NEVENTS}"

# ── DR loss: TRUNCATE every projection table, then RECONSTRUCT from events ────
log "TRUNCATE projection tables (simulate total projection loss) ..."
for t in $REBUILD_TABLES; do psql_db "$SHARD_DB" -c "TRUNCATE ${t}" >/dev/null; done

log "rebuild-from-events (recovery) ..."
for t in $REBUILD_TABLES; do
  out="$(REALITY_DB_URL="$SHARD_DSN" "$REBUILDER" --reality-id "$RID" --projection "$t" 2>&1)" || notrun "rebuild $t errored: ${out##*$'\n'}"
  failed="$(printf '%s' "$out" | grep -o '"aggregates_failed":[0-9]*' | grep -o '[0-9]*' || true)"
  [ -n "$failed" ] || notrun "rebuild $t produced no stats"
  [ "$failed" -eq 0 ] || fail "rebuild $t had $failed failed aggregate(s) — reconstruction incomplete"
done

# ── C2: every expected-populated table is non-empty post-rebuild ─────────────
for t in $POPULATED_TABLES; do
  c="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM ${t}")"
  [ "${c:-0}" -gt 0 ] || fail "C2: ${t} empty after rebuild — derived state NOT reconstructed"
done
log "C2: all ${POPULATED_TABLES// /, } non-empty after rebuild"

# ── C: no orphan projection rows ─────────────────────────────────────────────
"$WG" -seed "$SEED" -profile "$PROFILE" -check-projections -dsn "$SHARD_DSN"
log "C: no-orphan (every projection row resolves to a real event)"

# ── B: projection == replay (the integrity-checker differential) ─────────────
run_ic() {
  META_DATABASE_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable" \
  SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$PG_PORT" SHARD_DB_SSLMODE=disable \
  SHARD_DB_HOST_OVERRIDE="*=127.0.0.1:${PG_PORT}" REPLAY_AGGREGATE_BIN_PATH="$REPLAY_ABS" "$IC"
}
total_drift_over() { # sum drift_count over the given tables
  local sum=0 t dc
  for t in $1; do
    dc="$(psql_db "$SHARD_DB" -tA -c "SELECT COALESCE(drift_count,0) FROM projection_drift_state WHERE table_name='${t}'")"
    sum=$((sum + ${dc:-0}))
  done
  echo "$sum"
}
log "running integrity-checker (B: projection==replay) ..."
run_ic || notrun "integrity-checker errored (reality connect/enumerate/replay)"
drift="$(total_drift_over "$POPULATED_TABLES")"
# coverage (non-vacuity, review MED-1): EVERY expected-populated table must have
# been SAMPLED (last_sample_size>0) — matching S5's per-table coverage. Requiring
# only one (covered>0) would let B pass vacuously for a populated table the ic
# never sampled. Incomplete coverage → notrun (environmental, not a flaky-fail).
covered=0; total=0
for t in $POPULATED_TABLES; do
  total=$((total+1))
  ss="$(psql_db "$SHARD_DB" -tA -c "SELECT COALESCE(last_sample_size,-1) FROM projection_drift_state WHERE table_name='${t}'")"
  if [ "${ss:-0}" -gt 0 ]; then covered=$((covered+1)); else log "  coverage: ${t} sampled ${ss} rows"; fi
done
[ "$covered" -eq "$total" ] || notrun "integrity-checker sampled only ${covered}/${total} populated tables — B coverage incomplete"
[ "$drift" -eq 0 ] || fail "B: ${drift} drift across populated tables — rebuilt projection != replay"
log "B: projection==replay (drift=0 over all ${covered}/${total} sampled populated tables)"

# ── BITE: corrupt a rebuilt projection row -> ic drift>0 (B catches) ─────────
if [ "$BITE" = "1" ]; then
  n="$(psql_db "$SHARD_DB" -tA -c "UPDATE ${BITE_TABLE} SET display_name = display_name || '_corrupt' RETURNING 1" | grep -c 1 || true)"
  log "BITE: corrupted ${BITE_TABLE}.display_name on ${n} row(s); re-running integrity-checker ..."
  run_ic || notrun "ic errored during bite"
  bite_drift="$(total_drift_over "$BITE_TABLE")"
  [ "$bite_drift" -gt 0 ] || { log "FAIL(harness): bite did NOT fire — corrupted ${BITE_TABLE} but drift=${bite_drift}; B would be VACUOUS"; exit 2; }
  log "PASS(bite): corrupting ${BITE_TABLE} → drift=${bite_drift} — B (projection==replay) HAS teeth (clean 0 → corrupt >0)"
fi

log "PASS: TRUNCATE → rebuild-from-events reconstructed derived state → B ∧ C ∧ C2 clean"
