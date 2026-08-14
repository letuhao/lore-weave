"""Shadow comparison between two `GraphStore` adapters (plan T43, decision X1).

WHAT THIS IS FOR
----------------
X1: the engine is chosen by **measurement on real traffic**, not by argument. This wraps two
adapters, serves every call from the PRIMARY, and — best-effort — replays it against the
SECONDARY and records whether they agreed. The caller never sees the secondary: its result
is evidence, never an answer.

WHY IT COULD NOT EXIST UNTIL NOW
--------------------------------
`port-adoption-gate` measured the reason on 2026-08-12: the `GraphStore` port had **three
conforming adapters and ZERO call sites**. A shadow comparison of traffic that does not flow
through the port observes nothing, so the plan's coverage floor — *"no cutover while any port
operation has zero shadow observations"* — was not a slow number but an unreachable one.
T17's migration closed that: every port-covered operation now has zero DIRECT callers.

THE COVERAGE FLOOR IS THE POINT, AND IT IS ABOUT ABSENCE
--------------------------------------------------------
Merge/split/restore/coref/triage are rare. A comparison that ran for a week and reported
"100 % agreement" while never once exercising `restore_entity` would be evidence about
`relations_for` wearing the costume of evidence about the port. So `coverage_report()`
answers per OPERATION, and an operation at zero **blocks cutover** regardless of how well the
others agree.

⚠️ **DISAGREEMENT ≠ FAILURE, AND ABSENCE ≠ AGREEMENT.** Three outcomes are recorded, never
two: `agreed`, `diverged`, and `uncovered` (the secondary raised `NotImplementedError`).
`AgeGraphStore.status_at_order` / `events_in_window` deliberately raise
(`D-T42-AGE-EVENT-SURFACE`), and folding that into either of the other buckets would let a
COVERAGE gap read as a DATA result — the exact confusion those methods raise to prevent.

THE SECONDARY MUST NEVER BREAK THE CALLER
------------------------------------------
Every secondary call is wrapped. A shadow that can take production down converts a
measurement into an outage, and the first thing anyone would do is turn it off — which is how
the measurement never gets taken.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from app.ports.graph_store import EventAxis, GraphStore, RelationDirection

logger = logging.getLogger(__name__)

__all__ = ["ShadowGraphStore", "ShadowStats", "OPERATIONS"]

#: Every operation the port declares. The coverage report is keyed on THIS, not on what
#: happened to be called — an operation missing from the report would read as "no problem"
#: when it means "never observed", which is the failure this whole file guards.
#: EVERY port operation, derived from the port's own surface rather than hand-listed.
#:
#: 🔴 IT HELD NINE OF TWENTY UNTIL 2026-08-14, and the floor could not block on the other
#: eleven because it did not know they existed. `cutover_permitted` was therefore answerable
#: `True` while `invalidate_relation`, `recreate_relation`, `merge_fact`, `facts_for` and seven
#: more had NEVER been compared once — and the row's own justification for the floor names
#: exactly that class: *"merge/split/restore/coref/triage are rare and would diverge silently,
#: and the graph feeds canon checks."*
#:
#: A floor computed over a subset of the surface is not a floor; it is a floor-shaped number.
#: `test_OPERATIONS_covers_the_WHOLE_port` keeps this list and the port in step, so an operation
#: added to the port cannot again be invisible to the thing that gates the cutover.
OPERATIONS = (
    "resolve_or_merge_entity",
    "find_entities_by_name",
    "neighborhood",
    "archive_entity",
    "restore_entity",
    "upsert_relation",
    "relations_for",
    "get_relation",
    "invalidate_relation",
    "recreate_relation",
    "events_page",
    "get_event",
    "merge_event",
    "update_event_fields",
    "archive_event",
    "merge_fact",
    "facts_for",
    "add_evidence",
    "status_at_order",
    "events_in_window",
)


#: Which WRITE each read depends on. A read whose write the secondary refused cannot be
#: compared: the secondary's store legitimately has nothing to return. Declared rather than
#: inferred, so adding an operation forces the question "what has to exist for this to mean
#: anything?" — which is the question the refusal artifact came from not asking.
_DEPENDS_ON: dict[str, tuple[str, ...]] = {
    "find_entities_by_name": ("resolve_or_merge_entity",),
    "neighborhood": ("resolve_or_merge_entity",),
    "archive_entity": ("resolve_or_merge_entity",),
    "restore_entity": ("resolve_or_merge_entity",),
    "relations_for": ("upsert_relation",),
    "get_relation": ("upsert_relation",),
    "invalidate_relation": ("upsert_relation",),
    "recreate_relation": ("upsert_relation",),
    "events_page": ("merge_event",),
    "events_in_window": ("merge_event",),
    "get_event": ("merge_event",),
    "update_event_fields": ("merge_event",),
    "archive_event": ("merge_event",),
    "facts_for": ("merge_fact",),
    "status_at_order": ("merge_fact",),
    "add_evidence": ("resolve_or_merge_entity",),
}


@dataclass
class ShadowStats:
    """Per-operation observations. Three counters, deliberately — see the module docstring."""

    agreed: dict[str, int] = field(default_factory=dict)
    diverged: dict[str, int] = field(default_factory=dict)
    uncovered: dict[str, int] = field(default_factory=dict)
    errored: dict[str, int] = field(default_factory=dict)
    #: id-keyed calls skipped because the primary node had no secondary twin yet
    unmapped: dict[str, int] = field(default_factory=dict)
    samples: list[tuple[str, str]] = field(default_factory=list)

    def observations(self, op: str) -> int:
        """Comparisons that actually produced a verdict.

        `uncovered`, `errored` and `unmapped` are all EXCLUDED: the secondary refused, blew
        up, or was never asked. Counting any of them would let a method that has never once
        been compared satisfy the coverage floor — precisely the lie the floor exists to
        catch.
        """
        return self.agreed.get(op, 0) + self.diverged.get(op, 0)


class ShadowGraphStore:
    """Serves from `primary`; compares against `secondary`. Satisfies `GraphStore`.

    Construct with two adapters that have both passed
    `tests/integration/db/test_graph_store_conformance.py`. That is not a formality: a
    comparison between two unproven implementations measures **agreement**, and two adapters
    can agree by sharing a bug. Conformance is what makes agreement mean correctness.
    """

    def __init__(self, primary: GraphStore, secondary: GraphStore) -> None:
        self._primary = primary
        self._secondary = secondary
        self.stats = ShadowStats()
        # ── the identity mapping (D-T43-ID-KEYED-OPS-NEED-A-MAPPING) ──────────────────
        # primary node id -> secondary node id.
        #
        # WHY IT IS REQUIRED, measured rather than anticipated: the first shadow run
        # reported `archive_entity`, `restore_entity`, `upsert_relation` and `relations_for`
        # as DIVERGED with `secondary=None`. None of those was an engine difference. Each
        # engine mints its OWN node id, so an id-keyed call handed the secondary a node it
        # had never seen — the two stores were asked about different things and answered
        # correctly.
        #
        # Publishing that as evidence about AGE, in the document that decides the engine,
        # would have been the worst outcome available. Hence a mapping rather than an
        # exemption list: an exemption would have made the report *look* clean while 6 of 9
        # operations stayed uncompared.
        self._ids: dict[str, str] = {}
        #: Write operations the SECONDARY has refused this run. Reads that depend on one
        #: are `uncovered` rather than compared — see `_DEPENDS_ON` and `_shadow`.
        self._refused: set[str] = set()

    def _map_id(self, primary_id: str | None) -> str | None:
        """Translate a primary node id for the secondary, or None if unknown.

        Returning None (rather than passing the primary id through) is deliberate: an
        unmapped id would silently become a lookup for a node that cannot exist, and the
        miss would be recorded as a divergence — re-creating the exact false signal this
        mapping was built to remove.
        """
        return self._ids.get(primary_id) if primary_id else None

    async def _shadow_by_id(self, op: str, primary_result: Any, primary_id: str | None,
                            call) -> Any:
        """Replay an id-keyed call, but only when the id is mapped.

        An unmapped id is `unmapped`, NOT a divergence and NOT an agreement — a fourth
        outcome for the same reason there is a third: the comparison did not happen, and a
        report that cannot say so is a report that overstates its coverage.
        """
        secondary_id = self._map_id(primary_id)
        if secondary_id is None:
            self.stats.unmapped[op] = self.stats.unmapped.get(op, 0) + 1
            return primary_result
        return await self._shadow(op, primary_result, lambda s: call(s, secondary_id))

    # ── the comparison ───────────────────────────────────────────────

    @staticmethod
    def _comparable(value: Any) -> Any:
        """Reduce a result to what the two engines must agree ON.

        Node ids are engine-assigned and must NOT be compared — Neo4j and AGE mint different
        ids for the same logical entity, so comparing them would report 100 % divergence and
        say nothing. What must agree is the identity tuple and the fields a caller acts on.
        """
        if value is None:
            return None
        if isinstance(value, list):
            return sorted(ShadowGraphStore._comparable(v) for v in value)
        # TUPLE — `events_page` returns `(rows, total)`, and without this the whole tuple fell
        # through to its repr, carrying every row's engine-assigned id straight back into the
        # comparison the projections below exist to keep them out of. Position is preserved
        # (unlike the list branch, which sorts): a page and its count are not interchangeable.
        if isinstance(value, tuple):
            return tuple(ShadowGraphStore._comparable(v) for v in value)
        # DICT — `update_event_fields` returns `(updated, PRE-EDIT SNAPSHOT)`, and the snapshot
        # is a plain dict carrying the engine-assigned id and both wall-clock stamps. Those
        # three keys are dropped for the same reason the object projections drop them; every
        # other key is compared, because the snapshot is what a correction event records and a
        # difference in it is a real difference.
        if isinstance(value, dict):
            return sorted(
                (str(k), ShadowGraphStore._comparable(v))
                for k, v in value.items()
                if k not in ("id", "created_at", "updated_at")
            )
        if all(hasattr(value, a) for a in ("canonical_name", "kind", "project_id")):
            # ⚠️ `archived_at` is compared as PRESENCE, not as an instant. Each engine stamps
            # its own clock — Neo4j with Cypher's `datetime()`, AGE with Python's `now()` —
            # so the two are never equal to the microsecond. The first mapped run reported
            # exactly that as the sole divergence:
            #     primary=(… '2026-08-11 20:18:04.446000+00:00')
            #     secondary=(… '2026-08-11 20:17:56.949623+00:00')
            # Same entity, both archived. **Whether an entity is archived is the semantic
            # fact the caller acts on; when, to the microsecond, is engine-local bookkeeping.**
            # Comparing the instant would report a permanent 100 % divergence on every
            # lifecycle operation and drown any real difference in it.
            return (
                str(value.canonical_name), str(value.kind), str(value.project_id),
                value.archived_at is not None,
            )
        # EVENT — projected for exactly the reason entities are. Without this an Event fell
        # through to its full repr, which carries the engine-assigned `id` and the wall-clock
        # `created_at`/`updated_at`, so `merge_event`, `get_event`, `events_page` and
        # `events_in_window` ALL reported divergence on their first Kuzu run while agreeing on
        # every field a caller acts on. The shadow was reporting a difference it created.
        #
        # `event_order` is in and the timestamps are out on purpose: the story position is the
        # thing a canon read depends on, the wall clock is when the row happened to be written.
        if all(hasattr(value, a) for a in ("canonical_title", "chapter_id", "event_order")):
            return (
                str(value.canonical_title), str(value.chapter_id), str(value.event_order),
                str(value.chronological_order), str(value.project_id),
                sorted(str(x) for x in (value.participants or [])),
                sorted(str(x) for x in (value.source_types or [])),
                str(value.confidence), str(value.archived_at is not None),
            )
        # FACT — same reason. The ordinal CHAIN is the point (`maintain_chain` is what AGE
        # refuses and Kuzu honours), so both bounds are compared and the id is not.
        if all(hasattr(value, a) for a in ("canonical_content", "valid_from_ordinal", "type")):
            return (
                str(value.type), str(value.canonical_content), str(value.project_id),
                str(value.valid_from_ordinal), str(value.valid_to_ordinal),
                str(value.predicate), str(value.object), str(value.confidence),
            )
        if all(hasattr(value, a) for a in ("predicate", "confidence", "valid_from_ordinal")):
            return (str(value.predicate), str(value.confidence),
                    str(value.valid_from_ordinal))
        return str(value)

    async def _shadow(self, op: str, primary_result: Any, call) -> Any:
        # ⚠️ REFUSAL PROPAGATES FORWARD. If the secondary refused the write that would have
        # created this data, its read is EMPTY for a reason that is not a defect — and
        # comparing it would score a divergence the shadow caused itself.
        #
        # Measured 2026-08-14 against Neo4j↔AGE, which refuses `merge_event` and `merge_fact`:
        #     facts_for    primary=[('None','0.0','5')]      secondary=[]
        #     events_page  primary=([Event E4, Event E6],2)  secondary=([],0)
        # Three read operations scored DIVERGED while every one of them was correct. T43 exists
        # to choose an engine by measurement; a measurement that condemns an adapter for reads
        # that are right is worse than no measurement.
        blocked_by = [w for w in _DEPENDS_ON.get(op, ()) if w in self._refused]
        if blocked_by:
            self.stats.uncovered[op] = self.stats.uncovered.get(op, 0) + 1
            return primary_result
        try:
            secondary_result = await call(self._secondary)
        except NotImplementedError:
            # The adapter refused, on purpose. NOT a divergence and NOT an agreement.
            self._refused.add(op)
            self.stats.uncovered[op] = self.stats.uncovered.get(op, 0) + 1
            return primary_result
        except Exception as exc:  # noqa: BLE001 — a shadow must never break the caller
            self.stats.errored[op] = self.stats.errored.get(op, 0) + 1
            logger.warning("shadow %s: secondary raised %s: %s", op, type(exc).__name__, exc)
            return primary_result

        a, b = self._comparable(primary_result), self._comparable(secondary_result)
        if a == b:
            self.stats.agreed[op] = self.stats.agreed.get(op, 0) + 1
        else:
            self.stats.diverged[op] = self.stats.diverged.get(op, 0) + 1
            if len(self.stats.samples) < 20:
                self.stats.samples.append((op, f"primary={a!r} secondary={b!r}"))
            logger.warning("shadow %s DIVERGED: primary=%r secondary=%r", op, a, b)
        return primary_result

    def coverage_report(self) -> dict:
        """Per-operation coverage, and whether a cutover is permitted.

        `blocked_by` lists every operation with zero real comparisons. An empty list is the
        only state in which the sealed design allows a cutover, and the report says so rather
        than leaving a reader to infer it from a table.
        """
        rows = {
            op: {
                "observations": self.stats.observations(op),
                "agreed": self.stats.agreed.get(op, 0),
                "diverged": self.stats.diverged.get(op, 0),
                "uncovered": self.stats.uncovered.get(op, 0),
                "errored": self.stats.errored.get(op, 0),
                "unmapped": self.stats.unmapped.get(op, 0),
            }
            for op in OPERATIONS
        }
        blocked = [op for op in OPERATIONS if rows[op]["observations"] == 0]
        return {
            "operations": rows,
            "blocked_by": blocked,
            "cutover_permitted": not blocked
            and not any(r["diverged"] for r in rows.values()),
            "samples": list(self.stats.samples),
        }

    # ── the port surface ─────────────────────────────────────────────

    async def resolve_or_merge_entity(self, **kw):
        out = await self._primary.resolve_or_merge_entity(**kw)

        async def _call(s):
            twin = await s.resolve_or_merge_entity(**kw)
            # THE mapping is learned here, and only here: this is the one operation keyed on
            # NATURAL identity (user + project + canonical name + kind), so it is the only
            # place the two engines can be known to be talking about the same entity.
            if out is not None and twin is not None:
                self._ids[out.id] = twin.id
            return twin

        return await self._shadow("resolve_or_merge_entity", out, _call)

    async def find_entities_by_name(self, **kw):
        out = await self._primary.find_entities_by_name(**kw)
        return await self._shadow("find_entities_by_name", out,
                                  lambda s: s.find_entities_by_name(**kw))

    async def neighborhood(self, **kw):
        out = await self._primary.neighborhood(**kw)
        return await self._shadow("neighborhood", out, lambda s: s.neighborhood(**kw))

    async def archive_entity(self, **kw):
        out = await self._primary.archive_entity(**kw)
        return await self._shadow_by_id(
            "archive_entity", out, kw.get("canonical_id"),
            lambda s, sid: s.archive_entity(**{**kw, "canonical_id": sid}))

    async def restore_entity(self, **kw):
        out = await self._primary.restore_entity(**kw)
        return await self._shadow_by_id(
            "restore_entity", out, kw.get("canonical_id"),
            lambda s, sid: s.restore_entity(**{**kw, "canonical_id": sid}))

    async def upsert_relation(self, **kw):
        out = await self._primary.upsert_relation(**kw)
        # TWO endpoints, and BOTH must be mapped — a half-mapped edge would be written
        # between one real node and one absent one, which is worse than not replaying it.
        subj = self._map_id(kw.get("subject_id"))
        obj = self._map_id(kw.get("object_id"))
        if subj is None or obj is None:
            self.stats.unmapped["upsert_relation"] = (
                self.stats.unmapped.get("upsert_relation", 0) + 1)
            return out
        async def _call(s):
            twin = await s.upsert_relation(**{**kw, "subject_id": subj, "object_id": obj})
            # LEARNS the relation mapping, for the same reason `resolve_or_merge_entity` and
            # `merge_event` do: this is the only relation operation keyed on natural identity
            # (subject + predicate + object). Without it every id-keyed relation op —
            # `get_relation`, `invalidate_relation` — reports `unmapped` FOREVER and can never
            # gain an observation, so the coverage floor is unmeetable for them by
            # construction. Found by the corpus-coverage assertion, not by reading.
            if out is not None and twin is not None:
                self._ids[out.id] = twin.id
            return twin

        return await self._shadow("upsert_relation", out, _call)

    async def relations_for(self, **kw):
        out = await self._primary.relations_for(**kw)
        return await self._shadow_by_id(
            "relations_for", out, kw.get("entity_id"),
            lambda s, sid: s.relations_for(**{**kw, "entity_id": sid}))

    async def status_at_order(self, **kw):
        out = await self._primary.status_at_order(**kw)
        return await self._shadow("status_at_order", out, lambda s: s.status_at_order(**kw))

    async def events_in_window(self, **kw):
        out = await self._primary.events_in_window(**kw)
        return await self._shadow("events_in_window", out, lambda s: s.events_in_window(**kw))

    # ── the ELEVEN that were never wrapped ────────────────────────────────────────────────
    # Added 2026-08-14 with the coverage-floor widening. Until then `OPERATIONS` listed nine,
    # so the floor could not block on these and `cutover_permitted` was answerable True while
    # they had never been compared once — including the rare correction paths the floor's own
    # justification names as *"would diverge silently"*.
    #
    # Each is the same two shapes as above: NATURAL-keyed calls replay directly; ID-keyed ones
    # go through `_shadow_by_id`, which reports `unmapped` rather than inventing an agreement
    # when the primary's node has no twin yet.

    async def get_relation(self, **kw):
        out = await self._primary.get_relation(**kw)
        return await self._shadow_by_id(
            "get_relation", out, kw.get("relation_id"),
            lambda s, sid: s.get_relation(**{**kw, "relation_id": sid}))

    async def invalidate_relation(self, **kw):
        out = await self._primary.invalidate_relation(**kw)
        return await self._shadow_by_id(
            "invalidate_relation", out, kw.get("relation_id"),
            lambda s, sid: s.invalidate_relation(**{**kw, "relation_id": sid}))

    async def recreate_relation(self, **kw):
        out = await self._primary.recreate_relation(**kw)
        subj = self._map_id(kw.get("subject_id"))
        obj = self._map_id(kw.get("object_id"))
        if subj is None or obj is None:
            self.stats.unmapped["recreate_relation"] = (
                self.stats.unmapped.get("recreate_relation", 0) + 1)
            return out
        return await self._shadow(
            "recreate_relation", out,
            lambda s: s.recreate_relation(**{**kw, "subject_id": subj, "object_id": obj}))

    async def events_page(self, **kw):
        out = await self._primary.events_page(**kw)
        return await self._shadow("events_page", out, lambda s: s.events_page(**kw))

    async def get_event(self, **kw):
        out = await self._primary.get_event(**kw)
        return await self._shadow_by_id(
            "get_event", out, kw.get("event_id"),
            lambda s, sid: s.get_event(**{**kw, "event_id": sid}))

    async def merge_event(self, **kw):
        out = await self._primary.merge_event(**kw)

        async def _call(s):
            twin = await s.merge_event(**kw)
            # Keyed on NATURAL identity (user + project + chapter + title), so — like
            # `resolve_or_merge_entity` — this is a place the mapping can be LEARNED rather
            # than assumed. Without it every id-keyed event op below stays `unmapped` forever.
            if out is not None and twin is not None:
                self._ids[out.id] = twin.id
            return twin

        return await self._shadow("merge_event", out, _call)

    async def update_event_fields(self, **kw):
        out = await self._primary.update_event_fields(**kw)
        return await self._shadow_by_id(
            "update_event_fields", out, kw.get("event_id"),
            lambda s, sid: s.update_event_fields(**{**kw, "event_id": sid}))

    async def archive_event(self, **kw):
        out = await self._primary.archive_event(**kw)
        return await self._shadow_by_id(
            "archive_event", out, kw.get("event_id"),
            lambda s, sid: s.archive_event(**{**kw, "event_id": sid}))

    async def merge_fact(self, **kw):
        out = await self._primary.merge_fact(**kw)
        subj = kw.get("subject_id")
        if subj is not None:
            mapped = self._map_id(subj)
            if mapped is None:
                self.stats.unmapped["merge_fact"] = self.stats.unmapped.get("merge_fact", 0) + 1
                return out
            kw = {**kw, "subject_id": mapped}
        return await self._shadow("merge_fact", out, lambda s: s.merge_fact(**kw))

    async def facts_for(self, **kw):
        out = await self._primary.facts_for(**kw)
        return await self._shadow_by_id(
            "facts_for", out, kw.get("subject_id"),
            lambda s, sid: s.facts_for(**{**kw, "subject_id": sid}))

    async def add_evidence(self, **kw):
        out = await self._primary.add_evidence(**kw)
        return await self._shadow_by_id(
            "add_evidence", out, kw.get("target_id"),
            lambda s, sid: s.add_evidence(**{**kw, "target_id": sid}))

