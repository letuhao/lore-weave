"""In-memory `GraphStore` for tests (plan T18).

The biggest of the three fakes, and the one T20's ~561 tests will lean on hardest. Same
rule as the others: it enforces the CONTRACT, not the signatures. Specifically —

  - **tenant scoping on every read.** A fake that ignored `user_id` would let a
    cross-tenant read pass every test in the suite.
  - **archived entities excluded by default.** A resolver that matched an archived entity
    silently re-anchors extraction onto something the author deleted.
  - **the as-of rule, including its edge case.** A positionless edge is EXCLUDED by an
    as-of read. Cypher gets that free from three-valued logic; Python does not, and a fake
    that let `None` through would make the untimed-legacy-data bug invisible until
    production.
  - **half-open intervals.** `valid_from <= N < valid_to`. An off-by-one here is exactly
    the class of bug the whole refactor exists to remove, so the fake must not smooth it.

Identity mirrors the real store: an entity is keyed by its canonical id, so
`resolve_or_merge_entity` on an existing name RETURNS it rather than minting a duplicate.
A fake that appended would hide every idempotency bug in the resolver.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from loreweave_extraction.canonical import canonicalize_entity_name, entity_canonical_id
from app.db.neo4j_repos.entities import Entity, EntityDetail
from app.db.neo4j_repos.events import Event
from app.db.neo4j_repos.relations import Relation
from app.ports.graph_store import EventAxis, RelationDirection

logger = logging.getLogger(__name__)

__all__ = ["FakeGraphStore"]


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeGraphStore:
    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._relations: list[Relation] = []
        self._events: list[Event] = []
        # (user, project, entity_id) -> [(from_order, status)], newest-wins at a position.
        self._statuses: dict[tuple[str, str | None, str], list[tuple[int, str, int]]] = {}

    # ── test affordances (not part of the port) ──────────────────────

    def add_event(self, event: Event) -> None:
        self._events.append(event)

    def set_status(
        self, *, user_id: str, project_id: str | None, entity_id: str,
        from_order: int, status: str, evidence: int = 1,
    ) -> None:
        self._statuses.setdefault((user_id, project_id, entity_id), []).append(
            (from_order, status, evidence)
        )

    def entity_count(self) -> int:
        return len(self._entities)

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
        # The REAL canonical id function, not a fake scheme: the id is a hash of
        # (user, project, name, kind), and tests elsewhere assert on it. A fake with its
        # own identity would agree with nothing.
        canonical = canonicalize_entity_name(name)
        eid = entity_canonical_id(
            user_id=user_id, project_id=project_id, name=canonical, kind=kind,
        )
        existing = self._entities.get(eid)
        if existing is not None:
            # Idempotent, and the ON MATCH semantics are copied from the real MERGE rather
            # than guessed. QC-2's parity diff caught three of these missing on its FIRST
            # run — the fake was returning a well-formed entity that simply was not the one
            # the real store produces, and every unit test using it agreed with the fake.
            if source_type and source_type not in existing.source_types:
                existing.source_types.append(source_type)
            # aliases accumulate the name, UNLESS a human edited them — the extractor must
            # not silently undo a user's edit.
            if not getattr(existing, "user_edited", False) and name not in existing.aliases:
                existing.aliases.append(name)
            # confidence is a HIGH-WATER MARK: a lower-confidence re-observation never
            # lowers it.
            if confidence > existing.confidence:
                existing.confidence = confidence
            # NOTE: `provenances` is written by the Cypher but is NOT a field on the
            # Entity model, so it never crosses this boundary. Mirroring it here would be
            # inventing state the real store's RETURN cannot produce.
            existing.version = (existing.version or 1) + 1
            return existing
        entity = Entity(
            id=eid, user_id=user_id, project_id=project_id, name=name,
            canonical_name=canonical, kind=kind, source_types=[source_type],
            # ON CREATE seeds aliases with the name itself — an entity is always an alias
            # of its own name, and a fake that started empty made every alias-resolution
            # test agree with a graph that does not exist.
            aliases=[name],
            confidence=confidence, version=1, auto_created=auto_created,
            created_at=_now(), updated_at=_now(),
        )
        self._entities[eid] = entity
        return entity

    async def find_entities_by_name(
        self,
        *,
        user_id: str,
        project_id: str | None,
        name: str,
        include_archived: bool = False,
        exclude_project_ids: list[str] | None = None,
    ) -> list[Entity]:
        wanted = canonicalize_entity_name(name)
        excluded = set(exclude_project_ids or ())
        out = []
        for e in self._entities.values():
            if e.user_id != user_id or e.canonical_name != wanted:
                continue
            if project_id is not None and e.project_id != project_id:
                continue
            if e.project_id in excluded:
                continue
            if not include_archived and getattr(e, "archived_at", None) is not None:
                continue
            out.append(e)
        return out

    async def neighborhood(
        self,
        *,
        user_id: str,
        glossary_entity_id: str,
        project_id: str | None = None,
        rel_cap: int = 50,
    ) -> EntityDetail | None:
        anchor = next(
            (e for e in self._entities.values()
             if e.user_id == user_id and e.glossary_entity_id == glossary_entity_id
             and (project_id is None or e.project_id == project_id)),
            None,
        )
        if anchor is None:
            return None
        edges = [
            r for r in self._relations
            if r.user_id == user_id and (r.subject_id == anchor.id or r.object_id == anchor.id)
            and r.valid_until is None
        ]
        # The cap is applied, not ignored: it is what stops a hub entity's neighbourhood
        # eating a prompt budget, and a fake that returned everything would let an
        # unbounded context block pass every test.
        return EntityDetail(entity=anchor, relations=edges[:rel_cap])

    async def archive_entity(
        self, *, user_id: str, canonical_id: str, reason: str,
    ) -> Entity | None:
        e = self._entities.get(canonical_id)
        if e is None or e.user_id != user_id:
            return None
        e.archived_at = _now()
        # `archive_reason`, not `archived_reason` — the real model's spelling. A fake that
        # invented a field name would fail only when a test read it back.
        e.archive_reason = reason
        return e

    async def restore_entity(self, *, user_id: str, canonical_id: str) -> Entity | None:
        e = self._entities.get(canonical_id)
        if e is None or e.user_id != user_id:
            return None
        e.archived_at = None
        e.archive_reason = None
        return e

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
        for r in self._relations:
            if (r.user_id == user_id and r.subject_id == subject_id
                    and r.predicate == predicate and r.object_id == object_id
                    and r.valid_until is None):
                r.confidence = max(r.confidence, confidence)
                if source_event_id and source_event_id not in r.source_event_ids:
                    r.source_event_ids.append(source_event_id)
                return r
        rel = Relation(
            id=f"{subject_id}|{predicate}|{object_id}",
            user_id=user_id, subject_id=subject_id, predicate=predicate,
            object_id=object_id, confidence=confidence,
            source_event_ids=[source_event_id] if source_event_id else [],
            valid_from_ordinal=valid_from_ordinal, created_at=_now(), updated_at=_now(),
        )
        self._relations.append(rel)
        return rel

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
        out: list[Relation] = []
        for r in self._relations:
            if r.user_id != user_id or r.valid_until is not None:
                continue
            if r.confidence < min_confidence:
                continue
            if direction == "outgoing" and r.subject_id != entity_id:
                continue
            if direction == "incoming" and r.object_id != entity_id:
                continue
            if direction == "both" and entity_id not in (r.subject_id, r.object_id):
                continue
            # An edge to an ARCHIVED peer is excluded (the repo's
            # `include_archived_peer=False` default).
            #
            # 🐞 MISSING until 2026-08-12, and this fake is what ~561 tests lean on (T20) —
            # so every one of them could see a relation to an entity the author archived,
            # while production would not. Found by T43's property-based differential run
            # catching it in the AGE adapter, then by the conformance rule added alongside
            # the fix catching it HERE too. A fake that is more permissive than the real
            # adapters does not merely miss bugs; it teaches its tests the wrong contract.
            peer_id = r.object_id if r.subject_id == entity_id else r.subject_id
            peer = self._entities.get(peer_id)
            if peer is not None and peer.archived_at is not None:
                continue
            if as_of is not None:
                # A POSITIONLESS edge is excluded. Cypher gets this from three-valued
                # logic (`NULL <= N` is NULL, not true); Python must say it, and a fake
                # that let None through would hide untimed legacy data leaking into a
                # timed answer until production.
                if r.valid_from_ordinal is None:
                    continue
                if r.valid_from_ordinal > as_of:
                    continue
                # Half-open: `valid_to_ordinal == as_of` means the edge has already ENDED.
                if r.valid_to_ordinal is not None and as_of >= r.valid_to_ordinal:
                    continue
            out.append(r)
        out.sort(key=lambda r: (-r.confidence, r.predicate))
        return out[:limit]

    # ── status ───────────────────────────────────────────────────────

    async def status_at_order(
        self,
        *,
        user_id: str,
        project_id: str | None,
        entity_ids: list[str],
        at_order: int,
        min_evidence: int = 1,
    ) -> dict[str, str]:
        out: dict[str, str] = {}
        for eid in entity_ids:
            rows = self._statuses.get((user_id, project_id, eid), [])
            # The LATEST status established at or before the position wins — a status is a
            # step function, not an interval, so "most recent <= N" is the whole rule.
            applicable = [
                (order, status) for order, status, evidence in rows
                if order <= at_order and evidence >= min_evidence
            ]
            if applicable:
                out[eid] = max(applicable, key=lambda t: t[0])[1]
        return out

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
        key = {
            "narrative": "event_order",
            "chronological": "chronological_order",
            "date": "event_date_iso",
        }[axis]

        out: list[Event] = []
        for e in self._events:
            if e.user_id != user_id:
                continue
            if project_id is not None and e.project_id != project_id:
                continue
            if not include_archived and getattr(e, "archived_at", None) is not None:
                continue
            value = getattr(e, key, None)
            # An event with no value on the requested axis is not IN a window on that axis.
            # The real store sinks it last via a null-sentinel; either way a bounded query
            # must not return it, or "events between 10 and 20" includes the undated ones.
            if value is None:
                if after is not None or before is not None:
                    continue
                out.append(e)
                continue
            if after is not None and value < after:
                continue
            if before is not None and value > before:
                continue
            out.append(e)

        out.sort(key=lambda e: (getattr(e, key, None) is None, getattr(e, key, None) or 0
                                if key != "event_date_iso" else (getattr(e, key, None) or "")))
        return out[:limit]
