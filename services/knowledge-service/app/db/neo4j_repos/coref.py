"""Coreference-detection graph reads (plan T12).

Moved out of `app/extraction/coref_detect.py`, which called them "a THIN Neo4j loader"
and kept the Cypher inline. Unlike the other two moves in this task there was no bypass
to fix here — both queries already went through `run_read` and carried `$user_id`. The
reason to move them anyway is the one the phase exists for: a module that speaks Cypher
cannot be put behind a storage port, and `coref_detect.py` is otherwise pure scoring
logic that its own docstring describes as testable with fakes.

The detector's SCORING stays where it was. Only the two reads live here.
"""

from __future__ import annotations

import logging

from app.db.neo4j_helpers import CypherSession, run_read

logger = logging.getLogger(__name__)

__all__ = [
    "CorefEntityRow",
    "load_anchored_kinds",
    "load_coref_entities",
]


# A plain tuple-shaped row rather than the detector's `CorefEntity`: the repo returns
# what the graph holds, and the detector builds its own frozen dataclass from it. Keeping
# the domain type on the detector side is what stops this module importing back up into
# `app.extraction` and turning a one-way dependency into a cycle.
CorefEntityRow = dict


_ANCHORED_KINDS_CYPHER = """
MATCH (e:Entity {user_id: $user_id})
WHERE e.project_id = $project_id AND e.glossary_entity_id IS NOT NULL
RETURN DISTINCT e.kind AS kind
"""


_COREF_ENTITIES_CYPHER = """
MATCH (e:Entity {user_id: $user_id, kind: $kind})
WHERE e.project_id = $project_id AND e.glossary_entity_id IS NOT NULL
OPTIONAL MATCH (e)-[r:RELATES_TO]-(n:Entity)
  WHERE r.user_id = $user_id AND r.valid_until IS NULL
WITH e, collect(DISTINCT n.id) AS neighbor_ids
RETURN e.glossary_entity_id AS gid, e.name AS name, e.aliases AS aliases,
       e.mention_count AS mentions, neighbor_ids AS neighbor_ids
ORDER BY mentions DESC
LIMIT $limit
"""


async def load_anchored_kinds(
    session: CypherSession, *, user_id: str, project_id: str
) -> list[str]:
    """Distinct kinds of glossary-anchored entities in the project — the default scope
    when a detect request omits an explicit `kinds` list."""
    result = await run_read(
        session, _ANCHORED_KINDS_CYPHER, user_id=user_id, project_id=project_id
    )
    kinds: list[str] = []
    async for row in result:
        kind = row.get("kind")
        if kind:
            kinds.append(str(kind))
    logger.debug(
        "load_anchored_kinds: project=%s kinds=%d", project_id, len(kinds)
    )
    return kinds


async def load_coref_entities(
    session: CypherSession, *, user_id: str, project_id: str, kind: str, limit: int
) -> list[CorefEntityRow]:
    """Anchored entities of one kind with their names, aliases, mention counts and
    one-hop live neighbours — the four signals the detector scores on.

    Ordered by mention count so `limit` keeps the entities most worth comparing: the
    candidate step is pairwise, so the cap is what stops it going quadratic on a large
    project. Rows without a glossary id are dropped — the detector proposes MERGES into
    the glossary, so an unanchored node has nothing to merge into.
    """
    result = await run_read(
        session, _COREF_ENTITIES_CYPHER,
        user_id=user_id, project_id=project_id, kind=kind, limit=limit,
    )
    rows: list[CorefEntityRow] = []
    async for row in result:
        gid = row.get("gid")
        if not gid:
            continue
        rows.append({
            "gid": str(gid),
            "name": row.get("name") or "",
            "aliases": tuple(row.get("aliases") or ()),
            "mentions": int(row.get("mentions") or 0),
            "neighbor_ids": [str(n) for n in (row.get("neighbor_ids") or []) if n],
        })
    logger.debug(
        "load_coref_entities: project=%s kind=%s limit=%d rows=%d",
        project_id, kind, limit, len(rows),
    )
    return rows
