"""KG-TL — Event-timeline Layer-2 localization (M2 participants + M3 free text).

Extends C7's read-time localization (graph-view / edge-timeline) to the Event
timeline surface. Layer-1 :Event fields stay source-language (AC-T6); everything
here is DERIVED onto the response-only ``*_localized`` / ``*_translated`` Event
fields and a Postgres cache, never written back to the node.

Two passes, both gated on a resolved ``reader_lang`` (when none resolves the
router skips this module entirely → byte-compatible canonical response, AC-T5):

  - **M2 participants** (:func:`localize_participants`): events store participants
    as bare NAME strings (no glossary anchor — RC5). Resolve each DISTINCT name to
    a glossary entity id at read time via ``find_entities_by_name`` (inverting the
    same canonicalization the timeline's entity_id filter uses), then reuse C7's
    ``glossary.fetch_entity_display_names`` to get the reader-language name. A name
    that doesn't resolve, or whose entity has no translation, keeps its SOURCE form
    and is marked ``translated=False`` (AC-T3 — never a silent mix).

  - **M3 summary/time_cue/title** (:func:`localize_event_text`): coalesce-read the
    ``event_text_translations`` cache for the page; a hit fills ``*_localized`` +
    ``translated=True``, a miss falls back to source + ``translated=False`` AND
    enqueues a fire-and-forget lazy fill (translate-text → upsert cache). The GET
    is never blocked by the LLM (AC-T4); the first reader sees source-with-marker,
    later readers see the cached translation.
"""

from __future__ import annotations

import asyncio
import logging
from uuid import UUID

from app.clients.glossary_client import GlossaryClient
from app.clients.translation_client import TranslationClient
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import resolve_participant_anchors
from app.db.neo4j_repos.events import Event
from app.db.repositories.event_text_translations import (
    EVENT_TEXT_FIELDS,
    EventTextTranslationsRepo,
    source_hash,
)

logger = logging.getLogger(__name__)

__all__ = [
    "localize_participants",
    "localize_event_text",
]

# Strong refs to in-flight lazy-fill tasks so the event loop's weak task set
# can't GC them mid-flight before the response returns (the documented
# create_task idiom — mirrors cache_invalidation.py). Discarded on completion.
_pending_fills: set[asyncio.Task] = set()


async def _resolve_names_to_entity_ids(
    *,
    user_id: str,
    project_id: str | None,
    names: list[str],
) -> dict[str, str]:
    """Invert NAME → glossary_entity_id for a page's participant names (Option B,
    read-time fallback for events whose stored anchors are absent/misaligned).

    Delegates to the shared :func:`resolve_participant_anchors` — the SAME
    resolution the write path stores at extraction time — so read-time fallback
    and write-time anchoring can never drift. Opens one Neo4j session for the
    whole batch. A name with no anchored match is omitted (it stays source +
    marked, AC-T3).
    """
    if not names:
        return {}
    async with neo4j_session() as session:
        return await resolve_participant_anchors(
            session, user_id=user_id, project_id=project_id, names=names,
        )


async def localize_participants(
    events: list[Event],
    *,
    user_id: str,
    project_id: str | None,
    book_id: UUID | None,
    language: str,
    glossary: GlossaryClient,
) -> None:
    """M2 — fill ``participants_localized`` / ``participants_translated`` in place.

    No-op (leaves the fields None) when there is no book to anchor the glossary
    join on — without a book_id the entity-name translation table can't be keyed,
    so honest behavior is to skip rather than mark everything as a false miss.
    """
    if not events or book_id is None:
        return
    # KG-TL Option A (D-KG-TL-PARTICIPANT-ANCHOR) — prefer the anchor STORED on
    # the event at extraction time over re-resolving names at read time.
    #   - An event whose ``participant_entity_ids`` is aligned (same length as
    #     ``participants``) is trusted wholesale: a non-empty slot is the glossary
    #     id; a ``""`` slot is a KNOWN-unanchored participant (source fallback) —
    #     not re-resolved.
    #   - An event with absent / length-mismatched anchors (legacy, un-backfilled,
    #     or a re-mention that grew a short array) falls back to read-time name
    #     resolution for its names only (Option B). A fully-backfilled page does
    #     ZERO read-time resolution — the durable win.
    name_to_eid: dict[str, str] = {}
    anchored_names: set[str] = set()  # names settled by a stored array (id or "")
    for e in events:
        ids = e.participant_entity_ids
        if not ids or len(ids) != len(e.participants):
            continue
        for p, eid in zip(e.participants, ids):
            if not (p and p.strip()):
                continue
            anchored_names.add(p)
            if eid and p not in name_to_eid:
                name_to_eid[p] = eid
    # Residual = names from events WITHOUT an aligned stored array, and not
    # already settled by some other event's array.
    residual: list[str] = list(
        {
            p
            for e in events
            if not e.participant_entity_ids
            or len(e.participant_entity_ids) != len(e.participants)
            for p in e.participants
            if p and p.strip() and p not in anchored_names and p not in name_to_eid
        }
    )
    if residual:
        resolved = await _resolve_names_to_entity_ids(
            user_id=user_id, project_id=project_id, names=residual
        )
        for n, eid in resolved.items():
            name_to_eid.setdefault(n, eid)
    translated_names: dict[str, str] = {}
    if name_to_eid:
        eid_to_name = await glossary.fetch_entity_display_names(
            book_id=book_id,
            entity_ids=list({eid for eid in name_to_eid.values()}),
            language=language,
        )
        # Re-key glossary's {entity_id: translated_name} back to {source_name: …}.
        for src_name, eid in name_to_eid.items():
            if eid in eid_to_name:
                translated_names[src_name] = eid_to_name[eid]
    # Decorate each event: same length+order as participants; per-slot flag.
    for e in events:
        loc: list[str] = []
        flags: list[bool] = []
        for p in e.participants:
            t = translated_names.get(p)
            if t:
                loc.append(t)
                flags.append(True)
            else:
                loc.append(p)  # source fallback (AC-T3) — FE marks via the flag
                flags.append(False)
        e.participants_localized = loc
        e.participants_translated = flags


async def localize_event_text(
    events: list[Event],
    *,
    user_id: UUID,
    language: str,
    repo: EventTextTranslationsRepo,
    translation: TranslationClient,
) -> None:
    """M3 — coalesce-read the cache into ``*_localized`` / ``*_translated`` and
    fire a lazy fill for the page's misses.

    Read is synchronous + cheap (one batched SELECT). The lazy fill is
    fire-and-forget (``asyncio.create_task``) so the timeline GET never blocks on
    the LLM (AC-T4). The first reader of a language sees source + marker; once the
    background fill lands, a later read is a cache hit.
    """
    if not events:
        return

    def _field_value(e: Event, field: str) -> str | None:
        return getattr(e, field, None)

    # Build the (event_id, field) key set for every non-empty source field.
    keys: list[tuple[str, str]] = []
    for e in events:
        for field in EVENT_TEXT_FIELDS:
            val = _field_value(e, field)
            if isinstance(val, str) and val.strip():
                keys.append((e.id, field))

    cached = await repo.fetch(user_id=user_id, language_code=language, keys=keys)

    # Misses to lazily translate: (event_id, field, source_text, project_id).
    misses: list[tuple[str, str, str, UUID | None]] = []
    for e in events:
        pid = UUID(e.project_id) if e.project_id else None
        for field in EVENT_TEXT_FIELDS:
            val = _field_value(e, field)
            if not (isinstance(val, str) and val.strip()):
                continue
            hit = cached.get((e.id, field))
            translated = False
            localized = val
            # A cache hit counts ONLY when the source hasn't changed since it was
            # cached (source_hash guard) — else it's a stale row → treat as miss.
            if hit is not None and hit[1] == source_hash(val):
                localized = hit[0]
                translated = True
            else:
                misses.append((e.id, field, val, pid))
            setattr(e, f"{field}_localized", localized)
            setattr(e, f"{field}_translated", translated)

    if misses:
        # Fire-and-forget: do NOT await (the GET must not block on the LLM).
        # Hold a strong ref until done so the loop can't GC the task mid-flight.
        try:
            task = asyncio.create_task(
                _fill_misses(
                    misses,
                    user_id=user_id,
                    language=language,
                    repo=repo,
                    translation=translation,
                )
            )
        except RuntimeError:
            # No running loop (shouldn't happen on the async read path) — skip
            # the lazy fill; the next read retries the miss.
            return
        _pending_fills.add(task)
        task.add_done_callback(_pending_fills.discard)


async def _fill_misses(
    misses: list[tuple[str, str, str, UUID | None]],
    *,
    user_id: UUID,
    language: str,
    repo: EventTextTranslationsRepo,
    translation: TranslationClient,
) -> None:
    """Background lazy-fill: translate each miss via the translate-text primitive
    and upsert into the cache (never clobbering a verified row). Best-effort —
    any failure for one field is logged and skipped; the next read retries it."""
    for event_id, field, src, project_id in misses:
        try:
            out = await translation.translate_text(
                user_id=user_id, text=src, target_language=language
            )
            if not out:
                continue
            await repo.upsert_machine(
                event_id=event_id,
                field=field,
                language_code=language,
                value=out,
                src_hash=source_hash(src),
                user_id=user_id,
                project_id=project_id,
            )
        except Exception as exc:  # never let the background task raise
            logger.warning(
                "event-text lazy fill failed (event=%s field=%s): %s",
                event_id, field, exc,
            )
