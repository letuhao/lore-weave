"""event_text_translations repository — KG-TL M3.

The on-demand + cached Layer-2 translation store for free-text :Event fields
(``summary`` / ``time_cue`` / ``title``) on the Timeline tab. Modeled EXACTLY on
glossary's ``attribute_translations`` cache (see
``docs/specs/2026-06-26-kg-timeline-localization.md`` §4.1):

  - **read = coalesce + signal** — :func:`fetch` batch-loads the cached values for
    a timeline page and returns ``(value, translated)`` per (event_id, field). A
    miss simply isn't in the map, so the router coalesces to the source text and
    marks ``translated=False`` (AC-T4 — never a blocking inline LLM on the GET).
  - **write = upsert machine, never clobber verified** — :func:`upsert_machine`
    mirrors glossary's
    ``ON CONFLICT (...) DO UPDATE ... WHERE confidence <> 'verified'`` so a
    human-verified translation is never overwritten by a machine one. It also
    re-translates when the source text changed (``source_hash`` mismatch).

SECURITY: every method takes ``user_id`` and filters by it — a caller can never
read or write another tenant's cached translations.
"""

from __future__ import annotations

import hashlib
from uuid import UUID

import asyncpg

__all__ = [
    "EventTextTranslationsRepo",
    "source_hash",
    "EVENT_TEXT_FIELDS",
]

# The free-text fields that ride the cache. Mirrors the CHECK constraint in
# migrate.py; the router localizes these three.
EVENT_TEXT_FIELDS: tuple[str, ...] = ("summary", "time_cue", "title")


def source_hash(text: str) -> str:
    """sha256 of the source text a cache row translates. Guards against serving a
    stale translation after the source field is edited: the read compares the
    cached ``source_hash`` to the live source's hash and treats a mismatch as a
    miss (re-translate), so an edited summary never shows its old translation."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class EventTextTranslationsRepo:
    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    async def fetch(
        self,
        *,
        user_id: UUID,
        language_code: str,
        keys: list[tuple[str, str]],
    ) -> dict[tuple[str, str], tuple[str, str]]:
        """Batch-load cached translations for a timeline page.

        ``keys`` is a list of ``(event_id, field)`` the page needs. Returns
        ``{(event_id, field): (value, source_hash)}`` for the rows that exist in
        ``language_code`` for this user. The router compares the returned
        ``source_hash`` to the live source's hash; equal ⇒ cache hit (use
        ``value``, ``translated=True``); missing or mismatched ⇒ miss (source
        fallback + lazy-fill). Empty input short-circuits without a query.
        """
        if not keys:
            return {}
        event_ids = list({eid for eid, _ in keys})
        rows = await self._pool.fetch(
            """
            SELECT event_id, field, value, source_hash
            FROM event_text_translations
            WHERE user_id = $1
              AND language_code = $2
              AND event_id = ANY($3::text[])
            """,
            user_id,
            language_code,
            event_ids,
        )
        wanted = set(keys)
        out: dict[tuple[str, str], tuple[str, str]] = {}
        for r in rows:
            k = (r["event_id"], r["field"])
            if k in wanted:
                out[k] = (r["value"], r["source_hash"])
        return out

    async def upsert_machine(
        self,
        *,
        event_id: str,
        field: str,
        language_code: str,
        value: str,
        src_hash: str,
        user_id: UUID,
        project_id: UUID | None,
    ) -> bool:
        """Lazily cache a MACHINE translation (the on-demand fill).

        Mirrors glossary's upsert: inserts a ``'machine'`` row, and on conflict
        updates ONLY when the existing row is not ``'verified'`` (a human
        translation is never clobbered). The conflict-update also refreshes the
        ``source_hash`` so a re-translation after a source edit lands. Returns
        True when a row was written/updated, False when an existing ``verified``
        row was preserved (skipped).
        """
        result = await self._pool.execute(
            """
            INSERT INTO event_text_translations
                (event_id, field, language_code, value, source_hash,
                 confidence, translator, user_id, project_id)
            VALUES ($1, $2, $3, $4, $5, 'machine', 'knowledge-timeline', $6, $7)
            ON CONFLICT (event_id, field, language_code) DO UPDATE
              SET value = EXCLUDED.value,
                  source_hash = EXCLUDED.source_hash,
                  confidence = 'machine',
                  translator = EXCLUDED.translator,
                  updated_at = now()
              WHERE event_text_translations.confidence <> 'verified'
            """,
            event_id,
            field,
            language_code,
            value,
            src_hash,
            user_id,
            project_id,
        )
        # asyncpg returns e.g. "INSERT 0 1" / "UPDATE 1" / "INSERT 0 0" (the
        # WHERE-guard suppressed the verified-row update). Trailing count > 0 ⇒
        # a row landed.
        try:
            return int(result.rsplit(" ", 1)[1]) > 0
        except (ValueError, IndexError):
            return False

    async def delete_for_project(self, *, project_id: UUID) -> int:
        """AC-T7 purge cascade — drop every cached translation for a project's
        events. Called from the project/book purge path so the cache leaves no
        orphans when the underlying graph partition is deleted. Returns the row
        count removed."""
        result = await self._pool.execute(
            "DELETE FROM event_text_translations WHERE project_id = $1",
            project_id,
        )
        try:
            return int(result.rsplit(" ", 1)[1])
        except (ValueError, IndexError):
            return 0
