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


@pytest.mark.asyncio
async def test_count_chapters_forwards_sort_range_as_query_params(bc: BookClient):
    """D-K16.2-02 — ``from_sort``/``to_sort`` kwargs must arrive at
    book-service as query params, not as body or headers. The estimate
    tests stub the whole client, so this is the only assertion that
    the actual HTTP wire carries the range."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 7})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        result = await bc.count_chapters(book_id, from_sort=10, to_sort=20)

    assert result == 7
    assert captured["query"]["from_sort"] == "10"
    assert captured["query"]["to_sort"] == "20"
    assert captured["query"]["limit"] == "1"


@pytest.mark.asyncio
async def test_count_chapters_omits_sort_params_when_not_set(bc: BookClient):
    """Unset kwargs must NOT materialise on the wire — otherwise
    book-service would see ``from_sort=None`` (string) and reject 400."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 3})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id)

    assert "from_sort" not in captured["query"]
    assert "to_sort" not in captured["query"]


@pytest.mark.asyncio
async def test_count_chapters_from_sort_only(bc: BookClient):
    """One-sided range (upper unbounded) must omit ``to_sort``."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 5})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id, from_sort=3)

    assert captured["query"]["from_sort"] == "3"
    assert "to_sort" not in captured["query"]


@pytest.mark.asyncio
async def test_count_chapters_from_sort_zero_sent_not_dropped(bc: BookClient):
    """Regression: ``from_sort=0`` must reach the wire, not be dropped
    as falsy — the handler distinguishes ``None`` (skip filter) from
    ``0`` (filter starting at sort_order 0)."""
    book_id = uuid4()
    captured: dict = {}

    def capture(request: httpx.Request) -> httpx.Response:
        captured["query"] = dict(request.url.params)
        return httpx.Response(200, json={"total": 2})

    with respx.mock() as mock:
        mock.get(_count_url(book_id)).mock(side_effect=capture)
        await bc.count_chapters(book_id, from_sort=0, to_sort=0)

    assert captured["query"]["from_sort"] == "0"
    assert captured["query"]["to_sort"] == "0"


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
