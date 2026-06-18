#!/usr/bin/env bash
# verify-cycle-25 — C25 Packer override-merge (BE composition). Per
# RAID_WORKFLOW.md §13 (exit 0 = pass). dị bản M0 two-project merge / G2 /
# override-at-retrieve self-syncing / GUARD project-scoping. Asserts: (1) the
# packer merges a derivative's BASE (source project ≤ branch_point) + DELTA
# (derivative project, full) with DELTA precedence; (2) `entity_override[]` is
# APPLIED to inherited base entities before the prompt window, re-read+re-applied
# every pack (no cache — self-syncing); (3) the GUARD asserts derivative
# project-scoping (refuses null/missing base or delta project_id); (4) the base
# never leaks content after branch_point. Static greps + targeted pytest
# (pack + override + engine + grounding) + py_compile + provider-gate.
set -euo pipefail
CYCLE=25
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
CS="$REPO_ROOT/services/composition-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-25] FAIL: $1" >&2; audit "verify_cycle_25_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-25] running CI gate"

PACK="$CS/app/packer/pack.py"
MERGE="$CS/app/packer/merge.py"
ASM="$CS/app/packer/assemble.py"
LENSES="$CS/app/packer/lenses.py"
GROUNDING="$CS/app/routers/grounding.py"
ENGINE="$CS/app/routers/engine.py"
TEST="$CS/tests/unit/test_pack_override.py"

for f in "$PACK" "$MERGE" "$ASM" "$LENSES" "$GROUNDING" "$ENGINE" "$TEST"; do
  [ -f "$f" ] || fail "missing source file: $f"
done

# ── 1. merge module — two-project merge + override apply + normalization ──
have "$MERGE" "def merge_present" "merge missing merge_present (base+delta entity merge)"
have "$MERGE" "def merge_timeline" "merge missing merge_timeline"
have "$MERGE" "def merge_lore" "merge missing merge_lore"
have "$MERGE" "def apply_entity_overrides" "merge missing apply_entity_overrides (override mutation seam)"
# DELTA precedence — delta is consumed first into `seen`, base only fills gaps.
grep -Fq "delta wins" "$MERGE" || fail "merge does not document/implement delta precedence"
# Normalization seam — case/whitespace-folded identity reconciliation.
have "$MERGE" "def _norm_name" "merge missing the normalization helper (base/delta identity seam)"
have "$MERGE" "casefold" "merge does not casefold the identity key (normalization seam)"
have "$MERGE" "OVERRIDE_CANON_FIELD" "merge missing the added canon-rule override scope"

# ── 2. packer — two-project base+delta merge + branch filter + GUARD wiring ──
have "$PACK" "source_project_id" "pack missing the derivative base project (source_project_id)"
have "$PACK" "branch_point" "pack missing the branch_point cutoff"
have "$PACK" "is_derivative" "pack missing the derivative branch"
have "$PACK" "assert_derivative_scoped" "pack does not assert derivative project-scoping (GUARD)"
have "$PACK" "M.merge_present" "pack does not merge base+delta present"
have "$PACK" "M.merge_timeline" "pack does not merge base+delta timeline"
have "$PACK" "M.merge_lore" "pack does not merge base+delta lore"
have "$PACK" "M.apply_entity_overrides" "pack does not apply entity overrides"
# base read capped at the branch cutoff (min of scene + branch).
have "$PACK" "_min_cutoff" "pack does not cap the base read at the branch cutoff"
have "$PACK" "_cap_events" "pack missing the post-branch base-event belt"
# self-syncing: overrides re-read every pack (build_derivative_context, no cache).
have "$PACK" "build_derivative_context" "pack missing the per-pack derivative-context builder"
grep -Fq "no cache" "$PACK" || fail "pack does not document the self-syncing (no-cache) override re-application"

# ── 3. GUARD — assert_derivative_scoped refuses null base OR delta ──
have "$ASM" "def assert_derivative_scoped" "assemble missing the derivative project-scoping GUARD"
grep -Fq "source_project_id is None" "$ASM" || fail "GUARD does not refuse a null base source_project_id"
# extra canon-rule scope renders in the <canon> block.
have "$ASM" "bundle.extra_canon" "assemble does not render the override canon-rule scope"
have "$LENSES" "extra_canon" "LensBundle missing the extra_canon field (override canon scope)"

# ── 4. call-site wiring — all pack call sites thread the derivative context ──
have "$GROUNDING" "build_derivative_context" "grounding router does not build the derivative context"
have "$GROUNDING" "source_project_id=deriv.source_project_id" "grounding router does not thread the base project"
grep -c "build_derivative_context" "$ENGINE" | grep -Eq "^[3-9]|^[1-9][0-9]" \
  || fail "engine router does not thread the derivative context at all 3 pack call sites"

# ── 5. py_compile syntax gate (touched files) ──
echo "[verify-cycle-25] py_compile"
python -m py_compile "$PACK" "$MERGE" "$ASM" "$LENSES" "$GROUNDING" "$ENGINE" \
  || fail "py_compile failed on a touched file"

# ── 6. provider-gate (composition has NO AI imports — keep it) ──
echo "[verify-cycle-25] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 7. targeted pytest — pack + override + engine + grounding ──
echo "[verify-cycle-25] pytest (pack + override-merge + engine + grounding)"
( cd "$CS" && python -m pytest \
    tests/unit/test_pack.py \
    tests/unit/test_pack_override.py \
    tests/unit/test_engine_router.py \
    tests/unit/test_grounding_router.py \
    tests/unit/test_assembly_mode.py \
    -q 2>&1 | tail -6 ) || fail "composition-service C25 pytest failed"

audit "verify_cycle_25_passed"
echo "[verify-cycle-25] PASS"
exit 0
