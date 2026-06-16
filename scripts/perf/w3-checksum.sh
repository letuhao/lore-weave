#!/usr/bin/env bash
# scripts/perf/w3-checksum.sh
#
# W3.4 — stored content checksum, LIVE (closes D-LEDGER-STORED-CHECKSUM).
#
# events.content_sha256 (migration 0013) is frozen at INSERT as the PG-canonical
# hash of the event's JSONB CONTENT — payload AND metadata — combined via
# jsonb_build_object('p',payload,'m',metadata). Both writers — the dp-kernel
# append AND the Go emit path — set it with the IDENTICAL SQL expression, so PG is
# the single canonicalizer and Go≡Rust agree with no cross-language JSON library.
# The ledger `-check-checksum` re-derives the hash in PG and flags any row whose
# payload OR metadata was mutated after write.
#
#   smoke   emit (rows now carry content_sha256) → -check-checksum PASS, covered>=1.
#           NULL-skip: insert a pre-0013-shaped row (content_sha256 NULL) →
#           -check-checksum STILL passes (NULL rows have no baseline → skipped,
#           aligned rows NOT false-flagged). BITE 1 rot ONE row's payload → diverge
#           EXACTLY one row, CLI FAILS naming stored-checksum-mismatch. Heal, then
#           BITE 2 rot ONLY metadata → still caught (content checksum covers
#           metadata too — a payload-only hash would miss it).
#
# The kernel-side write path + its own tamper bite are covered by the gated Rust
# test crates/dp-kernel/tests/integration_event_store.rs (LOREWEAVE_TEST_PG_URL).
#
# Verdict: NOTRUN(2) setup; FAIL(1) clean check flagged / NULL row flagged / rot
# not caught / vacuous (0 covered); PASS(0). Reuses the S12 scale rig shard-0
# (no pgvector needed).
set -euo pipefail
export MSYS_NO_PATHCONV=1

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"
PG_USER="foundation"; PG_PASS="foundation"
SHARD_C="scale-pg-shard-0"
DB="w3_checksum"
DSN="postgres://${PG_USER}:${PG_PASS}@127.0.0.1:55511/${DB}?sslmode=disable"
SEED="${W3_SEED:-7}"; PROFILE="${W3_PROFILE:-single-reality}"

log()    { printf '[w3-checksum] %s\n' "$*"; }
notrun() { log "NOTRUN(setup): $*"; exit 2; }
fail()   { log "FAIL: $*"; exit 1; }
require() { docker inspect -f '{{.State.Running}}' "$SHARD_C" 2>/dev/null | grep -q true || notrun "$SHARD_C not running"; }
psql_adm() { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d foundation "$@"; }
psql_db()  { docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" "$@"; }
scalar()   { docker exec -i "$SHARD_C" psql -tA -U "$PG_USER" -d "$DB" -c "$1" | tr -d '[:space:]'; }

# Same content-checksum expression the writers + the Go checker use — re-derived
# here to COUNT mismatches precisely (the CLI only returns pass/fail).
CKEXPR="encode(sha256(convert_to(jsonb_build_object('p', payload, 'm', metadata)::text, 'UTF8')), 'hex')"
mismatch_count() { scalar "SELECT count(*) FROM events WHERE content_sha256 IS NOT NULL AND content_sha256 <> ${CKEXPR}"; }

setup() {
  psql_adm -c "DROP DATABASE IF EXISTS ${DB} WITH (FORCE)" >/dev/null
  psql_adm -c "CREATE DATABASE ${DB}" >/dev/null
  local m
  for m in 0001_initial 0002_events_table 0005_events_outbox_table 0013_events_content_sha256; do
    docker exec -i "$SHARD_C" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" \
      < "contracts/migrations/per_reality/${m}.up.sql" || notrun "migration ${m} failed"
  done
  psql_db -c "CREATE TABLE IF NOT EXISTS events_p_default PARTITION OF events DEFAULT" >/dev/null || notrun "default partition"
  log "w3_checksum ready (events + outbox + content_sha256)"
}

build_bin() {
  go -C tests/workload-gen build -o wg.exe ./cmd/workload-gen || notrun "build wg failed"
  WG="tests/workload-gen/wg.exe"
}

main() {
  require; setup; build_bin

  log "emit seed=${SEED} profile=${PROFILE}"
  "$WG" -seed "$SEED" -profile "$PROFILE" -emit -dsn "$DSN" >/dev/null 2>&1 || notrun "emit failed"

  # Every emitted row must carry a checksum (emit.go stamps it) — non-vacuity.
  local total nullc metac
  total="$(scalar "SELECT count(*) FROM events")"
  nullc="$(scalar "SELECT count(*) FROM events WHERE content_sha256 IS NULL")"
  metac="$(scalar "SELECT count(*) FROM events WHERE metadata IS NOT NULL")"
  [ "${total:-0}" -ge 1 ] || notrun "no events emitted"
  [ "${nullc:-0}" -eq 0 ] || fail "emit left ${nullc}/${total} rows with a NULL content_sha256 — the Go write path did not stamp the checksum"
  [ "${metac:-0}" -ge 1 ] || notrun "no emitted row carries metadata — cannot exercise the metadata-tamper bite"
  log "emitted ${total} rows, all carry content_sha256 (${metac} with metadata)"

  # Clean: -check-checksum passes and reports coverage > 0 (not vacuous).
  out="$("$WG" -check-checksum -dsn "$DSN" 2>&1)" || fail "clean -check-checksum flagged a mismatch: ${out}"
  printf '%s' "$out" | grep -q 'stored-checksum clean' || fail "clean -check-checksum did not confirm coverage: ${out}"
  [ "$(mismatch_count)" = "0" ] || fail "clean DB already shows a checksum mismatch"
  log "PASS(clean): ${out##*: }"

  # NULL-skip: insert a pre-0013-shaped row (content_sha256 omitted → NULL).
  # -check-checksum MUST still pass: NULL rows have no baseline (skipped) AND the
  # checksum-bearing rows are not false-flagged.
  psql_db -c "INSERT INTO events
      (event_id, reality_id, aggregate_type, aggregate_id, aggregate_version, event_type, event_version, payload, occurred_at, recorded_at)
      VALUES (gen_random_uuid(), gen_random_uuid(), 'region', 'null-baseline', 1, 'region.created', 1, '{\"x\":1}'::jsonb, now(), now())" >/dev/null \
    || notrun "insert NULL-baseline row failed"
  "$WG" -check-checksum -dsn "$DSN" >/dev/null 2>&1 \
    || fail "a NULL-checksum (pre-0013) row was flagged — NULL rows must be SKIPPED, not failed"
  log "PASS(null-skip): a NULL-checksum row is skipped (coverage boundary), aligned rows not false-flagged"

  # BITE 1 (payload): rot ONE checksum-bearing row's payload, leaving its frozen
  # content_sha256 stale → re-derive must diverge for EXACTLY one row (not the
  # NULL row), and the CLI must FAIL naming stored-checksum-mismatch.
  psql_db -c "UPDATE events SET payload = payload || '{\"rot\":1}'::jsonb
              WHERE ctid = (SELECT ctid FROM events WHERE content_sha256 IS NOT NULL LIMIT 1)" >/dev/null \
    || notrun "bite setup: could not rot a payload"
  [ "$(mismatch_count)" = "1" ] || fail "payload rot should diverge EXACTLY one row, got $(mismatch_count) (NULL row must not count)"
  out="$("$WG" -check-checksum -dsn "$DSN" 2>&1)" && fail "bite VACUOUS: -check-checksum PASSED after rotting a payload"
  case "$out" in
    *stored-checksum-mismatch*) log "PASS(bite-payload): -check-checksum CAUGHT the rotted payload (exactly 1 row) — non-vacuous" ;;
    *) fail "the check failed but did NOT report stored-checksum-mismatch — got: ${out}" ;;
  esac

  # Heal: re-stamp the frozen checksum to match current content for all rows, so
  # the next bite isolates the metadata case. Confirm we return to clean.
  psql_db -c "UPDATE events SET content_sha256 = ${CKEXPR} WHERE content_sha256 IS NOT NULL" >/dev/null \
    || notrun "heal: could not re-stamp checksums"
  [ "$(mismatch_count)" = "0" ] || fail "re-stamp should restore a clean state, got $(mismatch_count)"

  # BITE 2 (metadata): rot ONLY metadata on a row that carries it. content_sha256
  # covers metadata too (review #2), so this MUST be caught — a payload-only
  # checksum would have missed it.
  psql_db -c "UPDATE events SET metadata = coalesce(metadata, '{}'::jsonb) || '{\"rot\":1}'::jsonb
              WHERE ctid = (SELECT ctid FROM events WHERE content_sha256 IS NOT NULL AND metadata IS NOT NULL LIMIT 1)" >/dev/null \
    || notrun "bite setup: could not rot metadata"
  [ "$(mismatch_count)" = "1" ] || fail "metadata rot should diverge EXACTLY one row, got $(mismatch_count)"
  out="$("$WG" -check-checksum -dsn "$DSN" 2>&1)" && fail "bite VACUOUS: -check-checksum PASSED after rotting metadata — metadata is NOT covered"
  case "$out" in
    *stored-checksum-mismatch*) log "PASS(bite-metadata): -check-checksum CAUGHT a metadata-only tamper — content checksum covers metadata, not just payload (non-vacuous)" ;;
    *) fail "the check failed but did NOT report stored-checksum-mismatch — got: ${out}" ;;
  esac
}
main "$@"
