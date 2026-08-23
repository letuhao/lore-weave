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
ORDER BY coalesce(r.valid_from, 2147483647) ASC, obj.id ASC
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
