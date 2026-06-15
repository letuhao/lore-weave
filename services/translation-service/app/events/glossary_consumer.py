"""M5c/M6b — glossary-staleness consumer (Redis Streams).

Consumes ``loreweave:events:glossary`` and, on a ``glossary.entity_updated``
event, marks affected chapter translations stale (``is_glossary_stale=true``) so
the living book can flag translations that predate a glossary change.

**M6b full-propagate** makes this *targeted*: the worker records a per-chapter
glossary-entity usage index (``chapter_translation_glossary_usage``), so a change
to entity E flags only the chapters that used E — optionally narrowed to the one
``target_language`` the event carries (a translation-specific edit). Chapters
translated before the index existed fall back to the coarse book-level flag (no
false-negatives). The flag is a non-destructive hint — a fresh re-translation
re-records usage and starts un-stale. See ``handle_glossary_event``.

Mirrors the knowledge-service consumer's correctness-critical bits (a blocking
XREADGROUP needs ``socket_timeout=None``; BUSYGROUP-safe group create; process
pending on startup; ack on success; bounded retry then ack). No DLQ table here —
on retry exhaustion we log + ack (a missed coarse stale-flag is tolerable, and
glossary events recur). Best-effort: never crashes the service.
"""
from __future__ import annotations

import asyncio
import json
import logging
from uuid import UUID

from loreweave_jobs import BaseTerminalConsumer

log = logging.getLogger(__name__)

STREAM = "loreweave:events:glossary"
GROUP_NAME = "translation-staleness"
GLOSSARY_CHANGE_EVENT = "glossary.entity_updated"
MAX_RETRIES = 3
BLOCK_MS = 5000

# M6b /review-impl MED-HIGH: the event's language_code (glossary) and the
# chapter_translations.target_language (translation job) are independent strings
# with no shared normalization — D-TRANSL-M6A-NOTES(a) documents the "vi" vs
# "vi-VN" drift. An exact `=` filter would silently drop affected chapters (the
# flywheel's worst failure: a confirmed name never flags its chapter). Match on
# the case-insensitive PRIMARY SUBTAG instead (mirrors M1c's "primary-subtag
# matched" policy). NULL ⇒ all languages (a name/structural change).
_LANG_MATCH = (
    "$2::text IS NULL OR "
    "LOWER(SPLIT_PART(target_language, '-', 1)) = LOWER(SPLIT_PART($2, '-', 1))"
)
_LANG_MATCH_CT = (
    "$3::text IS NULL OR "
    "LOWER(SPLIT_PART(ct.target_language, '-', 1)) = LOWER(SPLIT_PART($3, '-', 1))"
)


def parse_glossary_event(fields: dict) -> tuple[str, dict]:
    """(event_type, payload) from Redis Stream fields. Tolerant — bad JSON → {}."""
    event_type = fields.get("event_type", "")
    raw = fields.get("payload", "{}")
    try:
        payload = json.loads(raw) if raw else {}
    except (json.JSONDecodeError, TypeError):
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    return event_type, payload


async def handle_glossary_event(pool, event_type: str, payload: dict) -> bool:
    """Flag stale the chapter translations affected by a glossary change. Returns
    True if a row update ran; a missing/invalid book_id is a no-op (still acked).
    Idempotent (only flips false→true).

    M6b full-propagate — precision keyed on ``glossary_entity_id`` + the optional
    ``target_language``:

    - **Precise:** a translation whose usage index
      (``chapter_translation_glossary_usage``) records the changed entity is
      flagged.
    - **Legacy fallback (no false-negatives):** a translation with NO usage rows
      (translated before the index existed) is still flagged — today's coarse
      behavior, bounded by the language filter.
    - **Indexed-but-unused** translations stay un-flagged — the precision win.
    - **Language:** ``target_language`` set (a translation-specific change) ⇒ only
      that language; absent (a name/structural change) ⇒ all languages.
    - **No entity anchor** (a legacy event) ⇒ coarse book-level (the old path).
    """
    if event_type != GLOSSARY_CHANGE_EVENT:
        return False
    book_id = payload.get("book_id")
    if not book_id:
        return False
    try:
        book_uuid = UUID(str(book_id))
    except (ValueError, TypeError):
        log.warning("glossary event with invalid book_id=%r — skipping", book_id)
        return False

    # target_language: None ⇒ all languages (name/structural change).
    target_language = payload.get("target_language") or None

    # entity_id is the precision key. A legacy event without it ⇒ coarse fallback.
    raw_entity = payload.get("glossary_entity_id")
    entity_uuid = None
    if raw_entity:
        try:
            entity_uuid = UUID(str(raw_entity))
        except (ValueError, TypeError):
            log.warning("glossary event invalid entity_id=%r — coarse fallback", raw_entity)

    if entity_uuid is None:
        await pool.execute(
            "UPDATE chapter_translations SET is_glossary_stale = true "
            "WHERE book_id = $1 AND COALESCE(is_glossary_stale, false) = false "
            "AND (" + _LANG_MATCH + ")",
            book_uuid, target_language,
        )
        log.info("M6b: coarse stale flag for book=%s lang=%s (no entity anchor)",
                 book_uuid, target_language or "*")
        return True

    await pool.execute(
        """
        UPDATE chapter_translations ct SET is_glossary_stale = true
        WHERE ct.book_id = $1
          AND COALESCE(ct.is_glossary_stale, false) = false
          AND (""" + _LANG_MATCH_CT + """)
          AND (
            EXISTS (SELECT 1 FROM chapter_translation_glossary_usage u
                    WHERE u.chapter_translation_id = ct.id AND u.entity_id = $2)
            OR NOT EXISTS (SELECT 1 FROM chapter_translation_glossary_usage u2
                           WHERE u2.chapter_translation_id = ct.id)
          )
        """,
        book_uuid, entity_uuid, target_language,
    )
    # T2-M3.2: per-SEGMENT precision. Flag the segment translations (in this book,
    # matching language) whose segment's SOURCE references the changed entity
    # (segment_glossary_usage, language-independent). Only the precise entity path
    # propagates to segments — the coarse fallback stays chapter-level. A re-translate
    # clears the segment flag (record resets is_glossary_stale=false).
    await pool.execute(
        """
        UPDATE segment_translations st SET is_glossary_stale = true
        WHERE COALESCE(st.is_glossary_stale, false) = false
          AND ($3::text IS NULL OR
               LOWER(SPLIT_PART(st.target_language, '-', 1)) = LOWER(SPLIT_PART($3, '-', 1)))
          AND EXISTS (SELECT 1 FROM segment_glossary_usage u
                      WHERE u.chapter_id = st.chapter_id
                        AND u.segment_index = st.segment_index
                        AND u.entity_id = $2)
          AND EXISTS (SELECT 1 FROM chapter_translations ct
                      WHERE ct.chapter_id = st.chapter_id AND ct.book_id = $1)
        """,
        book_uuid, entity_uuid, target_language,
    )
    log.info("M6b/M3.2: targeted stale flag (chapter+segment) for book=%s entity=%s lang=%s",
             book_uuid, entity_uuid, target_language or "*")
    return True


class GlossaryStaleConsumer(BaseTerminalConsumer):
    """Glossary-staleness consumer on the shared transport scaffold. Reads the
    ``loreweave:events:glossary`` stream (NOT the terminal stream) at ``id="$"``
    (forward-looking — starting at "0" would replay the ~200k retained glossary
    backlog on deploy, mass-flagging every book). Business fold = ``handle`` →
    ``handle_glossary_event``; no sweeper."""

    stream = STREAM
    group = GROUP_NAME
    max_retries = MAX_RETRIES
    consumer_name_prefix = "transl"
    retry_prefix = "transl:retry"

    def __init__(self, redis_url: str, pool, *, consumer_name: str | None = None) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool

    async def handle(self, fields: dict) -> None:
        event_type, payload = parse_glossary_event(fields)
        await handle_glossary_event(self._pool, event_type, payload)
