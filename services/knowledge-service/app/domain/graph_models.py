"""The graph domain models — the vocabulary the `GraphStore` port speaks.

WHY THEY MOVED OUT OF `neo4j_repos` (T17)
------------------------------------------
`ports/graph_store.py` imported `Entity`, `Relation`, `Event` and friends from
`db/neo4j_repos/` — so **the port imported its own implementation**. Every signature on the
port was typed in the vocabulary of one engine, and `port-adoption-gate` counted the port
itself among the modules bound to the concrete layer, correctly: an import is an import.

That is not a cosmetic problem. It is the reason the gate's ceiling could not reach zero no
matter how many call sites migrated, and it meant a second adapter (AGE) returned Neo4j's
models by definition rather than by agreement.

These classes never depended on the repository layer — checked by AST before moving, and
every one came back with no module-level dependency except `EntityDetail` on `Entity`,
which moved with it. They are plain Pydantic/dataclass shapes: the DOMAIN's vocabulary that
happened to be defined next to the first thing that spoke it.

⚠️ `neo4j_repos` re-exports every name from here, so existing imports keep working. That is
deliberate: moving 380 lines of models and rewriting ~60 importers in one commit would make
a mechanical change impossible to review. The re-exports are the compatibility shim, and the
gate's ceiling is what records callers moving off them.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, computed_field, model_serializer

__all__ = [
    "Entity",
    "EntityDetail",
    "EvidenceWriteResult",
    "Event",
    "PromotionSignals",
    "Relation",
]


class Entity(BaseModel):
    """Pydantic projection of an `:Entity` node.

    Mirrors the property set documented in KSA §3.4.B + §3.4.E.
    Fields that are populated by K11.5b (embeddings) or K11.8
    (evidence_count) are present as Optional so the model can
    represent both a freshly-merged entity and a fully-anchored
    one without two separate types.
    """

    id: str
    user_id: str
    project_id: str | None = None
    name: str
    canonical_name: str
    kind: str
    aliases: list[str] = Field(default_factory=list)
    canonical_version: int = 1
    source_types: list[str] = Field(default_factory=list)
    confidence: float = 0.0

    # Two-layer anchoring (KSA §3.4.E).
    glossary_entity_id: str | None = None
    anchor_score: float = 0.0

    # Soft-archive (KSA §3.4.F).
    archived_at: datetime | None = None
    archive_reason: str | None = None

    # K11.8 maintains this; K11.5a queries against the
    # `entity_user_evidence` composite index.
    evidence_count: int = 0
    # K11.5b: mention_count is the number of times this entity
    # was observed during extraction. K11.8 increments it; K11.5b's
    # recompute_anchor_score divides by max-per-project to derive
    # anchor_score for discovered (non-anchored) entities.
    mention_count: int = 0

    # K19d γ-a: set to True by `update_entity_fields` (backing the
    # PATCH /entities/{id} route). Once true, `merge_entity`'s
    # ON MATCH branch no longer re-adds extracted name variants to
    # `aliases` — the extractor can't silently undo a user's edit.
    # Existing nodes created before K19d γ-a lack this property and
    # read-path `coalesce(user_edited, false) = false` treats them
    # as un-edited, preserving the old behaviour on re-extraction.
    user_edited: bool = False

    # C9 (D-K19d-γa-01): optimistic-concurrency counter. Bumped by
    # every user-facing write (PATCH, unlock, user-merge, extraction
    # merge_entity). Pre-C9 nodes without the property read as 1 via
    # `_node_to_entity`'s coalesce — the first write after C9 will
    # mint the value. Router hands out weak ETags of the form
    # `W/"<version>"` and requires If-Match on PATCH.
    version: int = 1

    # Cycle 73e: True when minted by Pass2 writer's Tier-B autocreate
    # (relation subject/object unresolved against extracted entity
    # list AND not in anchors). Cleared on legit re-extraction via
    # `_MERGE_ENTITY_CYPHER`'s ON MATCH promotion CASE. Legacy nodes
    # without the property read as False via `_node_to_entity` +
    # `coalesce(e.auto_created, false)` Cypher idiom.
    auto_created: bool = False

    created_at: datetime | None = None
    updated_at: datetime | None = None

    # C8 (C8-entity-status LOCKED) — DERIVED status, never a stored
    # column. The two-layer anchor model already carries the source
    # fields (`archived_at`, `glossary_entity_id`); `status` is a pure
    # projection over them so the FE renders ⭐/💭/📦 without inferring
    # the precedence itself.
    #
    # Precedence (BE+FE MUST agree): `archived` wins over `canonical`.
    # A soft-archive (`_ARCHIVE_CYPHER`) already nulls
    # `glossary_entity_id`, so in practice the two are mutually
    # exclusive — but if a future write path ever leaves both set, an
    # archived entity must read as archived (it is out of the active
    # retrieval set), not canonical. `discovered` = unanchored + active.
    @computed_field  # type: ignore[prop-decorator]
    @property
    def status(self) -> str:
        if self.archived_at is not None:
            return "archived"
        if self.glossary_entity_id is not None:
            return "canonical"
        return "discovered"

@dataclass(frozen=True)
class PromotionSignals:
    """Graph-native per-entity promotion inputs (P3a): evidence + mentions + edit
    recency, as stored on the `:Entity` node. Scoring lives in the selector; this
    module only reads."""
    evidence_count: int
    mention_count: int
    updated_at: datetime | None

class EntityDetail(BaseModel):
    """K19d.4 — `GET /v1/knowledge/entities/{id}` response payload.

    Relations are projected with both endpoint node id/name/kind so
    the FE can render `(subject)-[predicate]->(object)` without a
    second round-trip per row. Direction is inferable by comparing
    `relations[i].subject_id == entity.id`.
    """

    entity: Entity
    relations: list[Relation]
    relations_truncated: bool = False
    total_relations: int = 0

class Relation(BaseModel):
    """Pydantic projection of a `:RELATES_TO` edge.

    The endpoints are returned alongside the edge properties so
    the caller can render `(subject_name)-[predicate]->(object_name)`
    without a second round-trip. Endpoint nodes are projected as
    just `id` + `name` + `kind` to keep the payload small —
    callers that need the full node go through K11.5's
    `get_entity`.
    """

    id: str
    user_id: str
    subject_id: str
    object_id: str
    predicate: str
    confidence: float = 0.0
    source_event_ids: list[str] = Field(default_factory=list)
    source_chapter: str | None = None
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    # F3 — story (valid) time axis (chapter ordinals). The existing
    # valid_from/valid_until above are wall-clock TRANSACTION-time; these are the
    # STORY-time half-open interval [valid_from_ordinal, valid_to_ordinal) over
    # the (subject, predicate) arc. valid_from_ordinal is stamped at write time
    # (the chapter ordinal the edge was established at, on the same scale as
    # events.event_order); valid_to_ordinal is set ONLY by temporal.maintain_chain
    # when a later instance on the same (subject, predicate) chain supersedes it.
    # NULL on legacy / positionless edges. See app.db.neo4j_repos.temporal + §12.3.
    valid_from_ordinal: int | None = None
    valid_to_ordinal: int | None = None
    valid_to_ordinal_eff: int | None = None
    # dec-3 (D-KG-INSTORY-EVENTDATE) — detected in-story (narrative) time as a
    # truncated ISO string: "YYYY" / "YYYY-MM" / "YYYY-MM-DD". An ADDITIONAL,
    # optional valid-time REFINEMENT alongside the chapter-ordinal axis
    # (valid_from_ordinal) — chapter-ordinal stays the PRIMARY / spoiler-safe
    # story-time axis; event_date_iso is a SECONDARY descriptive sort/filter key
    # supplied only when the prose carries an explicit in-story date. NULL is the
    # dominant case and never affects the ordinal chain. Mirrors :Event /
    # :Fact event_date_iso (same truncated-ISO shape, precision-preferring merge).
    event_date_iso: str | None = None
    pending_validation: bool = False
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # Endpoint projection — populated by find_* helpers.
    subject_name: str | None = None
    subject_kind: str | None = None
    object_name: str | None = None
    object_kind: str | None = None

class Event(BaseModel):
    """Pydantic projection of an `:Event` node."""

    id: str
    user_id: str
    project_id: str | None = None
    title: str
    canonical_title: str
    summary: str | None = None
    chapter_id: str | None = None
    # C6 (D-K19e-β-01) — resolved chapter title denormalized in from
    # book-service at response time via BookClient.get_chapter_titles.
    # ``None`` on both pre-resolution and book-service unavailable
    # paths; the FE falls back to a UUID-suffix short via the
    # existing ``chapterShort()`` helper.
    chapter_title: str | None = None
    event_order: int | None = None
    chronological_order: int | None = None
    # C18 (D-K19e-α-02 closer) — in-story wall-clock date as ISO with
    # optional truncation: "YYYY" / "YYYY-MM" / "YYYY-MM-DD". String
    # not date so partial-precision dates ("summer 1880" → "1880-06")
    # preserve the "I don't know the day" signal. Sort-stable
    # lexicographically. Distinct from `time_cue` (free-text narrative
    # hint, kept for display).
    event_date_iso: str | None = None
    # C18-DEF-01 — narrative time hint preserved verbatim from the LLM
    # (e.g. "the next morning", "in his youth", "summer 1880"). Distinct
    # from event_date_iso: time_cue is free-text for FE display;
    # event_date_iso is the structured timeline-filter axis (parsed via
    # parse_time_cue_to_iso when possible). First-write-wins on
    # ON MATCH so re-mentions don't churn the original phrasing.
    time_cue: str | None = None
    # D-W10-ARC-CONFORMANCE-THREAD-TAG — the narrative-thread label (combat/romance/…)
    # the thread-tag classifier assigns from a caller-supplied vocabulary (the arc's
    # threads). None until tagged; the motif_beat extractor prefers it over chapter_id
    # so deep arc-conformance can measure realized thread-progression from prose.
    narrative_thread: str | None = None
    # D-W10-ARC-CONFORMANCE-SUCCESSION — which arc-placement motif (by code) this event
    # realizes, assigned by the motif-tag classifier. None until tagged; motif_beat emits it
    # so deep arc-conformance reconstructs the realized motif order for the succession diff.
    realized_motif_code: str | None = None
    # D-W8-MOTIF-BEAT-LLM-EXTRACTOR — which catalog motif (by code) this event most embodies,
    # assigned by the tag-beats classifier against the user's VISIBLE motif catalog (system +
    # user motifs), independent of any arc. None until tagged. DISTINCT from realized_motif_code
    # (that one is arc-scoped, vs the arc's placements) so mining and arc-conformance never
    # clobber each other's tags. The motif_beat producer emits it as the generic beat/thread
    # axes so corpus PrefixSpan mines reusable motif-SEQUENCES (arc skeletons), not one-off
    # concrete titles. "" / null is the Option-A fallback (title/chapter_id).
    mined_motif_code: str | None = None
    participants: list[str] = Field(default_factory=list)
    # KG-TL Option A (D-KG-TL-PARTICIPANT-ANCHOR) — stored anchor: the glossary
    # ``entity_id`` per participant slot, same length+order as ``participants``,
    # ``""`` where the participant couldn't be anchored (Neo4j lists can't hold
    # nulls → ``""`` sentinel, never a real UUID). ``exclude=True``: populated
    # FROM the node so the read-time localizer can consume it, but NOT serialized
    # into the timeline API response — it's an internal anchor, not FE-facing, so
    # the wire contract is unchanged. ``None`` / a length-mismatched array signals
    # "not resolved" → the localizer falls back to read-time name resolution.
    participant_entity_ids: list[str] | None = Field(default=None, exclude=True)
    confidence: float = 0.0
    source_types: list[str] = Field(default_factory=list)
    evidence_count: int = 0
    mention_count: int = 0
    archived_at: datetime | None = None
    # Phase B C2: optimistic-concurrency version for user edits (If-Match).
    # ON CREATE = 1; bumped only by update_event_fields (user edit), NOT by
    # extraction re-mention (merge_event ON MATCH leaves it) so a user's
    # If-Match baseline stays valid across re-extractions. Pre-C2 nodes lack
    # the property → defaults to 1 here + coalesce(e.version,1) in Cypher.
    version: int = 1
    created_at: datetime | None = None
    updated_at: datetime | None = None

    # ── KG-TL (timeline localization) — DERIVED, response-only Layer-2 fields ──
    # NEVER stored on the :Event node (AC-T6): the source `title`/`summary`/
    # `time_cue`/`participants` above stay canonical source-language. These are
    # populated ONLY when a reader language resolves on the read path; absent a
    # reader language they stay None (the no-op / back-compat path, AC-T5).
    #
    # M2 — participant names localized via the glossary entity-name join. Same
    # length + order as `participants`; each slot is the reader-language name when
    # the glossary had a translation, else the source name. `*_translated` is the
    # per-slot signal (True ⇒ localized; False ⇒ source-fallback, FE marks it).
    participants_localized: list[str] | None = None
    participants_translated: list[bool] | None = None
    # M3 — free-text fields localized via the on-demand event_text_translations
    # cache. `*_localized` = COALESCE(cache, source); `*_translated` = cache hit?
    # On a cache MISS the localized value IS the source text and the flag is False
    # (AC-T4: source + "translation pending" marker, never a blocking inline LLM).
    summary_localized: str | None = None
    summary_translated: bool | None = None
    time_cue_localized: str | None = None
    time_cue_translated: bool | None = None
    title_localized: str | None = None
    title_translated: bool | None = None

    # C14 (C14-importance-major-pivotal LOCKED) — DERIVED importance,
    # never a stored column and never an extraction pass. The :Event
    # node already carries the salience signals (mention_count,
    # participants, confidence, evidence_count); `importance` is a pure
    # projection over them so the timeline rail can render major/pivotal
    # badges without re-extracting or migrating the graph.
    #
    # Closed enum = major | pivotal ONLY (EVENT_IMPORTANCE). The default
    # is None ("unset") — an ordinary event is NEVER mislabeled major.
    # Back-compat: callers that ignore the field are unaffected; the wire
    # gains an optional key whose value is null for the common case.
    #
    # Derivation (BE+FE agree the enum but only BE computes). Salience is a
    # blend of two independent signals so the score is robust when either is
    # degenerate (e.g. a corpus whose extraction never accumulated re-mentions
    # leaves every mention_count == 1 — then participant-breadth + confidence
    # carry the signal; a sparse-cast corpus leans on re-mention frequency):
    #   - pivotal = a clear hinge: (≥3 named participants AND confidence ≥ 0.75)
    #     OR a heavily re-referenced event (mention_count ≥ 5). The multi-party
    #     high-confidence scene is the one a reader would mark even if it is
    #     only mentioned once.
    #   - major   = notable-but-not-hinge: (≥2 participants AND confidence ≥ 0.6)
    #     OR mention_count ≥ 3. Recurs through the narrative without the full
    #     pivotal signature.
    #   - else None — the long tail of one-off, single-party, lightly-
    #     referenced events stays unbadged (the *whole point* of the feature:
    #     highlight the few that matter, don't paint everything major).
    @computed_field  # type: ignore[prop-decorator]
    @property
    def importance(self) -> str | None:
        participant_count = len(self.participants)
        if (
            participant_count >= 3 and self.confidence >= 0.75
        ) or self.mention_count >= 5:
            return "pivotal"
        if (
            participant_count >= 2 and self.confidence >= 0.6
        ) or self.mention_count >= 3:
            return "major"
        return None

    # KG-TL — keep the canonical (no-reader-language) response BYTE-IDENTICAL
    # (AC-T5). The 8 derived localization fields above stay None on the canonical
    # path; rather than emit 8 new `null` keys (which would change the wire shape
    # for every existing consumer), drop them from the serialized output WHEN they
    # are all None. When a reader language resolves and the router populates them,
    # they serialize normally. This is surgical — only the KG-TL fields are
    # affected; every other nullable field (summary, time_cue, …) is untouched.
    _KG_TL_FIELDS = (
        "participants_localized",
        "participants_translated",
        "summary_localized",
        "summary_translated",
        "time_cue_localized",
        "time_cue_translated",
        "title_localized",
        "title_translated",
    )

    @model_serializer(mode="wrap")
    def _serialize(self, handler):  # type: ignore[no-untyped-def]
        data = handler(self)
        # Only when localization didn't run (every KG-TL field is None) do we omit
        # the keys — preserving today's exact wire shape. If ANY is set, keep all
        # so the FE sees the full parallel arrays/flags.
        if all(getattr(self, f) is None for f in self._KG_TL_FIELDS):
            for f in self._KG_TL_FIELDS:
                data.pop(f, None)
        return data

class EvidenceWriteResult(BaseModel):
    """Returned by `add_evidence` so the caller can log the
    post-write counters and tell whether the edge was newly
    created or already present."""

    evidence_count: int
    mention_count: int
    created: bool


# ── the reading axis (T17 A4) ────────────────────────────────────────────────
#
# CM4 — reading-order (`event_order`) scale. `event_order = chapter sort_order × this
# stride + within-chapter index`, so the axis is dense at chapter granularity. **Single
# source of truth** — the write path (`pass2_writer`) AND the backfill MUST import this; a
# divergence would put their event_orders on different scales and corrupt the timeline. It
# is also the chapter→order contract a composition spoiler-cutoff uses: "canon before
# chapter N" = `before_order N × EVENT_ORDER_CHAPTER_STRIDE`.
#
# It lives HERE and not in `neo4j_repos` because it is a fact about the BOOK, not about a
# graph engine. Leaving it there made every consumer of the reading axis — including ones
# that touch no Cypher at all — count as bound to the concrete layer, which is both untrue
# and, for `port-adoption-gate`, indistinguishable from a real binding.
EVENT_ORDER_CHAPTER_STRIDE = 1_000_000
