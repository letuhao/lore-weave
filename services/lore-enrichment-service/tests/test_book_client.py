"""book-service read-client tests for the profile-authoring reads (C3 / slice 0d, T1).

respx-mocked — no live stack. Covers `get_projection` (AI-suggest metadata seed)
and `list_chapters` (selection picker + sampling source). Author-supplied prose
(title/description/summary/chapter titles) is injection-neutralized (M4); a 404
maps to a typed BookServiceError.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import respx

from app.clients.book import BookClient, BookServiceError
from app.config import settings


def _client() -> BookClient:
    return BookClient(base_url=settings.book_service_url, internal_token="t")


# ── get_projection ────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_get_projection_shapes_and_neutralizes():
    book, owner = uuid4(), uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/projection").respond(
        200,
        json={
            "book_id": str(book),
            "owner_user_id": str(owner),
            "title": "封神演义",
            "description": "商周神魔小说",
            "original_language": "zh",
            "summary_excerpt": "姜子牙佐周伐纣……",
            "genre_tags": ["神话", "历史"],
            "chapter_count": 100,
            "lifecycle_state": "active",
        },
    )
    c = _client()
    try:
        proj = await c.get_projection(book_id=book)
    finally:
        await c.aclose()
    assert proj.book_id == book
    assert proj.owner_user_id == owner
    assert proj.title == "封神演义"
    assert proj.original_language == "zh"
    assert proj.description == "商周神魔小说"
    assert proj.summary_excerpt.startswith("姜子牙")
    assert proj.genre_tags == ["神话", "历史"]
    assert proj.chapter_count == 100


@respx.mock
@pytest.mark.asyncio
async def test_get_projection_404_raises():
    book = uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/projection").respond(404)
    c = _client()
    try:
        with pytest.raises(BookServiceError) as exc:
            await c.get_projection(book_id=book)
    finally:
        await c.aclose()
    assert exc.value.status_code == 404
    assert exc.value.retryable is False


@respx.mock
@pytest.mark.asyncio
async def test_get_projection_tolerates_missing_optional_fields():
    book = uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/projection").respond(
        200, json={"book_id": str(book), "title": "Untitled"}
    )
    c = _client()
    try:
        proj = await c.get_projection(book_id=book)
    finally:
        await c.aclose()
    assert proj.title == "Untitled"
    assert proj.original_language == ""
    assert proj.genre_tags == []
    assert proj.chapter_count == 0


# ── list_chapters ─────────────────────────────────────────────────────────────

@respx.mock
@pytest.mark.asyncio
async def test_list_chapters_shapes_and_total():
    book, c1, c2 = uuid4(), uuid4(), uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/chapters").respond(
        200,
        json={
            "items": [
                {"chapter_id": str(c1), "title": "第一回", "sort_order": 1,
                 "original_language": "zh", "word_count_estimate": 1200},
                {"chapter_id": str(c2), "title": "第二回", "sort_order": 2,
                 "original_language": "zh", "word_count_estimate": 900},
            ],
            "total": 100, "limit": 200, "offset": 0,
        },
    )
    c = _client()
    try:
        items, total = await c.list_chapters(book_id=book)
    finally:
        await c.aclose()
    assert total == 100
    assert [ch.chapter_id for ch in items] == [c1, c2]
    assert items[0].title == "第一回" and items[0].sort_order == 1
    assert items[0].word_count_estimate == 1200


@respx.mock
@pytest.mark.asyncio
async def test_list_chapters_empty_book():
    book = uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/chapters").respond(
        200, json={"items": [], "total": 0, "limit": 200, "offset": 0}
    )
    c = _client()
    try:
        items, total = await c.list_chapters(book_id=book)
    finally:
        await c.aclose()
    assert items == [] and total == 0


@respx.mock
@pytest.mark.asyncio
async def test_list_chapters_404_raises():
    book = uuid4()
    respx.get(f"{settings.book_service_url}/internal/books/{book}/chapters").respond(404)
    c = _client()
    try:
        with pytest.raises(BookServiceError):
            await c.list_chapters(book_id=book)
    finally:
        await c.aclose()
