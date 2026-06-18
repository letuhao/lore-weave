"""T2.1 — unit tests for the Cast & Codex spoiler-window resolver.

The FAIL-CLOSED behaviour is the security-critical bit: an unresolvable chapter
must restrict (no leak), inverting book_client.get_chapter_sort_orders' fail-OPEN
posture. No Neo4j needed — book_client is mocked.
"""

from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from app.db.neo4j_repos.events import EVENT_ORDER_CHAPTER_STRIDE
from app.spoiler_window import FAIL_CLOSED_BEFORE_ORDER, resolve_before_order


@pytest.mark.asyncio
async def test_resolve_happy_inclusive_through_chapter():
    cid = uuid4()
    book = AsyncMock()
    book.get_chapter_sort_orders = AsyncMock(return_value={cid: 3})
    before_order, available = await resolve_before_order(book, cid)
    # inclusive-through-chapter-3 ceiling = (3+1)*STRIDE - 1 → covers all of ch3.
    assert before_order == 4 * EVENT_ORDER_CHAPTER_STRIDE - 1
    assert available is True


@pytest.mark.asyncio
async def test_resolve_chapter_zero():
    cid = uuid4()
    book = AsyncMock()
    book.get_chapter_sort_orders = AsyncMock(return_value={cid: 0})
    before_order, available = await resolve_before_order(book, cid)
    assert before_order == EVENT_ORDER_CHAPTER_STRIDE - 1  # all of chapter 0
    assert available is True


@pytest.mark.asyncio
async def test_resolve_none_chapter_fails_closed():
    book = AsyncMock()
    book.get_chapter_sort_orders = AsyncMock()
    before_order, available = await resolve_before_order(book, None)
    assert before_order == FAIL_CLOSED_BEFORE_ORDER == -1
    assert available is False
    book.get_chapter_sort_orders.assert_not_awaited()  # short-circuits, no network


@pytest.mark.asyncio
async def test_resolve_book_service_empty_fails_closed():
    # book-service down / over-ingest returns {} — we must NOT fall open.
    cid = uuid4()
    book = AsyncMock()
    book.get_chapter_sort_orders = AsyncMock(return_value={})
    before_order, available = await resolve_before_order(book, cid)
    assert before_order == -1
    assert available is False


@pytest.mark.asyncio
async def test_resolve_chapter_not_in_response_fails_closed():
    cid = uuid4()
    other = uuid4()
    book = AsyncMock()
    book.get_chapter_sort_orders = AsyncMock(return_value={other: 5})
    before_order, available = await resolve_before_order(book, cid)
    assert before_order == -1
    assert available is False
