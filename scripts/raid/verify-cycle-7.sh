#!/usr/bin/env bash
# verify-cycle-7 — C7 projects browser = HOME + build polish (FE, M1) gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only. Asserts: real cursor
# pagination (NOT a fake 100-cap), search/sort/filter-by-state narrowing,
# rows route INTO the C6 detail shell, build polish (post-submit visible
# feedback + running-build label), and that the cross-project surface
# stays secondary. Static asserts + targeted vitest (vitest run resiliently
# — bash-spawned vitest can hang in this env; PowerShell proves it at VERIFY).
set -euo pipefail
CYCLE=7
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-7] FAIL: $1" >&2; audit "verify_cycle_7_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-7] running CI gate"

HOOK="$FE/src/features/knowledge/hooks/useProjects.ts"
TAB="$FE/src/features/knowledge/components/ProjectsTab.tsx"
CTRL="$FE/src/features/knowledge/components/ProjectsBrowserControls.tsx"
LIB="$FE/src/features/knowledge/lib/projectBrowser.ts"
ROW="$FE/src/features/knowledge/components/ProjectRow.tsx"
BUILD="$FE/src/features/knowledge/components/BuildGraphDialog.tsx"
RUNCARD="$FE/src/features/knowledge/components/state_cards/BuildingRunningCard.tsx"

# ── 1. REAL cursor pagination — the hook wires the BE cursor + accumulates ──
[ -f "$HOOK" ] || fail "useProjects.ts not found"
have "$HOOK" "useInfiniteQuery" "useProjects no longer uses an accumulating paged query"
have "$HOOK" "getNextPageParam" "useProjects missing cursor next-page wiring"
have "$HOOK" "next_cursor" "useProjects does not read next_cursor from the BE"
have "$HOOK" "fetchNextPage" "useProjects does not expose loadMore/fetchNextPage"
# anti-fake: there must be NO single-page 100-cap return shape anymore.
grep -Eq 'hasMore:\s*!!\s*query\.data\?\.next_cursor' "$HOOK" \
  && fail "useProjects still caps at one page (fake pagination)"

# ── 2. browser controls: search + sort + filter-by-state ──
[ -f "$CTRL" ] || fail "ProjectsBrowserControls.tsx not found"
have "$CTRL" "projects-search" "browser missing search input"
have "$CTRL" "projects-state-filter" "browser missing state filter"
have "$CTRL" "projects-sort" "browser missing sort control"
# narrowing is pure + client-side over loaded rows (no new BE list param).
[ -f "$LIB" ] || fail "projectBrowser.ts (narrowing) not found"
have "$LIB" "narrowProjects" "projectBrowser missing narrowProjects"
have "$TAB" "narrowProjects" "ProjectsTab does not narrow the loaded rows"
# explicit handlers, NOT useEffect-for-events (CLAUDE.md FE rule).
grep -Eq 'useEffect\(' "$TAB" && fail "ProjectsTab uses useEffect (events must be explicit handlers)"
# real Load-more button wired to fetchNextPage.
have "$TAB" "projects-load-more" "ProjectsTab missing a real Load more control"
have "$TAB" "loadMore" "ProjectsTab does not call loadMore"

# ── 3. rows route INTO the C6 detail shell (not a modal / flat tab) ──
have "$TAB" "/knowledge/projects/" "ProjectsTab row does not navigate into the C6 shell"
grep -Eq 'navigate\(`/knowledge/projects/\$\{p\.project_id\}/overview`\)' "$TAB" \
  || fail "ProjectsTab row does not navigate to /knowledge/projects/:id/overview"
have "$ROW" "onOpen" "ProjectRow missing onOpen routing affordance"

# ── 4. build polish: post-submit visible feedback + running-build label ──
have "$BUILD" "startSuccess" "BuildGraphDialog missing post-submit success feedback (KN-5)"
have "$RUNCARD" "building_running.elapsed" "BuildingRunningCard missing running-build elapsed label (KN-9)"

# ── 5. cross-project surface stays secondary (flat-tab default untouched) ──
have "$FE/src/pages/KnowledgePage.tsx" "/knowledge/projects" "KnowledgePage default landing drifted"

# ── 6. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-7] vitest (browser + pagination + polish)"
npx vitest run \
  src/features/knowledge/lib/__tests__/projectBrowser.test.ts \
  src/features/knowledge/lib/__tests__/formatElapsed.test.ts \
  src/features/knowledge/hooks/__tests__/useProjects.pagination.test.tsx \
  src/features/knowledge/components/__tests__/ProjectsTab.browser.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -14

audit "verify_cycle_7_passed"
echo "[verify-cycle-7] PASS"
exit 0
