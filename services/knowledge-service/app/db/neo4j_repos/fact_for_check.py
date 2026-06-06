"""A2-S2 — `fact-for-check` read: the canon snapshot a composition draft is
checked against at a story position.

Given a set of entity ids and a reading-axis position `at_order` (an
`event_order`, the same scale the composition packer's spoiler window uses),
returns everything A2-S3's SCORE-style symbolic guard + LLM-judge need to ask
*"is entity E in a contradicted status at P?"*:

  - **status** — the position-aware `active`/`gone` per entity (A2-S1
    `status_at_order`); the symbolic SCORE signal (a `gone` entity acting is a
    hard contradiction).
  - **entities** — id → name/canonical_name/kind, so the guard can map draft
    mentions onto the checked entity set.
  - **relations** — current valid relations for the set (supporting context for
    the LLM-judge). NOTE: relations carry datetime validity (`valid_until`), a
    DIFFERENT axis from `event_order`, so they are NOT position-windowed here —
    "current canon relations", documented, not a bug.
  - **events** — events with `event_order ≤ P` that involve the entity set (the
    timeline up to the check position), newest-first.

Read-only; K11.4 user-scoped + project-scoped throughout. No mutation, no
evidence change.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read
from app.db.neo4j_repos.entity_status import status_at_order
from app.db.neo4j_repos.relations import find_relations_for_entity

logger = logging.getLogger(__name__)

__all__ = [
    "FactCheckEntity",
    "FactCheckRelation",
    "FactCheckEvent",
    "FactForCheck",
    "get_fact_for_check",
]


class FactCheckEntity(BaseModel):
    entity_id: str
    glossary_entity_id: str | None = None  # FK back to the glossary id (the cast id)
    name: str | None = None
    canonical_name: str | None = None
    kind: str | None = None
    status: str = "active"  # position-aware status at `at_order`


class FactCheckRelation(BaseModel):
    subject_id: str
    predicate: str
    object_id: str
    subject_name: str | None = None
    object_name: str | None = None
    confidence: float = 0.0


class FactCheckEvent(BaseModel):
    event_id: str
    title: str | None = None
    summary: str | None = None
    event_order: int | None = None
    participants: list[str] = Field(default_factory=list)


class FactForCheck(BaseModel):
    at_order: int
    entities: list[FactCheckEntity] = Field(default_factory=list)
    relations: list[FactCheckRelation] = Field(default_factory=list)
    events: list[FactCheckEvent] = Field(default_factory=list)


_ENTITIES_BY_ID_CYPHER = """
UNWIND $entity_ids AS eid
MATCH (e:Entity {id: eid})
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
RETURN e.id AS id, e.glossary_entity_id AS glossary_entity_id, e.name AS name,
       e.canonical_name AS canonical_name, e.kind AS kind
"""

# A2-S3 — resolve composition's cast (glossary entity_ids) to knowledge :Entity
# ids via the glossary_entity_id FK. The composition guard holds glossary ids
# (suggest-cast), not knowledge canonical_ids.
_RESOLVE_GLOSSARY_IDS_CYPHER = """
UNWIND $glossary_entity_ids AS gid
MATCH (e:Entity {user_id: $user_id, glossary_entity_id: gid})
WHERE ($project_id IS NULL OR e.project_id = $project_id)
RETURN e.id AS id
"""

# Events at or before the check position whose participants include any of the
# entity-set's names (case-insensitive). Participants are stored as display
# strings, so the match is toLower equality against the entity name + canonical
# name set — honorific-variant participants are a known miss (coarse V1).
_EVENTS_AT_OR_BEFORE_CYPHER = """
UNWIND $names AS nm
MATCH (e:Event)
WHERE e.user_id = $user_id
  AND ($project_id IS NULL OR e.project_id = $project_id)
  AND e.event_order IS NOT NULL
  AND e.event_order <= $at_order
  AND any(p IN coalesce(e.participants, []) WHERE toLower(p) = nm)
WITH DISTINCT e
RETURN e.id AS id, e.title AS title, e.summary AS summary,
       e.event_order AS event_order, e.participants AS participants
ORDER BY e.event_order DESC
LIMIT $limit
"""


async def get_fact_for_check(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    entity_ids: list[str] | None = None,
    glossary_entity_ids: list[str] | None = None,
    at_order: int,
    min_evidence: int = 1,
    relation_limit: int = 50,
    event_limit: int = 50,
) -> FactForCheck:
    """Assemble the canon snapshot for the entity set at reading position
    `at_order`. The set is given as knowledge `:Entity` ids (`entity_ids`)
    and/or composition glossary ids (`glossary_entity_ids`, resolved via the
    `glossary_entity_id` FK). See module docstring."""
    if not isinstance(at_order, int):
        raise ValueError("at_order must be an int (reading-axis event_order)")
    ids = list(dict.fromkeys(entity_ids or []))

    # A2-S3 — resolve composition's glossary cast ids → knowledge :Entity ids.
    if glossary_entity_ids:
        gres = await run_read(
            session, _RESOLVE_GLOSSARY_IDS_CYPHER,
            user_id=user_id, project_id=project_id,
            glossary_entity_ids=list(dict.fromkeys(glossary_entity_ids)),
        )
        async for rec in gres:
            if rec["id"] not in ids:
                ids.append(rec["id"])

    if not ids:
        return FactForCheck(at_order=at_order)

    # 1. position-aware status (default 'active' for ids with no transition).
    status_map = await status_at_order(
        session, user_id=user_id, project_id=project_id,
        entity_ids=ids, at_order=at_order, min_evidence=min_evidence,
    )

    # 2. entity metadata (name/canonical_name/kind).
    ent_result = await run_read(
        session, _ENTITIES_BY_ID_CYPHER,
        user_id=user_id, project_id=project_id, entity_ids=ids,
    )
    meta: dict[str, dict] = {}
    names: set[str] = set()
    async for rec in ent_result:
        meta[rec["id"]] = {
            "glossary_entity_id": rec["glossary_entity_id"],
            "name": rec["name"],
            "canonical_name": rec["canonical_name"],
            "kind": rec["kind"],
        }
        for v in (rec["name"], rec["canonical_name"]):
            if v:
                names.add(v.lower())

    entities = [
        FactCheckEntity(
            entity_id=eid,
            glossary_entity_id=meta.get(eid, {}).get("glossary_entity_id"),
            name=meta.get(eid, {}).get("name"),
            canonical_name=meta.get(eid, {}).get("canonical_name"),
            kind=meta.get(eid, {}).get("kind"),
            status=status_map.get(eid, "active"),
        )
        for eid in ids
    ]

    # 3. current valid relations for the set (deduped; capped).
    seen_rel: set[tuple[str, str, str]] = set()
    relations: list[FactCheckRelation] = []
    for eid in ids:
        if len(relations) >= relation_limit:
            break
        rels = await find_relations_for_entity(
            session, user_id=user_id, entity_id=eid, project_id=project_id,
            limit=relation_limit,
        )
        for r in rels:
            key = (r.subject_id, r.predicate, r.object_id)
            if key in seen_rel:
                continue
            seen_rel.add(key)
            relations.append(FactCheckRelation(
                subject_id=r.subject_id, predicate=r.predicate,
                object_id=r.object_id, subject_name=r.subject_name,
                object_name=r.object_name, confidence=r.confidence,
            ))
            if len(relations) >= relation_limit:
                break

    # 4. events at/before P involving the set (newest-first).
    events: list[FactCheckEvent] = []
    if names:
        ev_result = await run_read(
            session, _EVENTS_AT_OR_BEFORE_CYPHER,
            user_id=user_id, project_id=project_id,
            names=sorted(names), at_order=at_order, limit=event_limit,
        )
        async for rec in ev_result:
            events.append(FactCheckEvent(
                event_id=rec["id"], title=rec["title"], summary=rec["summary"],
                event_order=rec["event_order"],
                participants=list(rec["participants"] or []),
            ))

    return FactForCheck(
        at_order=at_order, entities=entities,
        relations=relations, events=events,
    )
