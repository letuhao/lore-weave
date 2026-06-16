#!/usr/bin/env bash
# scripts/standing-integrity-gate-smoke.sh
#
# S5 — Standing integrity gate (Battery B) over N seeded shards in parallel.
#
#   for each of N shards (distinct seed ⇒ distinct stream + distinct reality_id):
#     workload-gen -emit  →  events + events_outbox (real outbox write path)
#     rebuilder           →  replays those events into the LIVE projections
#     register            →  a reality_registry row in the shared meta DB
#   integrity-checker (daily)  →  the REAL B differential: sample each projection
#                                 row → replay-aggregate bin → `to_jsonb - meta`
#                                 byte-compare → persist projection_drift_state
#   gate  →  (a) checker exit 0, (b) SUM(drift_count)==0 across all shards, AND
#            (c) per-table COVERAGE on the expected-populated set (last_verified_at
#                NOT NULL ∧ last_sample_size>0) — so "0 drift" can't be vacuous
#                ("0 drift because nothing was checked").
#
# The drift signal is the checker's OWN persisted output — we reuse the oracle,
# we do not reimplement it. The checker exits non-zero only on a reality ERROR
# (drift→exit 0), so the gate reads projection_drift_state to turn drift into red.
#
# Re-runnable (drops + recreates the meta + N shard DBs). BITE=1 runs the
# non-vacuity self-test (see the BITE block) and is exercised by Inc 2.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"
PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
SHARDS="${SHARDS:-4}"
PROFILE="${PROFILE:-multi-reality}"
META_DB="standing_gate_meta"
SHARD_PREFIX="standing_gate_shard_"
BITE="${BITE:-0}"
# `--bite` flag (env BITE=1 equivalent) so the conformance case can request the
# embedded non-vacuity self-test without relying on inherited env.
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done

# The 6 projection tables the generator's multi-reality profile leaves with rows
# (Battery-B coverage set) and the 4 L3.A tables it provably leaves EMPTY — a
# DOCUMENTED, asserted exclusion, not silent under-coverage. canon_projection is
# intentionally absent from both: it is not in the L3.A allowlist, so the
# integrity-checker does not check it (outside B).
#
# world_kv_projection is EXCLUDED because the generator emits world.kv_set THEN
# world.kv_unset (gen.go:154-157) — they net to an empty projection, so B has no
# row to sample (the EVENT path is exercised; the projection-row oracle has
# nothing). Tracked: D-S5-WORLDKV-NETS-EMPTY (a set-without-unset profile would
# give B a world_kv row to verify). The other 3 are tables no event populates yet.
POPULATED_TABLES="pc_projection pc_inventory_projection npc_projection npc_session_memory_projection region_projection session_participants"
EXCLUDED_TABLES="pc_relationship_projection npc_pc_relationship_projection npc_session_memory_embedding world_kv_projection"

# Tables to rebuild — the exact set + order workload-gen-pipeline-smoke.sh proved
# clean (incl. the multi-aggregate npc_session_memory_projection via the
# rebuilder's global path, D-REBUILDER-MULTI-AGG). canon_projection rebuilds too
# (it has cascade rows) even though B does not check it.
REBUILD_TABLES="region_projection npc_projection npc_session_memory_projection pc_projection pc_inventory_projection session_participants world_kv_projection canon_projection"

log() { printf '[s5-gate] %s\n' "$*"; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }
shard_db()  { printf '%s%s' "$SHARD_PREFIX" "$1"; }
shard_dsn() { printf 'postgres://%s:%s@127.0.0.1:%s/%s?sslmode=disable' "$PG_USER" "$PG_PASS" "$PG_PORT" "$(shard_db "$1")"; }

# Non-vacuity guard (review-impl #1): the gate is "N PARALLEL shards" (the
# CockroachDB-50× rationale needs N>1). N<2 makes the seq-loops below iterate too
# few times — at N=0, nothing is seeded/checked and total_drift=0 passes
# VACUOUSLY. Refuse it as a setup error (exit 2 → notrun, not green). Placed after
# log() is defined so the message renders.
[ "$SHARDS" -ge 2 ] 2>/dev/null || { log "FAIL(setup): SHARDS must be >= 2 (N parallel shards); got '$SHARDS'"; exit 2; }

# ── binaries (prefer prebuilt; exit 2 = notrun, never a false green) ──────────
WG="${WG_BIN:-}"
[ -n "$WG" ] || { [ -x tests/workload-gen/wg.exe ] && WG="tests/workload-gen/wg.exe"; }
[ -n "$WG" ] || { [ -x tests/workload-gen/wg ] && WG="tests/workload-gen/wg"; }
[ -n "$WG" ] || { log "FAIL(setup): workload-gen binary not found (go build -C tests/workload-gen -o wg.exe ./cmd/workload-gen)"; exit 2; }

REBUILDER="${REBUILDER_BIN:-target/debug/rebuilder.exe}"
[ -x "$REBUILDER" ] || REBUILDER="target/debug/rebuilder"
[ -x "$REBUILDER" ] || { log "FAIL(setup): rebuilder not found (cargo build -p world-service --bin rebuilder)"; exit 2; }

REPLAY="${REPLAY_BIN:-target/debug/replay-aggregate.exe}"
[ -x "$REPLAY" ] || REPLAY="target/debug/replay-aggregate"
[ -x "$REPLAY" ] || { log "FAIL(setup): replay-aggregate not found (cargo build -p world-service --bin replay-aggregate)"; exit 2; }
REPLAY_ABS="$(cd "$(dirname "$REPLAY")" && pwd)/$(basename "$REPLAY")"

IC="${IC_BIN:-}"
[ -n "$IC" ] || { [ -x services/integrity-checker/ic.exe ] && IC="services/integrity-checker/ic.exe"; }
[ -n "$IC" ] || { [ -x services/integrity-checker/ic ] && IC="services/integrity-checker/ic"; }
[ -n "$IC" ] || { log "FAIL(setup): integrity-checker binary not found (go build -C services/integrity-checker -o ic.exe ./cmd/integrity-checker — pass IC_BIN)"; exit 2; }

log "config: shards=$SHARDS profile=$PROFILE pg_port=$PG_PORT bite=$BITE"

# ── bring up postgres ────────────────────────────────────────────────────────
log "bringing up foundation-dev postgres ..."
docker compose -f "$COMPOSE" up -d postgres-foundation >/dev/null
for _ in $(seq 1 30); do
  if docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1; then break; fi
  sleep 2
done

# ── meta DB (reality_registry the checker enumerates) ────────────────────────
log "(re)creating meta DB $META_DB ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null
psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
log "applying meta migration (reality_registry — the only meta table the checker reads) ..."
docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" < "migrations/meta/001_reality_registry.up.sql"

# ── seed + rebuild N shards IN PARALLEL ──────────────────────────────────────
# set -e does NOT cross `( … ) &` boundaries, so each shard writes its reality_id
# to a temp file and we check every PID's exit code explicitly after wait.
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

seed_shard() {
  local i="$1" db dsn rid
  db="$(shard_db "$i")"; dsn="$(shard_dsn "$i")"
  psql_db foundation -c "DROP DATABASE IF EXISTS ${db}" >/dev/null
  psql_db foundation -c "CREATE DATABASE ${db}" >/dev/null
  # 0007_drift_metadata is REQUIRED here (the pipeline smoke omits it) — it
  # creates + seeds projection_drift_state, the gate's signal table.
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0006_projections \
           0007_drift_metadata 0008_pgvector_setup 0009_canon_projection; do
    docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$db" < "contracts/migrations/per_reality/${m}.up.sql"
  done
  psql_db "$db" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
  "$WG" -seed "$i" -profile "$PROFILE" -emit -dsn "$dsn"
  rid="$(psql_db "$db" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")"
  [ -n "$rid" ] || { echo "shard $i: no reality_id after emit" >&2; return 1; }
  # The rebuilder rebuilds ONE table per call (--reality-id --projection); it
  # selects the global-order path internally for the multi-aggregate table.
  for t in $REBUILD_TABLES; do
    out="$(REALITY_DB_URL="$dsn" "$REBUILDER" --reality-id "$rid" --projection "$t" 2>&1)" || { echo "shard $i: rebuild $t failed: $out" >&2; return 1; }
    # Parse the JSON stats on stdout (`"aggregates_failed":N`) — present on BOTH
    # the per-aggregate AND the GLOBAL-ORDER path (the stderr human line differs).
    failed="$(printf '%s' "$out" | grep -o '"aggregates_failed":[0-9]*' | grep -o '[0-9]*' || true)"
    [ -n "$failed" ] || { echo "shard $i: rebuild $t produced no stats: $out" >&2; return 1; }
    [ "$failed" -eq 0 ] || { echo "shard $i: rebuild $t had $failed failed aggregate(s)" >&2; return 1; }
  done
  printf '%s' "$rid" > "$TMP/shard_${i}.rid"
}

declare -a pids=()
declare -a idxs=()
for i in $(seq 1 "$SHARDS"); do
  log "seeding+rebuilding shard $i (seed=$i) ..."
  seed_shard "$i" & pids+=("$!"); idxs+=("$i")
done
fail=0
for k in "${!pids[@]}"; do
  if ! wait "${pids[$k]}"; then
    log "FAIL: shard ${idxs[$k]} seed/rebuild errored"
    fail=1
  fi
done
[ "$fail" -eq 0 ] || { log "FAIL: one or more shards did not seed cleanly"; exit 1; }

# ── register every shard in the meta registry (serial — avoid INSERT races) ──
log "registering $SHARDS shards in reality_registry ..."
for i in $(seq 1 "$SHARDS"); do
  rid="$(cat "$TMP/shard_${i}.rid")"
  db="$(shard_db "$i")"
  psql_db "$META_DB" -c "INSERT INTO reality_registry
      (reality_id, db_host, db_name, status, locale,
       session_max_pcs, session_max_npcs, session_max_total, deploy_cohort)
    VALUES ('${rid}', 'pg-shard-1.internal', '${db}', 'active', 'en', 10, 10, 20, 5)" >/dev/null
done

# ── run the REAL integrity-checker once over all N realities ─────────────────
log "running integrity-checker (daily B differential) ..."
export META_DATABASE_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable"
export SHARD_DB_USER="$PG_USER"
export SHARD_DB_PASSWORD="$PG_PASS"
export SHARD_DB_PORT="$PG_PORT"
export SHARD_DB_SSLMODE="disable"   # resolver defaults empty→'require' → would fail on local non-TLS PG
export SHARD_DB_HOST_OVERRIDE="*=127.0.0.1:${PG_PORT}"
export REPLAY_AGGREGATE_BIN_PATH="$REPLAY_ABS"
ic_rc=0
"$IC" || ic_rc=$?
[ "$ic_rc" -eq 0 ] || { log "FAIL: integrity-checker exited $ic_rc (reality error — connect/enumerate/replay)"; exit 1; }

# ── gate: drift==0 AND per-table coverage, per shard; emit results JSON ───────
log "evaluating gate (drift + coverage) over $SHARDS shards ..."
RESULTS_DIR="tests/conformance/results"
mkdir -p "$RESULTS_DIR"
RUN_ID="${RUN_ID:-$(date -u +%Y%m%dT%H%M%SZ)}"
RESULTS="$RESULTS_DIR/standing-gate-${RUN_ID}.json"

total_drift=0
gate_fail=0
{
  printf '{\n  "run_id": "%s",\n  "shards": [\n' "$RUN_ID"
} > "$RESULTS"

for i in $(seq 1 "$SHARDS"); do
  db="$(shard_db "$i")"
  rid="$(cat "$TMP/shard_${i}.rid")"
  [ "$i" -eq 1 ] && sep="" || sep=","
  printf '%s    {"shard": %s, "reality_id": "%s", "db": "%s", "tables": [' "$sep" "$i" "$rid" "$db" >> "$RESULTS"
  tsep=""
  # populated set — assert COVERAGE (verified ∧ sampled) and accumulate drift
  for t in $POPULATED_TABLES; do
    row="$(psql_db "$db" -tA -F '|' -c \
      "SELECT COALESCE(drift_count,0), COALESCE(last_sample_size,-1), (last_verified_at IS NOT NULL) FROM projection_drift_state WHERE table_name='${t}'")"
    dc="${row%%|*}"; rest="${row#*|}"; ss="${rest%%|*}"; verified="${rest##*|}"
    if [ "$verified" != "t" ]; then
      log "FAIL(coverage): shard $i table $t was never verified (last_verified_at NULL) — gate would be vacuous"
      gate_fail=1
    # ss is guaranteed numeric here: COALESCE(...,-1) + the row always exists
    # (0007 seeds all 10), and a failed query would have left verified != 't'
    # (caught above). So no error-masking redirect is needed (review-impl #3).
    elif [ "$ss" -le 0 ]; then
      log "FAIL(coverage): shard $i table $t verified but sampled 0 rows (last_sample_size=$ss) — populated table checked nothing"
      gate_fail=1
    fi
    total_drift=$((total_drift + dc))
    printf '%s{"table":"%s","sample_size":%s,"verified":%s,"drift_count":%s}' "$tsep" "$t" "$ss" "$([ "$verified" = t ] && echo true || echo false)" "$dc" >> "$RESULTS"
    tsep=","
  done
  # excluded set — assert the row EXISTS (in seed/allowlist); coverage NOT required
  for t in $EXCLUDED_TABLES; do
    cnt="$(psql_db "$db" -tA -c "SELECT count(*) FROM projection_drift_state WHERE table_name='${t}'")"
    [ "$cnt" = "1" ] || { log "FAIL: shard $i excluded table $t missing from projection_drift_state seed"; gate_fail=1; }
  done
  printf ']}' >> "$RESULTS"
done

printf '\n  ],\n  "total_drift": %s\n}\n' "$total_drift" >> "$RESULTS"
log "results written: $RESULTS (total_drift=$total_drift)"

[ "$gate_fail" -eq 0 ] || { log "FAIL: coverage assertion(s) failed — see above"; exit 1; }
if [ "$total_drift" -ne 0 ]; then
  log "FAIL: total drift = $total_drift across $SHARDS shards (projection != replay(events))"
  log "  NOTE: a non-zero CLEAN run is a REAL discovery (D-WORKLOAD-GEN-INTEGRITY-DIFF), not a"
  log "  harness bug — triage which table drifts and which side (rebuilder vs replay) is truth."
  exit 1
fi
log "PASS(clean): $SHARDS shards · 6 populated tables each verified+sampled · total_drift=0"

# ── BITE: non-vacuity self-test (review-impl #2) ─────────────────────────────
# Prove the green gate CAN go red, with the BYTE-COMPARE (not a structural
# impossibility) being what catches drift. Without this, "total_drift=0" could
# be vacuous. Embedded in the conformance run (BITE=1) so every pass carries the
# proof — the S4 `--self-test` pattern applied to a live differential.
[ "$BITE" -eq 1 ] || exit 0

BITE_DB="$(shard_db 1)"; BITE_TABLE="region_projection"; BITE_COL="display_name"
log "BITE: corrupting ALL rows of ${BITE_TABLE} on shard 1, then re-sweeping ..."
n="$(psql_db "$BITE_DB" -tA -c "SELECT count(*) FROM ${BITE_TABLE}")"
# Fail as a HARNESS error (not a vacuous bite "pass") if the table is empty — a
# 0-row UPDATE would no-op and falsely read non-vacuous.
[ "$n" -gt 0 ] 2>/dev/null || { log "FAIL(setup): bite table ${BITE_TABLE} empty (n=$n) — cannot prove non-vacuity"; exit 2; }
# Corrupt the WHOLE table (not one row) so the daily sampler cannot miss it.
# display_name is a COMPARED column (not one of the 5 stripped meta keys:
# event_id, aggregate_version, applied_at, last_verified_event_version,
# last_verified_at) — so `to_jsonb - meta` byte-compare sees the change.
psql_db "$BITE_DB" -c "UPDATE ${BITE_TABLE} SET ${BITE_COL} = ${BITE_COL} || '__BITE__'" >/dev/null
"$IC" >/dev/null 2>&1 || true   # re-sweep; drift never changes the checker's exit code
bite_drift="$(psql_db "$BITE_DB" -tA -c "SELECT COALESCE(drift_count,0) FROM projection_drift_state WHERE table_name='${BITE_TABLE}'")"
if [ "$bite_drift" -gt 0 ] 2>/dev/null; then
  log "PASS(bite): corrupting ${BITE_TABLE} (${n} rows) → drift_count=${bite_drift} — the differential HAS teeth (clean 0 → corrupt >0)"
  exit 0
fi
log "FAIL(harness): bite did NOT fire — corrupted ${BITE_TABLE} but drift_count=${bite_drift}. The gate would be VACUOUS."
exit 2
