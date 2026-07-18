"""review-impl P1 — BookClient.list_chapters MUST paginate.

The whole-book KG rebuild enumerates chapters through this one call. It used to issue a
single `GET ?limit=1000` with no offset loop — but book-service CLAMPS chapter-list page
size to 100 (parseLimitOffset). So for any book with more than 100 kg-indexed chapters the
rebuild silently enumerated only the FIRST 100, extracted them, and reported SUCCESS.
Chapters 101+ never reached the knowledge graph, with no error and no warning: the
`silent-success-is-a-bug` class, on the exact path WS-0.6b made load-bearing.

Every other test in this suite mocks `list_chapters` itself, so none of them could catch
this — the bug lived in the method they were stubbing out. These tests drive the REAL
method against a fake transport.
"""

from __future__ import annotations

from uuid import uuid4

import httpx
import pytest

from app.clients import BookClient, _LIST_CHAPTERS_PAGE


def _chapter(i: int) -> dict:
    rev = str(uuid4())
    return {
        "chapter_id": str(uuid4()),
        "title": f"Chapter {i}",
        "sort_order": i,
        "editorial_status": "draft",
        "kg_indexed_revision_id": rev,
        "published_revision_id": None,
        "kg_exclude": False,
    }


def _client_serving(total: int) -> tuple[BookClient, list[str]]:
    """A BookClient whose transport serves `total` chapters, CLAMPING each page to 100 —
    exactly as book-service does. Returns the client and a log of the URLs requested."""
    all_chapters = [_chapter(i) for i in range(total)]
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        params = request.url.params
        limit = int(params.get("limit", 20))
        offset = int(params.get("offset", 0))
        # book-service clamps to 100 no matter what the caller asks for.
        limit = min(limit, 100)
        page = all_chapters[offset : offset + limit]
        return httpx.Response(200, json={"items": page, "total": total})

    bc = BookClient("http://book", "tok", 5.0)
    bc._http = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return bc, seen


@pytest.mark.asyncio
async def test_list_chapters_pages_past_the_100_row_clamp():
    """THE BUG: a 250-chapter book must enumerate all 250, not the first 100."""
    bc, seen = _client_serving(250)
    try:
        out = await bc.list_chapters(uuid4(), kg_indexed=True)
    finally:
        await bc.aclose()

    assert out is not None
    assert len(out) == 250, (
        f"enumerated {len(out)} of 250 chapters. book-service clamps the page size to 100, "
        "so a single ?limit=1000 request silently returns only the first 100 — the rebuild "
        "then extracts 100 chapters, reports SUCCESS, and the other 150 never reach the "
        "knowledge graph."
    )
    # It really did page (3 requests: 0, 100, 200).
    assert len(seen) == 3, f"expected 3 pages, got {len(seen)}: {seen}"
    assert "offset=100" in seen[1] and "offset=200" in seen[2]
    # And it kept asking the right question on every page.
    assert all("kg_indexed=true" in u for u in seen)


@pytest.mark.asyncio
async def test_list_chapters_pins_the_kg_indexed_revision():
    """Each ChapterInfo.revision_id must be the revision the KG reflects.

    A None revision_id makes the extractor fall back to LIVE DRAFT text, so this is not
    cosmetic — it is what keeps the rebuild reading the prose the user actually indexed.
    """
    bc, _ = _client_serving(3)
    try:
        out = await bc.list_chapters(uuid4(), kg_indexed=True)
    finally:
        await bc.aclose()

    assert out is not None and len(out) == 3
    assert all(c.revision_id for c in out), "every chapter must carry its pinned revision"


@pytest.mark.asyncio
async def test_list_chapters_exact_page_boundary_does_not_loop_forever():
    """A book whose size is an exact multiple of the page size must terminate."""
    bc, seen = _client_serving(_LIST_CHAPTERS_PAGE)  # exactly one full page
    try:
        out = await bc.list_chapters(uuid4(), kg_indexed=True)
    finally:
        await bc.aclose()

    assert out is not None and len(out) == _LIST_CHAPTERS_PAGE
    # One full page, then one empty page to learn it is the end.
    assert len(seen) == 2, f"expected 2 requests at the exact boundary, got {len(seen)}"


@pytest.mark.asyncio
async def test_list_chapters_empty_book():
    bc, seen = _client_serving(0)
    try:
        out = await bc.list_chapters(uuid4(), kg_indexed=True)
    finally:
        await bc.aclose()

    assert out == []
    assert len(seen) == 1
