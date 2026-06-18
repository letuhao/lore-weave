#!/usr/bin/env bash
# verify-cycle-18 — C18 Graph subgraph endpoint (BE knowledge) gate.
# Per RAID_WORKFLOW.md §13 (exit 0 = pass). BE knowledge-service only.
# Asserts: the new project subgraph repo query (get_project_subgraph)
# binds BOTH user_id AND project_id, enforces the node cap IN the Cypher
# with a deterministic ORDER (cap precedes edge traversal), exposes the
# hops/limit/center params; the route GET /projects/{id}/subgraph returns
# {nodes, edges}; provider-gate green; targeted pytest passes.
set -euo pipefail
CYCLE=18
REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KS="$REPO_ROOT/services/knowledge-service"
AUDIT_LOG="$REPO_ROOT/docs/audit/AUDIT_LOG.jsonl"
NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

audit() { mkdir -p "$(dirname "$AUDIT_LOG")"; echo "{\"ts\":\"$NOW\",\"event\":\"$1\",\"cycle\":$CYCLE}" >> "$AUDIT_LOG"; }
fail() { echo "[verify-cycle-18] FAIL: $1" >&2; audit "verify_cycle_18_failed"; exit 1; }
have() { grep -Fq "$2" "$1" || fail "$3"; }

echo "[verify-cycle-18] running CI gate"

REPO="$KS/app/db/neo4j_repos/relations.py"
ROUTER="$KS/app/routers/public/entities.py"

[ -f "$REPO" ] || fail "relations.py repo not found"
[ -f "$ROUTER" ] || fail "entities.py router not found"

# ── 1. repo — get_project_subgraph + models + caps ──
have "$REPO" "async def get_project_subgraph" "get_project_subgraph repo fn missing"
have "$REPO" "class Subgraph" "Subgraph response model missing"
have "$REPO" "class SubgraphNode" "SubgraphNode model missing"
have "$REPO" "class SubgraphEdge" "SubgraphEdge model missing"
have "$REPO" "SUBGRAPH_MAX_NODE_CAP" "node-cap ceiling const missing"
have "$REPO" "SUBGRAPH_MAX_HOPS" "hops ceiling const missing"

# ── 2. repo — partition: BOTH user_id AND project_id bound ──
have "$REPO" "n.user_id = user_id" "project-wide query missing user_id partition bind"
have "$REPO" "n.project_id = project_id" "project-wide query missing project_id partition bind"
# adversary F2 — the edge stage re-asserts project_id on BOTH endpoints
# (both project-wide + ego assemble), not relying on seed-id confinement.
have "$REPO" "a.project_id = \$project_id" "edge stage missing project_id bind on endpoint a"
have "$REPO" "b.project_id = \$project_id" "edge stage missing project_id bind on endpoint b"
# ego path: per-hop frontier step is partition-scoped on the neighbour
have "$REPO" "nbr.user_id = \$user_id" "ego hop step missing user_id partition bind"
have "$REPO" "nbr.project_id = \$project_id" "ego hop step missing project_id partition bind"

# ── 3. repo — cap IN the query, deterministic order, precedes edges ──
have "$REPO" "LIMIT \$limit" "node cap (LIMIT \$limit) missing from the Cypher"
have "$REPO" "ORDER BY coalesce(n.anchor_score" "deterministic node order missing"
have "$REPO" "OPTIONAL MATCH (a:Entity)-[r:RELATES_TO]->(b:Entity)" "edge stage missing"
# adversary F1 — the ego path must NOT use unbounded variable-length
# expansion (`RELATES_TO*1..N`); it uses a bounded per-hop frontier BFS
# (driven from Python via _ego_seed_ids) whose hop step caps the
# neighbour set with LIMIT before the next hop.
grep -Fq "RELATES_TO*" "$REPO" && fail "ego path uses unbounded variable-length expansion (hub-OOM risk)" || true
have "$REPO" "async def _ego_seed_ids" "bounded ego frontier BFS missing"
have "$REPO" "_EGO_HOP_STEP" "ego per-hop step query missing"
# the project-wide node-cap LIMIT must precede the edge OPTIONAL MATCH
# (cap BEFORE traversal — the unbounded-traversal guard).
python - "$REPO" <<'PY' || fail "node cap does not precede edge traversal (post-filter risk)"
import sys, re
src = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r"_PROJECT_SUBGRAPH_CYPHER = \"\"\"(.*?)\"\"\"", src, re.S)
assert m, "could not locate _PROJECT_SUBGRAPH_CYPHER"
body = m.group(1)
assert body.index("LIMIT $limit") < body.index("OPTIONAL MATCH"), "cap after traversal"
# the ego hop step must cap its frontier with LIMIT (bounds next hop)
h = re.search(r"_EGO_HOP_STEP = \"\"\"(.*?)\"\"\"", src, re.S)
assert h and "LIMIT $limit" in h.group(1), "ego hop step missing frontier cap"
PY

# ── 4. repo — clamp to ceilings (defence in depth past the route) ──
have "$REPO" "min(limit, SUBGRAPH_MAX_NODE_CAP)" "limit not clamped to ceiling"
have "$REPO" "min(hops, SUBGRAPH_MAX_HOPS)" "hops not clamped to ceiling"

# ── 5. route — GET /projects/{id}/subgraph + params + {nodes,edges} ──
have "$ROUTER" "/projects/{project_id}/subgraph" "subgraph route path missing"
have "$ROUTER" "get_project_subgraph" "route does not call the repo fn"
have "$ROUTER" "response_model=Subgraph" "route response model not Subgraph"
have "$ROUTER" "hops" "route missing hops param"
have "$ROUTER" "center" "route missing center param"
have "$ROUTER" "le=SUBGRAPH_MAX_NODE_CAP" "route does not cap limit at the ceiling"
have "$ROUTER" "le=SUBGRAPH_MAX_HOPS" "route does not cap hops at the ceiling"
# read-only: no write/edit op smuggled into the subgraph route
grep -Eq "@entities_router\.(post|patch|put|delete)\([^)]*subgraph" "$ROUTER" \
  && fail "subgraph must be read-only — a write verb route was added" || true

# ── 6. provider-gate green (no hardcoded model / id) ──
echo "[verify-cycle-18] provider-gate"
python "$REPO_ROOT/scripts/ai-provider-gate.py" >/dev/null 2>&1 || fail "ai-provider-gate failed"

# ── 7. targeted pytest (route + repo + entities regression) ──
# Integration tests (live Neo4j) auto-skip when TEST_NEO4J_URI is unset;
# the VERIFY-phase live-smoke carries the real-graph evidence.
echo "[verify-cycle-18] pytest (subgraph C18 + entities regression)"
( cd "$KS" && python -m pytest \
    tests/unit/test_subgraph_c18.py \
    tests/unit/test_subgraph_repo_c18.py \
    tests/unit/test_gaps_c10.py \
    tests/unit/test_entities_browse_api.py \
    tests/integration/db/test_relations_repo.py \
    -q 2>&1 | tail -8 )

audit "verify_cycle_18_passed"
echo "[verify-cycle-18] PASS"
exit 0
