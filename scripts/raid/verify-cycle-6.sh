#!/usr/bin/env bash
# verify-cycle-6 — C6 project-detail SHELL (FE, G6 IA backbone) acceptance gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: nested route + project-
# scoped sub-tab shell (no select-box when scoped) + Explore-graph deep-link.
# Static asserts + targeted vitest. vitest is run resiliently (bash-spawned
# vitest can hang in this env — kept to a small list; PowerShell proves it
# separately at VERIFY).
set -euo pipefail
CYCLE=6
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-6] FAIL: $1" >&2; audit "verify_cycle_6_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-6] running CI gate"

APP="$FE/src/App.tsx"
SHELL="$FE/src/pages/ProjectDetailShell.tsx"
OVERVIEW="$FE/src/features/knowledge/components/shell/OverviewSection.tsx"
ENT="$FE/src/features/knowledge/components/EntitiesTab.tsx"
TL="$FE/src/features/knowledge/components/TimelineTab.tsx"
RAW="$FE/src/features/knowledge/components/RawDrawersTab.tsx"
CC="$FE/src/features/knowledge/components/state_cards/CompleteCard.tsx"

# ── 1. nested route registered in App.tsx ──
have "$APP" "/knowledge/projects/:projectId/:section" "App.tsx missing nested project-detail route"
have "$APP" "ProjectDetailShell" "App.tsx missing ProjectDetailShell element"

# ── 2. shell reads projectId + section from the ROUTE (useParams), not state ──
[ -f "$SHELL" ] || fail "ProjectDetailShell.tsx not found"
have "$SHELL" "useParams" "ProjectDetailShell does not read route params"
grep -Eq 'projectId.*section|section.*projectId' "$SHELL" || fail "ProjectDetailShell missing projectId+section from route"
# Sub-tabs are route-driven <Link>s (not a conditional-unmount ternary).
have "$SHELL" "/knowledge/projects/" "ProjectDetailShell sub-tabs not route-driven Links"

# ── 3. scoped sub-tabs accept the route projectId AND hide their <select> ──
for f in "$ENT" "$TL" "$RAW"; do
  have "$f" "scopedProjectId" "$(basename "$f") missing scopedProjectId scope prop"
  # the project <select> must be conditionally hidden when scoped
  grep -Eq '!scoped|scopedProjectId \?' "$f" || fail "$(basename "$f") does not hide its project <select> when scoped"
done
have "$SHELL" "scopedProjectId={projectId}" "shell does not thread route projectId into scoped tabs"

# ── 4. Explore-graph CTA deep-links into the shell ──
have "$CC" "onExploreGraph" "CompleteCard missing Explore-graph CTA"
have "$CC" "exploreGraph" "CompleteCard missing exploreGraph action label"
grep -Fq "/knowledge/projects/" "$SHELL" || fail "shell Explore-graph does not deep-link into the shell"
grep -Eq 'navigate\(`/knowledge/projects/\$\{projectId\}/(entities|graph)`\)' "$SHELL" || fail "Explore-graph does not navigate into entities/graph sub-section"

# ── 5. cross-project surface stays secondary (KnowledgePage flat tabs untouched as default) ──
have "$FE/src/pages/KnowledgePage.tsx" "/knowledge/projects" "KnowledgePage default landing drifted"

# ── 6. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-6] vitest (shell + scoped tabs)"
npx vitest run \
  src/pages/__tests__/ProjectDetailShell.test.tsx \
  src/features/knowledge/components/__tests__/EntitiesTab.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

audit "verify_cycle_6_passed"
echo "[verify-cycle-6] PASS"
exit 0
