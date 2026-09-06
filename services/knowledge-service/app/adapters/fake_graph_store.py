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
from app.db.graph_repos.entities import Entity, EntityDetail
from app.db.graph_repos.events import Event
from app.db.graph_repos.relations import Relation
from app.domain.graph_labels import COUNTABLE_LABELS
from app.domain.graph_models import Fact
from app.ports.graph_store import EventAxis, RelationDirection

logger = logging.getLogger(__name__)

__all__ = ["FakeGraphStore"]


def _now() -> datetime:
    return datetime(2026, 1, 1, tzinfo=timezone.utc)


class FakeGraphStore:
    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._evidence: dict[tuple, dict] = {}
        self._evidence_counts: dict[str, int] = {}
        self._relations: list[Relation] = []
        self._facts: list[Fact] = []
        # `Fact` carries no subject_id — the real store attaches the subject with an
        # ABOUT edge — so the chain family key lives beside the list, not on the model.
        self._fact_subject: dict[str, str | None] = {}
        self._events: list[Event] = []
        # `Event` carries no origin title — the real store encodes it in the id — so the
        # identity key lives beside the list, the same shape `_fact_subject` uses.
        self._event_origin: dict[str, str] = {}
        # (user, project, entity_id) -> [(from_order, status)], newest-wins at a position.
        self._statuses: dict[tuple[str, str | None, str], list[tuple[int, str, int]]] = {}

    # ── test affordances (not part of the port) ──────────────────────

    def add_event(self, event: Event) -> None:
        self._events.append(event)
        self._event_origin[event.id] = event.canonical_title

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
            # ON MATCH, `auto_created` FALLS to false when a real extraction claims a node an
            # auto-creation minted. Copied from the Neo4j CASE arm, not guessed: the fake only
            # ever set this on CREATE, so an adapter that lost the arm agreed with the double.
            if auto_created is False:
                existing.auto_created = False
            existing.version = (existing.version or 1) + 1
            # ⚠️ A COPY, not the stored object. Returning the live instance made every
            # before/after assertion in every test using this double VACUOUS — the caller's
            # `a` and `b` were one object, so `b.version > a.version` compared 2 with 2. A real
            # store returns a snapshot; a double that does not is not modelling it.
            return existing.model_copy(deep=True)
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
        return entity.model_copy(deep=True)   # snapshot, for the reason above

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
        as_of: int | None = None,
    ) -> EntityDetail | None:
        anchor = next(
            (e for e in self._entities.values()
             if e.user_id == user_id and e.glossary_entity_id == glossary_entity_id
             and (project_id is None or e.project_id == project_id)),
            None,
        )
        if anchor is None:
            return None
        # T48s — the STORY window, in the double as well as the stores. A fake that ignored
        # `as_of` would make every conformance rule agree with the leak: the real adapters
        # would be judged against a double that has the same hole. Half-open, positionless
        # EXCLUDED, exactly as the port defines it.
        def _covers(r) -> bool:
            if as_of is None:
                return True
            if r.valid_from_ordinal is None:
                return False
            return r.valid_from_ordinal <= as_of and (
                r.valid_to_ordinal is None or as_of < r.valid_to_ordinal)

        edges = [
            r for r in self._relations
            if r.user_id == user_id and (r.subject_id == anchor.id or r.object_id == anchor.id)
            and r.valid_until is None and _covers(r)
        ]
        # The cap is applied, not ignored: it is what stops a hub entity's neighbourhood
        # eating a prompt budget, and a fake that returned everything would let an
        # unbounded context block pass every test.
        #
        # ⚠️ And the cap must be REPORTED. Returning the capped list while leaving
        # `total_relations` at its 0 default told every caller "nothing was cut" on exactly
        # the hub entities where something was — the same defect the AGE adapter carried, in
        # a second independent implementation, because no conformance rule read these two
        # fields back.
        capped = edges[:rel_cap]
        return EntityDetail(
            entity=anchor,
            relations=capped,
            relations_truncated=len(edges) > len(capped),
            total_relations=len(edges),
        )

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

    async def get_relation(self, *, user_id: str, relation_id: str) -> Relation | None:
        for r in self._relations:
            if r.id == relation_id and r.user_id == user_id:
                return r
        # A MISS for another user's relation, never an error — the port's
        # no-existence-oracle rule.
        return None

    async def invalidate_relation(
        self, *, user_id: str, relation_id: str, valid_until: datetime | None = None,
    ) -> Relation | None:
        rel = await self.get_relation(user_id=user_id, relation_id=relation_id)
        if rel is None:
            return None
        # Idempotent: an already-invalid edge moves to the new instant rather than failing.
        rel.valid_until = valid_until or _now()
        rel.updated_at = _now()
        return rel

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
        """Author-asserted: confidence 1.0, and it RESURRECTS a previously invalidated
        tuple by clearing `valid_until`. Matching ignores `valid_until` for exactly that
        reason — `upsert_relation`'s scan requires `valid_until is None`, so reusing it
        here would mint a duplicate beside the invalidated edge instead of reviving it."""
        for r in self._relations:
            if (r.user_id == user_id and r.subject_id == subject_id
                    and r.predicate == predicate and r.object_id == object_id):
                r.valid_until = None
                r.confidence = 1.0
                if valid_from_ordinal is not None:
                    r.valid_from_ordinal = valid_from_ordinal
                r.updated_at = _now()
                return r
        rel = Relation(
            id=f"{subject_id}|{predicate}|{object_id}",
            user_id=user_id, subject_id=subject_id, predicate=predicate,
            object_id=object_id, confidence=1.0, source_event_ids=[],
            valid_from_ordinal=valid_from_ordinal, created_at=_now(), updated_at=_now(),
        )
        self._relations.append(rel)
        return rel

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
        """A3 — the browse. Built ON TOP of the window read so the two cannot disagree about
        which events match; only paging and the extra filters are new here.

        `total` counts everything matching the FILTERS and ignores limit/offset — a total
        that shrank with the page would make "showing 1-50 of 50" true on every page of a
        thousand.
        """
        rows = await self.events_in_window(
            user_id=user_id, project_id=project_id, after=after, before=before, axis=axis,
            limit=10_000,
        )
        excluded = set(exclude_project_ids or ())
        wanted = set(participants or ())
        needle = (q or "").strip().lower()
        matched = []
        for e in rows:
            if e.project_id in excluded:
                continue
            if wanted and not wanted.intersection(e.participants or ()):
                continue
            if needle and needle not in (e.title or "").lower() and                     needle not in (e.summary or "").lower():
                continue
            matched.append(e)
        if sort_dir == "desc":
            matched.reverse()
        total = len(matched)
        return matched[offset:offset + limit], total

    async def merge_fact(
        self,
        *,
        user_id: str,
        project_id: str | None,
        type: str,
        content: str,
        confidence: float = 0.0,
        pending_validation: bool = False,
        source_type: str = "book_content",
        source_chapter: str | None = None,
        provenance: str = "human_authored",
        subject_id: str | None = None,
        from_order: int | None = None,
        valid_from_ordinal: int | None = None,
        event_date_iso: str | None = None,
        predicate: str | None = None,
        object: str | None = None,
        maintain_chain: bool = False,
    ) -> Fact:
        """Content-keyed upsert, and — when asked — the ordinal CHAIN.

        The chain is reproduced here rather than stubbed because it is the operation's whole
        point: a fake that accepted `maintain_chain` and left every interval open would make
        every as-of test agree with a graph that has no history, which is the failure the port
        docstring describes. Rule: within one `(user, project, subject, type)` family, the
        fact at each ordinal closes at the NEXT STRICTLY GREATER ordinal, and the newest opens.
        Re-derived from scratch on every call so out-of-order and backfill arrival land the
        same way the real store's `temporal.maintain_chain` puts them.
        """
        if valid_from_ordinal is None:
            valid_from_ordinal = from_order
        # Matched on the model's own fields, not a stashed attribute: `Fact` is a pydantic
        # model and will not carry one.
        fact = next(
            (f for f in self._facts
             if (f.user_id, f.project_id, f.type, f.content,
                 self._fact_subject.get(f.id)) == (user_id, project_id, type, content,
                                                   subject_id)),
            None,
        )
        if fact is None:
            fact = Fact(
                id=f"fact|{user_id}|{project_id}|{type}|{content}|{subject_id}",
                user_id=user_id, project_id=project_id, type=type, content=content,
                # The real store canonicalises for the content key; the fake mirrors it so
                # the model is the same shape both sides return.
                canonical_content=content.strip().lower(),
                confidence=confidence, pending_validation=pending_validation,
                source_types=[source_type] if source_type else [],
                # A26 — the fake DROPPED `source_chapter`, which both real adapters keep.
                # A conformance rule asserting it would have failed the double too, so none
                # was written: the missing rule and the missing field protected each other,
                # exactly as A24 found for `provenance`/`job_id`.
                source_chapter=source_chapter,
                from_order=from_order,
                valid_from_ordinal=valid_from_ordinal, event_date_iso=event_date_iso,
                predicate=predicate, object=object,
                created_at=_now(), updated_at=_now(),
            )
            self._facts.append(fact)
            self._fact_subject[fact.id] = subject_id
        else:
            fact.confidence = max(fact.confidence, confidence)
            if source_type and source_type not in fact.source_types:
                fact.source_types.append(source_type)
            # BACKFILL, never overwrite — `coalesce(f.valid_from_ordinal, $vfo)` in the
            # Neo4j repo. The fake had the SAME bug Kuzu did and nothing caught either,
            # because no rule re-mentioned one content at a later ordinal. A fake that
            # moved a fact's story birth forward would make the defect agree with itself
            # across ~561 unit tests.
            if valid_from_ordinal is not None and fact.valid_from_ordinal is None:
                fact.valid_from_ordinal = valid_from_ordinal
            fact.updated_at = _now()

        if maintain_chain and subject_id is not None:
            family = [f for f in self._facts
                      if (f.user_id, f.project_id, f.type,
                          self._fact_subject.get(f.id)) == (user_id, project_id, type,
                                                            subject_id)
                      and f.valid_from_ordinal is not None]
            family.sort(key=lambda f: f.valid_from_ordinal)
            for i, f in enumerate(family):
                nxt = family[i + 1].valid_from_ordinal if i + 1 < len(family) else None
                f.valid_to_ordinal = nxt
        return fact

    async def facts_for(
        self,
        *,
        user_id: str,
        subject_id: str,
        type: str | None = None,
        as_of: int | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        """Facts ABOUT one subject (SPEC §1.1) — the read that makes the merge checkable.

        The subject comes from `_fact_subject`, the same side table `merge_fact` writes and
        its chain maintenance reads: `Fact` itself carries no `subject_id` (the real store
        attaches the subject with an ABOUT edge), which is precisely why a returned `Fact`
        could never identify its own family.
        """
        out = [
            f for f in self._facts
            if f.user_id == user_id
            and self._fact_subject.get(f.id) == subject_id
            and (type is None or f.type == type)
            and f.valid_until is None
        ]
        if as_of is not None:
            # Half-open, and POSITIONLESS EXCLUDED — the rule `relations_for` states. A fact
            # with no ordinal cannot be placed on the axis; admitting it would mix untimed
            # rows into an answer whose whole value is that it is timed.
            out = [
                f for f in out
                if f.valid_from_ordinal is not None
                and f.valid_from_ordinal <= as_of
                and (f.valid_to_ordinal is None or as_of < f.valid_to_ordinal)
            ]
            out.sort(key=lambda f: (f.valid_from_ordinal, f.created_at))
        else:
            # Positionless facts sort LAST in a head read, not first: they have no place on
            # the axis, and leading with them would misread as "earliest".
            out.sort(key=lambda f: (f.valid_from_ordinal is None,
                                    f.valid_from_ordinal or 0, f.created_at))
        return out[:limit]

    async def get_event(self, *, user_id: str, event_id: str) -> Event | None:
        for e in self._events:
            if e.id == event_id and e.user_id == user_id:
                return e
        return None

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
        provenance: str = "human_authored",
    ) -> Event:
        """Idempotent on (user, project, chapter, title). The MERGE semantics are copied
        from the real Cypher rather than guessed — a fake that overwrote instead of
        upgrading would make every re-mention test agree with a graph that does not
        exist (the lesson QC-2's parity diff taught on `resolve_or_merge_entity`)."""
        canonical = canonicalize_entity_name(title)
        key = (user_id, project_id, chapter_id, canonical)
        for e in self._events:
            # 🔴 `_origin_title`, NOT `e.canonical_title` (T35d). The fake matched the mutable
            # one and forked the event on every re-extraction after an author rename — the
            # SAME defect Kuzu had, in the double ~561 unit tests lean on, so nothing in the
            # unit suite could disagree with it. A title comes out of the PROSE, so a later
            # pass arrives with the ORIGINAL and must land on the same node.
            origin = self._event_origin.get(e.id, e.canonical_title)
            if (e.user_id, e.project_id, e.chapter_id, origin) == key:
                if source_type and source_type not in e.source_types:
                    e.source_types.append(source_type)
                e.confidence = max(e.confidence, confidence)
                for pname in participants or ():
                    if pname not in e.participants:
                        e.participants.append(pname)
                # summary upgrades from NULL, never overwrites: a later thinner mention
                # must not erase a richer one.
                if e.summary is None and summary is not None:
                    e.summary = summary
                if e.time_cue is None and time_cue is not None:
                    e.time_cue = time_cue
                if e.event_date_iso is None and event_date_iso is not None:
                    e.event_date_iso = event_date_iso
                # CM4 spoiler-safety: the MINIMUM reading position wins. Taking the latest
                # would migrate an event forward and hide it from a reader who has already
                # passed it — silent in both directions, which is why it is pinned here.
                if event_order is not None:
                    e.event_order = (event_order if e.event_order is None
                                     else min(e.event_order, event_order))
                if e.chronological_order is None and chronological_order is not None:
                    e.chronological_order = chronological_order
                e.mention_count += 1
                e.updated_at = _now()
                return e
        event = Event(
            id=f"evt|{user_id}|{project_id}|{chapter_id}|{canonical}",
            user_id=user_id, project_id=project_id, title=title,
            canonical_title=canonical, summary=summary, chapter_id=chapter_id,
            event_order=event_order, chronological_order=chronological_order,
            event_date_iso=event_date_iso, time_cue=time_cue,
            participants=list(participants or []), confidence=confidence,
            source_types=[source_type] if source_type else [], mention_count=1,
            version=1, created_at=_now(), updated_at=_now(),
        )
        self._events.append(event)
        self._event_origin[event.id] = canonical
        return event

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
        event = await self.get_event(user_id=user_id, event_id=event_id)
        if event is None:
            return None, None
        if event.version != expected_version:
            # RAISES rather than no-ops. A lost update that reports success is
            # indistinguishable from a saved one to the caller who just overwrote
            # somebody else's edit.
            from app.db.repositories import VersionMismatchError

            raise VersionMismatchError(event)
        before = {
            "title": event.title, "summary": event.summary,
            "time_cue": event.time_cue, "event_date_iso": event.event_date_iso,
            "participants": list(event.participants),
        }
        if title is not None:
            event.title = title
            event.canonical_title = canonicalize_entity_name(title)
        if summary is not None:
            event.summary = summary
        if time_cue is not None:
            event.time_cue = time_cue
        if event_date_iso is not None:
            event.event_date_iso = event_date_iso
        event.version += 1
        event.updated_at = _now()
        return event, before

    async def archive_event(self, *, user_id: str, event_id: str) -> Event | None:
        event = await self.get_event(user_id=user_id, event_id=event_id)
        if event is None:
            return None
        # Idempotent: re-archiving succeeds so the correction is retryable.
        event.archived_at = event.archived_at or _now()
        return event

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
    ):
        """In-memory evidence + counter bump.

        Validation is copied from the repo deliberately: a fake that ACCEPTED an empty
        `job_id` would let ~561 tests encode a call the real adapters reject, which is the
        `fake-more-permissive-than-real` defect this suite already caught once on
        archived-peer exclusion.
        """
        if not all((target_id, source_id, extraction_model, job_id)):
            raise ValueError("target_id/source_id/extraction_model/job_id must be non-empty")
        if not 0.0 <= confidence <= 1.0:
            raise ValueError(f"confidence must be in [0,1], got {confidence}")

        from app.db.graph_repos.provenance import EvidenceWriteResult

        ent = self._entities.get(target_id)
        if ent is None or ent.user_id != user_id:
            return None
        key = (target_id, source_id, job_id)
        created = key not in self._evidence
        if created:
            self._evidence[key] = {"quote": quote, "model": extraction_model}
            self._evidence_counts[target_id] = self._evidence_counts.get(target_id, 0) + 1
            # The fake stores it ON THE ENTITY, not in a side table, because that is where
            # every reader looks — `find_gap_candidates` sorts and floors on it. A fake that
            # only reported the number in its return value would satisfy a test that reads the
            # result and fail every test that reads the graph.
            self._entities[target_id] = ent.model_copy(
                update={"mention_count": (ent.mention_count or 0) + 1})
        elif quote is not None:
            # A quote-bearing re-extraction BACKFILLS a quoteless edge and never wipes one.
            self._evidence[key]["quote"] = self._evidence[key]["quote"] or quote
        return EvidenceWriteResult(
            evidence_count=self._evidence_counts.get(target_id, 0),
            # Was hardcoded `0`. The port says this bumps the target's counterS, and a fake
            # that answers zero to one of them teaches every unit test that uses it a rule the
            # real stores do not follow.
            mention_count=self._entities[target_id].mention_count or 0,
            created=created,
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
        out: dict[str, str] = {}
        for eid in entity_ids:
            rows = self._statuses.get((user_id, project_id, eid), [])
            # The LATEST status established at or before the position wins — a status is a
            # step function, not an interval, so "most recent <= N" is the whole rule.
            applicable = [
                (order, status) for order, status, evidence in rows
                if order <= at_order and evidence >= min_evidence
            ]
            # ⚠️ FAIL OPEN, and the key is ALWAYS present. Omitting the entity entirely —
            # what this did — is not the same answer as `'active'`: a caller that iterates
            # the result, or that supplies its own `.get()` default, silently diverges from
            # both real adapters, which spell this `coalesce(latest.status, 'active')`. The
            # asymmetry is why it matters: a wrongly-`gone` entity vanishes from a panel,
            # while a wrongly-`active` one un-kills a character. Every consumer unit-tested
            # against this fake was testing the wrong shape.
            out[eid] = (
                max(applicable, key=lambda t: t[0])[1] if applicable else "active")
        return out

    # ── the project as a whole ───────────────────────────────────────

    async def find_gap_candidates(
        self, *, user_id: str, project_id: str | None,
        min_mentions: int = 50, limit: int = 100,
    ) -> list[Entity]:
        """The gap report in memory.

        The sort is written out in full rather than `sorted(key=...)` on one field, because
        the fake is what most unit tests see: a fake that ordered only by `mention_count`
        would make a two-key disagreement between the real adapters invisible to every test
        that uses it, which is the failure mode `fixtures can seed a field the writer never
        sets` describes from the other side.
        """
        if min_mentions < 0:
            raise ValueError(f"min_mentions must be >= 0, got {min_mentions}")
        if limit <= 0:
            raise ValueError(f"limit must be positive, got {limit}")
        out = [
            e for e in self._entities.values()
            if e.user_id == user_id
            and getattr(e, "glossary_entity_id", None) is None
            and getattr(e, "archived_at", None) is None
            and (e.mention_count or 0) >= min_mentions
            and (project_id is None or e.project_id == project_id)
        ]
        out.sort(key=lambda e: (-(e.mention_count or 0), -(e.confidence or 0.0), e.name or ""))
        return out[:limit]

    async def purge_project(self, *, project_id: str) -> dict[str, int]:
        """Drop every in-memory row for this project, across ALL the structures.

        The list is long on purpose. A fake that cleared `_entities` alone would still answer
        `facts_for` and `status_at_order` from the leftovers, and the conformance rule would
        pass on the fake while both real stores did a `DETACH DELETE` that takes the edges with
        it. Everything keyed by entity id is swept through the ids that are going.
        """
        gone = {e.id for e in self._entities.values() if e.project_id == project_id}
        nodes = len(gone)
        self._entities = {k: v for k, v in self._entities.items() if v.project_id != project_id}
        nodes += sum(1 for f in self._facts if f.project_id == project_id)
        self._facts = [f for f in self._facts if f.project_id != project_id]
        nodes += sum(1 for e in self._events if e.project_id == project_id)
        self._events = [e for e in self._events if e.project_id != project_id]
        self._relations = [
            r for r in self._relations
            if r.subject_id not in gone and r.object_id not in gone
        ]
        self._evidence = {k: v for k, v in self._evidence.items() if k[0] not in gone}
        self._evidence_counts = {
            k: v for k, v in self._evidence_counts.items() if k not in gone
        }
        self._fact_subject = {
            k: v for k, v in self._fact_subject.items()
            if k in {f.id for f in self._facts}
        }
        self._event_origin = {
            k: v for k, v in self._event_origin.items()
            if k in {e.id for e in self._events}
        }
        self._statuses = {k: v for k, v in self._statuses.items() if k[1] != project_id}
        # No index administration exists in memory, and saying so keeps the fake's shape the
        # same as AGE's rather than claiming a drop it never made.
        return {
            "nodes_deleted": nodes,
            "indexes_dropped": 0,
            "indexes_skipped": "an in-memory store has no vector indexes",
        }

    async def project_graph_stats(
        self, *, user_id: str, project_id: str,
    ) -> dict[str, int]:
        buckets = {
            "Entity": self._entities.values(),
            "Fact": self._facts,
            "Event": self._events,
        }
        # ARCHIVED ROWS COUNT. The Cypher this mirrors is a bare label match with a tenant
        # filter and no archive predicate, so a fake that quietly excluded them would make
        # `find_entities_by_name`'s default-hide rule leak into a place it does not apply —
        # and the conformance rule that pins this would then pass on the fake and fail on
        # both real adapters. A stats card counts what is in the graph.
        return {
            f"{label.lower()}_count": sum(
                1 for row in buckets[label]
                if row.user_id == user_id and row.project_id == project_id
            )
            for label in COUNTABLE_LABELS
        }

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
