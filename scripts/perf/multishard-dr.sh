#!/usr/bin/env bash
# scripts/perf/multishard-dr.sh
#
# S12 (Inc-5) — WHOLE-SYSTEM multi-shard DR drill (closes D-S8-MULTI-SHARD-DR).
#
# S8's recover-archive-restore drilled ONE shard. Real DR is N shards restored
# TOGETHER: a disaster takes out the whole fleet, and recovery must bring every
# shard back byte-consistent — not just one. This drill seeds N real Postgres
# shards, captures a per-shard content checksum, dumps each, simulates the
# disaster (DROP every shard DB), restores all from their dumps, and verifies
# every shard's events are byte-identical to pre-disaster.
#
#   drill [N]    seed + checksum + dump + DROP-all + restore-all + verify-all
#   bite  [N]    same, but tamper ONE dump before restore → the verify MUST catch it
#
# Verdict: NOTRUN(2) setup; FAIL(1) any shard restores non-identical, or the bite's
# tampered shard restores clean (verify is vacuous); PASS(0) all N byte-identical.
# Requires scale-rig.sh up. Re-runnable.
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_DB="scale_shard"
SHARDS="${SCALE_SHARDS:-3}"

log()    { printf '[multishard-dr] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
shard_c() { echo "scale-pg-shard-$1"; }
shard_hp() { echo "127.0.0.1:$((55511 + $1))"; }
psqlA()  { docker exec -i "$1" psql -tA -U "$PG_USER" -d "$2" -c "$3"; }

bin() { for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
WG="${WG_BIN:-$(bin tests/workload-gen/wg.exe tests/workload-gen/wg)}" || notrun "workload-gen not built"

# FULL-CONTENT checksum: count + a digest over event_id||aggregate_version||payload
# (ordered). Digesting the id ALONE would miss a payload/version corruption that
# kept the id — so "byte-identical" needs the content, not just the id set.
checksum() { # container
  psqlA "$1" "$SHARD_DB" "SELECT count(*)||':'||COALESCE(md5(string_agg(event_id::text||'|'||aggregate_version::text||'|'||payload::text, ',' ORDER BY event_id::text)),'empty') FROM events"
}

seed_shard() { # k
  local c dsn; c="$(shard_c "$1")"; dsn="postgres://${PG_USER}:${PG_PASS}@$(shard_hp "$1")/${SHARD_DB}?sslmode=disable"
  # Clean first so the deterministic wg seed always lands fresh (re-runnable) and
  # the checksum is reproducible (events PK includes deterministic event_ids).
  psqlA "$c" "$SHARD_DB" "TRUNCATE events, events_outbox" >/dev/null 2>&1 || true
  "$WG" -seed "$((500 + $1))" -profile multi-reality -emit -dsn "$dsn" 2>/dev/null || notrun "seed shard $1 failed (migrated?)"
}

run_drill() { # bite_flag
  local bite="$1" k c
  [ "$SHARDS" -ge 2 ] || notrun "DR needs N>=2 shards (got ${SHARDS})"
  for k in $(seq 0 $((SHARDS - 1))); do
    c="$(shard_c "$k")"
    docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true || notrun "$c not running (scale-rig.sh up)"
    psqlA "$c" "$SHARD_DB" "SELECT to_regclass('public.events')" 2>/dev/null | grep -q events || notrun "$c ${SHARD_DB} not migrated"
  done

  log "seeding ${SHARDS} shards + capturing pre-disaster checksums ..."
  declare -A PRE
  for k in $(seq 0 $((SHARDS - 1))); do
    c="$(shard_c "$k")"; seed_shard "$k"
    PRE[$k]="$(checksum "$c")"
    log "  shard ${k}: ${PRE[$k]}"
    # pg_dump the whole shard DB (schema + data + partitions) to container /tmp.
    docker exec "$c" sh -c "pg_dump -U ${PG_USER} ${SHARD_DB} > /tmp/dr_shard.sql" || notrun "pg_dump shard ${k} failed"
  done

  if [ "$bite" = "1" ]; then
    # Tamper shard 0's dump: drop the FIRST COPY data row (a UUID-prefixed event
    # line) so the restore silently loses one event.
    c="$(shard_c 0)"
    # Delete the FIRST data row inside the events partition COPY block specifically
    # (pg_dump writes partitioned event data under events_p_default; a UUID-prefixed
    # line elsewhere — e.g. events_outbox — would not change the events checksum).
    local before after
    before="$(docker exec "$c" sh -c "wc -l < /tmp/dr_shard.sql" | tr -d '[:space:]')"
    docker exec "$c" sh -c "awk '
        /^COPY .*events_p_default / {inblk=1; print; next}
        inblk && /^\\\\\\.\$/ {inblk=0; print; next}
        inblk && !done {done=1; next}
        {print}
      ' /tmp/dr_shard.sql > /tmp/dr_shard.sql.t && mv /tmp/dr_shard.sql.t /tmp/dr_shard.sql" \
      || notrun "could not tamper dump"
    after="$(docker exec "$c" sh -c "wc -l < /tmp/dr_shard.sql" | tr -d '[:space:]')"
    # Fail LOUD (notrun) if the tamper was a no-op — e.g. the partition naming
    # changed and the awk matched nothing — rather than letting a vacuous bite
    # masquerade as a real one.
    [ "${after:-0}" -lt "${before:-0}" ] || notrun "tamper was a no-op (${before}->${after} lines) — events_p_default COPY block not found? partition scheme changed"
    log "BITE: tampered shard 0's dump (deleted one events_p_default data row; ${before}->${after} lines)"
  fi

  log "DISASTER: dropping all ${SHARDS} shard DBs together ..."
  for k in $(seq 0 $((SHARDS - 1))); do
    c="$(shard_c "$k")"
    psqlA "$c" foundation "DROP DATABASE IF EXISTS ${SHARD_DB} WITH (FORCE)" >/dev/null || notrun "drop shard ${k} failed"
  done

  log "RESTORE: recreating + restoring all ${SHARDS} shards from their dumps ..."
  for k in $(seq 0 $((SHARDS - 1))); do
    c="$(shard_c "$k")"
    psqlA "$c" foundation "CREATE DATABASE ${SHARD_DB}" >/dev/null
    docker exec "$c" sh -c "psql -q -U ${PG_USER} -d ${SHARD_DB} < /tmp/dr_shard.sql" >/dev/null 2>&1 || notrun "restore shard ${k} failed"
  done

  log "VERIFY: every shard byte-identical to pre-disaster ..."
  local bad=0 tampered_caught=0
  for k in $(seq 0 $((SHARDS - 1))); do
    c="$(shard_c "$k")"; local post; post="$(checksum "$c")"
    if [ "$post" = "${PRE[$k]}" ]; then
      log "  shard ${k}: MATCH (${post})"
    else
      log "  shard ${k}: MISMATCH pre=${PRE[$k]} post=${post}"
      bad=$((bad + 1)); [ "$k" = 0 ] && tampered_caught=1
    fi
  done

  if [ "$bite" = "1" ]; then
    [ "$tampered_caught" = 1 ] \
      && { log "PASS(bite): the tampered shard restored NON-identical and the checksum caught it — DR verify has teeth"; return 0; } \
      || fail "the tampered shard restored clean — DR verify is vacuous"
  fi
  [ "$bad" -eq 0 ] || fail "${bad}/${SHARDS} shards restored non-identical — multi-shard DR broken"
  log "PASS: all ${SHARDS} shards restored together, byte-identical (D-S8-MULTI-SHARD-DR closed)"
}

main() {
  case "${1:-drill}" in
    drill) run_drill 0 ;;
    bite)  run_drill 1 ;;
    *) echo "usage: $0 {drill|bite}" >&2; exit 2 ;;
  esac
}
main "$@"
