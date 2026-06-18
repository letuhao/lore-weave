#!/usr/bin/env bash
# verify-cycle-19 — C19 Graph canvas (FE, G5) acceptance gate. ▶ M4.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: the project subgraph
# (C18) rendered as an explorable visual network — reuse GraphCanvas +
# generalize the RelationshipMap pattern, pan/zoom, click→detail,
# expand-hop, node cap, NO new graph library, read-only.
#
# Static grep-asserts + a NO-NEW-GRAPH-LIB package.json guard + targeted
# vitest. vitest is run resiliently (bash-spawned vitest can hang in this
# env — PowerShell proves the full run at VERIFY separately).
set -euo pipefail
CYCLE=19
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-19] FAIL: $1" >&2; audit "verify_cycle_19_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-19] running CI gate"

VIEW="$FE/src/features/knowledge/components/ProjectGraphView.tsx"
HOOK="$FE/src/features/knowledge/hooks/useProjectSubgraph.ts"
CANVAS="$FE/src/features/composition/components/GraphCanvas.tsx"
SHELL="$FE/src/pages/ProjectDetailShell.tsx"
API="$FE/src/features/knowledge/api.ts"
PKG="$FE/package.json"

[ -f "$VIEW" ] || fail "ProjectGraphView.tsx not found"
[ -f "$HOOK" ] || fail "useProjectSubgraph.ts not found"

# ── 1. REUSE GraphCanvas + GENERALIZE the RelationshipMap pattern (no fork) ──
have "$VIEW" "GraphCanvas" "ProjectGraphView does not reuse GraphCanvas"
have "$VIEW" "GraphEntityNode" "ProjectGraphView does not reuse the shared GraphEntityNode"
have "$VIEW" "RelationEdge" "ProjectGraphView does not reuse the shared RelationEdge"
have "$VIEW" "radialLayout" "ProjectGraphView does not reuse the hand-rolled radialLayout (RelationshipMap pattern)"

# ── 2. consume C18's subgraph endpoint (no BE change, no server layout) ──
have "$API" "getProjectSubgraph" "api.ts missing getProjectSubgraph client"
have "$API" "/subgraph" "api.ts subgraph client does not hit the /subgraph endpoint"
have "$HOOK" "getProjectSubgraph" "useProjectSubgraph does not call the subgraph endpoint"

# ── 3. pan/zoom on the shared canvas (hand-rolled, opt-in) ──
have "$CANVAS" "zoomable" "GraphCanvas missing the pan/zoom (zoomable) mode"
grep -Eq 'onWheel|deltaY' "$CANVAS" || fail "GraphCanvas has no wheel-zoom"
grep -Eq 'scale\(|transform=' "$CANVAS" || fail "GraphCanvas has no pan/zoom transform"
have "$VIEW" "zoomable" "ProjectGraphView does not enable pan/zoom on the canvas"

# ── 4. click node → reuse the existing entity-detail UI ──
have "$VIEW" "EntityDetailPanel" "ProjectGraphView does not reuse the existing EntityDetailPanel on click"
grep -Eq 'onNodeClick=' "$VIEW" || fail "ProjectGraphView does not wire a node-click handler"

# ── 5. expand-hop re-queries C18 (center) from the CLICK handler, not a useEffect ──
have "$HOOK" "center:" "useProjectSubgraph expand does not re-query with center"
have "$VIEW" "sg.expand" "ProjectGraphView does not fire expand-hop"
grep -Eq 'onExpand=\{\(\) => void sg\.expand' "$VIEW" || fail "expand-hop not fired from the click handler"
# the expand path must NOT be a useEffect-for-events.
if grep -Eq 'useEffect\([^)]*expand' "$VIEW"; then fail "expand-hop fired from a useEffect (FE event rule violation)"; fi

# ── 6. node cap honoured — no unbounded render ──
have "$HOOK" "SUBGRAPH_VIEW_NODE_CAP" "useProjectSubgraph has no FE node cap"
have "$HOOK" "node_cap_hit" "useProjectSubgraph ignores the BE node_cap_hit flag"
grep -Eq 'slice\(0, ?cap\)|slice\(0,cap\)' "$HOOK" || fail "useProjectSubgraph does not trim to the node cap"

# ── 7. read-only — no edit/mutation surface ON the canvas ──
if grep -Eq 'useUpdateEntity|useCorrectRelation|createRelation|updateEntity\(' "$VIEW"; then
  fail "ProjectGraphView has a write/edit surface — must be read-only (edits via existing dialogs)"
fi

# ── 8. wired into the project-detail shell graph section ──
have "$SHELL" "ProjectGraphView" "ProjectDetailShell graph section does not render ProjectGraphView"
grep -Eq "activeSection === 'graph'" "$SHELL" || fail "shell graph section missing"

# ── 9. NO NEW GRAPH LIBRARY — package.json grep guard (LOCKED) ──
for lib in cytoscape reactflow react-flow vis-network "d3-force" "force-graph" sigma ngraph; do
  if grep -Fq "\"$lib" "$PKG"; then fail "NEW GRAPH LIBRARY '$lib' added to package.json — LOCKED no-new-graph-library violation"; fi
done

# ── 10. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-19] vitest (subgraph hook + canvas zoom + graph view + relmap regression)"
npx vitest run \
  src/features/knowledge/hooks/__tests__/useProjectSubgraph.test.ts \
  src/features/composition/components/__tests__/GraphCanvasZoom.test.tsx \
  src/features/knowledge/components/__tests__/ProjectGraphView.test.tsx \
  src/features/composition/components/__tests__/RelationshipMap.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

audit "verify_cycle_19_passed"
echo "[verify-cycle-19] PASS"
exit 0
