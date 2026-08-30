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
  - **relations** — the relations that were true AT `at_order` (T36). A role is
    a relation with a story interval, so it is windowed by the same half-open
    convention every other positioned read uses:
    `valid_from_ordinal <= at_order < valid_to_ordinal`.

    This read used to be un-windowed, on the reasoning that "relations carry
    datetime validity (`valid_until`), a DIFFERENT axis from `event_order`".
    That reasoning is **stale**: F3 gave `:RELATES_TO` a story axis
    (`valid_from_ordinal`/`valid_to_ordinal`, stamped on the `event_order`
    scale) and T18 gave `find_relations_for_entity` the `as_of_ordinal`
    parameter to read it. Only the call site was never updated — so a role that
    ENDED at ch.20 still read as live when checking ch.10. Measured on the dev
    graph 2026-08-11: of 905 `:RELATES_TO` edges, **619 carry a story position
    and 175 have already been closed by `maintain_chain`** — 175 ended relations
    that the canon check was being handed as currently true. That is
    `D-CANON-CHECK-BLIND-TO-ROLE` in one number.

    POSITIONLESS edges (`valid_from_ordinal IS NULL` — legacy, or written
    without a chapter position) are EXCLUDED, per T18's stated rule: *"an edge
    that cannot be placed on the axis must not be mixed into an answer whose
    whole value is that it is placed."* They are counted and WARNed rather than
    silently dropped, because on today's graph they are 286 of 905 and a
    caller comparing before/after needs to see where the difference went.
  - **events** — events with `event_order ≤ P` that involve the entity set (the
    timeline up to the check position), newest-first.

Read-only; K11.4 user-scoped + project-scoped throughout. No mutation, no
evidence change.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read
from app.db.graph_repos.entity_status import status_at_order
from app.db.graph_repos.relations import find_relations_for_entity

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
    # T36 — WHICH story interval answered. Part of the contract, not decoration:
    # it is how a judge tells a role established last chapter from one that has
    # held since chapter 1, and how a reader of the payload can see that the
    # window was applied at all. `valid_to_ordinal` is None for an open interval.
    valid_from_ordinal: int | None = None
    valid_to_ordinal: int | None = None


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
  // §10.1 — see `entities._LIST_ENTITIES_FILTER_WHERE`: AGE does not parse `any(… WHERE …)`.
  AND size([p IN coalesce(e.participants, []) WHERE toLower(p) = nm]) > 0
WITH DISTINCT e
RETURN e.id AS id, e.title AS title, e.summary AS summary,
       e.event_order AS event_order, e.participants AS participants
// L2 — `e.id` is the TIE-BREAK, and without it this query is non-deterministic on real
// data. `event_order` is not unique: 51 colliding (project, event_order) pairs stand in
// `g_shared` today, 102 events across 6 projects, all written before the pass2_writer fix
// (b6c8fde13). With a bare `ORDER BY … DESC` in front of a `LIMIT`, which of two colliding
// events survives the cut is whatever the store hands back — so the same canon check can
// see a different evidence set on two runs, and neither run is wrong to look at.
//
// `e.id` rather than `e.title`: two sibling queries in `events.py` tie-break on title, and a
// title is EDITABLE. Ordering history by a field the user can change means renaming an event
// silently reorders the evidence behind a past check. §25 records that divergence rather
// than unifying all four call sites here, which would move public ordering.
ORDER BY e.event_order DESC, e.id DESC
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

    # 3. T36 — the relations that were true AT `at_order` (deduped; capped).
    # `as_of_ordinal=at_order` is the whole fix: the story axis and the parameter
    # that reads it both already existed (F3, T18), and only this call site was
    # left un-windowed. `valid_from_ordinal` is stamped on the `event_order`
    # scale, the same scale `at_order` is on, so the position passes through
    # unscaled — see the module docstring.
    seen_rel: set[tuple[str, str, str]] = set()
    relations: list[FactCheckRelation] = []
    for eid in ids:
        if len(relations) >= relation_limit:
            break
        rels = await find_relations_for_entity(
            session, user_id=user_id, entity_id=eid, project_id=project_id,
            as_of_ordinal=at_order,
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
                valid_from_ordinal=r.valid_from_ordinal,
                valid_to_ordinal=r.valid_to_ordinal,
            ))
            if len(relations) >= relation_limit:
                break

    # T36 diagnostic — an EMPTY windowed result is ambiguous: the set may
    # genuinely have no relations, or every relation it has may be positionless
    # (excluded by the as-of read, per T18's rule) or already closed before
    # `at_order`. Those look identical to a caller and lead to opposite
    # conclusions, so probe once — only in the empty case, so the normal path
    # keeps its query count — and say which it is.
    if not relations:
        unwindowed = 0
        for eid in ids:
            unwindowed += len(await find_relations_for_entity(
                session, user_id=user_id, entity_id=eid, project_id=project_id,
                limit=relation_limit,
            ))
        if unwindowed:
            logger.warning(
                "fact-for-check: no relation is true at at_order=%d, but the "
                "entity set has %d relation(s) off the window — positionless "
                "(no valid_from_ordinal) or closed before this position. The "
                "canon judge sees NO relational context for this check.",
                at_order, unwindowed,
            )

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
