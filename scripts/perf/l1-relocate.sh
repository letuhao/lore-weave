#!/usr/bin/env bash
# scripts/perf/l1-relocate.sh
#
# S13 (Inc-4, the headline) — cross-shard reality relocation, LIVE on the multi-shard
# rig. Relocates a reality's event DB shard-0 → shard-1 and proves the relocation is
# atomic-at-the-registry and loss-free:
#
#   active --CAS--> migrating         (relocate-drill, real AttemptStateTransition)
#   copy events shard-0 → shard-1     (pg_dump | restore — a real cross-host copy)
#   CONTENT-CHECKSUM gate             (event_id+aggregate_version+payload; target==source)
#   migrating --CAS--> active         (db_host + db_name ride as Payload in the SAME
#                                      CAS-guarded UPDATE — db_host flips ONLY here)
#   decommission source              (DROP the old DB — no orphan readable)
#
# Why these invariants (NOT "split-brain"): reality_registry has ONE db_host per
# reality_id (PK), so it can never be both-live. The real risks are (a) premature flip
# LOSS — db_host points at a target that lacks the full event set — and (b) orphan
# LEFTOVER — the old shard left readable after the flip. A half-done relocation must
# roll forward or back, never strand data.
#
#   relocate  happy path end-to-end.
#   fault     kill BETWEEN copy and the registry flip → assert db_host still points at
#             the SOURCE (full data, no loss) + nothing decommissioned; then RESUME →
#             re-verify checksum + flip + decommission (roll-forward).
#   abort     after migrating+copy the operator ABORTS → db_host stays on the SOURCE
#             (canonical), status→active, target cleaned up (roll-back).
#   bite      flip db_host to the target BEFORE the data lands (empty target) → the
#             content-checksum MUST catch the short target (the gate has teeth).
#   smoke     relocate + fault + abort + bite.
#
# SCOPE CAVEAT (D-S13-RELOCATE-FREEZE): the drill assumes the reality is QUIESCED while
# in `migrating` (no writes to the source between checksum and flip). The foundation has
# NO write-freeze-on-migrating enforcement yet, so a late write to the source after the
# checksum would be lost on the flip. This drill proves the registry-atomicity +
# loss-free-COPY invariants, NOT the freeze; the freeze is tracked as a deferred gap
# (sibling of D-S13-CLOSURE-DRAIN).
#
# Verdict: NOTRUN(2) setup; FAIL(1) loss/orphan/vacuous-bite; PASS(0) clean.
# Requires scale-rig.sh up with >=2 shards. Re-runnable (drops + recreates its DBs).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
META_C="scale-meta-pg"; META_DB="l1_relocate"; META_HP="127.0.0.1:55510"
DSN="postgres://${PG_USER}:${PG_PASS}@${META_HP}/${META_DB}?sslmode=disable"
SRC_C="scale-pg-shard-0"; SRC_DB="lw_reloc_src"; SRC_HOST="pg-shard-0.internal"
DST_C="scale-pg-shard-1"; DST_DB="lw_reloc_dst"; DST_HOST="pg-shard-1.internal"
SEED_EVENTS="${SEED_EVENTS:-200}"
R=""          # reality_id, set by setup
SRC_COUNT=0   # source event count captured at setup

log()    { printf '[l1-relocate] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
psqlA()  { docker exec -i "$1" psql -tA -U "$PG_USER" -d "$2" -c "$3"; }

bin() { local c; for c in "$@"; do [ -x "$c" ] && { echo "$c"; return 0; }; done; return 1; }
ensure_bin() {
  RB="$(bin services/meta-worker/reloc.exe services/meta-worker/reloc)" && return 0
  log "building relocate-drill ..."
  go -C services/meta-worker build -o reloc.exe ./cmd/relocate-drill || notrun "build failed"
  RB="services/meta-worker/reloc.exe"
}

require() {
  local c
  for c in "$META_C" "$SRC_C" "$DST_C"; do
    docker inspect -f '{{.State.Running}}' "$c" 2>/dev/null | grep -q true || notrun "$c not running (scale-rig.sh up, >=2 shards)"
  done
}

# event content checksum (count + digest over event_id||aggregate_version||payload,
# ordered) — id ALONE would miss a payload/version corruption. 2>/dev/null so a
# missing events table (empty target in the bite) yields an empty string (clean
# mismatch), not a script error. SCOPE: events only (the per-reality SSOT) — per the
# Inc-4 spec; events_outbox is derived/regenerable and not part of the relocation
# correctness contract, so it is intentionally NOT in the digest.
checksum() { # container db
  psqlA "$1" "$2" "SELECT count(*)||':'||COALESCE(md5(string_agg(event_id::text||'|'||aggregate_version::text||'|'||payload::text, ',' ORDER BY event_id::text)),'empty') FROM events" 2>/dev/null || true
}

migrate_meta() {
  psqlA "$META_C" foundation "DROP DATABASE IF EXISTS ${META_DB} WITH (FORCE)" >/dev/null
  psqlA "$META_C" foundation "CREATE DATABASE ${META_DB}" >/dev/null
  local m
  for m in 001_reality_registry 004_lifecycle_transition_audit 013_meta_write_audit 027_meta_write_audit_scrub_version; do
    docker exec -i "$META_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$META_DB" < "migrations/meta/${m}.up.sql" \
      || notrun "meta migration ${m} failed"
  done
}

migrate_events_db() { # container db
  psqlA "$1" foundation "DROP DATABASE IF EXISTS $2 WITH (FORCE)" >/dev/null
  psqlA "$1" foundation "CREATE DATABASE $2" >/dev/null
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table; do
    docker exec -i "$1" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$2" < "contracts/migrations/per_reality/${m}.up.sql" \
      || notrun "per_reality migration ${m} failed on $2"
  done
  psqlA "$1" "$2" "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null
}

seed_source() {
  psqlA "$SRC_C" "$SRC_DB" "INSERT INTO events
     (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version,
      event_type, event_version, payload, occurred_at, recorded_at)
     SELECT gen_random_uuid(), '${R}'::uuid, 'world', 'agg-'||g, g,
            'world.created', 1, jsonb_build_object('n', g), now(), now()
       FROM generate_series(1, ${SEED_EVENTS}) g" >/dev/null
  SRC_COUNT="$(psqlA "$SRC_C" "$SRC_DB" "SELECT count(*) FROM events" | tr -d '[:space:]')"
  [ "${SRC_COUNT:-0}" -eq "$SEED_EVENTS" ] || notrun "seed produced ${SRC_COUNT} events (want ${SEED_EVENTS})"
}

setup() {
  ensure_bin; require; migrate_meta
  migrate_events_db "$SRC_C" "$SRC_DB"
  R="$(psqlA "$META_C" "$META_DB" "SELECT gen_random_uuid()" | tr -d '[:space:]')"
  psqlA "$META_C" "$META_DB" "INSERT INTO reality_registry
     (reality_id,db_host,db_name,status,locale,session_max_pcs,session_max_npcs,session_max_total,deploy_cohort)
     VALUES ('${R}','${SRC_HOST}','${SRC_DB}','active','en',10,10,20,5)" >/dev/null
  seed_source
  log "setup: reality ${R} on ${SRC_HOST}/${SRC_DB} with ${SRC_COUNT} events"
}

# Real cross-host copy: a FULL dump (schema + data, incl. partitions) of the source
# on shard-0 → a host temp file → restore into a FRESH empty target DB on shard-1
# (the multishard-dr proven pattern; avoids partition data-only routing pitfalls).
copy_to_target() {
  psqlA "$DST_C" foundation "DROP DATABASE IF EXISTS ${DST_DB} WITH (FORCE)" >/dev/null
  psqlA "$DST_C" foundation "CREATE DATABASE ${DST_DB}" >/dev/null
  local dump; dump="$(mktemp)"
  docker exec "$SRC_C" pg_dump -U "$PG_USER" "$SRC_DB" > "$dump" || notrun "pg_dump source failed"
  docker exec -i "$DST_C" psql -q -U "$PG_USER" -d "$DST_DB" < "$dump" >/dev/null 2>&1 \
    || notrun "restore into target failed"
  rm -f "$dump"
}

to_migrating()  { "$RB" -meta-dsn "$DSN" -reality "$R" -mode to-migrating; }
to_active()     { "$RB" -meta-dsn "$DSN" -reality "$R" -mode to-active -db-host "$DST_HOST" -db-name "$DST_DB"; }
# Abort/roll-back: migrating→active staying on the SOURCE (db_host unchanged).
to_active_src() { "$RB" -meta-dsn "$DSN" -reality "$R" -mode to-active -db-host "$SRC_HOST" -db-name "$SRC_DB"; }
reg_host()     { psqlA "$META_C" "$META_DB" "SELECT db_host FROM reality_registry WHERE reality_id='${R}'" | tr -d '[:space:]'; }
reg_status()   { psqlA "$META_C" "$META_DB" "SELECT status  FROM reality_registry WHERE reality_id='${R}'" | tr -d '[:space:]'; }
src_db_exists(){ psqlA "$SRC_C" foundation "SELECT 1 FROM pg_database WHERE datname='${SRC_DB}'" | tr -d '[:space:]'; }
dst_count()    { psqlA "$DST_C" "$DST_DB" "SELECT count(*) FROM events" 2>/dev/null | tr -d '[:space:]'; }

cmd_relocate() {
  setup
  log "active → migrating (CAS) ..."; to_migrating
  log "copy events ${SRC_HOST} → ${DST_HOST} ..."; copy_to_target
  log "content-checksum gate (source == target) ..."
  local s d; s="$(checksum "$SRC_C" "$SRC_DB")"; d="$(checksum "$DST_C" "$DST_DB")"
  [ -n "$s" ] && [ "$s" = "$d" ] || fail "checksum mismatch BEFORE flip — copy lost/changed data (src=${s} dst=${d})"
  log "  checksum match: ${s}"
  log "migrating → active carrying db_host=${DST_HOST} (CAS, same UPDATE) ..."; to_active
  log "decommission source ${SRC_HOST}/${SRC_DB} ..."
  psqlA "$SRC_C" foundation "DROP DATABASE IF EXISTS ${SRC_DB} WITH (FORCE)" >/dev/null

  local host status dc src_left
  host="$(reg_host)"; status="$(reg_status)"; dc="$(dst_count)"; src_left="$(src_db_exists)"
  printf '{"phase":"relocate","db_host":%q,"status":%q,"target_events":%s,"source_db_left":%q}\n' \
    "$host" "$status" "${dc:-0}" "${src_left:-}"
  [ "$host" = "$DST_HOST" ] || fail "db_host did not flip to target (got ${host})"
  [ "$status" = "active" ] || fail "status not active after relocation (got ${status})"
  [ "${dc:-0}" -eq "$SRC_COUNT" ] || fail "target has ${dc} events, expected ${SRC_COUNT} — data loss"
  [ -z "$src_left" ] || fail "source DB still exists after decommission — orphan left readable"
  log "PASS(relocate): db_host flipped via CAS, ${dc} events complete at target, source decommissioned (no orphan)"
}

cmd_fault() {
  setup
  log "active → migrating (CAS) ..."; to_migrating
  log "copy events + checksum ..."; copy_to_target
  local s d; s="$(checksum "$SRC_C" "$SRC_DB")"; d="$(checksum "$DST_C" "$DST_DB")"
  [ "$s" = "$d" ] || fail "checksum mismatch after copy (src=${s} dst=${d})"

  # KILL POINT: crash BEFORE the registry flip. db_host must still point at the
  # SOURCE (full data) — never at a target before the flip commits.
  local host status src_ev src_left
  host="$(reg_host)"; status="$(reg_status)"
  src_ev="$(psqlA "$SRC_C" "$SRC_DB" "SELECT count(*) FROM events" | tr -d '[:space:]')"
  src_left="$(src_db_exists)"
  printf '{"phase":"fault-mid","db_host":%q,"status":%q,"source_events":%s,"source_db_left":%q}\n' \
    "$host" "$status" "${src_ev:-0}" "${src_left:-}"
  [ "$host" = "$SRC_HOST" ] || fail "db_host moved to target BEFORE the flip committed — premature flip / loss window (got ${host})"
  [ "${src_ev:-0}" -eq "$SRC_COUNT" ] || fail "source lost events mid-relocation (got ${src_ev})"
  [ -n "$src_left" ] || fail "source decommissioned before the flip — data destroyed mid-relocation"
  log "  mid-fault SAFE: db_host still ${host} (source, full ${src_ev} events); nothing decommissioned"

  # RESUME (roll-forward): a faithful resume RE-VERIFIES the target (it could have
  # drifted/been tampered during the outage) BEFORE flipping — re-run the checksum
  # gate, then flip + decommission.
  log "resume → re-verify checksum gate, then flip + decommission ..."
  s="$(checksum "$SRC_C" "$SRC_DB")"; d="$(checksum "$DST_C" "$DST_DB")"
  [ -n "$s" ] && [ "$s" = "$d" ] || fail "resume checksum mismatch — target drifted during the outage (src=${s} dst=${d})"
  to_active
  psqlA "$SRC_C" foundation "DROP DATABASE IF EXISTS ${SRC_DB} WITH (FORCE)" >/dev/null
  host="$(reg_host)"; src_left="$(src_db_exists)"
  [ "$host" = "$DST_HOST" ] && [ -z "$src_left" ] \
    || fail "resume did not complete (host=${host} src_left=${src_left})"
  log "PASS(fault): mid-relocation kill left db_host at the full source (no loss); resume re-verified + rolled forward cleanly"
}

# cmd_abort — the roll-BACK half of "roll forward or back": after migrating + copy,
# the operator ABORTS. db_host stays on the source (canonical), status returns to
# active, and the half-built target is cleaned up. No data moved.
cmd_abort() {
  setup
  log "active → migrating (CAS) ..."; to_migrating
  log "copy events (then DECIDE TO ABORT) ..."; copy_to_target
  log "ABORT: migrating → active staying on ${SRC_HOST} + drop the target ..."
  to_active_src
  psqlA "$DST_C" foundation "DROP DATABASE IF EXISTS ${DST_DB} WITH (FORCE)" >/dev/null

  local host status src_ev tgt_left
  host="$(reg_host)"; status="$(reg_status)"
  src_ev="$(psqlA "$SRC_C" "$SRC_DB" "SELECT count(*) FROM events" | tr -d '[:space:]')"
  tgt_left="$(psqlA "$DST_C" foundation "SELECT 1 FROM pg_database WHERE datname='${DST_DB}'" | tr -d '[:space:]')"
  printf '{"phase":"abort","db_host":%q,"status":%q,"source_events":%s,"target_db_left":%q}\n' \
    "$host" "$status" "${src_ev:-0}" "${tgt_left:-}"
  [ "$host" = "$SRC_HOST" ] || fail "abort moved db_host off the source (got ${host}) — roll-back not canonical"
  [ "$status" = "active" ]  || fail "abort did not return status to active (got ${status})"
  [ "${src_ev:-0}" -eq "$SRC_COUNT" ] || fail "source lost events during abort (got ${src_ev})"
  [ -z "$tgt_left" ] || fail "aborted target not cleaned up — orphan target DB left behind"
  log "PASS(abort): relocation rolled BACK — db_host stayed on the source, source intact (${src_ev} events), target cleaned up"
}

cmd_bite() {
  setup
  log "active → migrating (CAS) ..."; to_migrating
  # PREMATURE FLIP: create an EMPTY target (no copy, no schema) and flip db_host to it.
  psqlA "$DST_C" foundation "DROP DATABASE IF EXISTS ${DST_DB} WITH (FORCE)" >/dev/null
  psqlA "$DST_C" foundation "CREATE DATABASE ${DST_DB}" >/dev/null
  log "BITE: flipping db_host → ${DST_HOST} with an EMPTY target (no copy) ..."; to_active
  # A reader routing by the new db_host now hits an empty target. The content-checksum
  # MUST catch the short target.
  local s d; s="$(checksum "$SRC_C" "$SRC_DB")"; d="$(checksum "$DST_C" "$DST_DB")"
  printf '{"phase":"bite","source_checksum":%q,"target_checksum":%q}\n' "$s" "$d"
  [ "$s" != "$d" ] \
    && { log "PASS(bite): the content-checksum caught the premature flip — source(${s}) != empty target(${d}); the gate has teeth"; } \
    || fail "checksum matched a premature/empty flip — the relocation verify is VACUOUS"
}

cmd_smoke() {
  ensure_bin; require
  cmd_relocate
  cmd_fault
  cmd_abort
  cmd_bite
  log "PASS(smoke): relocate (atomic flip + complete target + no orphan) · fault (no-loss + roll-forward) · abort (roll-back, source canonical) · bite (checksum has teeth)"
}

main() {
  local sub="${1:-smoke}"; shift || true
  case "$sub" in
    relocate) cmd_relocate ;;
    fault)    cmd_fault ;;
    abort)    cmd_abort ;;
    bite)     cmd_bite ;;
    smoke)    cmd_smoke ;;
    *) echo "usage: $0 {relocate|fault|abort|bite|smoke}" >&2; exit 2 ;;
  esac
}
main "$@"
