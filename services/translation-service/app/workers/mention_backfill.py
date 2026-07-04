"""Deterministic per-chapter mention_count backfill (M7 / D-T5.2-WINDOWED-MENTIONS).

A NO-LLM recount job that re-derives `chapter_entity_links.mention_count` for books
extracted BEFORE M7 landed (their links default to 0). It is fully deterministic +
idempotent: re-running it converges on the same counts, so a retry / partial run is safe.

Flow per book (orchestrator `backfill_book_mention_counts`):
  1. list the book's chapters (book-service `/internal/books/{id}/chapters`),
  2. list the book's alive entities + their surface forms (glossary
     `/internal/books/{id}/entities` → name + aliases),
  3. for each chapter fetch its text (book-service `/internal/.../chapters/{cid}`) and
     recount every entity's mentions (CJK-aware longest-match, span-deduped) over it,
  4. POST the non-zero counts to glossary `/internal/books/{id}/recount-mention-counts`,
     which does a TARGETED, idempotent UPDATE of EXISTING links only (a count for an
     (entity,chapter) with no link is a 0-row no-op → presence-gating happens at the write).

The recount CORE (`recount_chapter`) is pure (text + forms in, counts out) so it is unit-
testable without any service. The orchestrator is best-effort + batched; a chapter/book
that can't be fetched is logged + skipped, never aborts the whole run.

NOTE (scope): the staleness wiring (recount one chapter on a chapter EDIT) is NOT a
scheduled consumer here — it is the same `recount_chapter` core invoked from the
chapter-update path. See `_recount_single_chapter` + the module-tail note. A full
scheduled/queued backfill JOB (progress rows, resume, rate-limit) is intentionally left as
a thin CLI driver below; promoting it to a managed job is tracked, not built in this lane.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from loreweave_internal_client import build_internal_client

from ..config import settings
from .mention_count import build_surface_forms, count_surface_form_mentions

log = logging.getLogger(__name__)

# Cap the POST batch so a huge book doesn't build one enormous request body.
_RECOUNT_BATCH = 500


def recount_chapter(
    chapter_text: str,
    entity_forms: dict[str, list[str]],
) -> dict[str, int]:
    """Pure recount core: for each entity, count its (pre-folded, longest-first) surface
    forms in `chapter_text`. Returns {entity_id: count} for entities with count > 0 only
    (a 0 means "not mentioned in this chapter" — nothing to update).

    `entity_forms` maps entity_id → the entity's surface forms as returned by
    `build_surface_forms` (folded + longest-first). Pass it pre-built so a multi-chapter
    backfill folds each entity's names ONCE, not per chapter.
    """
    out: dict[str, int] = {}
    if not chapter_text:
        return out
    for entity_id, forms in entity_forms.items():
        n = count_surface_form_mentions(chapter_text, forms)
        if n > 0:
            out[entity_id] = n
    return out


async def _fetch_chapter_list(client: httpx.AsyncClient, book_id: str) -> list[dict]:
    r = await client.get(
        f"{settings.book_service_internal_url}/internal/books/{book_id}/chapters",
    )
    r.raise_for_status()
    return r.json().get("items", []) or []


async def _fetch_chapter_text(client: httpx.AsyncClient, book_id: str, chapter_id: str) -> str:
    r = await client.get(
        f"{settings.book_service_internal_url}/internal/books/{book_id}/chapters/{chapter_id}",
    )
    if r.status_code == 404:
        return ""
    r.raise_for_status()
    return r.json().get("text_content") or ""


async def _fetch_entity_forms(client: httpx.AsyncClient, book_id: str) -> dict[str, list[str]]:
    """Page the glossary internal entities list → {entity_id: folded surface forms}."""
    forms: dict[str, list[str]] = {}
    cursor = ""
    while True:
        params = {"limit": 200}
        if cursor:
            params["cursor"] = cursor
        r = await client.get(
            f"{settings.glossary_service_internal_url}/internal/books/{book_id}/entities",
            params=params,
        )
        r.raise_for_status()
        body = r.json()
        items = body.get("items", body) if isinstance(body, dict) else body
        for e in items or []:
            eid = e.get("entity_id")
            if not eid:
                continue
            aliases = e.get("aliases") or []
            if isinstance(aliases, str):
                aliases = [aliases]
            forms[eid] = build_surface_forms(e.get("name", "") or "", aliases)
        cursor = body.get("next_cursor") if isinstance(body, dict) else None
        if not cursor:
            break
    return forms


async def _post_recounts(client: httpx.AsyncClient, book_id: str, counts: list[dict]) -> int:
    """POST a batch of {entity_id, chapter_id, mention_count} to glossary. Returns updated."""
    if not counts:
        return 0
    total = 0
    for i in range(0, len(counts), _RECOUNT_BATCH):
        chunk = counts[i : i + _RECOUNT_BATCH]
        r = await client.post(
            f"{settings.glossary_service_internal_url}/internal/books/{book_id}/recount-mention-counts",
            json={"counts": chunk},
        )
        r.raise_for_status()
        total += int(r.json().get("updated", 0))
    return total


async def backfill_book_mention_counts(book_id: str) -> dict:
    """Recount every chapter's mention_count for one book. Idempotent + best-effort.

    Returns a summary dict {book_id, chapters, entities, posted, updated}.
    """
    async with build_internal_client("", internal_token=settings.internal_service_token, timeout_s=60, connect_timeout_s=10) as client:
        chapters = await _fetch_chapter_list(client, book_id)
        entity_forms = await _fetch_entity_forms(client, book_id)
        if not entity_forms:
            log.info("mention-backfill: book %s has no entities — nothing to recount", book_id)
            return {"book_id": book_id, "chapters": len(chapters), "entities": 0, "posted": 0, "updated": 0}

        posted = 0
        updated = 0
        for ch in chapters:
            chapter_id = ch.get("chapter_id")
            if not chapter_id:
                continue
            try:
                text = await _fetch_chapter_text(client, book_id, chapter_id)
            except httpx.HTTPError as exc:
                log.warning("mention-backfill: skip chapter %s (fetch failed: %s)", chapter_id, exc)
                continue
            counts = recount_chapter(text, entity_forms)
            batch = [
                {"entity_id": eid, "chapter_id": chapter_id, "mention_count": n}
                for eid, n in counts.items()
            ]
            posted += len(batch)
            try:
                updated += await _post_recounts(client, book_id, batch)
            except httpx.HTTPError as exc:
                log.warning("mention-backfill: post failed for chapter %s: %s", chapter_id, exc)

        log.info("mention-backfill: book %s done — chapters=%d entities=%d posted=%d updated=%d",
                 book_id, len(chapters), len(entity_forms), posted, updated)
        return {
            "book_id": book_id, "chapters": len(chapters),
            "entities": len(entity_forms), "posted": posted, "updated": updated,
        }


async def _recount_single_chapter(book_id: str, chapter_id: str, chapter_text: str | None = None) -> int:
    """Staleness hook — recount ONE chapter (use on a chapter EDIT so its counts don't go
    stale). If `chapter_text` is provided (the edit path already holds it) it's used
    directly; otherwise it's fetched. Returns rows updated. Idempotent."""
    async with build_internal_client("", internal_token=settings.internal_service_token, timeout_s=60, connect_timeout_s=10) as client:
        entity_forms = await _fetch_entity_forms(client, book_id)
        text = chapter_text if chapter_text is not None else await _fetch_chapter_text(client, book_id, chapter_id)
        counts = recount_chapter(text, entity_forms)
        batch = [
            {"entity_id": eid, "chapter_id": chapter_id, "mention_count": n}
            for eid, n in counts.items()
        ]
        return await _post_recounts(client, book_id, batch)


if __name__ == "__main__":  # pragma: no cover — thin CLI driver
    import sys

    logging.basicConfig(level=logging.INFO)
    if len(sys.argv) < 2:
        print("usage: python -m app.workers.mention_backfill <book_id> [<book_id> ...]")
        raise SystemExit(2)

    async def _run() -> None:
        for bid in sys.argv[1:]:
            summary = await backfill_book_mention_counts(bid)
            print(summary)

    asyncio.run(_run())
