#!/usr/bin/env bash
# verify-cycle-28 — C28 Living-world view (FE, dị bản M6) acceptance gate. ▶ M6.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). FE-only: a world surfaces its canon
# Work as the TRUNK + each dị bản as a BRANCH (Works whose `source_work_id`
# chains into THIS world's books, anchored at chapter-level `branch_point`, G3),
# rendered on the REUSED GraphCanvas (LOCKED G5 — NO new graph library).
# Read-only; click a node → navigate into that Work via an EXPLICIT handler.
#
# Static grep-asserts + a NO-NEW-GRAPH-LIB package.json guard + targeted vitest
# (run resiliently — bash-spawned vitest can hang in this env; PowerShell proves
# the full run at VERIFY separately).
set -euo pipefail
CYCLE=28
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
FE="$REPO_ROOT/frontend"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-28] FAIL: $1" >&2; audit "verify_cycle_28_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-28] running CI gate"

TREE="$FE/src/features/world/components/LivingWorldTree.tsx"
NODE="$FE/src/features/world/components/WorldTreeNode.tsx"
HOOK="$FE/src/features/world/hooks/useLivingWorld.ts"
LIB="$FE/src/features/world/lib/livingWorldTree.ts"
API="$FE/src/features/world/api.ts"
WORKSPACE="$FE/src/features/world/pages/WorldWorkspacePage.tsx"
CANVAS="$FE/src/features/composition/components/GraphCanvas.tsx"
PKG="$FE/package.json"

for f in "$TREE" "$NODE" "$HOOK" "$LIB" "$API" "$WORKSPACE"; do
  [ -f "$f" ] || fail "missing expected file: $f"
done

# ── 1. REUSE GraphCanvas — NO fork, NO new graph code ──
have "$TREE" "GraphCanvas" "LivingWorldTree does not reuse the shared GraphCanvas"
have "$TREE" "from '@/features/composition/components/GraphCanvas'" "LivingWorldTree does not import the shared GraphCanvas"
grep -Eq 'nodeIds=|renderNode=|renderEdge=' "$TREE" || fail "LivingWorldTree does not feed GraphCanvas the node/edge render props"

# ── 2. branches via the C23 source_work_id chain into THIS world's books ──
have "$LIB" "source_work_id" "tree builder does not key branches on source_work_id (C23 chain)"
have "$LIB" "branch_point" "tree builder does not anchor branches at branch_point (G3)"
have "$HOOK" "listWorldBooks" "useLivingWorld does not enumerate the world's books (no cross-world bleed)"
have "$HOOK" "resolveWork" "useLivingWorld does not resolve per-book Works"
have "$API" "listWorldBooks" "api.ts missing listWorldBooks (the world's books read)"
have "$API" "/books" "listWorldBooks does not hit the world books endpoint"
# orphan guard: a derivative whose source is outside the world is NOT joined.
have "$LIB" "orphanSource" "tree builder has no cross-world orphan guard"

# ── 3. branch_point anchoring (chapter-level, G3) surfaced as metadata ──
have "$NODE" "branchPoint" "WorldTreeNode does not surface the branch_point metadata"
have "$TREE" "branchPoint" "branch connector does not carry the branch_point label"

# ── 4. click node → navigate into that Work from an EXPLICIT handler ──
have "$TREE" "useNavigate" "LivingWorldTree does not navigate on click"
have "$TREE" "onNodeClick" "LivingWorldTree does not wire a node-click handler"
grep -Eq 'navigate\(`?/books/' "$TREE" || fail "click does not navigate into the Work's book"
# the navigation must NOT be a useEffect-for-events (FE rule). Match an actual
# CALL (`useEffect(` / `React.useEffect(`), not the word in a comment.
if grep -Eq '(^|[^.a-zA-Z])useEffect\(' "$TREE"; then fail "LivingWorldTree calls useEffect — navigation must be an explicit handler (FE event rule)"; fi
if grep -Eq '(^|[^.a-zA-Z])useEffect\(' "$NODE"; then fail "WorldTreeNode calls useEffect (FE event rule)"; fi

# ── 5. READ-ONLY — no edit/mutation surface on the tree ──
if grep -Eq 'useMutation|patchWork|deriveWork|createNode|updateEntity\(|deleteSceneLink' "$TREE" "$NODE"; then
  fail "the living-world tree has a write/edit surface — must be read-only navigation"
fi

# ── 6. wired into the world workspace ──
have "$WORKSPACE" "LivingWorldTree" "WorldWorkspacePage does not render the LivingWorldTree"
have "$WORKSPACE" "living-world-section" "WorldWorkspacePage missing the living-world section"

# ── 7. NO NEW GRAPH LIBRARY — package.json grep guard (LOCKED G5) ──
for lib in cytoscape reactflow react-flow vis-network "d3-force" "force-graph" sigma ngraph dagre elkjs; do
  if grep -Fq "\"$lib" "$PKG"; then fail "NEW GRAPH LIBRARY '$lib' added to package.json — LOCKED no-new-graph-library violation"; fi
done

# ── 8. targeted vitest green ──
cd "$FE"
echo "[verify-cycle-28] vitest (tree builder + hook + tree component + workspace regression)"
npx vitest run \
  src/features/world/lib/__tests__/livingWorldTree.test.ts \
  src/features/world/hooks/__tests__/useLivingWorld.test.tsx \
  src/features/world/components/__tests__/LivingWorldTree.test.tsx \
  src/features/world/__tests__/WorldWorkspace.test.tsx \
  --reporter=dot --testTimeout=10000 2>&1 | tail -12

audit "verify_cycle_28_passed"
echo "[verify-cycle-28] PASS"
exit 0
