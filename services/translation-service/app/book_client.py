"""Thin internal client for book-service reads the translation worker needs."""
import httpx

from .config import settings


async def get_chapter_blocks(book_id, chapter_id) -> list[dict]:
    """T2: the chapter's extracted blocks (ordered, with content_hash) for the
    segmenter. Returns [] for a chapter with no blocks."""
    url = (
        f"{settings.book_service_internal_url}"
        f"/internal/books/{book_id}/chapters/{chapter_id}/blocks"
    )
    async with httpx.AsyncClient(timeout=30) as client:
        r = await client.get(url, headers={"X-Internal-Token": settings.internal_service_token})
        # A chapter present in chapter_translations but absent in book-service (deleted /
        # orphaned translation row) → no blocks → no segments. Treat 404 as empty rather
        # than raising, so a backfill / finalize-hook rebuild is a clean no-op instead of
        # a 500 (D-TRANSL-T2M1 LOW-1, confirmed live by the backfill run). 5xx still raises
        # (transient — should retry, not wipe segments).
        if r.status_code == 404:
            return []
        r.raise_for_status()
        return r.json().get("blocks", []) or []
