"""V3 knowledge context brief (M4b, G4).

Turns the glossary's tiered entity selection + the knowledge layer's relation
neighbourhoods into a compact, sanitized **pronoun/honorific brief** injected
into the Translator and the LLM Verifier. This is the "killer feature" for
context-correct names (who outranks/relates to whom → 你/您, anh/em/ngài).

Pipeline (once per chapter):
  select-for-context (entity_id + bio)  →  parallel wiki-neighborhood per entity
  →  trust-laddered, token-bounded, sanitized brief string.

Trust ladder (§11.2): a confirmed/glossary-anchored relation is stated plainly;
a `pending_validation` / low-confidence one is labelled "(unconfirmed)" so the
model treats it cautiously. Every interpolated field is sanitized — this text
crosses a service boundary into an LLM prompt (§11.4 injection-defense).

Fully best-effort: any failure (glossary/knowledge down, feature off) yields an
empty brief — knowledge enrichment must never fail a translation.
"""
from __future__ import annotations

import asyncio
import logging
import re

from ..glossary_client import fetch_context_entities, ContextEntity
from ..knowledge_client import (
    fetch_wiki_neighborhood, WikiNeighborhood, fetch_timeline, TimelineEvent,
)
from ..kal_client import get_canonical_cached, CanonicalSnapshot
from ..chunk_splitter import estimate_tokens

log = logging.getLogger(__name__)

_MAX_ENTITIES = 20
_FETCH_CONCURRENCY = 8
# D-TRANSL-M4B-RESIDUALS: per-entity fetch timeout. A single hung neighbourhood
# fetch must not stall the whole chapter's brief assembly (best-effort enrichment).
_FETCH_TIMEOUT_S = 5.0
_TOKEN_BUDGET = 600
_TRUST_CONFIDENCE = 0.8  # ≥ this and not pending_validation ⇒ stated as fact
_MAX_RELATIONS_PER_ENTITY = 4
_FIELD_MAX = 200
# X5: how much of an entity's as-of-N canonical snapshot to fold into its brief line.
# Bounded — the canonical is already ≤ canonicalMaxRunes from the KAL, but the brief
# is per-entity-line budgeted, so keep the injected slice tight.
_CANONICAL_MAX = 240

_HEADER = (
    "CHARACTER & RELATION CONTEXT — use the EXACT names below and let the "
    "relationships guide pronouns/honorifics; treat \"(unconfirmed)\" items as "
    "weak hints, not facts:"
)

_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_BLOCK_MARKER = re.compile(r"\[\s*block", re.IGNORECASE)


def _sanitize(text: str, max_len: int = _FIELD_MAX) -> str:
    """Make a cross-service string safe to embed in an LLM prompt.

    Collapses whitespace/newlines, strips control chars, neutralizes anything
    resembling a ``[BLOCK n]`` marker (so injected text can't impersonate the
    block protocol), and caps length.
    """
    if not text:
        return ""
    t = _CONTROL.sub(" ", text)
    t = _BLOCK_MARKER.sub("(block", t)
    t = " ".join(t.split())  # collapse all whitespace runs
    if len(t) > max_len:
        t = t[:max_len].rstrip() + "…"
    return t


def _is_trusted(rel) -> bool:
    return (not rel.pending_validation) and rel.confidence >= _TRUST_CONFIDENCE


def _format_entity(
    entity: ContextEntity,
    nb: WikiNeighborhood,
    canonical: CanonicalSnapshot | None = None,
) -> str | None:
    """One brief line per entity: name (kind): bio · as-of-N state · relations. None if empty.

    ``canonical`` (X5) is the entity's as-of-N canonical snapshot from the KAL —
    the story state valid AS OF the chapter being translated (spoiler-free). When
    present + buildable it is folded in as a "state here" clause; absent/unbuildable
    it is simply omitted (degrade-safe — the bio + relations line is unchanged, so
    the default no-KAL path is byte-identical to pre-X5)."""
    name = _sanitize(entity.name)
    if not name:
        return None
    head = name
    if entity.kind:
        head += f" ({_sanitize(entity.kind, 40)})"
    parts = [head]
    bio = _sanitize(entity.short_description)
    if bio:
        parts.append(bio)

    # X5: as-of-N canonical state. Only when buildable + non-empty; sanitized like
    # every other cross-service field that lands in an LLM prompt (§11.4).
    if canonical is not None and canonical.found and canonical.canonical_status != "unbuildable":
        state = _sanitize(canonical.content, _CANONICAL_MAX)
        if state:
            parts.append(f"state here: {state}")

    rel_strs: list[str] = []
    for rel in nb.relations:
        # A 1-hop neighbourhood edge can have THIS entity as subject OR object,
        # so render the full triple — "{predicate} {object}" alone would reverse
        # the meaning of edges where the entity is the object.
        subj = _sanitize(rel.subject_name or "", 80)
        obj = _sanitize(rel.object_name or "", 80)
        pred = _sanitize(rel.predicate or "", 40)
        if not pred or not (subj or obj):
            continue
        triple = " ".join(x for x in (subj, pred, obj) if x)
        label = "" if _is_trusted(rel) else " (unconfirmed)"
        rel_strs.append(f"{triple}{label}")
        if len(rel_strs) >= _MAX_RELATIONS_PER_ENTITY:
            break
    if rel_strs:
        parts.append("relations: " + "; ".join(rel_strs))
    return " — ".join(parts)


async def _fetch_all_neighborhoods(
    user_id: str, entities: list[ContextEntity], concurrency: int,
) -> list[WikiNeighborhood]:
    """Fetch every entity's neighbourhood in parallel (bounded). Once per chapter.

    D-TRANSL-M4B-RESIDUALS: each fetch is timeout-bounded and failure-isolated — a
    single slow/failing entity degrades to an EMPTY neighbourhood (that entity still
    contributes its name/bio line) instead of aborting the whole brief. ``except
    Exception`` deliberately does NOT catch ``asyncio.CancelledError`` (BaseException
    in 3.8+), so a job cancel still propagates and aborts the fan-out — the "abort"
    half of this residual. Result list stays index-aligned with ``entities``.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(e: ContextEntity) -> WikiNeighborhood:
        async with sem:
            try:
                return await asyncio.wait_for(
                    fetch_wiki_neighborhood(user_id, e.entity_id), _FETCH_TIMEOUT_S,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort; cancel still propagates
                log.debug(
                    "knowledge_context: neighborhood fetch failed for %s (%s) — empty",
                    e.entity_id, exc,
                )
                return WikiNeighborhood.empty(e.entity_id)

    return await asyncio.gather(*(_one(e) for e in entities))


async def _fetch_all_canonicals(
    book_id: str,
    user_id: str,
    entities: list[ContextEntity],
    concurrency: int,
    *,
    content_hash: str,
    as_of: int | None,
) -> list[CanonicalSnapshot]:
    """X5 — fetch every entity's as-of-N canonical snapshot via the KAL, in parallel
    (bounded), immutable-once cached. Once per chapter.

    Mirrors ``_fetch_all_neighborhoods``: each fetch is timeout-bounded + failure-
    isolated to an EMPTY snapshot (the entity keeps its bio/relations line), and a
    job cancel still propagates (``except Exception`` doesn't catch CancelledError).
    The KAL client's own Null gate makes this a no-op (all-empty) when the feature is
    off — so the result list is always index-aligned with ``entities``."""
    sem = asyncio.Semaphore(concurrency)

    async def _one(e: ContextEntity) -> CanonicalSnapshot:
        async with sem:
            try:
                return await asyncio.wait_for(
                    get_canonical_cached(
                        book_id, e.entity_id,
                        content_hash=content_hash, as_of=as_of, user_id=user_id,
                    ),
                    _FETCH_TIMEOUT_S,
                )
            except Exception as exc:  # noqa: BLE001 — best-effort; cancel still propagates
                log.debug(
                    "knowledge_context: canonical fetch failed for %s (%s) — empty",
                    e.entity_id, exc,
                )
                return CanonicalSnapshot.empty()

    return await asyncio.gather(*(_one(e) for e in entities))


async def build_context_brief(
    book_id: str,
    user_id: str,
    chapter_text: str,
    *,
    max_entities: int = _MAX_ENTITIES,
    concurrency: int = _FETCH_CONCURRENCY,
    token_budget: int = _TOKEN_BUDGET,
    as_of: int | None = None,
    content_hash: str | None = None,
) -> str:
    """Build the per-chapter pronoun/honorific brief (empty string on no data).

    X5 (temporal-knowledge): when ``as_of`` (the chapter's story-time ordinal) AND
    ``content_hash`` (the chapter's bounded-unit content hash) are supplied, each
    entity's brief line is augmented with its KAL canonical snapshot valid AS OF that
    ordinal — the story state at chapter N, not the latest head (spoiler-free, §6B).
    That as-of knowledge is immutable-once cached on ``content_hash`` + ``as_of`` so a
    re-translation of unchanged content reuses it (§12.1 / D8). Both are additive and
    opt-in: omitted (or the KAL feature off) ⇒ NO canonical fetch and the brief is
    byte-identical to pre-X5."""
    entities = await fetch_context_entities(book_id, user_id, chapter_text, max_entities)
    if not entities:
        return ""

    neighborhoods = await _fetch_all_neighborhoods(user_id, entities, concurrency)

    # X5: as-of-N canonical state, only when the caller opted in (content_hash present).
    # The KAL client's Null gate additionally no-ops this when the feature is off.
    canonicals: list[CanonicalSnapshot | None]
    if content_hash is not None:
        canonicals = await _fetch_all_canonicals(
            book_id, user_id, entities, concurrency,
            content_hash=content_hash, as_of=as_of,
        )
    else:
        canonicals = [None] * len(entities)

    lines: list[str] = []
    used = estimate_tokens(_HEADER)
    for entity, nb, canon in zip(entities, neighborhoods, canonicals):
        line = _format_entity(entity, nb, canon)
        if not line:
            continue
        cost = estimate_tokens(line) + 1
        if used + cost > token_budget and lines:
            break  # budget exhausted — drop the rest
        lines.append(line)
        used += cost

    if not lines:
        return ""
    log.info("knowledge_context: %d entities in brief, ~%d tokens", len(lines), used)
    return _HEADER + "\n" + "\n".join(f"- {ln}" for ln in lines)


# ── M4d-1: timeline → "story so far" memo block ───────────────────────────────

_TIMELINE_HEADER = (
    "RECENT STORY EVENTS (what has happened up to here — keep names, "
    "relationships and plot consistent with these):"
)
_TIMELINE_TOKEN_BUDGET = 350
_TIMELINE_TITLE_MAX = 120
_TIMELINE_SUMMARY_MAX = 200
_TIMELINE_MAX_PARTICIPANTS = 6


def _format_timeline_event(ev: TimelineEvent) -> str | None:
    """One sanitized memo line per event. None when there is no usable title."""
    title = _sanitize(ev.title, _TIMELINE_TITLE_MAX)
    if not title:
        return None
    date = _sanitize(ev.event_date or "", 30)
    head = f"{date}: {title}" if date else title
    parts = [head]
    summary = _sanitize(ev.summary or "", _TIMELINE_SUMMARY_MAX)
    if summary:
        parts.append(summary)
    who = [p for p in (_sanitize(x, 60) for x in ev.participants) if p][:_TIMELINE_MAX_PARTICIPANTS]
    if who:
        parts.append("participants: " + ", ".join(who))
    return " — ".join(parts)


async def build_timeline_block(
    book_id: str,
    chapter_order: int,
    *,
    token_budget: int = _TIMELINE_TOKEN_BUDGET,
) -> str:
    """Build the cross-chapter "story so far" event memo (empty string on no data).

    ``chapter_order`` is the book-service chapter ``sort_order`` (global reading
    position). Best-effort, like ``build_context_brief``: feature-off / cold-start
    / any knowledge failure all yield an empty string. Injected into the
    Translator ``extra_system`` only (continuity context, not a verifier rule)."""
    brief = await fetch_timeline(book_id, chapter_order)
    if not brief.events:
        return ""

    lines: list[str] = []
    used = estimate_tokens(_TIMELINE_HEADER)
    for ev in brief.events:
        line = _format_timeline_event(ev)
        if not line:
            continue
        cost = estimate_tokens(line) + 1
        if used + cost > token_budget and lines:
            break  # budget exhausted — keep the earliest recent events
        lines.append(line)
        used += cost

    if not lines:
        return ""
    log.info("knowledge_context: %d timeline events in memo, ~%d tokens", len(lines), used)
    return _TIMELINE_HEADER + "\n" + "\n".join(f"- {ln}" for ln in lines)
