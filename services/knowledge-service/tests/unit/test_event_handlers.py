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


# ── C12a (D-K16.2-02b) — chapter_range gating ─────────────────────


def _make_job(scope="chapters", chapter_range=None):
    """Minimal ExtractionJob stub for the gating path. Only the
    fields the handler reads (scope + scope_range) need to be
    realistic; the rest are placeholders."""
    from datetime import datetime, timezone
    from decimal import Decimal
    from app.db.repositories.extraction_jobs import ExtractionJob
    return ExtractionJob(
        job_id=uuid4(),
        user_id=_USER,
        project_id=_PROJECT,
        scope=scope,
        scope_range={"chapter_range": list(chapter_range)} if chapter_range else None,
        status="running",
        llm_model="claude-sonnet-4-6",
        embedding_model="bge-m3",
        max_spend_usd=None,
        items_total=None,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=Decimal("0"),
        started_at=datetime.now(timezone.utc),
        paused_at=None,
        completed_at=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
        error_message=None,
        project_name=None,
    )


async def _run_chapter_saved_with_gating(
    monkeypatch, *, active_jobs, sort_orders,
):
    """Harness for C12a gating tests. Patches the same surfaces the
    existing ingest-ON test does plus list_active_for_project +
    get_chapter_sort_orders. Returns the ingest_mock so callers can
    assert whether ingest was called or not."""
    from contextlib import asynccontextmanager
    from unittest.mock import MagicMock

    pool, _conn = _mock_pool()
    pool.fetchrow = AsyncMock(return_value={
        "project_id": _PROJECT, "user_id": _USER,
        "embedding_model": "bge-m3", "embedding_dimension": 1024,
    })

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
        bc_mock = MagicMock()
        bc_mock.get_chapter_sort_orders = AsyncMock(return_value=sort_orders)
        monkeypatch.setattr(
            "app.clients.book_client.get_book_client", lambda: bc_mock,
        )
        monkeypatch.setattr(
            "app.clients.embedding_client.get_embedding_client",
            lambda: MagicMock(),
        )
        # Patch ExtractionJobsRepo.list_active_for_project on the class
        # so the handler's fresh instance sees the mock.
        monkeypatch.setattr(
            "app.db.repositories.extraction_jobs.ExtractionJobsRepo.list_active_for_project",
            AsyncMock(return_value=active_jobs),
        )

        event = _event(
            "chapter.saved",
            aggregate_id=str(_CHAPTER),
            payload={"book_id": str(_BOOK)},
        )
        await handle_chapter_saved(event, pool=pool)

    return ingest_mock


@pytest.mark.asyncio
async def test_chapter_saved_ingests_when_no_active_chapter_jobs(monkeypatch):
    """No active scope='chapters' jobs → ingest proceeds (baseline)."""
    ingest_mock = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[_make_job(scope="chat")],  # non-chapter scope
        sort_orders={_CHAPTER: 5},
    )
    ingest_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_chapter_saved_ingests_when_active_chapter_job_has_no_range(monkeypatch):
    """Active chapter-scope job with no chapter_range → full-scope
    intent → ingest proceeds. The gate only triggers when ALL active
    chapter-scope jobs have bounded ranges."""
    ingest_mock = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[_make_job(scope="chapters", chapter_range=None)],
        sort_orders={_CHAPTER: 5},
    )
    ingest_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_chapter_saved_skips_when_chapter_outside_range(monkeypatch):
    """Active chapter-scope job with range [10, 20] + chapter at
    sort_order=5 → skip ingest (out of range)."""
    ingest_mock = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[_make_job(scope="chapters", chapter_range=[10, 20])],
        sort_orders={_CHAPTER: 5},
    )
    ingest_mock.assert_not_awaited()


@pytest.mark.asyncio
async def test_chapter_saved_ingests_when_chapter_inside_range(monkeypatch):
    """Active chapter-scope job with range [10, 20] + chapter at
    sort_order=15 → in-range → ingest proceeds."""
    ingest_mock = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[_make_job(scope="chapters", chapter_range=[10, 20])],
        sort_orders={_CHAPTER: 15},
    )
    ingest_mock.assert_awaited_once()


@pytest.mark.asyncio
async def test_chapter_saved_disjoint_union_of_ranges(monkeypatch):
    """Two active chapter-scope jobs with non-overlapping ranges
    [10, 20] and [40, 50]. Chapter at sort_order=30 is in NEITHER
    range → skip. Chapter at sort_order=45 is in the second range
    → ingest. This locks the disjoint-union semantic (not outer
    envelope which would over-ingest 30)."""
    # sort_order=30: outside both → skip
    ingest_mock_skip = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[
            _make_job(scope="chapters", chapter_range=[10, 20]),
            _make_job(scope="chapters", chapter_range=[40, 50]),
        ],
        sort_orders={_CHAPTER: 30},
    )
    ingest_mock_skip.assert_not_awaited()

    # sort_order=45: in second range → ingest
    ingest_mock_yes = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[
            _make_job(scope="chapters", chapter_range=[10, 20]),
            _make_job(scope="chapters", chapter_range=[40, 50]),
        ],
        sort_orders={_CHAPTER: 45},
    )
    ingest_mock_yes.assert_awaited_once()


@pytest.mark.asyncio
async def test_chapter_saved_overingests_when_sort_order_fetch_fails(monkeypatch):
    """Graceful degrade: book-service returns empty sort_orders map
    → handler proceeds with ingest rather than silently skipping.
    Missing sort_order is uncertainty, not a confirmed out-of-range."""
    ingest_mock = await _run_chapter_saved_with_gating(
        monkeypatch,
        active_jobs=[_make_job(scope="chapters", chapter_range=[10, 20])],
        sort_orders={},  # book-service unavailable or chapter not found
    )
    ingest_mock.assert_awaited_once()


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
