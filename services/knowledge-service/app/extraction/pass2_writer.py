"""K17.8 — Pass 2 (LLM) extraction writer.

Maps LLM extraction candidates from K17.4–K17.7 to K11 Neo4j repository
calls with provenance tracking via EVIDENCED_BY edges.

**Relationship to K15.7 (Pass 1 writer):**
  - K15.7 writes pattern-extracted data with ``pending_validation=True``
    (quarantine).
  - K17.8 writer writes LLM-extracted data with ``pending_validation=False``
    (trusted).

**Key invariant:** every persisted text field goes through
``neutralize_injection`` before hitting Neo4j.

**Entity ID resolution:** K17.4–K17.7 candidates already carry
``canonical_id`` from the extraction step. The writer merges entities
first, then validates that relation endpoints / event participants /
fact subjects reference actually-merged entity IDs before creating
downstream edges. Unresolvable endpoints are skipped and counted.

Dependencies: K11.5 (entities), K11.6 (relations), K11.7 (events,
facts), K11.8 (provenance).

Reference: KSA §5.2, K17.8 plan row in
KNOWLEDGE_SERVICE_TRACK2_IMPLEMENTATION.md.
"""

from __future__ import annotations

import logging

from pydantic import BaseModel

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.events import merge_event
from app.db.neo4j_repos.facts import merge_fact
from app.db.repositories.entity_alias_map import EntityAliasMapRepo
from app.db.neo4j_repos.provenance import add_evidence, upsert_extraction_source
from app.db.neo4j_repos.relations import create_relation
from app.extraction.anchor_loader import Anchor
from app.extraction.entity_resolver import (
    build_anchor_index,
    resolve_or_merge_entity,
)
from app.extraction.injection_defense import neutralize_injection
from app.extraction.llm_entity_extractor import LLMEntityCandidate
from app.extraction.llm_event_extractor import LLMEventCandidate
from app.extraction.llm_fact_extractor import LLMFactCandidate
from app.extraction.llm_relation_extractor import LLMRelationCandidate

__all__ = [
    "Pass2WriteResult",
    "write_pass2_extraction",
]

logger = logging.getLogger(__name__)


class Pass2WriteResult(BaseModel):
    """Summary of what the Pass 2 writer persisted."""

    source_id: str
    entities_merged: int = 0
    relations_created: int = 0
    events_merged: int = 0
    facts_merged: int = 0
    evidence_edges: int = 0
    skipped_missing_endpoint: int = 0


def _sanitize(text: str, project_id: str | None) -> str:
    """Injection-sanitize a text field before persisting.

    KSA §5.1.5 Defense 2 (extraction-time). See K15.6
    ``neutralize_injection`` for the pattern set and
    ``tests/unit/test_pass2_writer.py`` K17.9 section for
    regression coverage on every persisted text field.
    """
    cleaned, _ = neutralize_injection(text, project_id=project_id)
    return cleaned


async def write_pass2_extraction(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    source_type: str,
    source_id: str,
    job_id: str,
    entities: list[LLMEntityCandidate] | None = None,
    relations: list[LLMRelationCandidate] | None = None,
    events: list[LLMEventCandidate] | None = None,
    facts: list[LLMFactCandidate] | None = None,
    extraction_model: str = "llm-v1",
    anchors: list[Anchor] | None = None,
    alias_map_repo: EntityAliasMapRepo | None = None,
) -> Pass2WriteResult:
    """Persist Pass 2 LLM extraction candidates to Neo4j.

    All candidate lists are optional — the writer persists whatever
    is provided. This supports running extractors individually (e.g.
    entities only) or all together.

    Args:
        session: K11.4 CypherSession (multi-tenant guarded).
        user_id: tenant id.
        project_id: optional project scope.
        source_type: K11.8 source type (``"chapter"`` / ``"chat_message"``).
        source_id: natural key of the source.
        job_id: unique per extraction run — dedupes evidence edges.
        entities: K17.4 entity candidates.
        relations: K17.5 relation candidates.
        events: K17.6 event candidates.
        facts: K17.7 fact candidates.
        extraction_model: tag for evidence edges.

    Returns:
        Pass2WriteResult with per-kind counters.
    """
    entity_list = entities or []
    relation_list = relations or []
    event_list = events or []
    fact_list = facts or []

    # K13.0 resolver: pre-build anchor index. Empty (default) preserves
    # pre-K13.0 behavior where every candidate mints a new :Entity.
    anchor_index = build_anchor_index(anchors or [])

    # Step 1 — upsert provenance source (idempotent).
    source = await upsert_extraction_source(
        session,
        user_id=user_id,
        project_id=project_id,
        source_type=source_type,
        source_id=source_id,
    )

    entities_merged = 0
    evidence_edges = 0
    merged_entity_ids: set[str] = set()

    # Step 2 — merge entities.
    for ent in entity_list:
        name_clean = _sanitize(ent.name, project_id)
        if not name_clean.strip():
            continue
        # NOTE: ``ent.aliases`` is intentionally dropped here — K11.5
        # ``merge_entity`` does not yet accept an ``aliases`` parameter.
        # Alias persistence is tracked for K18+. See K17.9 negative
        # assertion tests pinning this behavior.
        entity = await resolve_or_merge_entity(
            session,
            anchor_index,
            user_id=user_id,
            project_id=project_id,
            name=name_clean,
            kind=ent.kind,
            source_type=source_type,
            confidence=ent.confidence,
            alias_map_repo=alias_map_repo,
        )
        merged_entity_ids.add(entity.id)
        entities_merged += 1

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Entity",
            target_id=entity.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=ent.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    skipped = 0

    # Step 3 — create relations.
    relations_created = 0
    for rel in relation_list:
        if not rel.subject_id or not rel.object_id:
            skipped += 1
            continue
        if rel.subject_id not in merged_entity_ids or rel.object_id not in merged_entity_ids:
            skipped += 1
            continue

        # Predicate is pre-normalized by K17.5 `_normalize_predicate`
        # (`[^\w]+` → `_`), which already strips most English injection
        # markers. CJK (e.g. `无视指令`) survives normalization because
        # CJK characters are `\w` in Python 3, so sanitize is still
        # load-bearing — see K17.9 predicate CJK test.
        predicate_clean = _sanitize(rel.predicate, project_id)
        result = await create_relation(
            session,
            user_id=user_id,
            subject_id=rel.subject_id,
            predicate=predicate_clean,
            object_id=rel.object_id,
            confidence=rel.confidence,
            source_event_id=source.id,
            pending_validation=False,
        )
        if result is not None:
            relations_created += 1
        else:
            skipped += 1

    # Step 4 — merge events.
    events_merged = 0
    for evt in event_list:
        name_clean = _sanitize(evt.name, project_id)
        summary_clean = _sanitize(evt.summary, project_id)
        if not name_clean.strip():
            continue

        # NOTE: ``evt.location`` and ``evt.time_cue`` are intentionally
        # dropped here — K11.7 ``merge_event`` does not yet accept
        # these parameters. Tracked for K18+. See K17.9 negative
        # assertion test pinning this behavior.
        # C18: ``evt.event_date`` IS threaded — it's the structured
        # filter axis for the timeline endpoint's date-range Query.
        event = await merge_event(
            session,
            user_id=user_id,
            project_id=project_id,
            title=name_clean,
            summary=summary_clean or None,
            event_date_iso=evt.event_date,
            participants=[
                _sanitize(p, project_id) for p in evt.participants
            ],
            source_type=source_type,
            confidence=evt.confidence,
        )
        events_merged += 1

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Event",
            target_id=event.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=evt.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    # Step 5 — merge facts.
    facts_merged = 0
    for fact in fact_list:
        content_clean = _sanitize(fact.content, project_id)
        if not content_clean.strip():
            continue

        # NOTE: ``fact.subject`` and ``fact.subject_id`` are intentionally
        # dropped here — K11.7 ``merge_fact`` does not yet accept a
        # subject. Tracked for K18+. Additionally, ``fact.fact_id`` is
        # treated as advisory: K11.7 ``merge_fact`` derives its own ID
        # from the sanitized content hash, not the candidate's raw-
        # content-derived ``fact_id``. See K17.9 negative assertion test.
        f = await merge_fact(
            session,
            user_id=user_id,
            project_id=project_id,
            type=fact.type,
            content=content_clean,
            confidence=fact.confidence,
            pending_validation=False,
            source_type=source_type,
        )
        facts_merged += 1

        ev = await add_evidence(
            session,
            user_id=user_id,
            target_label="Fact",
            target_id=f.id,
            source_id=source.id,
            extraction_model=extraction_model,
            confidence=fact.confidence,
            job_id=job_id,
        )
        if ev is not None and ev.created:
            evidence_edges += 1

    return Pass2WriteResult(
        source_id=source.id,
        entities_merged=entities_merged,
        relations_created=relations_created,
        events_merged=events_merged,
        facts_merged=facts_merged,
        evidence_edges=evidence_edges,
        skipped_missing_endpoint=skipped,
    )
