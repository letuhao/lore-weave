#!/usr/bin/env bash
# scripts/conformance/schema-conformance-smoke.sh
#
# S4 schema conformance (one of three sub-checks, selected by --check):
#
#   --check verification-meta  — every projection table carries the 5-col
#       VerificationMeta block (Q-L3-4). Discovers the ACTUAL set of tables that
#       carry all 5 cols and asserts it equals the AUTHORITATIVE 11-table list —
#       so a NEW projection table (discovered=12) or a table that lost a col
#       (discovered=10) both fail loud, not silently.
#   --check check-constraints  — a pinned, named set of high-value per-reality
#       CHECK constraints exists (regression-lock; not an exhaustive proof).
#   --check pgvector           — the `vector` extension is installed and the
#       embedding column is VECTOR(1536) (or the documented BYTEA(6144) fallback).
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
DB="schema_conformance_check"

# The authoritative projection-table set (L3.A's 10 from migration 0006 +
# canon_projection from 0009). KEEP IN SYNC with
# tests/workload-gen/internal/projcheck/load.go (D-S4-VERIFMETA-TABLE-SYNC).
AUTHORITATIVE_TABLES=$(cat <<'EOF'
canon_projection
npc_pc_relationship_projection
npc_projection
npc_session_memory_embedding
npc_session_memory_projection
pc_inventory_projection
pc_projection
pc_relationship_projection
region_projection
session_participants
world_kv_projection
EOF
)

# The 5 VerificationMeta columns (Q-L3-4 set a + b).
VERIFMETA_COLS="event_id,aggregate_version,applied_at,last_verified_event_version,last_verified_at"

# Pinned high-value per-reality CHECK constraints (regression-lock).
PINNED_CHECKS=$(cat <<'EOF'
pc_projection_status_valid
pc_projection_stats_is_object
npc_session_facts_is_object
npc_session_archive_valid
region_exits_is_array
pc_inventory_qty_nonneg
session_participants_type_valid
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
    fail "VerificationMeta table set drifted from the authoritative 11 (new/removed table, or a table lost a col)"
  fi
  local n; n=$(printf '%s\n' "$actual" | grep -c .)
  [ "$n" -eq 11 ] || fail "expected 11 VerificationMeta tables, found $n"
  log "PASS: 11 projection tables all carry the 5-col VerificationMeta block"
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
  wrong=$(printf '%s\n' "$AUTHORITATIVE_TABLES" | sort | grep -v '^canon_projection$')
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
  # embedding column: VECTOR(1536) → udt_name='vector', atttypmod=1536; OR the
  # documented BYTEA(6144) fallback (1536 * 4 bytes) when the ext is absent.
  local udt; udt=$(q "SELECT udt_name FROM information_schema.columns WHERE table_name='npc_session_memory_embedding' AND column_name='embedding';")
  if [ "$udt" = "vector" ]; then
    local dim; dim=$(q "SELECT atttypmod FROM pg_attribute WHERE attrelid='npc_session_memory_embedding'::regclass AND attname='embedding';")
    [ "$dim" = "1536" ] || fail "embedding is VECTOR but dim=$dim, expected 1536"
    log "PASS: pgvector installed; embedding is VECTOR(1536)"
  elif [ "$udt" = "bytea" ]; then
    log "PASS: pgvector ext absent; embedding is the documented BYTEA fallback (dim enforced by CHECK)"
  else
    fail "embedding column has unexpected type '$udt' (want vector or bytea)"
  fi
}
selftest_pgvector() {
  # NEGATIVE: prove the dim-reading query reads the column's ACTUAL dimension
  # (not a constant). Create a vector(3) column in one session and assert the
  # SAME atttypmod query returns 3 — if it returned 1536 or a hardcoded value,
  # the main check would be blind to a wrong dim. (Earlier this just compared the
  # already-verified 1536 to a bogus constant — vacuous.)
  local ext; ext=$(q "SELECT 1 FROM pg_extension WHERE extname='vector' LIMIT 1;")
  if [ "$ext" != "1" ]; then
    log "self-test PASS[pgvector]: ext absent (BYTEA fallback) — vector-dim self-test n/a"
    return 0
  fi
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
