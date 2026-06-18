#!/usr/bin/env bash
# verify-cycle-16 — C16 Work-setup resilience (BE composition). Per
# RAID_WORKFLOW.md §13 (exit 0 = pass). WG-3 / writer-not-hard-blocked /
# G2-derivative-distinction. Asserts: (1) POST /work degrades on a knowledge
# OUTAGE (down/5xx) → lazy null-project Work + backfill marker (greenfield only);
# (2) a 4xx CONTRACT error still SURFACES (no silent swallow); (3) a DERIVATIVE
# work stays project_id NOT NULL (C23 guard — null path refused); (4) the packer
# tolerates a null project_id → EMPTY grounding, no knowledge lens called, no NPE;
# (5) the backfill seam stamps the project once knowledge recovers. Static greps +
# targeted pytest (routers + knowledge_client + pack + repo integration) +
# py_compile syntax gate + provider-gate.
set -euo pipefail
CYCLE=16
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CS="$REPO_ROOT/services/composition-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-16] FAIL: $1" >&2; audit "verify_cycle_16_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-16] running CI gate"

ROUTER="$CS/app/routers/works.py"
KC="$CS/app/clients/knowledge_client.py"
REPO="$CS/app/db/repositories/works.py"
MODEL="$CS/app/db/models.py"
MIG="$CS/app/db/migrate.py"
PACK="$CS/app/packer/pack.py"

for f in "$ROUTER" "$KC" "$REPO" "$MODEL" "$MIG" "$PACK"; do
  [ -f "$f" ] || fail "missing source file: $f"
done

# ── 1. knowledge_client — 4xx/5xx discrimination (surface vs degrade) ──
have "$KC" "class KnowledgeContractError" "knowledge_client missing KnowledgeContractError"
grep -Fq "raise KnowledgeContractError" "$KC" || fail "create_project does not RAISE on a 4xx contract error"
grep -Eq "400 <= resp.status_code < 500" "$KC" || fail "create_project missing the 4xx branch"
# 5xx / transport degrade to None (outage) — both the HTTPError and the non-2xx tail.
grep -Fq "outage" "$KC" || fail "create_project missing the outage→None degrade path"

# ── 2. router — resilient POST /work + derivative guard + backfill seam ──
have "$ROUTER" "KnowledgeContractError" "router does not import KnowledgeContractError"
have "$ROUTER" "is_derivative" "router missing the derivative branch flag"
have "$ROUTER" "source_work_id" "router missing the source_work_id derivative hook"
# A 4xx surfaces as PROJECT_CREATE_FAILED (no swallow).
grep -Fq "except KnowledgeContractError:" "$ROUTER" || fail "router does not catch+surface the contract error"
# A derivative outage surfaces (NEVER takes the null path) — C23 guard.
grep -Fq "if is_derivative:" "$ROUTER" || fail "router missing the derivative null-path guard"
# Greenfield outage → lazy null-project Work + backfill seam.
have "$ROUTER" "create_pending" "router does not create a lazy pending Work on outage"
have "$ROUTER" "get_pending_for_book" "router missing the pending re-get (idempotent reuse)"
have "$ROUTER" "backfill_project" "router missing the backfill seam"

# ── 3. repo — create_pending / get_pending_for_book / backfill_project ──
have "$REPO" "async def create_pending" "repo missing create_pending"
have "$REPO" "async def get_pending_for_book" "repo missing get_pending_for_book"
have "$REPO" "async def backfill_project" "repo missing backfill_project"
grep -Fq "VALUES (NULL," "$REPO" || fail "create_pending does not persist a NULL project_id"
grep -Fq "pending_project_backfill = false" "$REPO" || fail "backfill_project does not clear the marker"

# ── 4. model — nullable project_id + surrogate id + marker ──
grep -Fq "project_id: UUID | None = None" "$MODEL" || fail "CompositionWork.project_id not made nullable"
have "$MODEL" "pending_project_backfill: bool" "CompositionWork missing pending_project_backfill"
have "$MODEL" "id: UUID | None" "CompositionWork missing the surrogate id"

# ── 5. migration — additive re-key (id PK, nullable project_id, partial uniques) ──
have "$MIG" "ADD COLUMN IF NOT EXISTS id UUID" "migration missing surrogate id column"
have "$MIG" "ADD COLUMN IF NOT EXISTS pending_project_backfill BOOLEAN NOT NULL" "migration missing backfill marker"
have "$MIG" "ALTER COLUMN project_id DROP NOT NULL" "migration does not make project_id nullable"
grep -Fq "PRIMARY KEY (id)" "$MIG" || fail "migration does not re-point the PK to id"
have "$MIG" "uq_composition_work_project" "migration missing the backed-only 1:1 partial-unique index"
have "$MIG" "uq_composition_work_pending" "migration missing the per-(user,book) pending cap index"

# ── 6. packer — null-project tolerance (empty grounding, NO knowledge lens) ──
have "$PACK" "_pack_null_project" "pack does not branch to the null-project path"
grep -Fq "if req.project_id is None:" "$PACK" || fail "pack does not short-circuit on a null project_id"
# The null path must NOT call any knowledge lens (C23 no-widen) — it builds an
# empty LensBundle and returns grounding_available=False.
grep -Fq "knowledge_seen=False" "$PACK" || fail "null-project pack does not mark grounding unavailable"
grep -Fq "grounding_available=False" "$PACK" || fail "null-project pack does not set grounding_available=False"
# A1 chokepoint still guards the NON-null lens path.
have "$PACK" "assert_project_scoped" "pack dropped the A1 chokepoint for the scoped path"

# ── 7. py_compile syntax gate (touched files) ──
echo "[verify-cycle-16] py_compile"
python -m py_compile "$ROUTER" "$KC" "$REPO" "$MODEL" "$MIG" "$PACK" \
  || fail "py_compile failed on a touched file"

# ── 8. provider-gate (no direct SDK / hardcoded model) ──
echo "[verify-cycle-16] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 9. targeted pytest — routers + knowledge_client + pack ──
echo "[verify-cycle-16] pytest (routers + knowledge_client + pack)"
( cd "$CS" && python -m pytest \
    tests/unit/test_routers.py \
    tests/unit/test_knowledge_client.py \
    tests/unit/test_pack.py \
    -q 2>&1 | tail -6 ) || fail "composition-service C16 pytest failed"

# ── 10. repo integration (real PG) — gated on TEST_COMPOSITION_DB_URL ──
if [ -n "${TEST_COMPOSITION_DB_URL:-}" ]; then
  echo "[verify-cycle-16] pytest (repo integration — real PG)"
  ( cd "$CS" && python -m pytest tests/integration/db/test_repositories.py -q -k works 2>&1 | tail -6 ) \
    || fail "composition-service C16 integration pytest failed"
else
  echo "[verify-cycle-16] NOTE: TEST_COMPOSITION_DB_URL unset — skipping real-PG integration (covered live at VERIFY)"
fi

audit "verify_cycle_16_passed"
echo "[verify-cycle-16] PASS"
exit 0
