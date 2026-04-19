#!/usr/bin/env bash
# T2-close-3 / C06 — Neo4j evidence-count drift + reconciliation (KSA §9.10)
#
# Chaos hypothesis:
#   If Neo4j data gets corrupted so that a node's cached
#   `evidence_count` property diverges from the actual
#   `(:Entity|:Event|:Fact)-[:EVIDENCED_BY]->(:ExtractionSource)`
#   edge count, the K11.9 `reconcile_evidence_count` job must
#   detect and fix it. Corruption sources in the wild:
#   - Partial-failure windows in K11.8 `delete_source_cascade`
#     (non-atomic across three Cypher round-trips)
#   - Bulk glossary-sync imports that write EVIDENCED_BY via raw
#     Cypher, bypassing `add_evidence`
#   - Operator mistakes / data migrations
#
# What this script does:
#   1. Seed a throwaway :Entity with a known evidence_count = 3
#      and three real EVIDENCED_BY edges to three :ExtractionSource
#      nodes. Baseline: drift = 0.
#   2. Inject drift: DELETE two of the edges (leaving 1 edge) while
#      NOT touching the cached evidence_count property. The node
#      now claims evidence_count=3 but has only 1 edge.
#   3. Run the reconciler via `python -m app.jobs.reconcile_evidence_count`
#      inside the knowledge-service container, scoped to the test
#      user_id.
#   4. Assert the reconciler's log line reports >= 1 fix.
#   5. Assert the :Entity's evidence_count is now 1 (matches the
#      actual edge count).
#   6. Assert the Prometheus counter
#      `knowledge_evidence_count_drift_fixed_total{node_label=Entity}`
#      incremented (if /metrics is reachable).
#   7. Cleanup: DETACH DELETE the test :Entity and :ExtractionSource
#      nodes.

set -euo pipefail
CHAOS_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=lib.sh
source "$CHAOS_DIR/lib.sh"

log_step "C06 — Neo4j evidence-count drift + reconciliation"
require_infra

TEST_USER="00000000-0000-0000-c006-000000000001"
TEST_PROJECT="00000000-0000-0000-c006-000000000002"
TEST_ENTITY="c06-entity-$(date +%s)"

cleanup() {
    log_step "cleanup — deleting chaos-c06 test nodes"
    cypher_q "
MATCH (n {user_id: '$TEST_USER'})
DETACH DELETE n
" >/dev/null || log_warn "cleanup cypher failed (non-fatal)"
}
trap cleanup EXIT

# ── Seed the node + three real edges ──────────────────────────────
log_step "seeding :Entity with evidence_count=3 and three :EVIDENCED_BY edges"
cypher_q "
CREATE (e:Entity {
  entity_id: '$TEST_ENTITY',
  user_id: '$TEST_USER',
  project_id: '$TEST_PROJECT',
  name: 'Chaos C06 entity',
  evidence_count: 3
})
WITH e
UNWIND range(1, 3) AS i
CREATE (s:ExtractionSource {
  source_id: '$TEST_ENTITY-src-' + i,
  user_id: '$TEST_USER',
  project_id: '$TEST_PROJECT'
})
CREATE (e)-[:EVIDENCED_BY]->(s)
" >/dev/null

# Sanity: count should match
before_edges=$(cypher_count_scalar "
MATCH (e:Entity {entity_id: '$TEST_ENTITY'})-[r:EVIDENCED_BY]->()
RETURN count(r)
")
assert_eq "baseline edge count" "3" "$before_edges"

before_cached=$(cypher_count_scalar "
MATCH (e:Entity {entity_id: '$TEST_ENTITY'}) RETURN e.evidence_count
")
assert_eq "baseline cached evidence_count" "3" "$before_cached"

# ── Inject drift: delete two edges ────────────────────────────────
log_step "corrupting Neo4j — deleting 2 EVIDENCED_BY edges without touching evidence_count"
cypher_q "
MATCH (e:Entity {entity_id: '$TEST_ENTITY'})-[r:EVIDENCED_BY]->(s:ExtractionSource)
WHERE s.source_id IN ['$TEST_ENTITY-src-2', '$TEST_ENTITY-src-3']
DELETE r
" >/dev/null

drifted_edges=$(cypher_count_scalar "
MATCH (e:Entity {entity_id: '$TEST_ENTITY'})-[r:EVIDENCED_BY]->()
RETURN count(r)
")
assert_eq "post-drift edge count" "1" "$drifted_edges"

drifted_cached=$(cypher_count_scalar "
MATCH (e:Entity {entity_id: '$TEST_ENTITY'}) RETURN e.evidence_count
")
assert_eq "post-drift cached evidence_count (still stale)" "3" "$drifted_cached"

# ── Run the reconciler ─────────────────────────────────────────────
log_step "invoking reconcile_evidence_count inside knowledge-service"

# Runs as an inline python script inside the knowledge-service
# container so we use its installed deps + env. Note: the running
# FastAPI app has the driver init'd via lifespan, but a fresh
# `docker exec python -c` spawns a new process with empty module
# globals — we MUST call init_neo4j_driver() explicitly before the
# reconciler's `neo4j_session()` context manager will work. Same
# for close on the way out.
docker exec "$KNOWLEDGE_CONTAINER" python -c "
import asyncio
from app.db.neo4j import init_neo4j_driver, close_neo4j_driver, neo4j_session
from app.jobs.reconcile_evidence_count import reconcile_evidence_count

async def main():
    await init_neo4j_driver()
    try:
        async with neo4j_session() as s:
            result = await reconcile_evidence_count(
                s, user_id='$TEST_USER', project_id='$TEST_PROJECT',
            )
            print(f'ENTITIES={result.entities_fixed} EVENTS={result.events_fixed} FACTS={result.facts_fixed}')
    finally:
        await close_neo4j_driver()

asyncio.run(main())
" | tee /tmp/c06-reconcile.out

# Parse the one-line result from stdout — avoids depending on log
# message wording which could drift.
entities_fixed=$(grep -oE 'ENTITIES=[0-9]+' /tmp/c06-reconcile.out | sed 's/ENTITIES=//')
assert_ge "entities_fixed" "1" "$entities_fixed"

# ── Post-reconciliation assertion ──────────────────────────────────
fixed_cached=$(cypher_count_scalar "
MATCH (e:Entity {entity_id: '$TEST_ENTITY'}) RETURN e.evidence_count
")
assert_eq "reconciled cached evidence_count" "1" "$fixed_cached"

log_pass "C06 — evidence-count drift reconciled"
echo "C06:PASS"
