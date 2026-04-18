"""K18.2 — L2 fact selector with intent-driven hop count + temporal grouping.

Runs against Neo4j after the K18.2a intent classifier has extracted
entity names from the user's message. For each mentioned entity:

  - Always: 1-hop relations involving the entity (via
    ``find_relations_for_entity``, both directions, confidence ≥ 0.8,
    excluding pending-validation rows and archived peers).
  - When ``intent.hop_count == 2``: additionally 2-hop traversals
    (via ``find_relations_2hop``) so relational queries surface
    "A knows someone who knows B" paths.
  - Always: negative facts (``:Fact`` nodes with ``type='negation'``)
    touching the mentioned entities so the LLM respects "X does NOT
    know Y"-style guardrails.

**Temporal grouping (Commit 1 simplification).** The full KSA §4.2
spec buckets results into ``<current>``, ``<recent>``,
``<background>``, ``<negative>``. Bucketing by chapter requires the
evidence edges to carry chapter_index, which is not yet wired through
Pass 2. For this commit everything non-negation is placed in
``background`` — the bucketing will be refined in a follow-up once
chapter provenance lands on edges. Negation is still its own bucket.

**Multi-tenant safety.** Every underlying repo call carries ``user_id``
and ``project_id``; the selector does not touch Cypher directly.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.context.intent.classifier import Intent, IntentResult
from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.entities import find_entities_by_name
from app.db.neo4j_repos.facts import list_facts_by_type
from app.db.neo4j_repos.relations import (
    Relation,
    RelationHop,
    find_relations_2hop,
    find_relations_for_entity,
)

logger = logging.getLogger(__name__)

__all__ = ["L2FactResult", "select_l2_facts", "format_relation", "format_relation_hop"]


# Per-selector caps. The formatter will compress beyond this, but the
# Cypher-level limits keep the total payload from blowing up on
# celebrity characters with hundreds of edges.
_MAX_1HOP_PER_ENTITY = 20
_MAX_2HOP_PER_ENTITY = 10
_MAX_NEGATIVES = 15


@dataclass
class L2FactResult:
    """Grouped fact strings ready for the Mode 3 XML formatter.

    Each string is a human-readable fact sentence. The formatter in
    ``modes/full.py`` wraps these in ``<fact>`` elements; deciding
    which sub-block they go into is this selector's job.
    """

    current: list[str] = field(default_factory=list)
    recent: list[str] = field(default_factory=list)
    background: list[str] = field(default_factory=list)
    negative: list[str] = field(default_factory=list)

    def total(self) -> int:
        return (
            len(self.current) + len(self.recent)
            + len(self.background) + len(self.negative)
        )


def format_relation(r: Relation) -> str:
    """Render a 1-hop relation as ``subject - predicate - object``.

    Handles the case where the endpoint names failed to project (e.g.
    relation to an archived entity that slipped through): the relation
    is rendered with ``<unknown>`` placeholders rather than crashing.
    """
    subj = r.subject_name or "<unknown>"
    obj = r.object_name or "<unknown>"
    return f"{subj} — {r.predicate} — {obj}"


def format_relation_hop(hop: RelationHop) -> str:
    """Render a 2-hop path as ``A - p1 - Via - p2 - B``."""
    return (
        f"{hop.hop1.subject_name or '<unknown>'} — "
        f"{hop.hop1.predicate} — "
        f"{hop.via_name} — "
        f"{hop.hop2.predicate} — "
        f"{hop.hop2.object_name or '<unknown>'}"
    )


async def _resolve_entity_ids(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    entity_names: tuple[str, ...],
) -> list[tuple[str, str]]:
    """Look up `(name, canonical_id)` pairs for each mentioned entity.

    Names that don't resolve to any entity are dropped silently —
    absence detection (K18.5) picks them up.
    """
    resolved: list[tuple[str, str]] = []
    for name in entity_names:
        matches = await find_entities_by_name(
            session,
            user_id=user_id,
            project_id=project_id,
            name=name,
        )
        if matches:
            # Prefer the first match (repo orders anchored > discovered).
            resolved.append((name, matches[0].id))
    return resolved


async def select_l2_facts(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    intent: IntentResult,
    min_confidence: float = 0.8,
) -> L2FactResult:
    """Gather L2 fact strings for the intent's entity set.

    Args:
        session: CypherSession (multi-tenant guarded).
        user_id: tenant.
        project_id: project scope — required (Mode 3 is project-only).
        intent: K18.2a result; drives hop count and which entities to
            query.
        min_confidence: default 0.8 (matches KSA §4.2 L2 RAG loader).

    Returns:
        L2FactResult with separate buckets. ``total()`` is zero when
        the intent extracted no entities (nothing to anchor queries
        against) — not an error, just no L2 material.
    """
    result = L2FactResult()
    if not intent.entities:
        return result

    resolved = await _resolve_entity_ids(
        session,
        user_id=user_id,
        project_id=project_id,
        entity_names=intent.entities,
    )
    if not resolved:
        return result

    seen_relations: set[str] = set()

    for _name, entity_id in resolved:
        # 1-hop (always).
        one_hop = await find_relations_for_entity(
            session,
            user_id=user_id,
            project_id=project_id,
            entity_id=entity_id,
            min_confidence=min_confidence,
            limit=_MAX_1HOP_PER_ENTITY,
        )
        for r in one_hop:
            if r.id in seen_relations:
                continue
            seen_relations.add(r.id)
            result.background.append(format_relation(r))

        # 2-hop (relational intent only).
        if intent.hop_count >= 2:
            two_hop = await find_relations_2hop(
                session,
                user_id=user_id,
                project_id=project_id,
                entity_id=entity_id,
                min_confidence=min_confidence,
                limit=_MAX_2HOP_PER_ENTITY,
            )
            for hop in two_hop:
                key = f"{hop.hop1.id}|{hop.hop2.id}"
                if key in seen_relations:
                    continue
                seen_relations.add(key)
                result.background.append(format_relation_hop(hop))

    # Negative facts for the whole project — filtered to those that
    # mention any resolved entity. Negation Facts are cheap to list
    # and small in count (K15.5 extractor output), so a single
    # per-project query plus post-filter is simpler than per-entity
    # Cypher.
    negs = await list_facts_by_type(
        session,
        user_id=user_id,
        project_id=project_id,
        type="negation",
        limit=_MAX_NEGATIVES,
    )
    resolved_names_lower = {n.lower() for n, _ in resolved}
    for fact in negs:
        text = (fact.content or "").strip()
        if not text:
            continue
        if any(name in text.lower() for name in resolved_names_lower):
            result.negative.append(text)

    logger.debug(
        "K18.2: L2 fact selection intent=%s entities=%d resolved=%d "
        "background=%d negative=%d",
        intent.intent.value,
        len(intent.entities),
        len(resolved),
        len(result.background),
        len(result.negative),
    )
    return result
