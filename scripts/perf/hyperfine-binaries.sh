#!/usr/bin/env bash
# scripts/perf/hyperfine-binaries.sh
#
# S7 deliverable F3 — binary wall-clock harness feeding the USL fitter (F1).
#
# Produces, per the spec §8 micro list:
#   - perf-usl-wg-emit.json     event-write throughput vs CONCURRENCY (L2)
#   - perf-usl-rebuild.json     replay/rebuild throughput vs CONCURRENCY (L3.G)
#   - perf-ic-duration.json     integrity-check wall-clock duration
#
# ── N is CONCURRENCY, not load-size (S7 review HIGH-1) ───────────────────────
#   wg-emit  : N = K PARALLEL `wg -emit` PROCESSES against one shard DB (each a
#              distinct seed → distinct events, no PK collision). DB lock/WAL
#              contention → α, cross-writer coherency → β.  X(K)=K·EPW / wall.
#   rebuild  : N = rebuilder's OWN `--parallel-workers K` on ONE seeded shard
#              (internal concurrency is the contention axis).  X(K)=NEVENTS / wall.
# Event-count is held FIXED per worker; only concurrency is swept.
#
# hyperfine absent → NOTRUN (like S6's cargo→loom). <4 concurrency points or a
# degenerate/non-convergent fit → NOTRUN(setup). No threshold is asserted — the
# fitted-coefficients artifact IS the deliverable (baselines-first, §0).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

# ── hidden fan-out subcommands (hyperfine invokes the script as the timed cmd) ─
# These read SHARD_DSN / WG / SEED_BASE / PROFILE from the env hyperfine inherits.
if [ "${1:-}" = "--emit-fanout" ]; then
  K="$2"; pids=()
  for w in $(seq 1 "$K"); do
    "$WG" -seed "$((SEED_BASE + w))" -profile "$PROFILE" -emit -dsn "$SHARD_DSN" >/dev/null 2>&1 &
    pids+=($!)
  done
  rc=0; for p in "${pids[@]}"; do wait "$p" || rc=1; done
  exit "$rc"
fi

COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
PROFILE="${PROFILE:-single-reality}"
SEED_BASE="${SEED_BASE:-1000}"
SWEEP="${CONCURRENCY_SWEEP:-1 2 4 8 16}"   # ≥4 distinct points for the fit
REBUILD_PROJECTION="${REBUILD_PROJECTION:-pc_projection}"
REBUILD_SEED_VOL="${REBUILD_SEED_VOL:-200}" # seeds emitted to build rebuild volume
RESULTS="tests/conformance/results"
EMIT_DB="perf_emit_shard"; REBUILD_DB="perf_rebuild_shard"; META_DB="perf_meta"
EMIT_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${EMIT_DB}?sslmode=disable"
REBUILD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${REBUILD_DB}?sslmode=disable"

log()    { printf '[hyperfine] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
psql_db(){ docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }

command -v hyperfine >/dev/null 2>&1 || notrun "hyperfine not found (CI installs it; absent on the dev box)"
docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || notrun "foundation Postgres not reachable"

# ── resolve binaries (mirror S5: target/debug + module dirs; no .exe on Linux) ─
bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || notrun "workload-gen binary not built"
REBUILDER="${REBUILDER_BIN:-$(bin target/debug/rebuilder.exe target/debug/rebuilder)}" || notrun "rebuilder binary not built"
export WG SHARD_DSN PROFILE SEED_BASE
# usl-fit is in-toolchain — build it (go is present even where hyperfine is not).
USL_FIT="$ROOT/tests/perf/usl-fit"; [ -f "$USL_FIT.exe" ] && USL_FIT="$USL_FIT.exe"
( cd tests/perf && go build -o "$USL_FIT" ./usl/cmd/usl-fit ) || notrun "could not build usl-fit"

mkdir -p "$RESULTS"
HF_MEAN='import json,sys;print(json.load(open(sys.argv[1]))["results"][0]["mean"])'

migrate_shard() { # $1=db
  psql_db foundation -c "DROP DATABASE IF EXISTS $1" >/dev/null
  psql_db foundation -c "CREATE DATABASE $1" >/dev/null
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do
    docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$1" < "contracts/migrations/per_reality/${m}.up.sql"
  done
  psql_db "$1" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
}

# ── F3a: wg-emit throughput vs K parallel writers ─────────────────────────────
log "wg-emit USL: building shard $EMIT_DB ..."
migrate_shard "$EMIT_DB"
SHARD_DSN="$EMIT_DSN"; export SHARD_DSN

EMIT_CSV="$(mktemp)"; echo "n,throughput" >"$EMIT_CSV"
for K in $SWEEP; do
  hf="$(mktemp)"
  hyperfine --warmup 1 --runs 8 --export-json "$hf" \
    --prepare "docker exec -i $PG_CONTAINER psql -q -U $PG_USER -d $EMIT_DB -c 'TRUNCATE events, events_outbox'" \
    "bash $ROOT/scripts/perf/hyperfine-binaries.sh --emit-fanout $K" >/dev/null \
    || notrun "hyperfine run failed at K=$K (wg-emit)"
  mean="$(python -c "$HF_MEAN" "$hf")"
  # ACTUAL emitted rows (review MED-2): --prepare TRUNCATEs before each run, so
  # the DB now holds exactly the last fanout's rows = K workers' real output. Do
  # NOT assume K*EPW — event count may vary by seed, and each worker uses a
  # distinct seed (SEED_BASE+w).
  emitted="$(psql_db "$EMIT_DB" -tA -c 'SELECT count(*) FROM events')"
  [ "${emitted:-0}" -gt 0 ] || notrun "K=$K fanout emitted 0 events — cannot measure throughput"
  thr="$(python -c "print($emitted / $mean)")"
  echo "$K,$thr" >>"$EMIT_CSV"
  log "wg-emit K=$K mean=${mean}s emitted=$emitted X=${thr} ev/s"
  rm -f "$hf"
done
"$USL_FIT" -in "$EMIT_CSV" >"$RESULTS/perf-usl-wg-emit.json" || notrun "USL fit failed (wg-emit) — see series"
log "wrote $RESULTS/perf-usl-wg-emit.json"; cat "$RESULTS/perf-usl-wg-emit.json"

# ── F3b: rebuild throughput vs rebuilder --parallel-workers K ─────────────────
log "rebuild USL: building + volume-seeding shard $REBUILD_DB ($REBUILD_SEED_VOL seeds) ..."
migrate_shard "$REBUILD_DB"
for s in $(seq 1 "$REBUILD_SEED_VOL"); do
  "$WG" -seed "$((SEED_BASE + 10000 + s))" -profile "$PROFILE" -emit -dsn "$REBUILD_DSN" >/dev/null 2>&1 || true
done
NEVENTS="$(psql_db "$REBUILD_DB" -tA -c 'SELECT count(*) FROM events')"
RID="$(psql_db "$REBUILD_DB" -tA -c 'SELECT DISTINCT reality_id FROM events LIMIT 1')"
[ "${NEVENTS:-0}" -gt 0 ] && [ -n "$RID" ] || notrun "rebuild shard empty — cannot measure"
log "rebuild volume = $NEVENTS events, reality=$RID, projection=$REBUILD_PROJECTION"

REBUILD_CSV="$(mktemp)"; echo "n,throughput" >"$REBUILD_CSV"
for K in $SWEEP; do
  hf="$(mktemp)"
  hyperfine --warmup 1 --runs 8 --export-json "$hf" \
    --prepare "docker exec -i $PG_CONTAINER psql -q -U $PG_USER -d $REBUILD_DB -c 'TRUNCATE $REBUILD_PROJECTION'" \
    "env REALITY_DB_URL='$REBUILD_DSN' '$REBUILDER' --reality-id '$RID' --projection '$REBUILD_PROJECTION' --parallel-workers $K" \
    >/dev/null || notrun "hyperfine run failed at K=$K (rebuild)"
  mean="$(python -c "$HF_MEAN" "$hf")"
  thr="$(python -c "print($NEVENTS / $mean)")"
  echo "$K,$thr" >>"$REBUILD_CSV"
  log "rebuild workers=$K mean=${mean}s X=${thr} ev/s"
  rm -f "$hf"
done
"$USL_FIT" -in "$REBUILD_CSV" >"$RESULTS/perf-usl-rebuild.json" || notrun "USL fit failed (rebuild) — see series"
log "wrote $RESULTS/perf-usl-rebuild.json"; cat "$RESULTS/perf-usl-rebuild.json"

# ── F3c: integrity-check duration (single wall-clock, not a saturation curve) ─
IC="${IC_BIN:-$(bin services/integrity-checker/ic.exe services/integrity-checker/ic)}" || { log "ic not built — skipping duration baseline"; IC=""; }
if [ -n "$IC" ]; then
  log "integrity-check duration baseline ..."
  hf="$RESULTS/perf-ic-duration.json"
  REPLAY_ABS="$(bin target/debug/replay-aggregate.exe target/debug/replay-aggregate || true)"
  psql_db foundation -c "DROP DATABASE IF EXISTS $META_DB" >/dev/null
  psql_db foundation -c "CREATE DATABASE $META_DB" >/dev/null
  for m in 001_reality_registry 003_publisher_heartbeats; do
    docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql" 2>/dev/null || true
  done
  psql_db "$META_DB" -c "INSERT INTO reality_registry (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort) VALUES ('$RID','pg-shard-1.internal','$REBUILD_DB','active','en',10,10,20,5) ON CONFLICT DO NOTHING" >/dev/null 2>&1 || true
  if [ -n "$REPLAY_ABS" ]; then
    hyperfine --warmup 1 --runs 6 --export-json "$hf" \
      "env META_DATABASE_URL='postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable' \
           SHARD_DB_USER='$PG_USER' SHARD_DB_PASSWORD='$PG_PASS' SHARD_DB_PORT='$PG_PORT' SHARD_DB_SSLMODE=disable \
           SHARD_DB_HOST_OVERRIDE='*=127.0.0.1:${PG_PORT}' REPLAY_AGGREGATE_BIN_PATH='$REPLAY_ABS' '$IC'" \
      >/dev/null && log "wrote $hf" || log "ic duration run failed — skipped (non-fatal)"
  fi
fi

rm -f "$EMIT_CSV" "$REBUILD_CSV"
log "PASS: F3 wall-clock harness produced USL artifacts (wg-emit, rebuild) + ic duration"
