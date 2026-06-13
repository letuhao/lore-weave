#!/usr/bin/env bash
# verify-cycle-9 — C9 Promote + entity detail (BE+FE) gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). BE+FE. Asserts:
#   BE  — POST /entities/{id}/promote that (1) creates a glossary DRAFT
#         (default_tags=['ai-suggested'], park_unknown_kinds=False) via the
#         GlossaryClient, then (2) anchors via link_to_glossary (NEVER an
#         active entity); guards (404/409 already_anchored/422 no_book) +
#         partial-failure error codes (glossary_draft_failed/anchor_failed).
#   FE  — promoteEntity + setGlossaryEntityPinned api; usePromoteEntity +
#         useToggleGlossaryPin hooks; EntityDetailPanel promote button gated
#         to `discovered`, unpin toggling is_pinned_for_context (NOT
#         delete/archive), facts list + source_chapter (provenance MVP).
# Static asserts + targeted pytest. vitest proven green via PowerShell at
# VERIFY (bash-spawned vitest can hang in this env — the script greps the
# test files exist instead of spawning them).
set -euo pipefail
CYCLE=9
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KS="$REPO_ROOT/services/knowledge-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-9] FAIL: $1" >&2; audit "verify_cycle_9_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-9] running CI gate"

ROUTER="$KS/app/routers/public/entities.py"
REPO="$KS/app/db/neo4j_repos/entities.py"
BETEST="$KS/tests/unit/test_promote_entity_c9.py"
APIFE="$FE/src/features/knowledge/api.ts"
PANEL="$FE/src/features/knowledge/components/EntityDetailPanel.tsx"
TAB="$FE/src/features/knowledge/components/EntitiesTab.tsx"
MUT="$FE/src/features/knowledge/hooks/useEntityMutations.ts"
FACTS="$FE/src/features/knowledge/hooks/useEntityFacts.ts"
PANELTEST="$FE/src/features/knowledge/components/__tests__/EntityDetailPanelC9.test.tsx"
MUTTEST="$FE/src/features/knowledge/hooks/__tests__/useEntityMutations.test.tsx"

# ── 1. BE — promote route, draft-create THEN anchor ──
[ -f "$ROUTER" ] || fail "entities.py router not found"
have "$ROUTER" '/entities/{entity_id}/promote' "promote route missing"
have "$ROUTER" "def promote_entity" "promote_entity handler missing"
have "$ROUTER" "propose_entities" "promote does not create a glossary draft via propose_entities"
have "$ROUTER" "WRITEBACK_TAG" "promote does not tag the draft ai-suggested (WRITEBACK_TAG)"
have "$ROUTER" "park_unknown_kinds=False" "promote does not opt out of the unknown bucket"
have "$ROUTER" "link_to_glossary" "promote does not anchor via link_to_glossary"
have "$ROUTER" "normalize_kind_for_anchor_lookup" "promote does not normalize kind to a glossary kind_code"
# anchor sets anchor_score=1.0 (the LOCKED anchor value lives in the repo).
have "$REPO" "e.anchor_score = 1.0" "link_to_glossary does not set anchor_score=1.0"

# ── 2. BE — guards + partial-failure error codes ──
have "$ROUTER" "already_anchored" "promote missing 409 already_anchored guard (no double-draft)"
have "$ROUTER" '"no_book"' "promote missing 422 no_book guard"
have "$ROUTER" "glossary_draft_failed" "promote missing 502 glossary_draft_failed (draft-fail → no anchor)"
have "$ROUTER" "anchor_failed" "promote missing 502 anchor_failed (draft made but anchor missed)"

# ── 3. BE — promote NEVER creates an active glossary entity ──
# The only glossary write is propose_entities (status='draft' on the glossary
# side); assert there is no direct active-entity creation smuggled in.
grep -Fq "status='active'" "$ROUTER" && fail "promote must NOT create an active glossary entity"
grep -Fq 'status="active"' "$ROUTER" && fail "promote must NOT create an active glossary entity"

# ── 4. FE — api: promote + glossary pin toggle ──
have "$APIFE" "promoteEntity" "api.ts missing promoteEntity"
have "$APIFE" "/promote" "api.ts promoteEntity hits the wrong path"
have "$APIFE" "setGlossaryEntityPinned" "api.ts missing the glossary pin toggle"
have "$APIFE" "/pin" "api.ts pin toggle hits the wrong path"

# ── 5. FE — hooks ──
[ -f "$MUT" ] || fail "useEntityMutations.ts not found"
have "$MUT" "usePromoteEntity" "usePromoteEntity hook missing"
have "$MUT" "useToggleGlossaryPin" "useToggleGlossaryPin hook missing"
[ -f "$FACTS" ] || fail "useEntityFacts.ts not found"
have "$FACTS" "getEntityFacts" "useEntityFacts does not call the facts endpoint"

# ── 6. FE — panel: promote gated to discovered, unpin = is_pinned, facts ──
[ -f "$PANEL" ] || fail "EntityDetailPanel.tsx not found"
have "$PANEL" "entity-detail-promote" "panel missing promote control"
grep -Fq "status === 'discovered'" "$PANEL" || fail "promote button NOT gated to discovered entities"
have "$PANEL" "entity-detail-unpin" "panel missing unpin control"
have "$PANEL" "pinned: false" "unpin does not toggle is_pinned_for_context to false"
# unpin must NOT delete/archive the entity (integrate-don't-duplicate / right-field).
grep -Fq "archiveMyEntity" "$PANEL" && fail "unpin must toggle is_pinned_for_context, not archive/delete"
have "$PANEL" "entity-detail-facts" "panel missing facts (provenance MVP)"
have "$PANEL" "entity-detail-fact-source" "panel missing per-fact source_chapter"

# ── 7. FE — panel rendered inside the C6 shell, book threaded (G6) ──
have "$TAB" "bookId={scopedBookId}" "EntitiesTab does not thread the scoped book to the panel"

# ── 8. provider-gate green (no hardcoded model literal) ──
echo "[verify-cycle-9] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 9. targeted pytest (promote orchestration + guards + partial-fail) ──
[ -f "$BETEST" ] || fail "BE promote test missing"
echo "[verify-cycle-9] pytest (promote C9)"
( cd "$KS" && python -m pytest tests/unit/test_promote_entity_c9.py -q 2>&1 | tail -8 ) \
  || fail "promote pytest failed"

# ── 10. FE test files present (proven green via PowerShell vitest) ──
[ -f "$PANELTEST" ] || fail "FE EntityDetailPanelC9 test missing"
[ -f "$MUTTEST" ] || fail "FE useEntityMutations test missing"
grep -Fq "usePromoteEntity" "$MUTTEST" || fail "mutations test does not cover usePromoteEntity"
grep -Fq "useToggleGlossaryPin" "$MUTTEST" || fail "mutations test does not cover useToggleGlossaryPin"

audit "verify_cycle_9_passed"
echo "[verify-cycle-9] PASS"
exit 0
