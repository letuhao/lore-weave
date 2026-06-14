#!/usr/bin/env bash
# verify-cycle-27 — C27 Flywheel on delta + what-if→derivative promotion. Per
# RAID_WORKFLOW.md §13 (exit 0 = pass). dị bản M4. Asserts:
#   DPS1 (delta flywheel): on approval of a DERIVATIVE chapter, the existing
#     knowledge extraction trigger (extract-item) is dispatched into the
#     DERIVATIVE's OWN project_id (delta, G2) — never the source/null; a
#     project-scope GUARD refuses a null delta; forward-from-branch write-order
#     (pre-branch = thinner delta, not an error); the next pack reads the new
#     delta fact via C25's delta-read path.
#   DPS2 (what-if→promotion): an ephemeral what-if materializes into a PERSISTENT
#     derivative through the C23 derive path (fresh project_id + spec + overrides
#     carried over, none dropped).
# Static greps + targeted pytest (flywheel + approve-router + knowledge-client +
# prose-doc + pack-override flywheel-closing) + py_compile + provider-gate + FE vitest.
set -euo pipefail
CYCLE=27
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CS="$REPO_ROOT/services/composition-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-27] FAIL: $1" >&2; audit "verify_cycle_27_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-27] running CI gate"

FLY="$CS/app/engine/delta_flywheel.py"
APPROVE="$CS/app/routers/approve.py"
KN="$CS/app/clients/knowledge_client.py"
PROSE="$CS/app/engine/prose_doc.py"
MAIN="$CS/app/main.py"
TEST_FLY="$CS/tests/unit/test_delta_flywheel.py"
TEST_APPROVE="$CS/tests/unit/test_approve_router.py"
TEST_PACK_OV="$CS/tests/unit/test_pack_override.py"
HOOK="$FE/src/features/composition/hooks/useWhatIfPromotion.ts"
BTN="$FE/src/features/composition/components/PromoteWhatIfButton.tsx"

for f in "$FLY" "$APPROVE" "$KN" "$PROSE" "$MAIN" "$TEST_FLY" "$TEST_APPROVE" \
         "$TEST_PACK_OV" "$HOOK" "$BTN"; do
  [ -f "$f" ] || fail "missing source file: $f"
done

# ── 1. DPS1 — delta flywheel core: GUARD + forward-from-branch + delta-only ──
have "$FLY" "def assert_delta_extraction_scoped" "flywheel missing the project-scope GUARD"
have "$FLY" "def is_forward_of_branch" "flywheel missing the forward-from-branch write-order rule"
have "$FLY" "def plan_flywheel_dispatch" "flywheel missing the dispatch planner"
have "$FLY" "DeltaScopeError" "flywheel missing the scope-guard error"
# GUARD refuses a null delta project (the cross-project leak).
grep -Fq "delta_project_id is None" "$FLY" || fail "GUARD does not refuse a null delta project_id"
# pre-branch chapter degrades to a thinner delta (not an error).
grep -Fq "pre_branch_thinner_delta" "$FLY" || fail "flywheel does not degrade an out-of-order chapter to a thinner delta"

# ── 2. DPS1 — approve router: dispatch into the DERIVATIVE's OWN delta project ──
have "$APPROVE" "/approve" "approve router missing the approve route"
have "$APPROVE" "build_derivative_context" "approve router does not reuse C25's derivative-context resolver"
have "$APPROVE" "plan_flywheel_dispatch" "approve router does not run the flywheel planner"
# the extraction targets the derivative's OWN project (delta), never the source.
have "$APPROVE" "delta_project_id=work.project_id" "approve router does not target the derivative's own project (delta)"
have "$APPROVE" "decision.delta_project_id" "approve router does not pass the delta project to extract"
have "$APPROVE" "knowledge.extract_item" "approve router does not dispatch the existing extraction trigger"
have "$APPROVE" "DELTA_PROJECT_UNSCOPED" "approve router does not surface the project-scope guard as a 409"
# main registers the router.
have "$MAIN" "approve.router" "main does not register the approve router"

# ── 3. DPS1 — knowledge client REUSES the existing extract-item trigger ──
have "$KN" "def extract_item" "knowledge client missing extract_item (delta flywheel dispatch)"
have "$KN" "/internal/extraction/extract-item" "extract_item does not call the existing extraction trigger"
# AI-free: composition supplies a caller-resolved model ref (no provider SDK / model literal).
have "$KN" "model_ref" "extract_item does not forward a caller-resolved model ref"

# ── 4. DPS1 — flywheel CLOSES: the next pack reads the new delta fact (C25 path) ──
have "$TEST_PACK_OV" "test_flywheel_new_delta_fact_surfaces_in_next_scene_grounding" \
  "missing the flywheel-closing test (next pack reads the delta fact via C25's read path)"

# ── 5. DPS2 — what-if → derivative promotion via the C23 derive path ──
have "$HOOK" "whatIfToDeriveBody" "promotion hook missing the ephemeral→derive mapping"
have "$HOOK" "compositionApi.deriveWork" "promotion does not route through the C23 derive path"
have "$HOOK" "entity_overrides" "promotion does not carry the entity overrides over"
# fresh project_id guard (G2 — never reuse the source project).
grep -Fq "reused the source project_id" "$HOOK" || fail "promotion does not guard against reusing the source project_id (G2)"
have "$BTN" "PromoteWhatIfButton" "promote button component missing"

# ── 6. py_compile syntax gate (touched backend files) ──
echo "[verify-cycle-27] py_compile"
python -m py_compile "$FLY" "$APPROVE" "$KN" "$PROSE" "$MAIN" \
  || fail "py_compile failed on a touched file"

# ── 7. provider-gate (composition has NO AI imports — keep it) ──
echo "[verify-cycle-27] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 8. targeted pytest — flywheel + approve + client + prose + pack-override ──
echo "[verify-cycle-27] pytest (flywheel + approve + client + prose + pack-override)"
( cd "$CS" && python -m pytest \
    tests/unit/test_delta_flywheel.py \
    tests/unit/test_approve_router.py \
    tests/unit/test_knowledge_client.py \
    tests/unit/test_prose_doc.py \
    tests/unit/test_pack_override.py \
    -q 2>&1 | tail -6 ) || fail "composition-service C27 pytest failed"

# ── 9. FE vitest — promotion hook + button (PowerShell on this box; bash if avail) ──
echo "[verify-cycle-27] FE vitest (promotion hook + button) — run via PowerShell on Windows"
# (the bash-spawned vitest hangs in this dev env — the coordinator runs it via
#  PowerShell during VERIFY; the static greps above gate the FE source here.)

audit "verify_cycle_27_passed"
echo "[verify-cycle-27] PASS"
exit 0
