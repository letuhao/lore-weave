"""Thin internal client for book-service reads the translation worker needs."""
import httpx

from .config import settings


async def book_owns_chapter(book_id, chapter_id) -> bool:
    """Authoritative chapter→book binding check (book-service is the single
    authority for chapter ownership). Returns True iff `chapter_id` is an active
    chapter of `book_id`.

    Used by the Tier-W confirm spine to assert each requested chapter actually
    belongs to the book bound in the confirm token (`claims.resource_id`) — a
    confirm payload must NOT be able to retarget chapters under a DIFFERENT book
    than the one whose grant was (re-)authorized. The blocks endpoint validates
    `chapter_id AND book_id` server-side (`SELECT EXISTS(... WHERE id=? AND
    book_id=? AND lifecycle_state='active')`) and 404s when unbound — so a 2xx is
    a positive binding proof, a 404 a clean "not bound".

    Fail-CLOSED: a transport error / 5xx raises (the caller must NOT spend on an
    unverifiable binding); only a definitive 404 returns False."""
    url = (
        f"{settings.book_service_internal_url}"
        f"/internal/books/{book_id}/chapters/{chapter_id}/blocks"
    )
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(url, headers={"X-Internal-Token": settings.internal_service_token})
        if r.status_code == 404:
            return False
        r.raise_for_status()
        return True


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
