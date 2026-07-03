"""A4 — schema-component usage counts over the derived graph.

Before a human deletes (deprecates) a schema component on a LIVE project schema,
the GUI warns "N graph elements reference this". That count lives in Neo4j (the
derived graph, Postgres-SSOT + Neo4j-derived), not in the schema tables. We count
the two component kinds that map to concrete graph elements:

  * ``node_kind`` → ``(:Entity {kind})`` nodes in the project
  * ``edge_type`` → live ``[:RELATES_TO {predicate}]`` edges in the project
    (``valid_until IS NULL`` — superseded relations don't count)

``fact_type`` / ``vocab_value`` have a fuzzier usage model (fact rows / entity
attributes) and are reported as *not counted* — the caller shows a plain confirm.

Project scoping: entities carry ``project_id``; relations don't, so an edge is
attributed to the project via its SUBJECT entity's ``project_id`` (the same anchor
scoping the L2 loader uses). All queries are ``user_id``-scoped (tenancy).
"""

from __future__ import annotations

from app.db.neo4j_helpers import CypherSession, run_read

# node_kind → count Entity nodes of that kind in the project.
_NODE_KIND_CYPHER = """
MATCH (e:Entity {user_id: $user_id})
WHERE e.project_id = $project_id AND e.kind = $code
RETURN count(e) AS total
"""

# edge_type → count LIVE relations of that predicate, scoped by the subject's project.
_EDGE_TYPE_CYPHER = """
MATCH (s:Entity {user_id: $user_id})-[r:RELATES_TO]->(:Entity)
WHERE s.project_id = $project_id AND r.predicate = $code AND r.valid_until IS NULL
RETURN count(r) AS total
"""

_CYPHER_BY_TYPE = {
    "node_kind": _NODE_KIND_CYPHER,
    "edge_type": _EDGE_TYPE_CYPHER,
}


async def count_component_usage(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    node_type: str,
    code: str,
) -> int | None:
    """Number of graph elements referencing ``code`` for a ``node_kind``/``edge_type``.

    Returns ``None`` for a component type we don't count (fact_type/vocab_value/
    anything else) so the caller can distinguish "0 uses" from "not counted"."""
    cypher = _CYPHER_BY_TYPE.get(node_type)
    if cypher is None:
        return None
    result = await run_read(session, cypher, user_id=user_id, project_id=project_id, code=code)
    record = await result.single()
    return int(record["total"] or 0) if record is not None else 0
