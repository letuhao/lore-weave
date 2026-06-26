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
from app.db.neo4j_repos.entities import find_entities_by_name
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
    """Invert NAME → glossary_entity_id for a page's distinct participant names.

    For each name, take the best ``find_entities_by_name`` match that carries a
    glossary anchor (the helper already ranks anchored entities first). Ambiguous
    names (same surface, two entities) tie-break on that ranking — preferring the
    anchored, higher-confidence entity already in this project's graph (Option B
    tie-break in the spec §5c). A name with no anchored match is omitted (it stays
    source + marked). One Neo4j session for the whole page.
    """
    out: dict[str, str] = {}
    if not names:
        return out
    async with neo4j_session() as session:
        for name in names:
            try:
                matches = await find_entities_by_name(
                    session,
                    user_id=user_id,
                    project_id=project_id,
                    name=name,
                )
            except Exception as exc:  # best-effort — a resolution miss never 500s
                logger.warning("participant name resolution failed for %r: %s", name, exc)
                continue
            for ent in matches:
                if ent.glossary_entity_id:
                    out[name] = ent.glossary_entity_id
                    break
    return out


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
    # Distinct participant names across the whole page → ONE resolution + ONE
    # glossary round-trip (not per-event).
    distinct: list[str] = list(
        {p for e in events for p in e.participants if p and p.strip()}
    )
    if not distinct:
        return
    name_to_eid = await _resolve_names_to_entity_ids(
        user_id=user_id, project_id=project_id, names=distinct
    )
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
