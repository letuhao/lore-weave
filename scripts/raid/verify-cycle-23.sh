#!/usr/bin/env bash
# verify-cycle-23 — C23 Derivative schema + API (BE composition). Per
# RAID_WORKFLOW.md §13 (exit 0 = pass). dị bản M0 / COW substrate /
# ARCH-REVIEW GUARD reconciled with C16. Asserts: (1) composition_work gains
# source_work_id (self-ref FK) + chapter-level branch_point; (2) new tables
# divergence_spec + entity_override; (3) the CONDITIONAL project_id GUARD
# (CHECK source_work_id IS NULL OR project_id IS NOT NULL) — NOT a blanket SET
# NOT NULL, so C16's greenfield null-path survives; (4) POST /works/{id}/derive
# provisions a FRESH project_id (G2, never the source's), persists spec+overrides,
# NO chapter clone, rejects a null/absent project_id (4xx); (5) the down SQL drops
# the 2 tables + 2 columns + the constraint cleanly (round-trip). Static greps +
# targeted pytest (routers + derivatives repo + migration round-trip) + py_compile
# + provider-gate.
set -euo pipefail
CYCLE=23
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CS="$REPO_ROOT/services/composition-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-23] FAIL: $1" >&2; audit "verify_cycle_23_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-23] running CI gate"

ROUTER="$CS/app/routers/works.py"
REPO="$CS/app/db/repositories/works.py"
DREPO="$CS/app/db/repositories/derivatives.py"
MODEL="$CS/app/db/models.py"
MIG="$CS/app/db/migrate.py"
DEPS="$CS/app/deps.py"

for f in "$ROUTER" "$REPO" "$DREPO" "$MODEL" "$MIG" "$DEPS"; do
  [ -f "$f" ] || fail "missing source file: $f"
done

# ── 1. migration — columns + tables + CONDITIONAL guard + self-ref FK ──
have "$MIG" "ADD COLUMN IF NOT EXISTS source_work_id UUID" "migration missing source_work_id column"
grep -Fq "REFERENCES composition_work(id) ON DELETE SET NULL" "$MIG" || fail "source_work_id is not a self-ref FK"
have "$MIG" "ADD COLUMN IF NOT EXISTS branch_point INT" "migration missing chapter-level branch_point column"
have "$MIG" "CREATE TABLE IF NOT EXISTS divergence_spec" "migration missing divergence_spec table"
have "$MIG" "CREATE TABLE IF NOT EXISTS entity_override" "migration missing entity_override table"
have "$MIG" "canon_rule  TEXT[]" "divergence_spec missing canon_rule[] (M0 canon-rule overrides)"
have "$MIG" "pov_anchor  UUID" "divergence_spec missing pov_anchor"
have "$MIG" "overridden_fields JSONB" "entity_override missing overridden_fields JSON"
# The CONDITIONAL guard — derivative ⟹ project_id NOT NULL, NOT a blanket SET NOT NULL.
have "$MIG" "chk_derivative_project_required" "migration missing the conditional project_id GUARD constraint"
grep -Fq "CHECK (source_work_id IS NULL OR project_id IS NOT NULL)" "$MIG" \
  || fail "GUARD is not the conditional CHECK (derivative ⟹ project_id NOT NULL)"
# Must NOT blanket-NOT-NULL project_id (would regress C16 greenfield + fail on 163 null rows).
grep -Eq "composition_work[[:space:]]+ALTER COLUMN project_id SET NOT NULL" "$MIG" \
  && fail "migration blanket-SETs project_id NOT NULL — regresses C16 greenfield null-path" || true

# ── 2. down SQL — clean reverse (round-trip) ──
have "$MIG" "C23_DOWN_SQL" "migration missing the C23_DOWN_SQL round-trip constant"
have "$MIG" "DROP TABLE IF EXISTS entity_override" "down SQL does not drop entity_override"
have "$MIG" "DROP TABLE IF EXISTS divergence_spec" "down SQL does not drop divergence_spec"
have "$MIG" "DROP CONSTRAINT IF EXISTS chk_derivative_project_required" "down SQL does not drop the GUARD"
have "$MIG" "DROP COLUMN IF EXISTS branch_point" "down SQL does not drop branch_point"
have "$MIG" "DROP COLUMN IF EXISTS source_work_id" "down SQL does not drop source_work_id"

# ── 3. model — CompositionWork derivative fields + new row models ──
have "$MODEL" "source_work_id: UUID | None" "CompositionWork missing source_work_id"
have "$MODEL" "branch_point: int | None" "CompositionWork missing branch_point"
have "$MODEL" "class DivergenceSpec" "models missing DivergenceSpec"
have "$MODEL" "class EntityOverride" "models missing EntityOverride"

# ── 4. repos — create_derivative + spec/override writers ──
have "$REPO" "async def create_derivative" "works repo missing create_derivative"
grep -Fq "source_work_id" "$REPO" || fail "create_derivative does not persist source_work_id"
have "$DREPO" "async def create_spec" "derivatives repo missing create_spec"
have "$DREPO" "async def create_override" "derivatives repo missing create_override"
have "$DEPS" "get_derivatives_repo" "deps missing the derivatives repo factory"

# ── 5. router — POST /works/{id}/derive: fresh project, GUARD, no clone ──
have "$ROUTER" "/derive" "router missing the derive endpoint path"
have "$ROUTER" "async def derive_work" "router missing derive_work"
# ALWAYS provisions a FRESH project (G2) — create_project, never the source's id.
grep -Fq "knowledge.create_project" "$ROUTER" || fail "derive does not provision a fresh knowledge project"
have "$ROUTER" "create_derivative" "derive does not insert a derivative Work"
# GUARD: a null/absent project (outage) is REJECTED, never degraded to a null Work.
have "$ROUTER" "PROJECT_CREATE_UNAVAILABLE" "derive does not reject when a project can't be provisioned"
grep -Fq "except KnowledgeContractError:" "$ROUTER" || fail "derive does not surface a 4xx contract error"
# Persists spec + overrides.
have "$ROUTER" "create_spec" "derive does not persist the divergence_spec"
have "$ROUTER" "create_override" "derive does not persist entity_override[]"
# COW: NO chapter/scene clone — the derive flow must NOT call a draft/clone write path.
grep -Fq "patch_draft" "$ROUTER" && fail "derive appears to clone chapters (patch_draft present)" || true

# ── 6. py_compile syntax gate (touched files) ──
echo "[verify-cycle-23] py_compile"
python -m py_compile "$ROUTER" "$REPO" "$DREPO" "$MODEL" "$MIG" "$DEPS" \
  || fail "py_compile failed on a touched file"

# ── 7. provider-gate (composition has no AI imports — keep it that way) ──
echo "[verify-cycle-23] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 8. targeted pytest — router derive + works/derivatives repo (unit) ──
echo "[verify-cycle-23] pytest (routers — derive)"
( cd "$CS" && python -m pytest tests/unit/test_routers.py -q 2>&1 | tail -6 ) \
  || fail "composition-service C23 router pytest failed"

# ── 9. migration round-trip + derivative-guard on real PG (gated) ──
if [ -n "${TEST_COMPOSITION_DB_URL:-}" ]; then
  echo "[verify-cycle-23] pytest (migration round-trip + guard — real PG)"
  ( cd "$CS" && python -m pytest tests/integration/db/test_repositories.py -q -k "c23 or works" 2>&1 | tail -6 ) \
    || fail "composition-service C23 integration pytest failed"
else
  echo "[verify-cycle-23] NOTE: TEST_COMPOSITION_DB_URL unset — skipping real-PG round-trip (covered live at VERIFY)"
fi

audit "verify_cycle_23_passed"
echo "[verify-cycle-23] PASS"
exit 0
