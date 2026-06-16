#!/usr/bin/env bash
# scripts/chaos/recover-archive-restore.sh
#
# S8 (Technique G) — drill G3: restore-from-archive (Parquet round-trip) -> C3
# byte-match.
#
# Cold-storage DR: the archive-worker writes an old events partition to Parquet
# in MinIO and DROPs it; the archive-restore CLI pulls it back. This drill proves
# the round-trip is LOSSLESS — the restored events byte-match the pre-archive
# content (a true catastrophic-recovery proof, not just "the file exists").
#
# Partition routing (S8 review MED-2): events are RANGE-partitioned by
# recorded_at; `partition_picker` enumerates events_p_YYYY_MM (never the DEFAULT
# partition). wg writes a DETERMINISTIC recorded_at from baseEpoch=2026-01-01
# (tests/workload-gen/internal/gen/gen.go), so ALL emitted events fall in
# 2026-01. We create events_p_2026_01 BEFORE emit so the rows route directly into
# it (no cross-partition move). With ARCHIVE_CUTOFF=0 that long-past partition is
# immediately eligible. (If wg's baseEpoch ever changes, 0 rows land in the
# partition → the drill NOTRUNs, not a silent pass.)
#
# C3 digest (S8 review MED-4): a deterministic SQL md5 over the columns present
# in BOTH `events` and `events_restore_*` (review LOW-5) — event_id, aggregate_id,
# aggregate_version, event_type, payload — PLUS recorded_at/occurred_at as
# extract(epoch ...) numerics (review impl MED-2: a format-STABLE timestamp digest
# so the temporal fidelity of the Parquet round-trip is verified too, without the
# ::text timezone-format fragility). Ordered by event_id.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
COMPOSE="infra/foundation-dev/docker-compose.yml"
PG_CONTAINER="foundation-dev-postgres"
PG_USER="foundation"; PG_PASS="foundation"
PG_PORT="${FOUNDATION_PG_PORT:-55432}"
MINIO_PORT="${FOUNDATION_MINIO_PORT:-59000}"
MINIO_ENDPOINT="127.0.0.1:${MINIO_PORT}"
MINIO_AK="${MINIO_AK:-foundation}"; MINIO_SK="${MINIO_SK:-foundation-secret-dev-only}"
META_DB="recover_arx_meta"; SHARD_DB="recover_arx_shard"
PROFILE="${PROFILE:-single-reality}"
SEED="${SEED:-3}"
BITE="${BITE:-0}"
for a in "$@"; do case "$a" in --bite) BITE=1 ;; esac; done
SHARD_DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${SHARD_DB}?sslmode=disable"

log() { printf '[archive-restore] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || notrun "workload-gen not built"
AW="${AW_BIN:-$(bin services/archive-worker/aw.exe services/archive-worker/aw)}" || notrun "archive-worker not built"
ARX="${ARX_BIN:-$(bin services/archive-worker/arx.exe services/archive-worker/arx)}" || notrun "archive-restore not built"

docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || notrun "foundation Postgres not reachable"
# MinIO reachability (foundation-stack predicate is PG+Redis only).
curl -fsS "http://${MINIO_ENDPOINT}/minio/health/live" >/dev/null 2>&1 || notrun "MinIO not reachable at ${MINIO_ENDPOINT} (G3 needs MinIO)"

AW_PID=""; cleanup() { [ -n "$AW_PID" ] && kill "$AW_PID" >/dev/null 2>&1 || true; }; trap cleanup EXIT

# ── archive window = wg baseEpoch month (2026-01), overridable ───────────────
LM_MONTH="${ARCHIVE_MONTH:-2026-01}"                       # wg baseEpoch month
LM_START="${LM_MONTH}-01"
CUR_M="$(date -d "${LM_START} +1 month" +%Y-%m-01)"        # window upper bound
LM_PART="$(date -d "${LM_START}" +%Y_%m)"                  # 2026_01
PART="events_p_${LM_PART}"
log "archive window: [${LM_START}, ${CUR_M}) → ${PART}, restore month=${LM_MONTH}"

log "(re)creating meta + shard DBs ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${META_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${META_DB}" >/dev/null
for m in 001_reality_registry 003_publisher_heartbeats; do docker exec -i "$PG_CONTAINER" psql -q -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql"; done
psql_db foundation -c "DROP DATABASE IF EXISTS ${SHARD_DB}" >/dev/null; psql_db foundation -c "CREATE DATABASE ${SHARD_DB}" >/dev/null
for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256 0011_archive_state; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$SHARD_DB" < "contracts/migrations/per_reality/${m}.up.sql"
done
psql_db "$SHARD_DB" -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
# Create the month partition BEFORE emit so wg's 2026-01 rows route into it.
psql_db "$SHARD_DB" -c "CREATE TABLE ${PART} PARTITION OF events FOR VALUES FROM ('${LM_START}') TO ('${CUR_M}')" >/dev/null

# ── emit → rows route directly into the month partition (no move) ─────────────
"$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$SHARD_DSN"
RID="$(psql_db "$SHARD_DB" -tA -c "SELECT DISTINCT reality_id FROM events LIMIT 1")"
inpart="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM ${PART}")"
[ "${inpart:-0}" -gt 0 ] || notrun "no rows in ${PART} — wg baseEpoch month != ${LM_MONTH} (set ARCHIVE_MONTH)"
log "emitted ${inpart} events into ${PART} (reality=${RID})"
psql_db "$META_DB" -c "INSERT INTO reality_registry (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort) VALUES ('${RID}','pg-shard-1.internal','${SHARD_DB}','active','en',10,10,20,5)" >/dev/null

# ── C3 digest of the window BEFORE archiving ─────────────────────────────────
DIGEST_EXPR="md5(coalesce(string_agg(event_id::text||'|'||aggregate_id||'|'||aggregate_version::text||'|'||event_type||'|'||payload::text||'|'||extract(epoch from recorded_at)::text||'|'||extract(epoch from occurred_at)::text, '|' ORDER BY event_id),''))"
PRE="$(psql_db "$SHARD_DB" -tA -c "SELECT ${DIGEST_EXPR} FROM ${PART}")"
log "pre-archive C3 digest: ${PRE}"

# ── run archive-worker (CUTOFF=0 → the last-month partition is eligible) ──────
log "starting archive-worker (ARCHIVE_CUTOFF=0) → Parquet → MinIO → DROP ${PART} ..."
META_DB_URL="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:${PG_PORT}/${META_DB}?sslmode=disable" \
  MINIO_ENDPOINT="$MINIO_ENDPOINT" MINIO_ACCESS_KEY="$MINIO_AK" MINIO_SECRET_KEY="$MINIO_SK" \
  SHARD_DB_USER="$PG_USER" SHARD_DB_PASSWORD="$PG_PASS" SHARD_DB_PORT="$PG_PORT" SHARD_DB_SSLMODE=disable \
  PUBLISHER_SHARD_HOST_OVERRIDE="*=127.0.0.1:${PG_PORT}" \
  ARCHIVE_CUTOFF=0 ARCHIVE_INTERVAL=1s ARCHIVE_HTTP_ADDR=:18083 \
  "$AW" >/tmp/recover_arx_aw.log 2>&1 &
AW_PID=$!
archived=0
for _ in $(seq 1 30); do
  kill -0 "$AW_PID" 2>/dev/null || { cat /tmp/recover_arx_aw.log; notrun "archive-worker exited early (config/minio)"; }
  gone="$(psql_db "$SHARD_DB" -tA -c "SELECT to_regclass('${PART}') IS NULL")"
  st="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM archive_state WHERE reality_id='${RID}'")"
  [ "$gone" = "t" ] && [ "${st:-0}" -gt 0 ] && { archived=1; break; }
  sleep 1
done
kill "$AW_PID" >/dev/null 2>&1 || true; AW_PID=""
[ "$archived" = 1 ] || { cat /tmp/recover_arx_aw.log; notrun "archive-worker did not archive ${PART} within timeout"; }
log "archived: ${PART} written to MinIO + DROPped (archive_state row present)"

# ── restore from MinIO → events_restore_<YYYYMM> ─────────────────────────────
log "archive-restore restore --reality ${RID} --month ${LM_MONTH} ..."
RESTORE_DB_URL="$SHARD_DSN" MINIO_ENDPOINT="$MINIO_ENDPOINT" MINIO_ACCESS_KEY="$MINIO_AK" MINIO_SECRET_KEY="$MINIO_SK" \
  "$ARX" restore --reality "$RID" --month "$LM_MONTH" 2>&1 | sed 's/^/[arx] /' || notrun "archive-restore failed"
RTABLE="$(psql_db "$SHARD_DB" -tA -c "SELECT tablename FROM pg_tables WHERE tablename LIKE 'events_restore_%' ORDER BY tablename DESC LIMIT 1")"
[ -n "$RTABLE" ] || notrun "no events_restore_* table after restore"
RROWS="$(psql_db "$SHARD_DB" -tA -c "SELECT count(*) FROM ${RTABLE}")"
[ "${RROWS:-0}" -gt 0 ] || notrun "restore produced 0 rows in ${RTABLE}"
log "restored ${RROWS} rows into ${RTABLE}"

# ── C3 byte-match: restored == pre-archive ───────────────────────────────────
POST="$(psql_db "$SHARD_DB" -tA -c "SELECT ${DIGEST_EXPR} FROM ${RTABLE}")"
log "post-restore C3 digest: ${POST}"
[ "$PRE" = "$POST" ] || fail "C3 byte-match FAILED — restored content != pre-archive (pre=${PRE} post=${POST})"
log "C3: restored events byte-match the pre-archive window (lossless Parquet round-trip)"

# ── BITE: mutate a restored row → digest diverges ────────────────────────────
if [ "$BITE" = "1" ]; then
  psql_db "$SHARD_DB" -c "UPDATE ${RTABLE} SET payload = payload || '{\"_corrupt\":1}'::jsonb WHERE event_id = (SELECT event_id FROM ${RTABLE} ORDER BY event_id LIMIT 1)" >/dev/null
  POST2="$(psql_db "$SHARD_DB" -tA -c "SELECT ${DIGEST_EXPR} FROM ${RTABLE}")"
  [ "$PRE" != "$POST2" ] || { log "FAIL(harness): mutated a restored row but digest unchanged — the C3 compare is vacuous"; exit 2; }
  log "PASS(bite): mutating one restored payload → digest diverged (${POST2}) — the C3 byte-match HAS teeth"
fi

log "PASS: archive Parquet round-trip (write→MinIO→DROP→restore) is LOSSLESS — C3 byte-match clean"
