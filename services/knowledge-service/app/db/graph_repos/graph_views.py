"""Graph-view reads for the KG browse surfaces (plan T17).

Moved out of `app/routers/public/graph_views.py`. The router keeps everything that makes
these views a PRODUCT — the view lens, the as-of filter, localisation, the grant
resolution — and this module keeps the two reads they run.

⚠️ **The temporal filter is deliberately NOT in the Cypher.** `valid_until IS NULL` keeps
superseded edges out, but the chapter-ordinal as-of predicate is applied in PYTHON
(`edge_visible_at`) so it stays pure and unit-testable without a live graph. That is a
decision the original author made and it survives the move intact — pushing it down here
would trade a unit-tested predicate for an untestable one.

⚠️ **Both reads bind the resolved OWNER, not the caller.** The graph partition is
owner-scoped, so a grantee correctly reads the owner's graph; binding the caller would
re-introduce the 404 that lane fixed (caller != owner ⇒ no rows). The router does that
resolution; this module just takes whatever `user_id` it is handed.
"""

from __future__ import annotations

from typing import Any

from app.db.neo4j_helpers import CypherSession, run_read

__all__ = ["read_entity_edge_timeline", "read_project_graph_edges"]


# Graph-read Cypher: every active :RELATES_TO edge in the (owner, project)
# partition, with its temporal props + both endpoint nodes. Multi-tenant:
# binds $user_id (K11.4) AND $project_id on every node. valid_until IS NULL
# keeps superseded (user-corrected) edges out; the chapter-ordinal temporal
# filter (valid_from/valid_to) is applied in PYTHON via edge_visible_at so the
# predicate is pure + unit-tested. predicate IS the edge_type code.
_GRAPH_READ_CYPHER = """
MATCH (subj:Entity)-[r:RELATES_TO]->(obj:Entity)
WHERE subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND subj.project_id = $project_id
  AND obj.project_id = $project_id
  AND r.user_id = $user_id
  AND r.valid_until IS NULL
  AND subj.archived_at IS NULL
  AND obj.archived_at IS NULL
RETURN properties(r) AS rel,
       properties(subj) AS subj,
       properties(obj) AS obj
ORDER BY r.predicate ASC, subj.id ASC, obj.id ASC
LIMIT $limit
"""

async def read_project_graph_edges(
    session: CypherSession, *, user_id: str, project_id: str, limit: int,
) -> list[dict[str, Any]]:
    """Every ACTIVE `:RELATES_TO` edge in one (owner, project) partition, with both
    endpoints. Returns raw `{rel, subj, obj}` records — assembly into a `GraphSlice` is the
    router's, and is unit-tested there without a database."""
    result = await run_read(
        session, _GRAPH_READ_CYPHER,
        user_id=user_id, project_id=project_id, limit=limit,
    )
    return [
        {"rel": dict(r["rel"]), "subj": dict(r["subj"]), "obj": dict(r["obj"])}
        async for r in result
    ]


# Timeline Cypher: every instance (active OR superseded) of one edge_type from
# one entity, ordered by the temporal opening ordinal. We do NOT filter
# valid_until here — the timeline is the FULL arc, including closed instances
# (that is the point: revenge→seek_dao→transcendence). Predicate is bound as a
# parameter (never interpolated). Multi-tenant via $user_id (K11.4).
_TIMELINE_CYPHER = """
MATCH (subj:Entity {id: $entity_id})-[r:RELATES_TO]->(obj:Entity)
WHERE subj.user_id = $user_id
  AND obj.user_id = $user_id
  AND r.user_id = $user_id
  AND r.predicate = $edge_type
RETURN properties(r) AS rel, properties(obj) AS obj
ORDER BY coalesce(r.valid_from_ordinal, 9223372036854775807) ASC, obj.id ASC
LIMIT $limit
"""

async def read_entity_edge_timeline(
    session: CypherSession, *, user_id: str, entity_id: str, edge_type: str, limit: int,
) -> list[dict[str, Any]]:
    """The FULL arc for one (entity, edge_type) — active AND superseded instances — ordered
    by opening chapter ordinal. Superseded instances are the point: this view exists to show
    how a relationship CHANGED, so filtering them would empty it."""
    result = await run_read(
        session, _TIMELINE_CYPHER,
        user_id=user_id, entity_id=entity_id, edge_type=edge_type, limit=limit,
    )
    return [dict(r) async for r in result]

# ── isolated nodes ────────────────────────────────────────────────────────
#
# Reconciled here 2026-09-03 from `routers/public/graph_views.py`, where the FE branch
# defined them. This branch's T17 refactor moved graph-view Cypher OUT of the router and
# into this module, so keeping them there would have left two homes for one concern. The
# consumer is `tools/graph_schema_tools.py`, which runs the isolated read itself; the REST
# handler deliberately does not (FE's own note: `isolated` DEFAULTS TO NONE SO THE REST
# CALLER IS UNTOUCHED).
#
# ✅ PROVEN ON AGE 2026-09-04 — and the suspicion recorded here was WRONG, which is worth
# more than quietly deleting it. `NOT EXISTS { MATCH ... }` is a Neo4j subquery form and this
# module's siblings document AGE refusing constructs Neo4j accepts (facts.py: "AGE refuses the
# second form"), so it was flagged unverified. Measured: AGE compiles it.
#
# Compiling was not the bar. `search_facts_by_text` was caught by a syntax error — the LOUD
# failure. A query that compiles and returns the wrong rows is the quiet one, and here it would
# be quiet in the worst direction: this read exists because an edgeless node is invisible to the
# edge-projected graph read, so a predicate AGE evaluated differently would report `nodes: []`
# on a project that holds entities — the exact answer the read was added to stop.
# `test_wave_9_the_ISOLATED_NODE_read_runs_on_AGE_and_discriminates` asserts the behaviour:
# the edgeless node comes back, connected ones do not, the scalar count is right, and neither
# another user nor another project can see the rows.

# 🔴 D-EDGELESS-NODE-INVISIBLE-TO-THE-GRAPH-READ. `_GRAPH_READ_CYPHER` projects nodes FROM EDGES,
# so a node with no active relation cannot appear in a graph read at all — and `kg_add_nodes`
# answers "node ready" for exactly such a node, because placing an edge needs an approved card.
# The agent then reads `nodes: [], nodes_total: 0` on a project whose store holds entities.
#
# MEASURED ON THIS INSTANCE 2026-08-26: 5,351 entities across 455 projects, of which 4,887 (91%)
# have no active edge, and 440 of the 455 projects have NO edges at all. The per-project isolated
# count is p50 2, p90 7, p99 41 — and max 3,172. So the rows are cheap for virtually every project
# and ruinous for two, which is why this is capped and counted rather than simply unioned in.
_ISOLATED_NODES_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND e.project_id = $project_id
  AND e.archived_at IS NULL
  AND NOT EXISTS {
    MATCH (e)-[r:RELATES_TO]-()
    WHERE r.valid_until IS NULL
  }
RETURN properties(e) AS node
ORDER BY e.name ASC, e.id ASC
LIMIT $limit
"""

#: The TRUE node count for the partition — every non-archived entity, connected or not. Separate
#: from the slice so a capped read can still state the whole set's size, which is K25's rule: a
#: capped slice must never read as the whole set.
_NODE_TOTAL_CYPHER = """
MATCH (e:Entity)
WHERE e.user_id = $user_id
  AND e.project_id = $project_id
  AND e.archived_at IS NULL
RETURN count(e) AS total
"""
