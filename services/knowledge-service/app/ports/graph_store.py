"""The `GraphStore` port (plan T18).

The knowledge graph as DOMAIN operations — resolve an entity, find its neighbours, ask
what its status was at a story position — with no Cypher and no session in any signature.
This is the port Phase 7 swaps: the Neo4j implementation stays, a second adapter is built
alongside it (T42), and T43's shadow comparison decides which one wins. Nothing downstream
of this file learns which answered.

── THE SKETCH SAID `relations_for(entity, as_of)`; TODAY NOTHING HONOURS `as_of` ─────────
The substrate does support it. `Relation` carries `valid_from_ordinal` /
`valid_to_ordinal` (the F3 story-time half-open interval), and
`temporal.AS_OF_ORDINAL_PREDICATE` is the LOCKED shared fragment every as-of read is
supposed to use. What is missing is that no relation read applies it — the relation
queries read the HEAD. So `as_of` is on this port, and the Neo4j adapter implements it
with that shared fragment, ADDITIVELY: omit it and the read is byte-identical to today's.

That distinction matters. Putting `as_of` on the port when the data could not answer it
would be a port that lies, and the KAL already reports `temporal_capability.kg` precisely
because that lie is expensive. Putting it on when the data CAN answer it and only the query
was missing is the port doing its job — the same as-of read Phase 1 built for the glossary,
on the other substrate.

── `events_in_window(after, before, axis)` — THERE ARE THREE AXES, NOT TWO ───────────────
`narrative` (the authored `event_order`), `chronological` (in-story chronology, where
undated events sink last), and `date` (the parsed `event_date_iso` timeline filter). They
are genuinely different questions and the repo already distinguishes them; collapsing them
into one "time" parameter would make a caller unable to ask the one it means.

── WHAT IS NOT HERE ─────────────────────────────────────────────────────────────────────
Subgraph/ego reads (`get_project_subgraph`, `get_world_subgraph`), motif and thread writes,
causal-edge merges. They are real operations but they are not what the port needs to be
swappable, and every method here has to be implemented twice in Phase 7 plus faked. A port
grows by demand, not by inventory — T42 building the second adapter is the forcing function
that says which of them belong.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Protocol, runtime_checkable

# ⚠️ These come from `app.domain`, NOT from `db/graph_repos/` (T17). A port that imports its
# own implementation is not a boundary: every signature here was typed in one engine's
# vocabulary, `port-adoption-gate` counted this file among the modules bound to the concrete
# layer (correctly — an import is an import), and a second adapter returned Neo4j's models by
# definition rather than by agreement. The classes never depended on the repo layer; they were
# simply defined next to the first thing that spoke them.
from app.domain.graph_models import (
    Entity,
    EntityDetail,
    EvidenceWriteResult,
    Event,
    Fact,
    Relation,
)

__all__ = ["EventAxis", "GraphStore", "RelationDirection"]

# Which time axis an event window is measured on. See the module docstring — these are
# three different questions, not three spellings of one.
EventAxis = Literal["narrative", "chronological", "date"]

RelationDirection = Literal["outgoing", "incoming", "both"]


@runtime_checkable
class GraphStore(Protocol):
    """Implementations: `adapters/neo4j_graph_store.py`, `adapters/fake_graph_store.py`,
    and (Phase 7) whichever second engine T43's shadow comparison selects."""

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
        """Idempotent upsert keyed on the canonical identity. Returns the entity whether it
        was created or matched — the caller almost never needs to know which, and the ones
        that do can compare `created_at`."""
        ...

    async def find_entities_by_name(
        self,
        *,
        user_id: str,
        project_id: str | None,
        name: str,
        include_archived: bool = False,
        exclude_project_ids: list[str] | None = None,
    ) -> list[Entity]:
        """Canonical-name and display-name matches. Archived entities are excluded by
        default: a resolver that matched one would silently re-anchor extraction onto an
        entity the author archived."""
        ...

    async def neighborhood(
        self,
        *,
        user_id: str,
        glossary_entity_id: str,
        project_id: str | None = None,
        rel_cap: int = 50,
        as_of: int | None = None,
    ) -> EntityDetail | None:
        """One entity plus its capped one-hop neighbourhood.

        `rel_cap` is part of the contract, not a tuning knob: this feeds a context block,
        and an uncapped neighbourhood on a hub entity is how a prompt budget disappears.

        🔴 **`as_of` ADDED 2026-08-30 (T48s), because it was MISSING and the read was leaking
        spoilers.** `/internal/books/{id}/kg/neighborhood` accepts `as_of_chapter`, computes
        `effective_as_of = kg_as_of_or_drop(...)`, reports
        `temporal_capability.kg = "ordinal_valid_time"` — and then called this operation
        WITHOUT the value, because the operation had nowhere to put it. Measured on the live
        stack: at `as_of=1` (ordinal 1 000 000) the endpoint returned edges with
        `valid_from_ordinal` up to **10 000 000**. A reader held at chapter 1 was shown
        relationships that do not exist until chapter 10.

        How it went missing is worth keeping. `neighborhood` was SPLIT from `relations_for`
        deliberately — that delegate applied `confidence >= 0.8` and excluded archived peers,
        which silently dropped edges from this answer. The replacement query filters
        `valid_until IS NULL` alone, i.e. the HEAD, and the `as_of` that `relations_for`
        already carried did not come across. **A correct fix to one filter removed another.**

        The window is `relations_for`'s, not a second one: `as_of=None` reads the HEAD, and
        `as_of=N` keeps only edges whose half-open story interval covers N —
        `valid_from_ordinal <= N < valid_to_ordinal` — with a POSITIONLESS edge EXCLUDED,
        because it cannot be placed on the axis and including it would mix untimed legacy
        data into an answer whose whole value is that it is timed. One concept, one
        definition; two would drift the first time either moved.
        """
        ...

    async def archive_entity(
        self, *, user_id: str, canonical_id: str, reason: str,
    ) -> Entity | None:
        """Soft-delete. `reason` is required because the archive is auditable — an entity
        that vanished with no reason cannot be told from one lost to a bug."""
        ...

    async def restore_entity(self, *, user_id: str, canonical_id: str) -> Entity | None:
        """Undo an archive. `None` when the id does not exist or is not this user's."""
        ...

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
        """Create or update one edge. `valid_from_ordinal` stamps the story position the
        edge was established at; leaving it `None` writes a positionless edge, which is
        what legacy data looks like and what an as-of read cannot place.

        NO `project_id`: an edge inherits its scope from the entities it connects, and both
        endpoints are already tenant-resolved. A project parameter here would be a third
        source of truth for the same fact, and the one most likely to disagree.

        `source_event_id` is SINGULAR — the write records the one event that established
        this edge. The plural lives on the READ (`Relation.source_event_ids`), where later
        events accumulate onto the same arc.
        """
        ...

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
        """This entity's edges. `as_of=None` reads the HEAD — byte-identical to the
        pre-port behaviour.

        With `as_of=N`, only edges whose story interval covers N are returned, using the
        half-open convention `valid_from_ordinal <= N < valid_to_ordinal`. **A positionless
        edge (`valid_from_ordinal IS NULL`) is EXCLUDED** by an as-of read: it cannot be
        placed on the axis, and including it would silently mix untimed legacy data into an
        answer whose entire value is that it is timed.
        """
        ...

    # ── relation corrections (T17/A1) ────────────────────────────────
    #
    # The three operations a CORRECTION path needs, which the read/upsert pair cannot
    # express. They are separate primitives on purpose: `recreate_relation` resurrects a
    # user-invalidated edge, and folding that into `upsert_relation` would let an extraction
    # re-run silently revive an edge the author deleted — the exact accident the concrete
    # repo split them to prevent.
    #
    # ⚠️ `invalidate_relation` closes the WALL-CLOCK interval (`valid_until`, a datetime).
    # It does NOT close the STORY interval (`valid_to_ordinal`, a chapter ordinal), which is
    # a different axis — see `D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL`, still open after this
    # batch. Two axes, two closes; conflating them is what T45 exists to prevent.

    async def get_relation(self, *, user_id: str, relation_id: str) -> Relation | None:
        """One edge by its deterministic id, or `None` if no row matches under this user.

        `None` is a MISS, never a permission error — the same no-existence-oracle shape the
        rest of the port uses: a caller cannot learn that someone else's relation exists.
        """
        ...

    async def invalidate_relation(
        self, *, user_id: str, relation_id: str, valid_until: datetime | None = None,
    ) -> Relation | None:
        """Soft-invalidate an edge by stamping `valid_until` (default: now).

        Idempotent — re-invalidating an already-invalid edge moves `valid_until` to the new
        instant rather than failing, because a correction that errors on a repeat is a
        correction that cannot be retried after a timeout.

        The default read filters exclude `valid_until IS NOT NULL`, so this hides the edge
        from every ordinary read without deleting it.
        """
        ...

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
        """The AUTHOR-asserted edge: confidence 1.0, and it RESURRECTS `valid_until` to NULL
        if this tuple was previously invalidated (F5).

        That resurrection is why this is not a flag on `upsert_relation`. An extraction
        writer re-mentioning a pair must never revive an edge a human removed, and a shared
        entry point with a boolean would make that one wrong argument away.

        `valid_from_ordinal` is the STORY position the author asserts the relation from —
        the same `event_order` axis the extraction writer stamps. Without it an authored
        relation is positionless and invisible to every as-of read, which is precisely how
        T36's roles were authored and then could not be found.
        """
        ...

    # ── the paginated browse (T17/A3) ────────────────────────────────

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
        """One PAGE of events plus the TOTAL that matched — the browse, not the window.

        ── The disagreement this method settles, kept legible ────────────────────────────
        The Neo4j adapter's own module docstring argued the other way, and it is quoted here
        rather than deleted by the side that won:

            "`chronological` and `date` need the filtered one, which also returns a total
             count this port drops — **a count belongs to a paginated browse, not to
             'give me the events in this window'**."

        That reasoning is CORRECT and is exactly why `events_in_window` still has no total:
        a windowed read answers "what happened between here and there", and a count would be
        an unrelated second question riding along. **The PO decision (2026-08-13,
        `T17: the port owns everything`) does not overrule the reasoning — it adds the browse
        the reasoning was pointing at.** The adapter was right that a count belongs to a
        paginated browse; there simply was not one, so the count was being dropped on the
        floor and every caller that needed it stayed bound to `graph_repos`.

        ── Why a tuple and not a page object ─────────────────────────────────────────────
        `(rows, total)` mirrors the concrete `list_events_filtered` exactly. A richer wrapper
        would be a THIRD shape for the same fact — the port's, the repo's, and the HTTP
        layer's — and this plan has already paid twice for a value that is re-expressed at
        each boundary and drifts at one of them.

        `total` is the count of everything matching the FILTERS, ignoring `limit`/`offset`.
        A total that shrank with the page would make "showing 1–50 of 50" true on every page
        of a thousand, which is the shape of an off-by-a-page bug nobody sees.
        """
        ...

    # ── event corrections (T17/A2) ───────────────────────────────────

    async def get_event(self, *, user_id: str, event_id: str) -> Event | None:
        """One event by id, or `None` for a miss — same no-existence-oracle rule as
        `get_relation`: another user's event is absent, not forbidden."""
        ...

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
        """Idempotent upsert keyed on (user, project, chapter, title).

        The merge semantics are CONTRACT, not implementation detail, because each one hides
        a different silent failure:

        * `source_types` accumulates, `confidence` is a max, `participants` union-merge —
          a re-mention must never narrow what is already known.
        * `summary` upgrades from NULL and **never overwrites** — a later, thinner mention
          must not erase a richer one.
        * `event_order` keeps the **MINIMUM** across mentions. That is spoiler-safety (CM4):
          the earliest reading position at which the event is known wins, so an event
          re-mentioned in chapter 40 does not migrate forward and become invisible to a
          reader at chapter 12. An adapter that took the latest would leak nothing and hide
          everything — the failure is silent in both directions.
        """
        ...

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
        """User-edit the display fields under OPTIMISTIC CONCURRENCY.

        Returns `(event, before)`; `before` is the pre-edit snapshot the correction event is
        written from. `(None, None)` is a miss. A stale `expected_version` raises
        `VersionMismatchError` — it must RAISE and not silently no-op, because a lost update
        that reports success is indistinguishable from a saved one to the caller who just
        overwrote someone else's edit.

        A `None` field means "leave unchanged", which is why every field is explicit rather
        than defaulted: an omitted argument and an intentional clear would otherwise be the
        same call.
        """
        ...

    async def archive_event(self, *, user_id: str, event_id: str) -> Event | None:
        """Soft-archive (the user-facing "delete" = hide). Idempotent — re-archiving an
        already-archived event succeeds, so the correction can be retried after a timeout.
        `None` is a miss."""
        ...

    # ── facts (T17/A7) ───────────────────────────────────────────────

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
        """Idempotent fact upsert, content-keyed.

        ⚠️ **`maintain_chain` is the operation this method exists for, and the one an adapter
        is most likely to get quietly wrong.** With it set (the extraction path), the store
        re-derives the `valid_to_ordinal` CHAIN for this fact's `(subject, type)` after the
        merge: the prior containing fact closes at this ordinal, and this one closes at the
        next strictly-greater ordinal — correct under out-of-order and backfill arrival, which
        is the whole difficulty. Left `False` (chat tools, the L2 loader) the merge is a plain
        upsert and no interval moves.

        An adapter that accepted the flag and did nothing would produce a graph where every
        fact is open forever: every as-of read then answers with the LATEST value at every
        position, which looks like a working timeline and is a book with no history. That
        failure is silent in exactly the way `D-T42A-PORT-CANNOT-CLOSE-AN-INTERVAL` describes
        for relations — this is the same axis, on the other node type.

        `valid_from_ordinal` defaults to `from_order` when omitted, so a positioned fact opens
        a story interval automatically. `type` must be one of `FACT_TYPES`
        (`app.domain.fact_types`) — the write path validates against that tuple, not against a
        wider vocabulary a caller might hold.

        NO `valid_from` datetime parameter: this port speaks the STORY axis. The wall-clock
        axis is a different question (T45), and offering both here is how a caller ends up
        passing the one it did not mean.
        """
        ...

    async def facts_for(
        self,
        *,
        user_id: str,
        subject_id: str,
        type: str | None = None,
        as_of: int | None = None,
        limit: int = 100,
    ) -> list[Fact]:
        """The facts ABOUT one subject — the READ that makes `merge_fact` checkable.

        Written for SPEC §1.1. `merge_fact` has two contracts and the port could verify
        NEITHER, because it could write a fact and not see one: the ordinal CHAIN is
        re-derived *after* the merge (so the returned `Fact` predates it, and carries no
        `subject_id` to identify its family), and DUPLICATION is invisible because the id is
        content-derived — an appending store returns the same id a merging one does.
        Detecting either needs a COUNT over the family, which is exactly this.

        `as_of=None` reads the HEAD. With `as_of=N` the same half-open story window every
        other timed read uses applies — `valid_from_ordinal <= N < valid_to_ordinal` — and a
        POSITIONLESS fact is EXCLUDED, for the reason `relations_for` states: it cannot be
        placed on the axis, and including it would mix untimed legacy data into an answer
        whose entire value is that it is timed.

        `type=None` reads every type on the subject. Ordered oldest-first by
        `valid_from_ordinal` so the chain reads as a chain; a head read that includes
        positionless facts sorts those last, since they have no place on the axis.

        This does NOT give a caller a way to SET `valid_to_ordinal`, and that stays
        deliberate (SPEC §1.1): a raw setter lets a caller write an inconsistent chain.
        `maintain_chain` is the close; this is how you check it worked.
        """
        ...

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
        """Attach an `EVIDENCED_BY` edge and atomically bump the target's counters.

        **Added to the port 2026-08-12 by DEMAND, not inventory** (T17): 8 call sites across
        3 modules — `pass2_writer`, `pattern_writer`, `backfill_status`. That is the rule the
        port's own header states, and the measured tail behind it is why the rule matters:
        106 distinct repo functions are still called, **64 % of them exactly once**. A port
        that absorbed all of those would be `graph_repos` with an interface in front.

        ⚠️ **The atomic counter increment is the whole point.** Writing the edge directly
        would let `evidence_count`/`mention_count` drift, and the K11.9 reconciler is only the
        offline net that catches drift — never producing it is the cheaper path. An adapter
        that implements this as "write edge, then read-modify-write the counter" satisfies the
        signature and breaks the invariant.

        Returns `None` when the target or the source does not exist under this user: *"no
        evidence to record"*, not an error. `quote` is the verbatim supporting span, and a
        re-extraction that carries one **backfills** a previously quoteless edge rather than
        wiping it.
        """
        ...

    async def status_at_order(
        self,
        *,
        user_id: str,
        project_id: str | None,
        entity_ids: list[str],
        at_order: int,
        min_evidence: int = 1,
    ) -> dict[str, str]:
        """`{entity_id: status}` at a story position — alive/gone as of chapter N.

        `min_evidence` exists because a status derived from a single mention is a guess;
        the canon guard raises the bar rather than acting on one.
        """
        ...

    # ── the project as a whole ───────────────────────────────────────

    async def project_graph_stats(
        self, *, user_id: str, project_id: str,
    ) -> dict[str, int]:
        """Node counts for one project, keyed `{label.lower()}_count` over
        `COUNTABLE_LABELS` — `entity_count`, `fact_count`, `event_count`.

        Zeros for an empty graph, which is a legitimate state (extraction enabled, nothing
        run yet) and not an error: the caller renders "Ready", not a failure.

        ⚠️ **`passage_count` is NOT here, and that is the port doing its job.** The repo
        function this replaces counts four labels, the fourth being `:Passage` — but a
        passage is the VECTOR layer's row, not the graph's. `VectorStore` owns it, §3.1
        moves it to Postgres, and neither the AGE nor the Kuzu adapter has a passage table
        at all. Keeping the field would force every future graph adapter to answer a
        question about a store it does not hold, and the only honest answers available to it
        are `0` (a lie that reads as "no passages") or a refusal (which would make a stats
        card unrenderable on a working engine). The caller that needs both counts asks both
        stores — which is what having two stores means.

        Spec §1.2 put this on the port over the janitors beside it because a second engine
        genuinely must answer it: it is a question about the BOOK ("how much is in here"),
        asked by a dashboard, not housekeeping.
        """
        ...

    async def find_gap_candidates(
        self,
        *,
        user_id: str,
        project_id: str | None,
        min_mentions: int = 50,
        limit: int = 100,
    ) -> list[Entity]:
        """Discovered entities with no glossary link, worth promoting — the gap report.

        Four predicates, and each one is load-bearing rather than a filter for tidiness:

        ```
        glossary_entity_id IS NULL   DISCOVERED only — a linked entity is not a gap
        archived_at IS NULL          the author already said no to this one
        mention_count >= $min        KSA §3.4.E; below the floor is extraction noise
        ORDER BY mention_count DESC, confidence DESC, name ASC
        ```

        **The sort is a three-key composite and every adapter must honour all three.** A
        gap report is a page the author works through top-down, so the order IS the product;
        two adapters that agree on the SET and disagree on the ORDER would show different
        work queues for the same book, and a set-equality test would call that parity.

        `min_mentions=0` is legal and means "everything discovered", which is a different
        request from the default and not a degenerate one — a fresh book has no entity at 50.
        A NEGATIVE floor, or a limit of zero or less, RAISES: they are caller errors, and the
        repo has refused them since it was written.
        """
        ...

    async def purge_project(self, *, project_id: str) -> dict[str, int]:
        """Delete every node this project owns. Returns `{nodes_deleted, indexes_dropped}`.

        ⚠️ **There is no `user_id` here, and its absence is the contract — not an oversight.**
        Every other method on this port filters by tenant, so a reader is entitled to assume
        this one does too. It must not, and the reason is the defect the operation exists to
        fix (`D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN`): the authority for a purge is the
        owner-gated Postgres project delete that has *already happened*. Once that row is gone
        every node carrying its `project_id` is an orphan, whoever wrote it — so a user-scoped
        purge would leave exactly the orphan this is here to prevent, and report success.

        Measured on dev before choosing (T17 A31), because "one project, one user" is a
        property of the data rather than of the schema:

            432 of 433 projects   exactly ONE distinct user_id  -> scoping is a no-op
            `p-assist`            21 users, 21 nodes, 1 each    -> the assistant sentinel,
                                                                   not reachable by project DELETE

        **Best-effort at the CALL SITE, not here.** The caller wraps this and logs; an adapter
        that swallowed its own failure would make "purged" and "could not reach the graph"
        the same observable, which is the confusion T17 A31 found in the AGE path — a named
        refusal from index administration read as *"graph orphaned, re-sweep owed"* on every
        single delete, while the nodes had in fact gone.

        `indexes_dropped` counts per-project summary vector indexes removed. It is `0` on any
        engine without Neo4j index administration, and such an engine reports the reason in
        `indexes_skipped` rather than pretending it dropped none because there were none.
        """
        ...

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
        """Events between two bounds on one axis.

        `after`/`before` are ordinals for `narrative` and `chronological`, and ISO date
        strings for `date`. Typing them as a union rather than splitting into three methods
        keeps the axis a value a caller can pass through — which is what the timeline UI
        actually does with its sort toggle.
        """
        ...
