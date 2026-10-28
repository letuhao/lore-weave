#!/usr/bin/env bash
# scripts/conformance/schema-conformance-smoke.sh
#
# S4 schema conformance (one of three sub-checks, selected by --check):
#
#   --check verification-meta  — current projections carry the 5-col
#       VerificationMeta block (Q-L3-4). The post-0017/0018 authoritative set
#       is canon_projection; added tables and missing columns both fail.
#   --check check-constraints  — a pinned, named set of high-value per-reality
#       CHECK constraints exists (regression-lock; not an exhaustive proof).
#   --check pgvector           — the vector extension works and the embedding
#       table retired by migration 0017 has not been resurrected.
#
# With --self-test, each check also runs its NEGATIVE polarity (a deliberately
# wrong expectation that the check MUST detect) so the oracle-bite is a standing,
# reproducible proof — not a one-time demo (S2/C3 corruption-injection discipline).
#
# Verdict: exit 0 = pass · exit 1 = a real conformance violation · exit 2 = could
# not provision here (no docker / PG) → the runner maps it to notrun.
#
# Live test: needs the foundation-dev Postgres container. Self-contained +
# re-runnable (drops + recreates a throwaway DB). Mirrors ledger-verify-smoke.sh.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PG_CONTAINER="${FOUNDATION_PG_CONTAINER:-foundation-dev-postgres}"
PG_USER="${FOUNDATION_PG_USER:-foundation}"
# db-safety-gate: file-ok — every database this script DROPs is named by a
# NON-OVERRIDABLE LITERAL (schema_conformance_check and the per-shard names derived from it), so no
# environment variable can retarget it at a real database. That is a stronger
# guarantee than a runtime marker check on an overridable name, which is what the
# gate would otherwise ask for. Brought into scope 2026-07-29 when the gate's
# shell-file selector was widened from "test" to test|smoke|drill.
DB="schema_conformance_check"

# Migrations 0017/0018 retired the producer-less projections; the rebuilder's
# all_projections() and the live projection discovery must agree on this set.
AUTHORITATIVE_TABLES=$(cat <<'EOF'
canon_projection
EOF
)
# 0017 (2026-08-08) dropped the seven pc_*/npc_* projections and 0018 dropped
# region_projection / session_participants / world_kv_projection: measured, none
# had a producer ("canon is the only projection with a producer" — world-service
# rebuild::all_projections, whose own test pins len==1). The authoritative
# VerificationMeta set is therefore canon_projection ALONE; listing a dropped
# table here kept this check red on every nightly since 2026-08-08.

# The 5 VerificationMeta columns (Q-L3-4 set a + b).
VERIFMETA_COLS="event_id,aggregate_version,applied_at,last_verified_event_version,last_verified_at"

# Pinned high-value per-reality CHECK constraints (regression-lock).
# Post-0017/0018 set: the old pins (pc_projection_status_valid,
# session_participants_type_valid, …) named constraints on tables those
# migrations dropped. The current pins cover the append-only spine (events,
# event_audit) and the rebuild-state enum that survived the retirement.
PINNED_CHECKS=$(cat <<'EOF'
events_payload_is_object
events_metadata_is_object_or_null
events_aggregate_version_pos
events_event_version_pos
event_audit_actor_type_enum
event_audit_flag_reason_required_when_flagged
projection_meta_rebuild_state_enum
EOF
)

CHECK=""
SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --check) CHECK="$2"; shift 2;;
    --self-test) SELF_TEST=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done
[ -n "$CHECK" ] || { echo "usage: $0 --check <verification-meta|check-constraints|pgvector> [--self-test]" >&2; exit 2; }

log() { printf '[schema-conf] %s\n' "$*"; }
fail() { printf '[schema-conf] FAIL: %s\n' "$*" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || { log "docker not available — notrun"; exit 2; }
docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || { log "postgres container not ready — notrun"; exit 2; }

psql_db() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" "${@:2}"; }
q() { docker exec -i "$PG_CONTAINER" psql -tA -U "$PG_USER" -d "$DB" -c "$1"; }

# --- setup: throwaway DB + per-reality migrations -------------------------------
log "(re)creating $DB ..."
psql_db foundation -c "DROP DATABASE IF EXISTS ${DB}" >/dev/null
psql_db foundation -c "CREATE DATABASE ${DB}" >/dev/null
log "applying per-reality migrations ..."
for f in contracts/migrations/per_reality/*.up.sql; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$f" >/dev/null 2>&1 \
    || { log "migration $f failed to apply — notrun (schema setup error)"; exit 2; }
done

# ── check: verification-meta ────────────────────────────────────────────────────
check_verification_meta() {
  # ACTUAL = tables carrying ALL 5 VerificationMeta cols.
  local actual
  actual=$(q "
    SELECT table_name FROM information_schema.columns
    WHERE table_schema='public'
      AND column_name IN ('event_id','aggregate_version','applied_at','last_verified_event_version','last_verified_at')
    GROUP BY table_name HAVING count(DISTINCT column_name)=5
    ORDER BY table_name;")
  local expected
  expected=$(printf '%s\n' "$AUTHORITATIVE_TABLES" | sort)
  if [ "$actual" != "$expected" ]; then
    printf '%s\n' "--- expected (authoritative) ---" "$expected" "--- actual (discovered) ---" "$actual" >&2
    fail "VerificationMeta table set drifted from the authoritative list (new/removed table, or a table lost a col)"
  fi
  local expected_n
  expected_n=$(printf '%s\n' "$AUTHORITATIVE_TABLES" | grep -c .)
  local n; n=$(printf '%s\n' "$actual" | grep -c .)
  [ "$n" -eq "$expected_n" ] || fail "expected $expected_n VerificationMeta tables, found $n"
  log "PASS: $n projection table(s) all carry the 5-col VerificationMeta block"
}
selftest_verification_meta() {
  # NEGATIVE: compare the discovered set against a WRONG expected (one table
  # dropped). The comparison MUST detect the difference, else it's vacuous.
  local actual wrong
  actual=$(q "
    SELECT table_name FROM information_schema.columns
    WHERE table_schema='public'
      AND column_name IN ('event_id','aggregate_version','applied_at','last_verified_event_version','last_verified_at')
    GROUP BY table_name HAVING count(DISTINCT column_name)=5
    ORDER BY table_name;")
  # "Drop" the single authoritative table → an EMPTY wrong-set. grep -v with
  # no surviving lines exits 1, and `set -o pipefail` turns that into a silent
  # abort of the whole self-test (it was written against the 11-table list,
  # where the grep always had survivors) — hence the || true: an empty wrong is
  # the CORRECT dropped state for a one-table list, and the comparison below
  # still detects it.
  wrong=$(printf '%s\n' "$AUTHORITATIVE_TABLES" | sort | grep -v '^canon_projection$' || true)
  [ "$actual" != "$wrong" ] || fail "self-test: comparison did NOT detect a dropped table (vacuous)"
  # And the events table (no VerificationMeta) must NOT be discovered.
  printf '%s\n' "$actual" | grep -qx 'events' && fail "self-test: discovery over-matched the events table"
  log "self-test PASS: drift + over-match both detected"
}

# ── check: check-constraints ────────────────────────────────────────────────────
check_constraints() {
  local missing=0 c
  while IFS= read -r c; do
    [ -n "$c" ] || continue
    local got; got=$(q "SELECT 1 FROM information_schema.table_constraints WHERE constraint_type='CHECK' AND constraint_name='${c}' LIMIT 1;")
    if [ "$got" != "1" ]; then echo "  missing CHECK: $c" >&2; missing=1; fi
  done <<< "$PINNED_CHECKS"
  [ "$missing" -eq 0 ] || fail "one or more pinned CHECK constraints are absent"
  log "PASS: all pinned per-reality CHECK constraints present"
}
selftest_constraints() {
  # NEGATIVE: a constraint that does not exist MUST report absent.
  local got; got=$(q "SELECT 1 FROM information_schema.table_constraints WHERE constraint_type='CHECK' AND constraint_name='__s4_definitely_not_a_real_constraint__' LIMIT 1;")
  [ -z "$got" ] || fail "self-test: a bogus constraint name was reported present"
  log "self-test PASS: absent constraint correctly not found"
}

# ── check: pgvector ─────────────────────────────────────────────────────────────
check_pgvector() {
  local ext; ext=$(q "SELECT 1 FROM pg_extension WHERE extname='vector' LIMIT 1;")
  [ "$ext" = "1" ] || fail "pgvector extension 'vector' not installed"
  # 0017/0018 dropped the last embedding table (npc_session_memory_embedding —
  # no producer, and game vocabulary in an engine table). The extension stays
  # (0008 still installs it; the embedding worker's return path is recorded
  # debt), and the RETIREMENT is what we regression-lock: the dropped table
  # must be absent. Its reappearance means someone re-created producer-less
  # machinery without re-registering it here.
  local resurrected
  resurrected=$(q "SELECT to_regclass('npc_session_memory_embedding') IS NOT NULL;")
  [ "$resurrected" = "f" ] || fail "npc_session_memory_embedding was dropped by 0017 but is present again — re-register it in this check (with a producer) or drop it back"
  log "PASS: pgvector installed; retired embedding table still absent (0017 holds)"
}
selftest_pgvector() {
  # NEGATIVE: prove the retirement pin can actually FIRE. Create a real table
  # under the dropped name, assert the check's query sees it, drop it. (A check
  # that could never fire would silently re-exempt the retirement.)
  q "CREATE TABLE npc_session_memory_embedding (embedding vector(3));" >/dev/null
  local seen
  seen=$(q "SELECT to_regclass('npc_session_memory_embedding') IS NOT NULL;")
  q "DROP TABLE npc_session_memory_embedding;" >/dev/null
  [ "$seen" = "t" ] || fail "self-test: resurrection probe did not see a table created under the retired name"
  log "self-test PASS[pgvector]: a resurrected retired table IS detected (then cleaned up)"

  # The dim-reading query must read the column's ACTUAL dimension (not a
  # constant): vector(3) probe → atttypmod 3.
  local probe
  probe=$(q "CREATE TEMP TABLE __s4_vec_selftest (e vector(3)); SELECT atttypmod FROM pg_attribute WHERE attrelid='__s4_vec_selftest'::regclass AND attname='e';" | grep -E '^[0-9]+$' | head -1)
  [ "$probe" = "3" ] || fail "self-test: dim query returned '$probe' for a vector(3) column (expected 3) — the dim read is not column-accurate"
  log "self-test PASS[pgvector]: dim query reads the real column dim (vector(3)→3)"
}

# `if … fi` (not `… && selftest || true`): the && || form would swallow a
# non-zero RETURN from a future self-test that doesn't exit via fail(); the if
# form propagates any failure while still being a no-op (exit 0) when SELF_TEST=0.
case "$CHECK" in
  verification-meta) check_verification_meta; if [ "$SELF_TEST" -eq 1 ]; then selftest_verification_meta; fi;;
  check-constraints) check_constraints;       if [ "$SELF_TEST" -eq 1 ]; then selftest_constraints; fi;;
  pgvector)          check_pgvector;          if [ "$SELF_TEST" -eq 1 ]; then selftest_pgvector; fi;;
  *) echo "unknown --check '$CHECK'" >&2; exit 2;;
esac
exit 0
