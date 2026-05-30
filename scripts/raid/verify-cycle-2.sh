#!/usr/bin/env bash
# verify-cycle-2.sh — CI gate for RAID cycle 2 (Data model + H0). Exit 0 = PASS.
# Generated from scripts/raid/verify-cycle-template.sh.
#
# Asserts (per docs/raid/cycle_briefs/02_data-model-h0.md acceptance criteria):
#   1. migrate.py exists with run_migrations + run_down_migrations; all 5 tables
#      and the H0 columns are declared; NO hardcoded provider/model names.
#   2. up-migration applies cleanly on the real loreweave_lore_enrichment
#      (all 5 tables present) — via the service's run_migrations.
#   3. H0 lifecycle round-trip + up/down idempotency tests pass against a REAL
#      DB (no mock-only false-green): confidence<1.0 CHECK, lifecycle DAG,
#      promote-only invariant, immutable origin, clean reversible down.
#   4. service unit suite green.
# Single-service, single-DB schema change → NO cross-service live-smoke token.
set -uo pipefail
CYCLE=2
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
SVC="$REPO_ROOT/services/lore-enrichment-service"
MIGRATE="$SVC/app/db/migrate.py"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

fail() { echo "[verify-cycle-2] FAIL: $1"; exit 1; }
ok()   { echo "[verify-cycle-2] ok: $1"; }

echo "[verify-cycle-2] running CI gate"

# ── 1. migration module shape + H0 columns + no hardcoded model names ──────────
[ -f "$MIGRATE" ] || fail "missing app/db/migrate.py"
grep -q "async def run_migrations" "$MIGRATE" || fail "run_migrations missing"
grep -q "async def run_down_migrations" "$MIGRATE" || fail "run_down_migrations (down path) missing"
ok "migrate.py defines up + down migrations"

for tbl in enrichment_job enrichment_proposal source_corpus enrichment_template cultural_grounding_ref; do
  grep -q "CREATE TABLE IF NOT EXISTS $tbl" "$MIGRATE" || fail "table $tbl not declared"
done
ok "all 5 tables declared"

# H0 columns on enrichment_proposal must be present.
for col in "origin" "technique" "provenance_json" "confidence" "source_refs_json" \
           "cultural_grounding_ref_id" "review_status" "promoted_entity_id" \
           "promoted_by" "promoted_at"; do
  grep -q "$col" "$MIGRATE" || fail "H0 column $col missing"
done
grep -qE "confidence[^\n]*CHECK[^\n]*< 1\.0|confidence < 1\.0" "$MIGRATE" \
  || fail "H0: confidence < 1.0 CHECK missing"
grep -q "promoted_from_proposal_id" "$MIGRATE" || fail "H0 permanent origin marker missing"
ok "H0 columns + confidence<1.0 CHECK + permanent origin marker present"

# No hardcoded provider/model names in the migration (LOCKED).
if grep -rniE --include="*.py" "text-embedding-bge-m3|bge-m3|nomic-embed|\bqwen|\bgemma|gpt-4|gpt-3\.|text-embedding-3|claude-[0-9]|\bllama" "$MIGRATE"; then
  fail "hardcoded provider/model name in migration"
fi
ok "no hardcoded provider/model names"

# ── 2. + 3. real-DB tests (migration up/down idempotency + H0 lifecycle) ───────
# Resolve a reachable DSN: prefer an explicit TEST_* / LORE_* env; else fall
# back to the compose host port (5555) which infra/docker-compose.yml maps.
DB_URL="${TEST_LORE_ENRICHMENT_DB_URL:-${LORE_ENRICHMENT_DB_URL:-postgresql://loreweave:loreweave_dev@localhost:5555/loreweave_lore_enrichment}}"

cd "$SVC" || fail "service dir missing"
if TEST_LORE_ENRICHMENT_DB_URL="$DB_URL" python -m pytest tests/db -q >/tmp/c2_db.log 2>&1; then
  # Confirm the DB suite actually RAN against a real DB (not all-skipped).
  if grep -qE "[0-9]+ passed" /tmp/c2_db.log && ! grep -qE "^[0-9]+ skipped|, 0 passed" /tmp/c2_db.log; then
    ok "real-DB H0 + up/down tests passed ($(grep -oE '[0-9]+ passed' /tmp/c2_db.log | head -1))"
  else
    cat /tmp/c2_db.log
    fail "DB suite did not exercise a real DB (all skipped → mock-only false-green risk)"
  fi
  # Belt-and-braces: confirm tables truly exist in the live DB the service uses.
  if docker compose -f "$REPO_ROOT/infra/docker-compose.yml" exec -T postgres \
       psql -U loreweave -d loreweave_lore_enrichment -tAc \
       "SELECT count(*) FROM information_schema.tables WHERE table_name IN ('enrichment_job','enrichment_proposal','source_corpus','enrichment_template','cultural_grounding_ref');" \
       2>/tmp/c2_psql.log | grep -q "^5$"; then
    ok "all 5 tables present in live loreweave_lore_enrichment"
  else
    echo "[verify-cycle-2] note: live psql table-count check unavailable (pytest already proved schema on real DB)"
  fi
else
  cat /tmp/c2_db.log
  # If the only reason is an unreachable DB, that is a legitimate infra skip for
  # a dev host without compose; but the gate's purpose is the real-DB proof, so
  # surface it loudly and fail (mock-only is NOT acceptable for H0).
  if grep -qE "no real LORE_ENRICHMENT_DB_URL|DB unreachable" /tmp/c2_db.log; then
    fail "live DB unreachable — H0 gate requires a real DB (start compose Postgres)"
  fi
  fail "real-DB H0 / migration round-trip tests red"
fi

# ── 4. full service unit suite green ───────────────────────────────────────────
if ! python -m pytest -q >/tmp/c2_unit.log 2>&1; then
  cat /tmp/c2_unit.log
  fail "service unit suite red"
fi
ok "service unit suite green ($(grep -oE '[0-9]+ passed' /tmp/c2_unit.log | head -1))"

mkdir -p "$(dirname "$AUDIT_LOG")"
echo "{\"ts\":\"$NOW\",\"event\":\"verify_cycle_pass\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"
echo "[verify-cycle-2] PASS"
exit 0
