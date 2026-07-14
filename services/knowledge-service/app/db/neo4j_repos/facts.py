"""K11.7 — facts repository.

Functions over `:Fact` nodes. A Fact is a typed propositional
statement extracted from text — distinct from `:Event` (a
discrete narrative happening) and from `:RELATES_TO` (a directed
edge between two entities). Examples per KSA §5.1:

  - decision: "We decided to use fire magic"
  - preference: "Kai always carries a sword"
  - milestone: "Phoenix completes her training"
  - negation: "Water Kingdom does not know Kai killed Zhao"

Facts have a temporal model identical to relations: `valid_from`
on creation, `valid_until` set by `invalidate_fact` when
contradicting evidence arrives. Pass 1 (pattern) facts carry
`pending_validation = true` and are excluded from the L2 RAG
context loader by default; K17 LLM Pass 2 promotes them by
re-merging with higher confidence.

Idempotency: deterministic id from `(user_id, project_id, type,
canonicalize_text(content))`. Re-extracting the same fact from
any source is a no-op.

Reference: KSA §3.4 (Fact nodes), §5.1 (Pass 1 quarantine),
K11.3 schema indexes fact_id_unique, fact_user_evidence.
"""

from __future__ import annotations

import hashlib
import logging
from datetime import date as date_cls
from datetime import datetime
from typing import Any, Literal, get_args

from pydantic import BaseModel, Field

from app.db.neo4j_helpers import CypherSession, run_read, run_write
from app.db.neo4j_repos.canonical import canonicalize_entity_name, canonicalize_text
from app.db.neo4j_repos.temporal import (
    MAINTAIN_FACT_CHAIN_CYPHER,
    ORDINAL_OPEN_CEILING,
)

logger = logging.getLogger(__name__)

__all__ = [
    "Fact",
    "FactType",
    "FACT_TYPES",
    "fact_id",
    "merge_fact",
    "get_fact",
    "list_facts_by_type",
    "list_facts_for_entity",
    "invalidate_fact",
    "delete_facts_with_zero_evidence",
    "fact_coverage_for_entity",
]

# Closed enum per KSA §5.1. New types require both a code change
# and an extraction-side pattern, so a Literal is fine.
FactType = Literal["decision", "preference", "milestone", "negation", "statement"]
# DERIVE the runtime validation tuple from the Literal — never hand-maintain a parallel copy. WS-2.1
# added 'statement' to the Literal but a hand-kept tuple missed it, so a statement fact queued fine yet
# 500'd at merge_fact (caught by the WS-2.4 live smoke). get_args keeps the two in lockstep by design.
FACT_TYPES: tuple[str, ...] = get_args(FactType)


def fact_id(
    user_id: str,
    project_id: str | None,
    type: str,
    content: str,
) -> str:
    """Deterministic id for a `:Fact` node.

    Same `(user_id, project_id, type, canonicalize_text(content))`
    tuple → same id. Re-extraction is a no-op.

    `type` is part of the key so two facts with identical content
    but different types ("decision: use fire magic" vs
    "preference: use fire magic") are distinct nodes.
    """
    if not user_id:
        raise ValueError("user_id is required for fact_id")
    if not type:
        raise ValueError("type is required for fact_id")
    if type not in FACT_TYPES:
        raise ValueError(f"type must be one of {FACT_TYPES}, got {type!r}")
    if not content:
        raise ValueError("content is required for fact_id")
    canonical = canonicalize_text(content)
    if not canonical:
        raise ValueError(
            f"content {content!r} canonicalizes to empty — cannot derive id"
        )
    key = f"v1:{user_id}:{project_id or 'global'}:{type}:{canonical}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


class Fact(BaseModel):
    """Pydantic projection of a `:Fact` node."""

    id: str
    user_id: str
    project_id: str | None = None
    type: str
    content: str
    canonical_content: str
    confidence: float = 0.0
    pending_validation: bool = False
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    source_types: list[str] = Field(default_factory=list)
    source_chapter: str | None = None
    # T2.1 — reading-axis order (chapter_sort_order × EVENT_ORDER_CHAPTER_STRIDE),
    # stamped at extraction so the codex can spoiler-window a fact to the chapter it
    # was established in. NULL on legacy facts + chat-tool facts (no chapter) → those
    # are excluded under any finite window (NULL <= X is null/false in Cypher).
    from_order: int | None = None
    # F3 — story (valid) time axis (chapter ordinals), UNIFIED with from_order.
    # Half-open interval [valid_from_ordinal, valid_to_ordinal); open = NULL =
    # +∞. valid_from_ordinal defaults to from_order at write time (the same
    # reading-axis ordinal the fact was established at); valid_to_ordinal is set
    # ONLY by temporal.maintain_chain (the single chain-maintenance writer) when
    # a later fact on the same (subject, type) chain supersedes it. The wall-
    # clock valid_from/valid_until above stay the TRANSACTION-time axis. NULL on
    # legacy / positionless facts (chat-tool facts with no chapter).
    # See app.db.neo4j_repos.temporal + spec §12.3.
    valid_from_ordinal: int | None = None
    valid_to_ordinal: int | None = None
    # Indexable null-sink ceiling for open intervals (= INT64_MAX when open);
    # maintained in lockstep with valid_to_ordinal by maintain_chain.
    valid_to_ordinal_eff: int | None = None
    # dec-3 (D-KG-INSTORY-EVENTDATE) — detected in-story (narrative) time as a
    # truncated ISO string: "YYYY" / "YYYY-MM" / "YYYY-MM-DD". This is an
    # ADDITIONAL, optional valid-time REFINEMENT alongside the chapter-ordinal
    # axis (valid_from_ordinal) — NOT a replacement. The chapter ordinal stays the
    # PRIMARY / spoiler-safe story-time axis (it is always present for a positioned
    # fact and drives the interval chain); event_date_iso is a SECONDARY,
    # descriptive sort/filter key that the extractor supplies only when the prose
    # carries an explicit in-story date. NULL is the dominant case (most facts have
    # no calendar date) and NEVER breaks the ordinal axis. Mirrors :Event's
    # event_date_iso (C18): same truncated-ISO shape, sort-stable lexicographically,
    # precision-preferring on re-mention. String (not date) so partial-precision
    # ("summer 1880" → "1880-06") keeps the "day unknown" signal.
    event_date_iso: str | None = None
    evidence_count: int = 0
    archived_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


def _node_to_fact(node: Any) -> Fact:
    if hasattr(node, "items"):
        data = dict(node.items())
    else:
        data = dict(node)
    for key, val in list(data.items()):
        if val is not None and hasattr(val, "to_native"):
            data[key] = val.to_native()
    return Fact.model_validate(data)


# ── merge_fact ────────────────────────────────────────────────────────


_MERGE_FACT_CYPHER = """
MERGE (f:Fact {id: $id})
ON CREATE SET
  f.user_id = $user_id,
  f.project_id = $project_id,
  f.type = $type,
  f.content = $content,
  f.canonical_content = $canonical_content,
  f.confidence = $confidence,
  f.pending_validation = $pending_validation,
  f.valid_from = coalesce($valid_from, datetime()),
  f.valid_until = NULL,
  f.source_types = [$source_type],
  f.provenances = [$provenance],
  f.source_chapter = $source_chapter,
  f.from_order = $from_order,
  // F3 — story valid-time axis. valid_from_ordinal is the ordinal the fact was
  // established at (unified with from_order); a fresh fact opens its interval
  // (valid_to_ordinal NULL → eff = +∞ null-sink). The interval CLOSE is done
  // by temporal.maintain_chain after the merge, never here.
  f.valid_from_ordinal = $valid_from_ordinal,
  f.valid_to_ordinal = NULL,
  f.valid_to_ordinal_eff = $open_ceiling,
  // dec-3 — detected in-story date (optional valid-time refinement). NULL when the
  // prose carried no explicit calendar date (the dominant case). Additive: it
  // never participates in the ordinal chain, only annotates/sorts.
  f.event_date_iso = $event_date_iso,
  f.evidence_count = 0,
  f.archived_at = NULL,
  f.created_at = datetime(),
  f.updated_at = datetime()
ON MATCH SET
  // Backfill from_order on a later re-extraction that DOES carry one (a fact first
  // seen via a positionless source keeps NULL until a positioned source re-mentions
  // it); never overwrite an existing order.
  f.from_order = coalesce(f.from_order, $from_order),
  // F3 — backfill the story-time lower bound on a later positioned re-extraction
  // (a fact first seen positionless keeps NULL until a positioned source
  // re-mentions it); never overwrite an existing one. valid_to_ordinal is owned
  // by maintain_chain, so it is NOT touched on MATCH here.
  f.valid_from_ordinal = coalesce(f.valid_from_ordinal, $valid_from_ordinal),
  f.valid_to_ordinal_eff = coalesce(
    f.valid_to_ordinal_eff,
    CASE WHEN f.valid_to_ordinal IS NULL THEN $open_ceiling ELSE f.valid_to_ordinal END
  ),
  // dec-3 — prefer the MORE precise (longer truncated-ISO) in-story date when both
  // non-null, mirroring :Event's C18 HIGH-1 semantic: a fact re-mentioned with a
  // less-precise date ("1880" vs an earlier "1880-06-15") must not downgrade the
  // stored precision. NULL new value leaves the stored one; NULL stored adopts the
  // new. Backfill-friendly: a fact first seen dateless gains a date on a later
  // re-extraction that carries one.
  f.event_date_iso = CASE
    WHEN $event_date_iso IS NULL THEN f.event_date_iso
    WHEN f.event_date_iso IS NULL THEN $event_date_iso
    WHEN size($event_date_iso) > size(f.event_date_iso) THEN $event_date_iso
    ELSE f.event_date_iso
  END,
  f.source_types = CASE
    WHEN $source_type IN f.source_types THEN f.source_types
    ELSE f.source_types + $source_type
  END,
  // CM5 provenance — accumulate deduped origins (mirrors source_types).
  f.provenances = CASE
    WHEN $provenance IN coalesce(f.provenances, []) THEN f.provenances
    ELSE coalesce(f.provenances, []) + $provenance
  END,
  f.confidence = CASE
    WHEN $confidence > f.confidence THEN $confidence
    ELSE f.confidence
  END,
  f.pending_validation = CASE
    WHEN $confidence > f.confidence THEN $pending_validation
    ELSE f.pending_validation
  END,
  f.updated_at = datetime()
WITH f
WHERE f.user_id = $user_id
RETURN f
"""


async def merge_fact(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None,
    type: str,
    content: str,
    confidence: float = 0.0,
    pending_validation: bool = False,
    valid_from: datetime | None = None,
    source_type: str = "book_content",
    source_chapter: str | None = None,
    provenance: str = "human_authored",
    subject_id: str | None = None,
    from_order: int | None = None,
    valid_from_ordinal: int | None = None,
    event_date_iso: str | None = None,
    maintain_chain: bool = False,
) -> Fact:
    """Idempotent upsert. Same (user, project, type, normalized
    content) returns the same node. K17 Pass 2 promotion
    semantics same as relations: higher confidence wins AND
    flips `pending_validation` to the new value.

    T2.1 — `subject_id` (when given + the entity exists for this user) MERGEs a
    `(:Fact)-[:ABOUT]->(:Entity)` edge so the codex can list a character's facts;
    the fact `id` stays content-keyed (idempotency unchanged), so two same-wording
    facts about different subjects share ONE node with multiple ABOUT edges.
    `from_order` is the reading-axis order (for spoiler-windowing).

    F3 — `valid_from_ordinal` is the STORY-time lower bound (chapter ordinal) the
    fact was established at, unified with `from_order`: when not given it defaults
    to `from_order`, so a positioned fact opens a story interval automatically.
    `maintain_chain=True` (the extraction path) re-derives the `valid_to_ordinal`
    chain for this fact's `(subject, type)` AFTER the merge via the ordinal-aware
    `temporal.maintain_chain` — the prior containing fact closes at this ordinal,
    this fact closes at the next strictly-greater one (open only if none later),
    correct under out-of-order/backfill arrival. Default `False` preserves the
    legacy byte-identical single-MERGE behaviour for callers (chat tools, L2)
    that don't drive the story-time chain.

    dec-3 (D-KG-INSTORY-EVENTDATE) — `event_date_iso` is the OPTIONAL detected
    in-story (narrative) date, a truncated ISO string ("YYYY" / "YYYY-MM" /
    "YYYY-MM-DD"). It is an ADDITIVE valid-time refinement ALONGSIDE
    `valid_from_ordinal` (the primary chapter-ordinal axis), never a replacement:
    chapter-ordinal stays the spoiler-safe primary, the in-story date is a
    secondary descriptive sort/filter key. `None` (the dominant case — most facts
    carry no calendar date) is fully null-safe and never affects the ordinal
    chain. Empty string normalizes to `None`. On re-mention the MORE precise date
    wins (mirrors :Event's C18 precision-preferring merge).
    """
    if type not in FACT_TYPES:
        raise ValueError(f"type must be one of {FACT_TYPES}, got {type!r}")
    if not content:
        raise ValueError("content must be a non-empty string")
    if not source_type:
        raise ValueError("source_type must be a non-empty string")
    fid = fact_id(
        user_id=user_id,
        project_id=project_id,
        type=type,
        content=content,
    )
    canonical_content = canonicalize_text(content)
    # K11.7-R1/R4: empty string → None for optional text fields.
    normalized_source_chapter = source_chapter or None
    # dec-3 — empty string → None so the Cypher's "NULL = no new value" precision
    # merge treats a blank date as absent (never clobbers a stored one on MATCH).
    normalized_event_date_iso = event_date_iso or None
    # F3 — unify the story-time lower bound with the reading axis: an explicit
    # valid_from_ordinal wins, else fall back to from_order (the same ordinal).
    effective_valid_from_ordinal = (
        valid_from_ordinal if valid_from_ordinal is not None else from_order
    )
    result = await run_write(
        session,
        _MERGE_FACT_CYPHER,
        user_id=user_id,
        id=fid,
        project_id=project_id,
        type=type,
        content=content,
        canonical_content=canonical_content,
        confidence=confidence,
        pending_validation=pending_validation,
        valid_from=valid_from,
        source_type=source_type,
        source_chapter=normalized_source_chapter,
        from_order=from_order,
        valid_from_ordinal=effective_valid_from_ordinal,
        open_ceiling=ORDINAL_OPEN_CEILING,
        event_date_iso=normalized_event_date_iso,
        provenance=provenance,
    )
    record = await result.single()
    if record is None:
        raise RuntimeError(f"merge_fact returned no row for id={fid!r}")
    # T2.1 — link the fact to its subject entity (idempotent). MATCH (not MERGE) the
    # Entity so an unresolved/cross-user subject silently no-ops instead of creating a
    # phantom node; the caller (pass2_writer) already validates subject ∈ merged ids.
    if subject_id:
        await run_write(
            session,
            _LINK_FACT_SUBJECT_CYPHER,
            user_id=user_id, fact_id=fid, subject_id=subject_id,
        )
        # F3 — drive the ordinal-aware interval-split close ONLY when the
        # extraction path asks for it AND we have both a subject to scope the
        # chain and a story-time position. maintain_chain re-derives valid_to
        # over the (subject, type) chain from valid_from_ordinal order, so a
        # back-filled out-of-order fact never inverts a later interval (A2).
        if maintain_chain and effective_valid_from_ordinal is not None:
            await run_write(
                session,
                MAINTAIN_FACT_CHAIN_CYPHER,
                user_id=user_id,
                entity_id=subject_id,
                attr=type,
                open_ceiling=ORDINAL_OPEN_CEILING,
            )
    return _node_to_fact(record["f"])


_LINK_FACT_SUBJECT_CYPHER = """
MATCH (f:Fact {id: $fact_id}), (e:Entity {id: $subject_id})
WHERE f.user_id = $user_id AND e.user_id = $user_id
MERGE (f)-[:ABOUT]->(e)
"""


# ── get_fact ──────────────────────────────────────────────────────────


_GET_FACT_CYPHER = """
MATCH (f:Fact {id: $id})
WHERE f.user_id = $user_id
RETURN f
"""


async def get_fact(
    session: CypherSession,
    *,
    user_id: str,
    fact_id: str,
) -> Fact | None:
    if not fact_id:
        raise ValueError("fact_id must be a non-empty string")
    result = await run_read(
        session,
        _GET_FACT_CYPHER,
        user_id=user_id,
        id=fact_id,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_fact(record["f"])


# ── list_facts_by_type ────────────────────────────────────────────────


# K11.7 acceptance: "Fact type filter efficient". The K11.3
# schema doesn't ship a per-type index because the type cardinality
# is tiny (4 values) — a full label scan with WHERE is fast
# enough for any realistic per-user fact volume. If profiling
# shows a hot path here, K11.3-R2 can add `(user_id, type)`.
_LIST_FACTS_BY_TYPE_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND ($project_id IS NULL OR f.project_id = $project_id)
  AND ($type IS NULL OR f.type = $type)
  AND ($source_type IS NULL OR $source_type IN f.source_types)
  AND ($exclude_pending = false OR coalesce(f.pending_validation, false) = false)
  AND f.confidence >= $min_confidence
  AND f.valid_until IS NULL
  AND ($include_archived OR f.archived_at IS NULL)
RETURN f
ORDER BY f.confidence DESC, f.created_at DESC
LIMIT $limit
"""


async def list_facts_by_type(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
    type: str | None = None,
    source_type: str | None = None,
    min_confidence: float = 0.8,
    exclude_pending: bool = True,
    include_archived: bool = False,
    limit: int = 100,
) -> list[Fact]:
    """List active facts, optionally filtered by `type`.

    Default filters match the L2 loader: confidence >= 0.8,
    valid_until IS NULL, pending_validation = false. The memory
    UI's "Quarantine" tab can pass `exclude_pending=False` and
    `min_confidence=0.0` to see Pass 1 candidates.

    `type=None` returns facts of all types; otherwise pass one
    of `FACT_TYPES`. `source_type` (WS-4C) filters to facts whose
    accumulated `source_types` list contains it (e.g. "llm_tool_call"
    for memory_remember facts) — None means any source.
    """
    if type is not None and type not in FACT_TYPES:
        raise ValueError(f"type must be one of {FACT_TYPES} or None, got {type!r}")
    if min_confidence < 0.0 or min_confidence > 1.0:
        raise ValueError(f"min_confidence must be in [0,1], got {min_confidence}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")

    result = await run_read(
        session,
        _LIST_FACTS_BY_TYPE_CYPHER,
        user_id=user_id,
        project_id=project_id,
        type=type,
        source_type=source_type,
        min_confidence=min_confidence,
        exclude_pending=exclude_pending,
        include_archived=include_archived,
        limit=limit,
    )
    return [_node_to_fact(record["f"]) async for record in result]


# ── WS-2.4 (spec 07 §Q2) — diary recall: days-since-epoch ordinal + a date-filtered read ───────────
#
# The headline promise "what did <person> say about <topic> last month" had NO query that could answer
# it: every diary fact was invisible because valid_from_ordinal was NULL (dropped by the position
# window) and the only date FILTER in the codebase was on :Event, never :Fact. This restores it:
#   1. days_since_epoch(entry_date) — a diary is perfectly ordinal (one primary entry per day, strictly
#      ordered), so this is a NOT-NULL valid_from_ordinal that re-arms every position-aware path.
#   2. recall_facts — a date-filtered :Fact read mirroring the :Event event_date_iso range predicate,
#      optionally narrowed to a subject via the :ABOUT edge (the "what did X say" half).

_EPOCH_DAY = datetime(1970, 1, 1)


def days_since_epoch(d: date_cls) -> int:
    """The diary's story-time ordinal: whole days from the Unix epoch. Strictly increasing per calendar
    day, so it orders diary entries exactly and gives merge_fact a NOT-NULL valid_from_ordinal."""
    return (datetime(d.year, d.month, d.day) - _EPOCH_DAY).days


# A date-filtered recall read. Unlike list_facts_by_type (project-wide, top-N-by-confidence, date-blind)
# this is the net-new read spec 07 §Q2 demanded: filter by event_date_iso range (the :Event idiom) and,
# when a subject is given, require an (:Fact)-[:ABOUT]->(:Entity{canonical_name}) edge. project_id is
# REQUIRED (never the all-projects fallback) so a non-assistant caller can't pull diary facts (D16).
_RECALL_FACTS_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND f.project_id = $project_id
  AND coalesce(f.pending_validation, false) = false
  AND f.valid_until IS NULL
  AND f.archived_at IS NULL
  AND f.confidence >= $min_confidence
  AND ($event_date_from IS NULL OR f.event_date_iso >= $event_date_from)
  AND ($event_date_to   IS NULL OR f.event_date_iso <= $event_date_to)
  AND (
    $subject_canonical IS NULL OR EXISTS {
      MATCH (f)-[:ABOUT]->(e:Entity)
      WHERE e.user_id = $user_id AND e.canonical_name = $subject_canonical
    }
  )
RETURN f
ORDER BY coalesce(f.event_date_iso, '') DESC, coalesce(f.valid_from_ordinal, 0) DESC, f.created_at DESC
LIMIT $limit
"""


async def recall_facts(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    event_date_from: str | None = None,
    event_date_to: str | None = None,
    subject_name: str | None = None,
    min_confidence: float = 0.0,
    limit: int = 50,
) -> list[Fact]:
    """WS-2.4 — the diary's date-filtered recall read. Returns active facts in [event_date_from,
    event_date_to] (truncated-ISO string compare, the :Event idiom), newest-first, optionally narrowed
    to those ABOUT `subject_name`. project_id is required — recall never spans all of a user's projects
    (D16: a novel-writing session must not surface work facts).

    The subject is matched by CANONICAL name: `subject_name` is run through the SAME
    `canonicalize_entity_name` that stored `e.canonical_name` at promote time (strips honorifics +
    punctuation, NFKC-casefolds, CJK-folds), so "Dr. Smith" / "田中様" / "Q3-Budget" recall the entity
    they were stored under. A raw toLower compare (the pre-fix behavior) silently missed every titled,
    punctuated, or non-Latin name (audit MED)."""
    if not project_id:
        raise ValueError("recall_facts requires an explicit project_id (D16 — no all-projects recall)")
    subject_canonical = canonicalize_entity_name(subject_name) if subject_name else None
    result = await run_read(
        session,
        _RECALL_FACTS_CYPHER,
        user_id=user_id,
        project_id=project_id,
        event_date_from=event_date_from,
        event_date_to=event_date_to,
        subject_canonical=(subject_canonical or None),
        min_confidence=min_confidence,
        limit=limit,
    )
    return [_node_to_fact(record["f"]) async for record in result]


# ── list_facts_for_entity (T2.1) ──────────────────────────────────────


# Facts ABOUT one entity, spoiler-windowed by `from_order`. Same L2-loader
# defaults as list_facts_by_type (confidence/pending/valid/archived). The
# window is INCLUSIVE: `f.from_order <= before_order`; a NULL from_order (legacy
# / chat-tool facts) never passes a finite window — they stay hidden until a
# positioned re-extraction stamps an order.
# dec-3 — the in-story-date variant ORDER BY. The chapter-ordinal `from_order`
# stays the PRIMARY (spoiler-safe) key; `event_date_iso` is the SECONDARY tiebreak,
# so facts established in the same chapter window are presented in in-story
# chronological order when they carry a date. Undated facts (NULL event_date_iso)
# sort BEFORE dated ones within a from_order group via the `coalesce(…, '')`
# null-sink (empty string < any "YYYY…"), keeping the order deterministic. The
# coalesce is required because Neo4j sorts NULLs last under ASC, which would
# scatter undated facts to the end of each group; the sentinel groups them first
# instead. Keyed by a closed boolean → the fragment is never user text.
_LIST_FACTS_FOR_ENTITY_ORDER_ORDINAL = (
    "f.from_order ASC, f.confidence DESC, f.created_at DESC"
)
_LIST_FACTS_FOR_ENTITY_ORDER_EVENT_DATE = (
    "f.from_order ASC, coalesce(f.event_date_iso, '') ASC, "
    "f.confidence DESC, f.created_at DESC"
)

# WHERE/RETURN body shared by both order variants. The ORDER BY fragment is
# appended from the CLOSED pair above (never user text) — concatenated, NOT
# str.format()'d, because the Cypher contains literal `{id: $entity_id}` braces
# that format() would misparse (KeyError: 'id'). Mirrors events.py `_page_cypher`.
_LIST_FACTS_FOR_ENTITY_BODY = """
MATCH (f:Fact)-[:ABOUT]->(e:Entity {id: $entity_id})
WHERE f.user_id = $user_id
  AND e.user_id = $user_id
  AND ($project_id IS NULL OR f.project_id = $project_id)
  AND ($exclude_pending = false OR coalesce(f.pending_validation, false) = false)
  AND f.confidence >= $min_confidence
  AND f.valid_until IS NULL
  AND ($include_archived OR f.archived_at IS NULL)
  AND ($before_order IS NULL OR f.from_order <= $before_order)
RETURN DISTINCT f
ORDER BY """


def _list_facts_for_entity_cypher(order_by_event_date: bool) -> str:
    """Assemble the list query with the chosen ORDER BY fragment (from the closed
    pair). Concatenation, not format() — the body has literal `{...}` braces."""
    order_by = (
        _LIST_FACTS_FOR_ENTITY_ORDER_EVENT_DATE
        if order_by_event_date
        else _LIST_FACTS_FOR_ENTITY_ORDER_ORDINAL
    )
    return _LIST_FACTS_FOR_ENTITY_BODY + order_by + "\nLIMIT $limit\n"


async def list_facts_for_entity(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    before_order: int | None = None,
    project_id: str | None = None,
    min_confidence: float = 0.8,
    exclude_pending: bool = True,
    include_archived: bool = False,
    order_by_event_date: bool = False,
    limit: int = 100,
) -> list[Fact]:
    """T2.1 — the known-facts list for one entity (`(:Fact)-[:ABOUT]->(:Entity)`),
    spoiler-windowed by `from_order <= before_order`. `before_order=None` = no
    window (all linked facts). Filters default to the L2 loader so quarantine /
    low-confidence candidates don't surface as established "known facts".

    dec-3 (D-KG-INSTORY-EVENTDATE) — `order_by_event_date=True` adds the optional
    in-story `event_date_iso` as a SECONDARY sort key (chapter-ordinal `from_order`
    stays the spoiler-safe PRIMARY), so facts established in the same chapter window
    are ordered by in-story chronology when they carry a date. Default `False`
    preserves the legacy `(from_order, confidence, created_at)` ordering exactly.
    Undated facts sort first within their from_order group (deterministic), so the
    refinement is purely additive and null-safe."""
    if not entity_id:
        raise ValueError("entity_id must be a non-empty string")
    if min_confidence < 0.0 or min_confidence > 1.0:
        raise ValueError(f"min_confidence must be in [0,1], got {min_confidence}")
    if limit <= 0:
        raise ValueError(f"limit must be positive, got {limit}")
    result = await run_read(
        session,
        _list_facts_for_entity_cypher(order_by_event_date),
        user_id=user_id,
        entity_id=entity_id,
        before_order=before_order,
        project_id=project_id,
        min_confidence=min_confidence,
        exclude_pending=exclude_pending,
        include_archived=include_archived,
        limit=limit,
    )
    return [_node_to_fact(record["f"]) async for record in result]


# ── invalidate_fact ───────────────────────────────────────────────────


_INVALIDATE_FACT_CYPHER = """
MATCH (f:Fact {id: $id})
WHERE f.user_id = $user_id
SET f.valid_until = coalesce($valid_until, datetime()),
    f.updated_at = datetime()
RETURN f
"""


async def invalidate_fact(
    session: CypherSession,
    *,
    user_id: str,
    fact_id: str,
    valid_until: datetime | None = None,
) -> Fact | None:
    """Soft-invalidate a fact by setting `valid_until`.

    Same idempotency semantics as `invalidate_relation`. Default
    queries exclude `valid_until IS NOT NULL` so invalidated
    facts vanish from the L2 loader without losing audit history.
    """
    if not fact_id:
        raise ValueError("fact_id must be a non-empty string")
    result = await run_write(
        session,
        _INVALIDATE_FACT_CYPHER,
        user_id=user_id,
        id=fact_id,
        valid_until=valid_until,
    )
    record = await result.single()
    if record is None:
        return None
    return _node_to_fact(record["f"])


# ── invalidate_facts_for_day (WS-2.6a leg 3 — D17 amendment reconcile) ─


_INVALIDATE_FACTS_FOR_DAY_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND f.project_id = $project_id
  AND f.event_date_iso = $event_date
  AND f.valid_until IS NULL
  AND coalesce(f.pending_validation, false) = false
SET f.valid_until = coalesce($valid_until, datetime()),
    f.updated_at = datetime()
RETURN count(f) AS invalidated
"""


async def invalidate_facts_for_day(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str,
    event_date: str,
    valid_until: datetime | None = None,
) -> int:
    """WS-2.6a leg 3 (D17) — soft-invalidate ALL of one diary day's CONFIRMED facts by setting
    `valid_until`, scoped to (user, assistant project, event_date). This is the reconcile leg of a
    memory correction: after the user amends a day's diary entry (leg 1) and the worker re-extracts the
    corrected facts into the inbox (leg 2), the day's OLD confirmed facts are superseded and must vanish
    from recall — otherwise the wrong fact ("Minh froze the budget") survives alongside the corrected
    one, and a KG rebuild resurrects it (the exact `memory_forget`-stops-at-leg-3 lie D17 names).

    Bi-temporal soft-invalidation (never a hard delete): `valid_until` is set so recall (which filters
    `valid_until IS NULL`) skips these, while the audit history + the :ABOUT edges survive. Only ACTIVE
    (`valid_until IS NULL`) confirmed (`pending_validation=false`) facts are touched, so it is idempotent
    — a re-run invalidates nothing more. `project_id` is REQUIRED (never all-projects) so a correction in
    the diary can never reach another project's facts (D16). Returns the number invalidated.

    NOTE this is deliberately DAY-scoped, not fact-scoped: the re-distill model (D-R30) treats the
    corrected ENTRY as the new source of truth for the whole day, so the whole day's derived facts are
    re-proposed from it. Unchanged facts re-appear in the inbox (same corrected entry ⇒ same facts) and
    the user re-confirms; the changed/removed ones simply don't come back — no resurrection.
    """
    if not user_id or not project_id or not event_date:
        raise ValueError("invalidate_facts_for_day requires user_id, project_id and event_date")
    result = await run_write(
        session,
        _INVALIDATE_FACTS_FOR_DAY_CYPHER,
        user_id=user_id,
        project_id=project_id,
        event_date=event_date,
        valid_until=valid_until,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["invalidated"])


# ── delete_facts_with_zero_evidence ───────────────────────────────────


_DELETE_FACTS_ZERO_EVIDENCE_CYPHER = """
MATCH (f:Fact)
WHERE f.user_id = $user_id
  AND ($project_id IS NULL OR f.project_id = $project_id)
  AND f.evidence_count = 0
DETACH DELETE f
RETURN count(*) AS deleted
"""


async def delete_facts_with_zero_evidence(
    session: CypherSession,
    *,
    user_id: str,
    project_id: str | None = None,
) -> int:
    """Cascade cleanup. Same race-window warning as
    `delete_entities_with_zero_evidence` and
    `delete_events_with_zero_evidence` — K11.8 must orchestrate
    so this never runs concurrently with extraction.
    """
    result = await run_write(
        session,
        _DELETE_FACTS_ZERO_EVIDENCE_CYPHER,
        user_id=user_id,
        project_id=project_id,
    )
    record = await result.single()
    if record is None:
        return 0
    return int(record["deleted"])


# ── fact_coverage_for_entity (F3 — canonical-snapshot staleness key) ───


# The max `updated_at` over the entity's STORY-time facts valid at/under an
# ordinal — the §12.1 staleness key for the per-entity canonical snapshot cache.
# A late / back-filled fact under `as_of_ordinal` bumps this max, so a snapshot
# whose stored `fact_coverage_at` is older is stale -> rebuild-on-read (B3 self-
# heal). Scopes to the same (subject, type) chains the canonical folds: facts
# ABOUT the entity, valid (TRANSACTION-time open) and positioned at/under the
# ordinal. NULL when the entity has no such facts (nothing to fold yet).
_FACT_COVERAGE_FOR_ENTITY_CYPHER = """
MATCH (f:Fact)-[:ABOUT]->(e:Entity {id: $entity_id})
WHERE f.user_id = $user_id
  AND e.user_id = $user_id
  AND f.valid_until IS NULL
  AND f.valid_from_ordinal IS NOT NULL
  AND f.valid_from_ordinal <= $as_of_ordinal
RETURN max(f.updated_at) AS coverage
"""


async def fact_coverage_for_entity(
    session: CypherSession,
    *,
    user_id: str,
    entity_id: str,
    as_of_ordinal: int,
) -> datetime | None:
    """F3 — the canonical-snapshot staleness key for one entity at an ordinal.

    Returns ``max(updated_at)`` over the entity's story-time facts valid at/under
    ``as_of_ordinal``. The snapshot cache compares its stored ``fact_coverage_at``
    against this: a newer value means a late/back-filled fact arrived after the
    snapshot was built -> the snapshot is stale -> rebuild-on-read (§12.1, B3).
    ``None`` when the entity has no positioned facts under the ordinal.
    """
    if not entity_id:
        raise ValueError("entity_id must be a non-empty string")
    result = await run_read(
        session,
        _FACT_COVERAGE_FOR_ENTITY_CYPHER,
        user_id=user_id,
        entity_id=entity_id,
        as_of_ordinal=as_of_ordinal,
    )
    record = await result.single()
    if record is None or record["coverage"] is None:
        return None
    coverage = record["coverage"]
    # neo4j temporal -> native datetime (mirrors _node_to_fact's to_native).
    if hasattr(coverage, "to_native"):
        return coverage.to_native()
    return coverage
