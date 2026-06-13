#!/usr/bin/env bash
# verify-cycle-8 — C8 Entities semantic layer (BE+FE) gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). BE+FE. Asserts: derived
# `status` (computed, no new column), `status` filter + sort_by=anchor_score,
# `semantic_query` vector path resolving the embedding via provider-registry
# (no hardcoded model), and the FE ⭐/💭/📦 rows + anchor badge + legend +
# semantic-search box + route-scoped <select> removal (G6). Static asserts +
# targeted pytest + targeted vitest (vitest via the script runs resiliently —
# bash-spawned vitest can hang in this env; PowerShell proves it at VERIFY).
set -euo pipefail
CYCLE=8
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KS="$REPO_ROOT/services/knowledge-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-8] FAIL: $1" >&2; audit "verify_cycle_8_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-8] running CI gate"

REPO="$KS/app/db/neo4j_repos/entities.py"
ROUTER="$KS/app/routers/public/entities.py"
APIFE="$FE/src/features/knowledge/api.ts"
TABLE="$FE/src/features/knowledge/components/EntitiesTable.tsx"
TAB="$FE/src/features/knowledge/components/EntitiesTab.tsx"
LEGEND="$FE/src/features/knowledge/components/EntityStatusLegend.tsx"
STATUSLIB="$FE/src/features/knowledge/lib/entityStatus.ts"

# ── 1. BE — derived status (computed field, NO new DB column) ──
[ -f "$REPO" ] || fail "entities.py repo not found"
have "$REPO" "def status(self)" "Entity.status computed field missing"
have "$REPO" "ENTITY_STATUSES" "ENTITY_STATUSES enum missing"
have "$REPO" "ENTITY_SORT_KEYS" "ENTITY_SORT_KEYS enum missing"
# anti-migration: no new `status` column smuggled into a migration.
if ls "$KS"/migrations/*.sql >/dev/null 2>&1; then
  grep -rEl 'ADD +COLUMN +status' "$KS"/migrations/ 2>/dev/null \
    && fail "a migration adds a status column — status MUST be derived"
fi

# ── 2. BE — status filter + sort_by in the repo query ──
have "$REPO" "sort_by" "list_entities_filtered missing sort_by"
grep -Fq "WHEN 'archived'" "$REPO" || fail "status-filter CASE missing archived arm"
grep -Fq "WHEN 'canonical'" "$REPO" || fail "status-filter CASE missing canonical arm"
grep -Fq "WHEN 'discovered'" "$REPO" || fail "status-filter CASE missing discovered arm"

# ── 3. BE — semantic_query vector path via provider-registry embedding ──
have "$ROUTER" "semantic_query" "router missing semantic_query param"
have "$ROUTER" "find_entities_by_vector" "router missing vector search call"
have "$ROUTER" "embedding_client.embed" "router does not embed via the provider-registry client"
have "$ROUTER" "model_ref=project.embedding_model" "embedding model not resolved from project (provider-registry) — possible hardcode"
have "$ROUTER" "status_codes" "router missing status filter/sort params plumbing"

# ── 4. FE — types + api params ──
have "$APIFE" "EntityStatus" "api.ts missing EntityStatus type"
have "$APIFE" "semantic_query" "api.ts listEntities does not send semantic_query"
have "$APIFE" "sort_by" "api.ts listEntities does not send sort_by"

# ── 5. FE — ⭐/💭/📦 glyphs + anchor badge + legend ──
[ -f "$STATUSLIB" ] || fail "entityStatus.ts lib not found"
have "$STATUSLIB" "⭐" "canonical glyph missing"
have "$STATUSLIB" "💭" "discovered glyph missing"
have "$STATUSLIB" "📦" "archived glyph missing"
have "$TABLE" "StatusGlyph" "EntitiesTable missing status glyph"
have "$TABLE" "AnchorBadge" "EntitiesTable missing anchor badge"
[ -f "$LEGEND" ] || fail "EntityStatusLegend.tsx not found"
have "$TAB" "EntityStatusLegend" "EntitiesTab does not render the legend"
have "$TAB" "entities-filter-status" "EntitiesTab missing status filter"
have "$TAB" "entities-semantic-search" "EntitiesTab missing semantic-search box"

# ── 6. FE — G6: project <select> still hidden when route-scoped ──
grep -Fq "{!scoped &&" "$TAB" || fail "EntitiesTab no longer hides the project <select> when scoped (G6)"

# ── 7. BE — provider-gate green (no hardcoded model literal) ──
echo "[verify-cycle-8] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 8. targeted pytest (derived status + filter + sort + semantic) ──
echo "[verify-cycle-8] pytest (entities semantic C8 + regression)"
( cd "$KS" && python -m pytest \
    tests/unit/test_entities_semantic_c8.py \
    tests/unit/test_entities_browse_api.py \
    -q 2>&1 | tail -8 )

# ── 9. targeted vitest (glyphs + badge + legend + filters + scoping) ──
echo "[verify-cycle-8] vitest (entities semantic C8)"
( cd "$FE" && npx vitest run \
    src/features/knowledge/components/__tests__/EntitiesSemanticC8.test.tsx \
    --reporter=dot --testTimeout=10000 2>&1 | tail -8 )

audit "verify_cycle_8_passed"
echo "[verify-cycle-8] PASS"
exit 0
