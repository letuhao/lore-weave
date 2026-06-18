#!/usr/bin/env bash
# verify-cycle-21 — C21 World container FE (prose-less worldbuilding) ▶ M5
# acceptance gate. Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE feature
# (features/world/) + a THIN gateway /v1/worlds passthrough. Static asserts +
# targeted vitest (PowerShell proves vitest separately at VERIFY; bash-spawned
# vitest can hang in this env so the list is small).
set -euo pipefail
CYCLE=21
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
GW="$REPO_ROOT/services/api-gateway-bff"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-21] FAIL: $1" >&2; audit "verify_cycle_21_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-21] running CI gate"

API="$FE/src/features/world/api.ts"
TYPES="$FE/src/features/world/types.ts"
LORE_HOOK="$FE/src/features/world/hooks/useWorldLore.ts"
WORKSPACE="$FE/src/features/world/pages/WorldWorkspacePage.tsx"
LORE_PANEL="$FE/src/features/world/components/WorldLorePanel.tsx"
GRAPH_SEC="$FE/src/features/world/components/WorldGraphSection.tsx"
APP="$FE/src/App.tsx"
GWSETUP="$GW/src/gateway-setup.ts"

# ── 1. features/world/ + worldsApi over the C20 routes ──
[ -f "$API" ] || fail "features/world/api.ts not found"
have "$API" "worldsApi" "world api missing worldsApi"
have "$API" "/v1/worlds" "worldsApi does not call the /v1/worlds routes"
have "$API" "createWorld" "worldsApi missing createWorld"

# ── 2. bible-chapter anchoring: lore creates an entity in the bible book then
#       chapter-links it to the bible chapter (the NOT-NULL anchor) ──
have "$API" "createBibleEntity" "worldsApi missing createBibleEntity (lore step 1)"
have "$API" "linkEntityToBibleChapter" "worldsApi missing linkEntityToBibleChapter (lore step 2)"
have "$API" "chapter-links" "lore does not anchor via the glossary chapter-links endpoint"
have "$TYPES" "bible_chapter_id" "World type missing the bible_chapter_id handle"
have "$LORE_HOOK" "bibleChapterId" "useWorldLore does not thread the bible chapter id"
grep -Eq 'linkEntityToBibleChapter\(' "$LORE_HOOK" || fail "useWorldLore does not chapter-link the authored entity"

# ── 3. no manuscript / book mechanic hidden in the workspace ──
[ -f "$WORKSPACE" ] || fail "WorldWorkspacePage not found"
have "$WORKSPACE" "WorldLorePanel" "workspace missing the lore panel"
have "$WORKSPACE" "WorldGraphSection" "workspace missing the graph section"
# The workspace must NOT surface a manuscript/chapter editor. Match RENDERED
# affordances (component imports / testids / editor routes), not comment prose:
# strip // and /* */ comments before grepping so an explanatory comment that
# says "no manuscript" doesn't trip the gate.
WORKSPACE_CODE="$(sed -E 's#//.*$##; s#/\*.*\*/##' "$WORKSPACE")"
echo "$WORKSPACE_CODE" | grep -Eq 'ChapterEditorPage|<ChapterEditor|data-testid="(manuscript|chapter-list|chapter-editor)"|/chapters/' && fail "workspace leaks a manuscript/chapter editor surface" || true
have "$LORE_PANEL" "extraction-optional-note" "lore panel missing extraction-optional messaging"

# ── 4. read-only graph reuse (C19 ProjectGraphView, no editing) ──
have "$GRAPH_SEC" "ProjectGraphView" "graph section does not reuse the C19 ProjectGraphView"
GRAPH_CODE="$(sed -E 's#//.*$##; s#/\*.*\*/##' "$GRAPH_SEC")"
echo "$GRAPH_CODE" | grep -Eq 'createRelation|updateEntity|onNodeDrag|RelationEditDialog' && fail "graph section adds editing affordances (must stay read-only)" || true

# ── 5. routes registered ──
have "$APP" "/worlds" "App.tsx missing /worlds route"
have "$APP" "WorldWorkspacePage" "App.tsx missing the world workspace route element"

# ── 6. thin gateway /v1/worlds passthrough (gateway invariant enabling) ──
[ -f "$GWSETUP" ] || fail "gateway-setup.ts not found"
have "$GWSETUP" "/v1/worlds" "gateway does not proxy /v1/worlds"
have "$GWSETUP" "worldsProxy" "gateway missing the worlds passthrough"

# ── 7. no new BE world model/schema/migration in this FE cycle ──
if git -C "$REPO_ROOT" diff --name-only HEAD 2>/dev/null | grep -E 'services/book-service/.*(migrat|schema|worlds\.go)' ; then
  fail "C21 must not touch book-service world model/schema (C20 owns BE; Step A was its own commit)"
fi

# ── 8. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-21] vitest (world lore + workspace)"
npx vitest run \
  src/features/world/__tests__/worldLore.test.tsx \
  src/features/world/__tests__/WorldWorkspace.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

audit "verify_cycle_21_passed"
echo "[verify-cycle-21] PASS"
exit 0
