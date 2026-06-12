#!/usr/bin/env bash
# scripts/conformance/meta-invariants-smoke.sh
#
# S4 meta-DB runtime invariants (bundled — output names the failing invariant):
#
#   I5  reality_registry CHECK — a row with an invalid db_host is rejected by the
#       `reality_registry_db_host_format` CHECK; a well-formed row is accepted.
#   I8  meta append-only — meta_write_audit's REVOKE UPDATE/DELETE is enforced for
#       app_service_role. NON-VACUOUS: the role is GRANTed INSERT/UPDATE/DELETE
#       first, UPDATE is proven to SUCCEED, THEN the migration's REVOKE is applied
#       and UPDATE/DELETE are proven DENIED while INSERT still succeeds. The
#       allowed→denied transition is what proves the REVOKE (not a missing grant)
#       is the cause — the trap a bare-role probe would fall into (only REVOKEs,
#       never GRANTs, exist in migrations/meta).
#   I9  lifecycle CAS — added in increment 4 (the metaprobe binary).
#
# Verdict: 0 pass · 1 a real invariant violation · 2 could-not-provision (notrun).
# Self-contained + re-runnable (throwaway meta DB). --self-test adds extra
# negatives (a second I5 CHECK + app_admin_role also denied).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

PG_CONTAINER="${FOUNDATION_PG_CONTAINER:-foundation-dev-postgres}"
PG_USER="${FOUNDATION_PG_USER:-foundation}"
DB="meta_invariants_check"
AUDIT_MIGRATION="migrations/meta/013_meta_write_audit.up.sql"

SELF_TEST=0
while [ $# -gt 0 ]; do
  case "$1" in
    --self-test) SELF_TEST=1; shift;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

log()  { printf '[meta-inv] %s\n' "$*"; }
fail() { printf '[meta-inv] FAIL[%s]: %s\n' "$1" "$2" >&2; exit 1; }

command -v docker >/dev/null 2>&1 || { log "docker not available — notrun"; exit 2; }
docker exec "$PG_CONTAINER" pg_isready -U "$PG_USER" >/dev/null 2>&1 || { log "postgres not ready — notrun"; exit 2; }

psql_root() { docker exec -i "$PG_CONTAINER" psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$1" -c "$2"; }
# runs as a (NOLOGIN) role via SET ROLE inside a superuser session; returns the
# psql exit code so the caller can assert allowed/denied.
as_role() { docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" -c "SET ROLE $1; $2" >/dev/null 2>&1; }

# --- setup: throwaway meta DB + all meta migrations + app roles -----------------
log "(re)creating $DB ..."
psql_root foundation "DROP DATABASE IF EXISTS ${DB}" >/dev/null
psql_root foundation "CREATE DATABASE ${DB}" >/dev/null
log "applying meta migrations ..."
for f in migrations/meta/*.up.sql; do
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$f" >/dev/null 2>&1 \
    || { log "meta migration $f failed to apply — notrun (setup error)"; exit 2; }
done
# App roles the platform provisioner would create (NOT in migrations — migrations
# only REVOKE). NOLOGIN is fine: SET ROLE works inside a superuser session.
psql_root "$DB" "DROP ROLE IF EXISTS app_service_role; DROP ROLE IF EXISTS app_admin_role; CREATE ROLE app_service_role NOLOGIN; CREATE ROLE app_admin_role NOLOGIN;" >/dev/null

# ── I5: reality_registry CHECK ──────────────────────────────────────────────────
VALID_RR="INSERT INTO reality_registry (reality_id, db_host, db_name, status, locale, session_max_pcs, session_max_npcs, session_max_total, deploy_cohort) VALUES (gen_random_uuid(), 'pg-shard-1.internal', 'reality_probe', 'active', 'en', 10, 10, 20, 5)"
psql_root "$DB" "$VALID_RR" >/dev/null 2>&1 || fail I5 "a VALID reality_registry row was rejected (CHECK too strict, or schema drift)"
if psql_root "$DB" "INSERT INTO reality_registry (reality_id, db_host, db_name, status, locale, session_max_pcs, session_max_npcs, session_max_total, deploy_cohort) VALUES (gen_random_uuid(), 'garbage', 'reality_bad', 'active', 'en', 10, 10, 20, 5)" >/dev/null 2>&1; then
  fail I5 "a row with an invalid db_host ('garbage') was ACCEPTED — reality_registry_db_host_format not enforced"
fi
log "PASS[I5]: valid row accepted; invalid db_host rejected by CHECK"
if [ "$SELF_TEST" -eq 1 ]; then
  # second CHECK: empty db_name (violates reality_registry_db_name_nonempty)
  if psql_root "$DB" "INSERT INTO reality_registry (reality_id, db_host, db_name, status, locale, session_max_pcs, session_max_npcs, session_max_total, deploy_cohort) VALUES (gen_random_uuid(), 'pg-shard-2.prod', '', 'active', 'en', 10, 10, 20, 5)" >/dev/null 2>&1; then
    fail I5 "self-test: an empty db_name was accepted (db_name_nonempty not enforced)"
  fi
  log "self-test PASS[I5]: empty db_name also rejected"
fi

# ── I8: meta_write_audit append-only (non-vacuous) ──────────────────────────────
AID1="11111111-1111-1111-1111-111111111111"
ROW1="INSERT INTO meta_write_audit (audit_id, table_name, operation, row_pk, actor_type, actor_id, created_at_nanos) VALUES ('$AID1', 't', 'INSERT', '{}'::jsonb, 'system', 'probe', 1600000000000000000)"
# Baseline GRANT (the platform provisioner's job; the migrations never GRANT).
psql_root "$DB" "GRANT INSERT, SELECT, UPDATE, DELETE ON meta_write_audit TO app_service_role" >/dev/null
# Pre-REVOKE: prove the role CAN update — else a later "denied" is vacuous.
as_role app_service_role "$ROW1"                                              || fail I8 "INSERT denied even with the baseline grant (setup broken)"
as_role app_service_role "UPDATE meta_write_audit SET reason='pre' WHERE audit_id='$AID1'" \
  || fail I8 "VACUITY GUARD: UPDATE denied BEFORE the REVOKE — the grant baseline failed, so a post-REVOKE denial would prove nothing"
log "PASS[I8] pre-REVOKE: UPDATE succeeds with the grant (non-vacuity established)"
# Apply the migration's REVOKE (the artifact under test). 013 is idempotent
# (IF NOT EXISTS); re-running it now (role present + granted) executes the REVOKE.
docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$AUDIT_MIGRATION" >/dev/null 2>&1 \
  || fail I8 "re-applying $AUDIT_MIGRATION failed"
# Post-REVOKE: INSERT still works (not revoked); UPDATE + DELETE denied.
as_role app_service_role "INSERT INTO meta_write_audit (audit_id, table_name, operation, row_pk, actor_type, actor_id, created_at_nanos) VALUES (gen_random_uuid(), 't', 'INSERT', '{}'::jsonb, 'system', 'probe', 1600000000000000001)" \
  || fail I8 "INSERT denied after the REVOKE — append-only must keep INSERT, only remove UPDATE/DELETE"
if as_role app_service_role "UPDATE meta_write_audit SET reason='post' WHERE audit_id='$AID1'"; then
  fail I8 "UPDATE ALLOWED after the REVOKE — append-only not enforced"
fi
if as_role app_service_role "DELETE FROM meta_write_audit WHERE audit_id='$AID1'"; then
  fail I8 "DELETE ALLOWED after the REVOKE — append-only not enforced"
fi
log "PASS[I8] post-REVOKE: INSERT still ok; UPDATE + DELETE denied (allowed→denied transition proves the REVOKE is the cause)"
if [ "$SELF_TEST" -eq 1 ]; then
  # app_admin_role is REVOKE'd too (migration revokes both roles).
  psql_root "$DB" "GRANT INSERT, UPDATE ON meta_write_audit TO app_admin_role" >/dev/null
  docker exec -i "$PG_CONTAINER" psql -q -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$DB" < "$AUDIT_MIGRATION" >/dev/null 2>&1
  if as_role app_admin_role "UPDATE meta_write_audit SET reason='admin' WHERE audit_id='$AID1'"; then
    fail I8 "self-test: UPDATE ALLOWED for app_admin_role after REVOKE"
  fi
  log "self-test PASS[I8]: app_admin_role UPDATE also denied"
fi

log "meta-invariants: I5 + I8 PASS"
exit 0
