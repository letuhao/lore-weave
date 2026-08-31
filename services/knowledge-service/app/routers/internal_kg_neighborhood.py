"""Internal KG neighborhood read — one entity's capped one-hop graph.

GET /internal/books/{book_id}/kg/neighborhood?entity_id=&hops=&cap=&as_of_chapter=

WHY THIS FILE EXISTS
--------------------
The knowledge-gateway's KAL read surface has called this endpoint since it was written, and
**the endpoint has never existed** — `kal-read.controller.ts` builds the URL, and nothing in
the repo serves it. It is not a private detail either: the route it backs is published in
`contracts/api/knowledge-gateway/kal.v1.yaml` as
`/v1/kal/books/{book_id}/entities/{entity_id}/neighborhood`, so the contract has been
advertising a 404 to every reader of the spec. Found while landing T26 (the gateway's only
`kgAsOfOrDrop` caller was this route); implemented here.

WHAT `entity_id` MEANS
---------------------
The GLOSSARY entity id, not the KG canonical id. The whole KAL surface is book-and-glossary
addressed — the gateway hands through whatever the FE has, which comes from the glossary —
and the KG node is reached via its `glossary_entity_id` anchor.

TENANCY
-------
Matches the sibling `/internal` routes: the caller is a trusted service authenticated by
`X-Internal-Token` and passes only the `book_id`. The owning tenant is resolved SERVER-SIDE
from `knowledge_projects`, so there is no user id for a caller to spoof — and the project
scope goes into the read, because the glossary FK is unique per *(user, project)* and an
unscoped lookup would return an arbitrary project's node (D-KG-GLOSSARY-FK-GLOBAL-UNIQUE).
"""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.domain.graph_models import EVENT_ORDER_CHAPTER_STRIDE
from app.db.pool import get_knowledge_pool
from app.kal.temporal import TemporalCapability, kg_as_of_or_drop, temporal_capability
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/books",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)

# The same project selection `internal_kg_state` uses, and for the same reason: a book can
# accumulate several knowledge projects over its life (a re-extraction mints a fresh one), and
# a derived/assistant scratch project is not the book's real KG.
_PROJECT_SQL = """
SELECT project_id, user_id
  FROM knowledge_projects
 WHERE book_id = $1
   AND NOT is_archived
   AND NOT is_derivative
   AND NOT is_assistant
 ORDER BY created_at DESC
 LIMIT 1
"""

# The contract's ceiling. `cap` exists because this feeds a context block and an uncapped
# neighbourhood on a hub entity is how a prompt budget disappears.
_MAX_CAP = 200
_DEFAULT_CAP = 50


class Edge(BaseModel):
    """One `:RELATES_TO` edge, projected to the published `Edge` schema.

    Direction is carried explicitly rather than left for the caller to infer: `from_entity` is
    the subject, `to_entity` the object, and the pair is meaningless without both.
    """

    predicate: str
    from_entity: str
    to_entity: str
    valid_from_ordinal: int | None = None
    valid_to_ordinal: int | None = None


class NeighborhoodResponse(BaseModel):
    """A book with no KG projection, or an entity with no node, is a 200 with no edges.

    "Nothing here yet" is the expected cold-start answer for most books, not an error — the
    same convention `internal_kg_state` and `/internal/knowledge/timeline` use. A 404 would
    force every caller to treat a normal state as a failure.

    `temporal_capability` rides along so the caller can tell an untimed answer from a
    story-timed one; see `app.kal.temporal`.
    """

    edges: list[Edge] = []
    truncated: bool = False
    total_relations: int = 0
    temporal_capability: TemporalCapability



def _ordinal(chapter: int | None) -> int | None:
    """A CHAPTER number onto the reading axis — `chapter × EVENT_ORDER_CHAPTER_STRIDE`.

    🔴 **The half of T48s that a green conformance suite could not catch.** The port's window
    was added and every adapter honoured it, and the live endpoint then returned ZERO edges at
    every position — because the route passed `as_of_chapter=1` straight through while the
    stored `valid_from_ordinal` values are `1_000_000, 2_000_000, …`. `valid_from_ordinal <= 1`
    excludes everything.

    An empty answer is the SAFE direction, which is exactly why it is dangerous: it looks like
    "this reader may see nothing yet" rather than "the units are wrong", and this repo has the
    failure written down already — *the reading axis is `sort_order × 1e6`; a raw chapter
    number gives an empty snapshot that looks like missing data*.

    `internal_timeline` has always done this (`before_order = chapter_order × STRIDE`). This
    route accepted the same unit in its parameter name — `as_of_chapter` — and never converted,
    because until now it never used the value at all.
    """
    return None if chapter is None else chapter * EVENT_ORDER_CHAPTER_STRIDE


@router.get("/{book_id}/kg/neighborhood", response_model=NeighborhoodResponse)
async def get_kg_neighborhood(
    book_id: UUID,
    entity_id: str = Query(..., description="the GLOSSARY entity id to centre on"),
    hops: int = Query(1, ge=1, description="traversal depth; only 1 is implemented"),
    cap: int = Query(_DEFAULT_CAP, ge=1, description="max edges returned"),
    as_of_chapter: int | None = Query(None, description="story position, honoured only if the KG is migrated"),
) -> NeighborhoodResponse:
    """One entity plus its capped one-hop neighbourhood, as edges."""
    # `hops` is REJECTED rather than silently narrowed. The graph port is one-hop by
    # construction, so answering a 2-hop request with 1-hop edges would hand back a truthful
    # -looking subgraph that quietly omits half of what was asked for — and a caller building
    # a context block from it has no way to notice. The contract has been narrowed to match
    # what exists (`maximum: 1`) rather than the endpoint pretending to meet it.
    if hops != 1:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"hops={hops} is not implemented; this endpoint traverses exactly 1 hop",
        )
    capped = min(cap, _MAX_CAP)

    caps = temporal_capability()
    # Drop rather than raise when the KG cannot honour a story position: a caller asking for
    # one mid-migration is the normal state, not a client error, and `temporal_capability.kg`
    # in the response is how it learns the answer came back untimed (T26).
    effective_as_of = kg_as_of_or_drop(as_of_chapter)
    if as_of_chapter is not None and effective_as_of is None:
        logger.debug(
            "kg/neighborhood: as_of_chapter=%s dropped — kg capability is %s",
            as_of_chapter, caps["kg"],
        )

    row = await get_knowledge_pool().fetchrow(_PROJECT_SQL, book_id)
    if row is None:
        logger.debug("kg/neighborhood: book %s has no live knowledge project", book_id)
        return NeighborhoodResponse(temporal_capability=caps)

    from app.config import settings

    if not settings.neo4j_uri:
        # Track 1 (no graph configured) — the same skip every KG-touching path makes.
        logger.debug("kg/neighborhood: NEO4J_URI unset — answering empty for book %s", book_id)
        return NeighborhoodResponse(temporal_capability=caps)

    # T17 — through the GraphStore PORT, not `graph_repos`. This endpoint asks a pure
    # domain question ("one entity plus its capped one-hop neighbourhood") that the port
    # already answers, so binding it to the Neo4j repository layer bought nothing and cost
    # substitutability: T43 chooses the engine on measurement, and an operation reachable
    # only through the concrete layer produces no shadow observations to measure.
    from app.adapters.graph_store_provider import get_graph_store
    from app.db.neo4j import graph_session

    async with graph_session() as session:
        detail = await get_graph_store(session).neighborhood(
            user_id=str(row["user_id"]),
            glossary_entity_id=entity_id,
            project_id=str(row["project_id"]),
            rel_cap=capped,
            # T48s — this value was COMPUTED and DISCARDED. `effective_as_of` existed on
            # line 126, was checked for None on 127, and reached nothing: the port had no
            # parameter for it. Meanwhile the response advertised
            # `temporal_capability.kg = "ordinal_valid_time"`, so the endpoint claimed a
            # spoiler window it did not apply.
            as_of=_ordinal(effective_as_of),
        )
    if detail is None:
        logger.debug("kg/neighborhood: no KG node for glossary entity %s", entity_id)
        return NeighborhoodResponse(temporal_capability=caps)

    edges = [
        Edge(
            predicate=r.predicate,
            from_entity=r.subject_id,
            to_entity=r.object_id,
            valid_from_ordinal=r.valid_from_ordinal,
            valid_to_ordinal=r.valid_to_ordinal,
        )
        for r in detail.relations
    ]
    return NeighborhoodResponse(
        edges=edges,
        truncated=detail.relations_truncated,
        total_relations=detail.total_relations,
        temporal_capability=caps,
    )
