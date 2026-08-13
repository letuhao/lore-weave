"""Neo4j implementation of the `GraphStore` port (plan T18).

Delegates to `neo4j_repos`, like the vector and ontology adapters, for the same reason:
the repos hold the `run_read`/`run_write` tenancy guards, and a second copy of a tenant
filter is how the two drift.

What this file owns is the translation between the port's vocabulary and the repos':

  - `events_in_window(axis=…)` routes to a different repo function per axis. `narrative`
    uses the cheap ordinal query; `chronological` and `date` need the filtered one, which
    also returns a total count this port drops — a count belongs to a paginated browse,
    not to "give me the events in this window".
  - `relations_for(as_of=…)` forwards to the repo's new `as_of_ordinal`. The port's name
    is the domain word; the repo's says which axis, because the repo also has a wall-clock
    `valid_until`.
"""

from __future__ import annotations

from datetime import datetime

import logging
import time

from app.db.neo4j_helpers import CypherSession
from app.db.neo4j_repos.provenance import EvidenceWriteResult, add_evidence
from app.db.neo4j_repos.entities import (
    Entity,
    EntityDetail,
    archive_entity,
    find_entities_by_name,
    get_neighborhood_by_glossary_id,
    merge_entity,
    restore_entity,
)
from app.db.neo4j_repos.entity_status import status_at_order
from app.db.neo4j_repos.events import Event, list_events_filtered, list_events_in_order
from app.db.neo4j_repos import events as _event_repo
from app.db.neo4j_repos import relations as _rel_repo
from app.db.neo4j_repos.relations import Relation, create_relation, find_relations_for_entity
from app.ports.graph_store import EventAxis, RelationDirection

logger = logging.getLogger(__name__)

__all__ = ["Neo4jGraphStore"]


class Neo4jGraphStore:
    def __init__(self, session: CypherSession) -> None:
        self._session = session

    # ── entities ─────────────────────────────────────────────────────

    async def resolve_or_merge_entity(
        self,
        *,
        user_id: str,
        project_id: str | None,
        name: str,
        kind: str,
        source_type: str,
        confidence: float = 0.0,
        auto_created: bool = False,
        provenance: str = "human_authored",
        job_id: str | None = None,
    ) -> Entity:
        return await merge_entity(
            self._session,
            user_id=user_id, project_id=project_id, name=name, kind=kind,
            source_type=source_type, confidence=confidence,
            auto_created=auto_created, provenance=provenance, job_id=job_id,
        )

    async def find_entities_by_name(
        self,
        *,
        user_id: str,
        project_id: str | None,
        name: str,
        include_archived: bool = False,
        exclude_project_ids: list[str] | None = None,
    ) -> list[Entity]:
        return await find_entities_by_name(
            self._session,
            user_id=user_id, project_id=project_id, name=name,
            include_archived=include_archived, exclude_project_ids=exclude_project_ids,
        )

    async def neighborhood(
        self,
        *,
        user_id: str,
        glossary_entity_id: str,
        project_id: str | None = None,
        rel_cap: int = 50,
    ) -> EntityDetail | None:
        started = time.perf_counter()
        detail = await get_neighborhood_by_glossary_id(
            self._session,
            user_id=user_id, glossary_entity_id=glossary_entity_id,
            project_id=project_id, rel_cap=rel_cap,
        )
        logger.debug(
            "graph neighborhood: backend=neo4j cap=%d found=%s elapsed_ms=%d",
            rel_cap, detail is not None, int((time.perf_counter() - started) * 1000),
        )
        return detail

    async def archive_entity(
        self, *, user_id: str, canonical_id: str, reason: str,
    ) -> Entity | None:
        return await archive_entity(
            self._session, user_id=user_id, canonical_id=canonical_id, reason=reason,
        )

    async def restore_entity(self, *, user_id: str, canonical_id: str) -> Entity | None:
        return await restore_entity(
            self._session, user_id=user_id, canonical_id=canonical_id,
        )

    # ── relations ────────────────────────────────────────────────────

    async def upsert_relation(
        self,
        *,
        user_id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        confidence: float = 0.0,
        source_event_id: str | None = None,
        valid_from_ordinal: int | None = None,
    ) -> Relation:
        return await create_relation(
            self._session,
            user_id=user_id,
            subject_id=subject_id, predicate=predicate, object_id=object_id,
            confidence=confidence, source_event_id=source_event_id,
            valid_from_ordinal=valid_from_ordinal,
        )

    async def get_relation(self, *, user_id: str, relation_id: str) -> Relation | None:
        return await _rel_repo.get_relation(
            self._session, user_id=user_id, relation_id=relation_id)

    async def invalidate_relation(
        self, *, user_id: str, relation_id: str, valid_until: datetime | None = None,
    ) -> Relation | None:
        return await _rel_repo.invalidate_relation(
            self._session, user_id=user_id, relation_id=relation_id,
            valid_until=valid_until)

    async def recreate_relation(
        self,
        *,
        user_id: str,
        subject_id: str,
        predicate: str,
        object_id: str,
        source_chapter: str | None = None,
        valid_from_ordinal: int | None = None,
    ) -> Relation | None:
        return await _rel_repo.recreate_relation(
            self._session, user_id=user_id, subject_id=subject_id,
            predicate=predicate, object_id=object_id, source_chapter=source_chapter,
            valid_from_ordinal=valid_from_ordinal)

    async def events_page(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        after: int | str | None = None,
        before: int | str | None = None,
        axis: EventAxis = "narrative",
        participants: list[str] | None = None,
        q: str | None = None,
        sort_dir: str = "asc",
        limit: int = 50,
        offset: int = 0,
        exclude_project_ids: list[str] | None = None,
    ) -> tuple[list[Event], int]:
        """A3 — the browse. The repo's filtered query ALREADY returned a total; this file's
        docstring above records that it was being dropped, and now it is not.

        The axis decides which pair of bounds `after`/`before` become, mirroring the repo's
        three-way split rather than aliasing two of them to the cheap one.
        """
        kw: dict = {}
        if axis == "narrative":
            kw["after_order"], kw["before_order"] = after, before
        else:
            kw["after_order"] = kw["before_order"] = None
            if axis == "chronological":
                kw["after_chronological"], kw["before_chronological"] = after, before
            else:  # date
                kw["event_date_from"], kw["event_date_to"] = after, before
        return await _event_repo.list_events_filtered(
            self._session, user_id=user_id, project_id=project_id,
            participant_candidates=participants, q=q, sort_by=axis, sort_dir=sort_dir,
            limit=limit, offset=offset, exclude_project_ids=exclude_project_ids, **kw)

    async def get_event(self, *, user_id: str, event_id: str) -> Event | None:
        return await _event_repo.get_event(
            self._session, user_id=user_id, event_id=event_id)

    async def merge_event(
        self,
        *,
        user_id: str,
        project_id: str | None,
        title: str,
        summary: str | None = None,
        chapter_id: str | None = None,
        event_order: int | None = None,
        chronological_order: int | None = None,
        event_date_iso: str | None = None,
        time_cue: str | None = None,
        participants: list[str] | None = None,
        source_type: str = "book_content",
        confidence: float = 0.0,
    ) -> Event:
        return await _event_repo.merge_event(
            self._session, user_id=user_id, project_id=project_id, title=title,
            summary=summary, chapter_id=chapter_id, event_order=event_order,
            chronological_order=chronological_order, event_date_iso=event_date_iso,
            time_cue=time_cue, participants=participants, source_type=source_type,
            confidence=confidence)

    async def update_event_fields(
        self,
        *,
        user_id: str,
        event_id: str,
        title: str | None,
        summary: str | None,
        time_cue: str | None,
        event_date_iso: str | None,
        expected_version: int,
    ) -> tuple[Event | None, dict | None]:
        return await _event_repo.update_event_fields(
            self._session, user_id=user_id, event_id=event_id, title=title,
            summary=summary, time_cue=time_cue, event_date_iso=event_date_iso,
            expected_version=expected_version)

    async def archive_event(self, *, user_id: str, event_id: str) -> Event | None:
        return await _event_repo.archive_event(
            self._session, user_id=user_id, event_id=event_id)

    async def relations_for(
        self,
        *,
        user_id: str,
        entity_id: str,
        project_id: str | None = None,
        direction: RelationDirection = "both",
        min_confidence: float = 0.8,
        as_of: int | None = None,
        limit: int = 100,
    ) -> list[Relation]:
        started = time.perf_counter()
        out = await find_relations_for_entity(
            self._session,
            user_id=user_id, entity_id=entity_id, project_id=project_id,
            direction=direction, min_confidence=min_confidence,
            # The port says `as_of`; the repo says `as_of_ordinal` because it ALSO has a
            # wall-clock `valid_until`, and a bare `as_of` there would be ambiguous about
            # which of the two axes it meant.
            as_of_ordinal=as_of,
            limit=limit,
        )
        logger.debug(
            "graph relations_for: backend=neo4j direction=%s as_of=%s hits=%d elapsed_ms=%d",
            direction, as_of, len(out), int((time.perf_counter() - started) * 1000),
        )
        return out

    # ── status ───────────────────────────────────────────────────────

    async def add_evidence(
        self,
        *,
        user_id: str,
        target_label: str,
        target_id: str,
        source_id: str,
        extraction_model: str,
        confidence: float,
        job_id: str,
        quote: str | None = None,
    ) -> EvidenceWriteResult | None:
        return await add_evidence(
            self._session,
            user_id=user_id, target_label=target_label, target_id=target_id,
            source_id=source_id, extraction_model=extraction_model,
            confidence=confidence, job_id=job_id, quote=quote,
        )

    async def status_at_order(
        self,
        *,
        user_id: str,
        project_id: str | None,
        entity_ids: list[str],
        at_order: int,
        min_evidence: int = 1,
    ) -> dict[str, str]:
        return await status_at_order(
            self._session,
            user_id=user_id, project_id=project_id, entity_ids=entity_ids,
            at_order=at_order, min_evidence=min_evidence,
        )

    # ── events ───────────────────────────────────────────────────────

    async def events_in_window(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        after: int | str | None = None,
        before: int | str | None = None,
        axis: EventAxis = "narrative",
        include_archived: bool = False,
        limit: int = 200,
    ) -> list[Event]:
        if axis == "narrative":
            # The cheap path, and the default: bounds are authored `event_order`.
            return await list_events_in_order(
                self._session,
                user_id=user_id, project_id=project_id,
                after_order=after, before_order=before,
                include_archived=include_archived, limit=limit,
            )

        kwargs: dict = {
            "after_order": None, "before_order": None,
            "sort_by": "chronological" if axis == "chronological" else "narrative",
        }
        if axis == "chronological":
            kwargs["after_chronological"] = after
            kwargs["before_chronological"] = before
        else:  # date
            kwargs["event_date_from"] = after
            kwargs["event_date_to"] = before

        # `list_events_filtered` returns (rows, total_count). The count is dropped on
        # purpose: it exists for a PAGINATED browse ("page 3 of N"), and this port asks for
        # a window, not a page. Returning it would put a pagination concern into every
        # implementation, including the ones that have no cheap count.
        rows, _total = await list_events_filtered(
            self._session,
            user_id=user_id, project_id=project_id,
            limit=limit, offset=0, **kwargs,
        )
        return rows
