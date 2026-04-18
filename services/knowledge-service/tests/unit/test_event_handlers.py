"""K14.5-K14.7 — Unit tests for event handlers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events.dispatcher import EventData
from app.events.handlers import handle_chat_turn, handle_chapter_saved, handle_chapter_deleted


_USER = uuid4()
_PROJECT = uuid4()
_BOOK = uuid4()
_CHAPTER = uuid4()


def _event(event_type, aggregate_id=None, payload=None):
    return EventData(
        stream="loreweave:events:chat",
        message_id="1-0",
        event_type=event_type,
        aggregate_id=aggregate_id or str(uuid4()),
        payload=payload or {},
        source="book",
        raw={},
    )


def _mock_pool():
    """Create a pool mock where acquire() is an async context manager."""
    mock_conn = AsyncMock()
    mock_conn.fetchrow = AsyncMock(return_value=None)
    mock_conn.execute = AsyncMock()

    @asynccontextmanager
    async def mock_acquire():
        yield mock_conn

    pool = MagicMock()
    pool.acquire = mock_acquire
    pool.fetchrow = mock_conn.fetchrow
    pool.execute = mock_conn.execute
    return pool, mock_conn


# ── K14.5: chat.turn_completed ───────────────────────────────────────


@pytest.mark.asyncio
@patch("app.events.handlers.should_extract", return_value=True)
async def test_chat_turn_queues_event_with_user_id(mock_gate):
    pool, conn = _mock_pool()
    event = _event(
        "chat.turn_completed",
        payload={"project_id": str(_PROJECT), "user_id": str(_USER)},
    )
    await handle_chat_turn(event, pool=pool)
    assert conn.fetchrow.call_count >= 1


@pytest.mark.asyncio
@patch("app.events.handlers.should_extract", return_value=True)
async def test_chat_turn_resolves_user_from_db(mock_gate):
    """user_id missing from payload — handler looks up from project."""
    pool, conn = _mock_pool()
    # First pool.fetchrow: user_id lookup from project
    pool.fetchrow = AsyncMock(return_value={"user_id": _USER})
    event = _event(
        "chat.turn_completed",
        payload={"project_id": str(_PROJECT)},  # no user_id
    )
    await handle_chat_turn(event, pool=pool)
    pool.fetchrow.assert_called_once()  # user lookup


@pytest.mark.asyncio
async def test_chat_turn_missing_project_id_skips():
    pool, conn = _mock_pool()
    event = _event("chat.turn_completed", payload={})
    await handle_chat_turn(event, pool=pool)
    conn.fetchrow.assert_not_called()


# ── K14.6: chapter.saved ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_chapter_saved_queues_event():
    pool, conn = _mock_pool()
    # D-K18.3-01: project lookup now also returns embedding config.
    # None values cause the passage-ingest branch to skip cleanly —
    # the core contract of this test is "extraction_pending queued".
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": None, "embedding_dimension": None,
    })

    event = _event(
        "chapter.saved",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},  # no user_id — realistic
    )
    await handle_chapter_saved(event, pool=pool)
    pool.fetchrow.assert_called_once()  # project lookup


@pytest.mark.asyncio
async def test_chapter_saved_no_project_skips():
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value=None)

    event = _event(
        "chapter.saved",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )
    await handle_chapter_saved(event, pool=pool)
    pool.fetchrow.assert_called_once()
    conn.fetchrow.assert_not_called()


@pytest.mark.asyncio
async def test_chapter_saved_missing_book_id_skips():
    pool, conn = _mock_pool()
    event = _event("chapter.saved", aggregate_id=str(_CHAPTER), payload={})
    await handle_chapter_saved(event, pool=pool)
    pool.fetchrow.assert_not_called()


@pytest.mark.asyncio
async def test_chapter_saved_triggers_passage_ingest_when_embedding_configured(
    monkeypatch,
):
    """D-K18.3-01: when project has embedding_model + dim + NEO4J_URI,
    the handler calls `ingest_chapter_passages` after queueing."""
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock

    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })

    # Patch the settings + the lazy-imported ingester.
    with patch("app.config.settings") as ms:
        ms.neo4j_uri = "bolt://fake"

        @asynccontextmanager
        async def fake_session():
            yield MagicMock()

        ingest_mock = AsyncMock()
        monkeypatch.setattr("app.db.neo4j.neo4j_session", fake_session)
        monkeypatch.setattr(
            "app.extraction.passage_ingester.ingest_chapter_passages", ingest_mock,
        )
        monkeypatch.setattr(
            "app.clients.book_client.get_book_client", lambda: MagicMock(),
        )
        monkeypatch.setattr(
            "app.clients.embedding_client.get_embedding_client",
            lambda: MagicMock(),
        )

        event = _event(
            "chapter.saved",
            aggregate_id=str(_CHAPTER),
            payload={"book_id": str(_BOOK)},
        )
        await handle_chapter_saved(event, pool=pool)

    ingest_mock.assert_awaited_once()
    kw = ingest_mock.await_args.kwargs
    assert kw["embedding_model"] == "bge-m3"
    assert kw["embedding_dim"] == 1024


@pytest.mark.asyncio
async def test_chapter_saved_skips_passage_ingest_when_no_embedding():
    """D-K18.3-01: project without embedding_model → queue extraction
    but skip passage ingest cleanly."""
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": None, "embedding_dimension": None,
    })

    event = _event(
        "chapter.saved",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )
    # Should NOT raise even though no embedding_client is patched in —
    # the guard returns early before any client lookup.
    await handle_chapter_saved(event, pool=pool)


# ── K14.7: chapter.deleted ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_chapter_deleted_clears_pending():
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={"project_id": _PROJECT, "user_id": _USER})

    event = _event(
        "chapter.deleted",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )

    with patch("app.config.settings") as ms:
        ms.neo4j_uri = ""
        await handle_chapter_deleted(event, pool=pool)

    pool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_chapter_deleted_no_project_skips():
    pool, conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value=None)

    event = _event(
        "chapter.deleted",
        aggregate_id=str(_CHAPTER),
        payload={"book_id": str(_BOOK)},
    )
    await handle_chapter_deleted(event, pool=pool)
    pool.execute.assert_not_called()
