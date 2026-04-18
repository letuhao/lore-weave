"""Unit tests for the book-service HTTP client.

Uses respx to mock book-service responses. Every failure path must
return a safe default — the caller never sees an exception.
"""
from __future__ import annotations

from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
import respx

from app.clients.book_client import BookClient


@pytest_asyncio.fixture
async def bc():
    client = BookClient(
        base_url="http://book-service:8082",
        internal_token="unit-test-token",
        timeout_s=0.5,
    )
    try:
        yield client
    finally:
        await client.aclose()


def _count_url(book_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/chapters"


def _chapter_url(book_id, chapter_id) -> str:
    return f"http://book-service:8082/internal/books/{book_id}/chapters/{chapter_id}"


# ── count_chapters ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_count_chapters_success(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(
            return_value=httpx.Response(200, json={"total": 42}),
        )
        assert await bc.count_chapters(book_id) == 42


@pytest.mark.asyncio
async def test_count_chapters_5xx_returns_none(bc: BookClient):
    book_id = uuid4()
    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(return_value=httpx.Response(503))
        assert await bc.count_chapters(book_id) is None


# ── get_chapter_text (D-K18.3-01) ───────────────────────────────────


@pytest.mark.asyncio
async def test_get_chapter_text_success(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(
                200,
                json={
                    "chapter_id": str(chapter_id),
                    "title": "Ch 1",
                    "text_content": "Arthur drew the sword from the stone.",
                },
            ),
        )
        text = await bc.get_chapter_text(book_id, chapter_id)
    assert text == "Arthur drew the sword from the stone."


@pytest.mark.asyncio
async def test_get_chapter_text_missing_field_returns_none(bc: BookClient):
    """Response without text_content → None (ingester treats as skip)."""
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(200, json={"chapter_id": str(chapter_id)}),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_get_chapter_text_empty_returns_none(bc: BookClient):
    """Empty text_content counts as None so we don't upsert empty passages."""
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(200, json={"text_content": "   "}),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_get_chapter_text_404_returns_none(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            return_value=httpx.Response(404),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_get_chapter_text_connection_error_returns_none(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(
            side_effect=httpx.ConnectError("boom"),
        )
        assert await bc.get_chapter_text(book_id, chapter_id) is None


@pytest.mark.asyncio
async def test_internal_token_header_sent(bc: BookClient):
    book_id = uuid4()
    chapter_id = uuid4()
    captured: list[str] = []

    def capture(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("X-Internal-Token", ""))
        return httpx.Response(200, json={"text_content": "hi"})

    with respx.mock() as mock:
        mock.get(_chapter_url(book_id, chapter_id)).mock(side_effect=capture)
        await bc.get_chapter_text(book_id, chapter_id)

    assert captured == ["unit-test-token"]
