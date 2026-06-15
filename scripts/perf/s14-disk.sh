#!/usr/bin/env bash
# scripts/perf/s14-disk.sh
#
# S14 (D1) — Disk I/O saturation under the spine's DURABLE write path, LIVE.
#
# The spine commits each event with fsync (events + events_outbox in one TX,
# synchronous_commit=on). Under concurrent load that durable path is bound by the
# disk's WAL-fsync latency. This drill proves the durable write path stays GRACEFUL
# when the disk is the bottleneck (commits keep landing, throughput makes real
# progress, recovers) and that the bottleneck is genuinely the DISK.
#
# A dedicated throwaway PG (must not disturb the shared rig) runs the REAL spine T2
# write (infra/scale/pgbench-event-insert.sql) via pgbench under CONC concurrent
# writers:
#
#   durable  synchronous_commit=on   → every commit waits for WAL fsync to disk
#   async    synchronous_commit=off  → commits do NOT wait for fsync  (BITE)
#
# BITE / self-saturation: async tps >> durable tps ⇒ the disk fsync WAS the real
# bound (removing the fsync wait sped it up). If async ≈ durable, the box wasn't
# disk/fsync-bound (e.g. an absurdly fast disk) → NOTRUN, never a fake PASS.
# GATE (graceful): under the durable path the writers keep committing, tps stays a
# real fraction of the async ceiling (doesn't collapse), and the PG recovers.
#
# WHY not shared_buffers/dataset>RAM here: empirically (WSL2/Docker Desktop) the
# durable WRITE path is fsync-bound and indifferent to buffer cache; capping
# shared_buffers/--memory does not move it. The dataset>RAM READ cache-thrash needs
# a reliably-constrained OS page cache, which WSL2 does not give predictably — that
# read-side disk pressure is tracked as D-S14-DISK-READ-THRASH (manual/fio capture),
# NOT faked here. The WRITE fsync path IS real disk I/O and is the spine's hot path.
#
# Verdict: NOTRUN(2) setup / not-disk-bound; FAIL(1) collapse; PASS(0). Self-contained
# (own container); cleans up on exit.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
IMG="${S14_PG_IMAGE:-postgres:16}"
PGUSER="foundation"; PGPASS="foundation"; PGDB="foundation"
SECS="${SECS:-8}"; CONC="${CONC:-16}"
SAT="${SAT:-150}"      # disk-bound self-proof: async tps >= SAT% of durable(concurrent) tps
# graceful: concurrent durable tps >= single-writer durable tps × GRACE — i.e. under
# many concurrent fsyncing writers the disk path HOLDS (group commit) and does not
# collapse below the single-writer rate (which would signal contention pathology). It
# is NOT compared to the async ceiling: the disk being many× slower than RAM is the
# bound we're PROVING, not a failure.
GRACE="${GRACE:-90}"   # percent: tps_concurrent >= tps_single × GRACE/100
SQL="infra/scale/pgbench-event-insert.sql"
PG="s14d-pg"

log()    { printf '[s14-disk] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; cleanup; exit 2; }
fail()   { log "FAIL: $*"; cleanup; exit 1; }
cleanup(){ docker rm -f "$PG" >/dev/null 2>&1 || true; }
trap cleanup EXIT

ge() { awk "BEGIN{exit !($1 >= $2)}"; }

start_pg() {
  docker rm -f "$PG" >/dev/null 2>&1 || true
  docker run -d --name "$PG" --memory=512m --memory-swap=512m \
    -e POSTGRES_USER="$PGUSER" -e POSTGRES_PASSWORD="$PGPASS" -e POSTGRES_DB="$PGDB" \
    "$IMG" -c fsync=on -c synchronous_commit=on -c full_page_writes=on \
    -c max_connections=64 >/dev/null || notrun "docker run failed"
  local i
  for i in $(seq 1 40); do
    docker exec "$PG" pg_isready -U "$PGUSER" -d "$PGDB" >/dev/null 2>&1 && break
    sleep 0.5
    [ "$i" = 40 ] && notrun "$PG not ready"
  done
}

migrate() {
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do
    docker exec -i "$PG" psql -q -v ON_ERROR_STOP=1 -U "$PGUSER" -d "$PGDB" \
      < "contracts/migrations/per_reality/${m}.up.sql" >/dev/null 2>&1 \
      || notrun "per_reality migration ${m} failed"
  done
  docker exec "$PG" psql -q -U "$PGUSER" -d "$PGDB" \
    -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
}

# load sync_commit(on|off) conc → prints "tps failed_txns"
load() {
  local sc="$1" conc="$2" out tps failed
  out="$(docker exec -e PGOPTIONS="-c synchronous_commit=${sc}" "$PG" \
        pgbench -n -f /tmp/s14.sql -c "$conc" -j "$conc" -T "$SECS" -U "$PGUSER" "$PGDB" 2>&1)" \
        || { echo "0 0"; return 0; }
  tps="$(printf '%s\n' "$out" | sed -n 's/^tps = \([0-9.]*\).*/\1/p' | head -1)"
  # pg16 prints "number of failed transactions: N (..%)"; absent ⇒ 0.
  failed="$(printf '%s\n' "$out" | sed -n 's/^number of failed transactions: \([0-9]*\).*/\1/p' | head -1)"
  echo "${tps:-0} ${failed:-0}"
}

count() { docker exec "$PG" psql -tA -U "$PGUSER" -d "$PGDB" -c "SELECT count(*) FROM events" 2>/dev/null | tr -d '[:space:]'; }

cmd_drill() {
  docker info >/dev/null 2>&1 || notrun "docker not available"
  [ -f "$SQL" ] || notrun "missing $SQL"
  start_pg; migrate
  docker exec -i "$PG" sh -c "cat > /tmp/s14.sql" < "$SQL"

  log "durable baseline: 1 writer, synchronous_commit=ON (single-writer disk fsync rate) ..."
  local tps_d1 _f1; read -r tps_d1 _f1 < <(load on 1)
  log "  durable(1): tps=${tps_d1}"

  log "durable load: ${CONC} concurrent writers, synchronous_commit=ON (disk fsync under concurrency) ..."
  local tps_dN failed_dN; read -r tps_dN failed_dN < <(load on "$CONC")
  local cnt_durable; cnt_durable="$(count)"
  log "  durable(${CONC}): tps=${tps_dN} failed_txns=${failed_dN} committed=${cnt_durable}"

  log "BITE: ${CONC} writers, synchronous_commit=OFF (fsync wait removed from the commit path) ..."
  local tps_async _fa; read -r tps_async _fa < <(load off "$CONC")
  log "  async(${CONC}): tps=${tps_async}"

  # recovery: durable PG still accepts a write after the load.
  local rec="no"
  docker exec "$PG" psql -q -U "$PGUSER" -d "$PGDB" \
    -c "INSERT INTO events (event_id,reality_id,aggregate_type,aggregate_id,aggregate_version,event_type,event_version,payload,occurred_at,recorded_at) VALUES (gen_random_uuid(),'00000000-0000-0000-0000-000000000001','pc','recover',999,'pc.moved',1,'{}'::jsonb,now(),now())" >/dev/null 2>&1 && rec="yes"

  local sat_need grace_need
  sat_need="$(awk "BEGIN{printf \"%.2f\", ${tps_dN}*${SAT}/100}")"
  grace_need="$(awk "BEGIN{printf \"%.2f\", ${tps_d1}*${GRACE}/100}")"
  printf '{"phase":"disk","tps_durable_1":%s,"tps_durable_N":%s,"tps_async":%s,"committed":%s,"failed_txns":%s,"sat_need":%s,"grace_need":%s,"recovered":%q}\n' \
    "${tps_d1:-0}" "${tps_dN:-0}" "${tps_async:-0}" "${cnt_durable:-0}" "${failed_dN:-0}" "$sat_need" "$grace_need" "$rec"

  # self-saturation / BITE: removing the fsync wait must speed it up meaningfully —
  # else the box wasn't disk/fsync-bound (mem-backed disk / absurd NVMe) → NOTRUN.
  if ! ge "${tps_async:-0}" "$sat_need"; then
    log "NOTRUN: async tps ${tps_async} not >= ${SAT}% of durable tps ${tps_dN} — the durable path was NOT fsync/disk-bound on this box; re-run / faster-disk caveat"
    return 2
  fi
  [ "${cnt_durable:-0}" -gt 0 ] || fail "durable run committed 0 events — write path did not stay alive under disk pressure"
  # graceful also means commits did not ERROR under disk pressure (not just decent tps).
  [ "${failed_dN:-0}" -eq 0 ] || fail "durable run had ${failed_dN} FAILED transactions under disk pressure — not graceful (commit errors, not just slower)"
  [ "$rec" = "yes" ] || fail "PG did not accept a write after the load — no recovery"
  # graceful: under many concurrent fsyncing writers the disk path HELD (group commit) —
  # concurrent tps did not collapse below the single-writer rate (contention pathology).
  if ! ge "${tps_dN:-0}" "$grace_need"; then
    fail "durable tps collapsed UNDER concurrency: ${CONC}-writer ${tps_dN} < 1-writer×${GRACE}% (${grace_need}) — contention pathology, not graceful"
  fi
  log "PASS: durable write path GRACEFUL under DISK (fsync) saturation — ${cnt_durable} committed; concurrency held (tps ${tps_dN} >= 1-writer ${tps_d1} × ${GRACE}%), recovered; BITE: async ${tps_async} >> durable ${tps_dN} proves the disk fsync was the real bound"
  return 0
}

main() {
  case "${1:-drill}" in
    drill) cmd_drill ;;
    *) echo "usage: $0 {drill}" >&2; exit 2 ;;
  esac
}
main "$@"
