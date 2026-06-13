#!/usr/bin/env bash
# verify-cycle-10 — C10 Glossary Gap Report (BE-thin + FE) gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). BE+FE. Asserts:
#   BE  — GET /v1/knowledge/projects/{project_id}/gaps that is a THIN
#         pass-through over find_gap_candidates() (entity gaps: high-mention,
#         no glossary entry); min_mentions + limit flow straight to the repo.
#   FE  — getProjectGaps api + useGaps hook + useBulkPromote (SEQUENTIAL reuse
#         of the C9 single-promote, progress + partial-failure) + GapReportTab
#         (summary cards, min_mentions threshold, limit control) rendered in
#         the C6 shell scoped by route (G6).
# LOCKED guards (grep-asserts): NOT merged with lore-enrichment detect-gaps;
#   NO batch-promote endpoint; bulk-promote reuses knowledgeApi.promoteEntity.
# Static asserts + targeted pytest. vitest proven green via PowerShell at
# VERIFY (bash-spawned vitest can hang in this env — the script greps the
# test files exist instead of spawning them).
set -euo pipefail
CYCLE=10
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KS="$REPO_ROOT/services/knowledge-service"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-10] FAIL: $1" >&2; audit "verify_cycle_10_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-10] running CI gate"

ROUTER="$KS/app/routers/public/entities.py"
BETEST="$KS/tests/unit/test_gaps_c10.py"
APIFE="$FE/src/features/knowledge/api.ts"
USEGAPS="$FE/src/features/knowledge/hooks/useGaps.ts"
BULK="$FE/src/features/knowledge/hooks/useBulkPromote.ts"
TAB="$FE/src/features/knowledge/components/GapReportTab.tsx"
SHELL="$FE/src/pages/ProjectDetailShell.tsx"
TABTEST="$FE/src/features/knowledge/components/__tests__/GapReportTab.test.tsx"
BULKTEST="$FE/src/features/knowledge/hooks/__tests__/useBulkPromote.test.tsx"

# ── 1. BE — gaps route is a THIN pass-through over find_gap_candidates ──
[ -f "$ROUTER" ] || fail "entities.py router not found"
have "$ROUTER" '/projects/{project_id}/gaps' "gaps route missing"
have "$ROUTER" "def get_project_gaps" "get_project_gaps handler missing"
have "$ROUTER" "find_gap_candidates" "gaps does not wire find_gap_candidates (entity gaps)"
have "$ROUTER" "min_mentions" "gaps missing min_mentions param"
# min_mentions + limit flow to the repo call as keyword args (pass-through).
grep -Eq "min_mentions=min_mentions" "$ROUTER" || fail "min_mentions not passed through to find_gap_candidates"
grep -Eq "limit=limit" "$ROUTER" || fail "limit not passed through to find_gap_candidates"

# ── 2. BE — LOCKED: NOT lore-enrichment detect-gaps; NO new gap engine ──
# the only gap source is find_gap_candidates; assert no detect-gaps merge.
grep -Fq "detect-gaps" "$ROUTER" && fail "gaps must NOT route through lore-enrichment detect-gaps (attribute gaps)"
grep -Fq "detect_gaps" "$ROUTER" && fail "gaps must NOT route through lore-enrichment detect_gaps (attribute gaps)"

# ── 3. FE — api: getProjectGaps hits the project-scoped gaps path ──
have "$APIFE" "getProjectGaps" "api.ts missing getProjectGaps"
have "$APIFE" "/gaps" "api.ts getProjectGaps hits the wrong path"
have "$APIFE" "min_mentions" "api.ts getProjectGaps does not forward min_mentions"

# ── 4. FE — useGaps query hook (threshold + limit in the queryKey) ──
[ -f "$USEGAPS" ] || fail "useGaps.ts not found"
have "$USEGAPS" "getProjectGaps" "useGaps does not call getProjectGaps"
have "$USEGAPS" "minMentions" "useGaps does not thread minMentions"

# ── 5. FE — useBulkPromote = SEQUENTIAL reuse of C9 single-promote ──
[ -f "$BULK" ] || fail "useBulkPromote.ts not found"
have "$BULK" "promoteEntity" "bulk-promote does not reuse the C9 promoteEntity"
# sequential: a for-loop awaiting each, NOT Promise.all (no batch).
grep -Fq "Promise.all" "$BULK" && fail "bulk-promote must be SEQUENTIAL, not Promise.all"
have "$BULK" "for (const" "bulk-promote is not a sequential loop"
have "$BULK" "progress" "bulk-promote missing a progress indicator"
have "$BULK" "failures" "bulk-promote missing partial-failure tracking"
# partial-failure survival: a try/catch inside the loop so one item can't abort.
grep -Fq "catch" "$BULK" || fail "bulk-promote does not catch per-item failure (partial-failure survival)"

# ── 6. FE — GapReportTab: summary cards + threshold + limit, route-scoped ──
[ -f "$TAB" ] || fail "GapReportTab.tsx not found"
have "$TAB" "gap-summary-count" "GapReportTab missing summary cards"
have "$TAB" "gap-min-mentions" "GapReportTab missing min_mentions threshold control"
have "$TAB" "gap-limit" "GapReportTab missing limit control"
have "$TAB" "gap-bulk-promote" "GapReportTab missing bulk-promote control"
have "$TAB" "gap-bulk-progress" "GapReportTab missing progress indicator"
have "$TAB" "useBulkPromote" "GapReportTab does not use the bulk-promote hook"
have "$TAB" "scopedProjectId" "GapReportTab not route-scoped (G6)"
# G6: no project select-box smuggled into the gap tab — the only <select>
# is the limit control; assert no project-picker state.
grep -Fq "projectFilter" "$TAB" && fail "GapReportTab must not add a project select-box (G6 route-scoping)"
grep -Fq "useProjects" "$TAB" && fail "GapReportTab must not list projects (route-scoped, G6)"

# ── 7. FE — wired into the C6 shell gap section (route-scoped) ──
have "$SHELL" "GapReportTab" "ProjectDetailShell does not render GapReportTab"
grep -Eq "activeSection === 'gap'.*projectId" "$SHELL" || grep -Eq "GapReportTab scopedProjectId=\{projectId\}" "$SHELL" || fail "gap section not route-scoped in the shell"

# ── 8. provider-gate green (no hardcoded model literal) ──
echo "[verify-cycle-10] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 9. targeted pytest (gaps pass-through + validation) ──
[ -f "$BETEST" ] || fail "BE gaps test missing"
echo "[verify-cycle-10] pytest (gaps C10)"
( cd "$KS" && python -m pytest tests/unit/test_gaps_c10.py -q 2>&1 | tail -8 ) \
  || fail "gaps pytest failed"

# ── 10. FE test files present (proven green via PowerShell vitest) ──
[ -f "$TABTEST" ] || fail "FE GapReportTab test missing"
[ -f "$BULKTEST" ] || fail "FE useBulkPromote test missing"
grep -Fq "promoteEntity" "$BULKTEST" || fail "bulk-promote test does not assert it reuses promoteEntity"
grep -Fq "survives a single-item failure" "$BULKTEST" || fail "bulk-promote test does not cover partial-failure survival"

audit "verify_cycle_10_passed"
echo "[verify-cycle-10] PASS"
exit 0
