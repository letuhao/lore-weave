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
        r.raise_for_status()
        return r.json().get("blocks", []) or []
