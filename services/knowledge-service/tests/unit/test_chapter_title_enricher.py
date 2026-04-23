"""C6 (D-K19b.3-01 + D-K19e-β-01) — enricher unit tests.

Covers in-place mutation semantics, dedup, graceful-degrade on
empty/missing chapter_ids, and the jobs path's cursor-shape matrix
(chapter cursor / chat cursor / missing cursor / malformed id).
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import UUID, uuid4

import pytest

from app.clients.chapter_title_enricher import (
    enrich_events_with_chapter_titles,
    enrich_jobs_with_current_chapter_titles,
)
from app.db.neo4j_repos.events import Event
from app.db.repositories.extraction_jobs import ExtractionJob


def _make_event(*, chapter_id: str | None = None, ident: str = "evt-1") -> Event:
    return Event(
        id=ident,
        user_id="user-1",
        project_id=None,
        title="Meeting at the bridge",
        canonical_title="meeting at the bridge",
        chapter_id=chapter_id,
        participants=[],
        confidence=0.9,
        source_types=["chapter"],
    )


def _make_job(
    *,
    cursor: dict | None = None,
    ident: str | None = None,
) -> ExtractionJob:
    now = datetime.now()
    return ExtractionJob(
        job_id=UUID(ident) if ident else uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        scope="chapters",
        status="running",
        llm_model="gpt-4o-mini",
        embedding_model="bge-m3",
        max_spend_usd=Decimal("5.00"),
        items_total=10,
        items_processed=3,
        current_cursor=cursor,
        cost_spent_usd=Decimal("0.50"),
        started_at=now,
        created_at=now,
        updated_at=now,
    )


# ── enrich_events_with_chapter_titles ─────────────────────────────


@pytest.mark.asyncio
async def test_enrich_events_empty_list_skips_network():
    """Short-circuit: empty input means no BookClient call."""
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock()
    await enrich_events_with_chapter_titles([], book_client)
    book_client.get_chapter_titles.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_events_no_chapter_ids_skips_network():
    """All events chapter_id=None → still no BookClient call."""
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock()
    events = [_make_event(chapter_id=None), _make_event(chapter_id=None, ident="evt-2")]
    await enrich_events_with_chapter_titles(events, book_client)
    book_client.get_chapter_titles.assert_not_called()
    for e in events:
        assert e.chapter_title is None


@pytest.mark.asyncio
async def test_enrich_events_happy_path_mutates_in_place():
    cid = uuid4()
    events = [_make_event(chapter_id=str(cid))]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={cid: "Chapter 5 — The Rescue"},
    )
    await enrich_events_with_chapter_titles(events, book_client)
    assert events[0].chapter_title == "Chapter 5 — The Rescue"


@pytest.mark.asyncio
async def test_enrich_events_dedup_same_chapter_id():
    """Multiple events on the same chapter → one id in BookClient call
    (dedup). Both events get the resolved title."""
    cid = uuid4()
    events = [
        _make_event(chapter_id=str(cid), ident="evt-1"),
        _make_event(chapter_id=str(cid), ident="evt-2"),
    ]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={cid: "Chapter 7 — Twice Here"},
    )
    await enrich_events_with_chapter_titles(events, book_client)
    assert events[0].chapter_title == "Chapter 7 — Twice Here"
    assert events[1].chapter_title == "Chapter 7 — Twice Here"
    # Dedup lock: only ONE id sent.
    call_ids = book_client.get_chapter_titles.await_args.args[0]
    assert len(call_ids) == 1
    assert call_ids[0] == cid


@pytest.mark.asyncio
async def test_enrich_events_partial_response_leaves_missing_as_none():
    """Some ids resolve, some don't — unresolved stays None; FE falls
    back to chapterShort()."""
    cid_resolved = uuid4()
    cid_missing = uuid4()
    events = [
        _make_event(chapter_id=str(cid_resolved), ident="evt-1"),
        _make_event(chapter_id=str(cid_missing), ident="evt-2"),
    ]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={cid_resolved: "Chapter 1 — Has Title"},
    )
    await enrich_events_with_chapter_titles(events, book_client)
    assert events[0].chapter_title == "Chapter 1 — Has Title"
    assert events[1].chapter_title is None


@pytest.mark.asyncio
async def test_enrich_events_book_client_empty_dict_leaves_all_none():
    """Graceful-degrade: BookClient returns {} on any failure, and
    we exit without touching events (chapter_title stays default None)."""
    events = [_make_event(chapter_id=str(uuid4()))]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(return_value={})
    await enrich_events_with_chapter_titles(events, book_client)
    assert events[0].chapter_title is None


@pytest.mark.asyncio
async def test_enrich_events_malformed_chapter_id_skipped():
    """Neo4j drift: chapter_id is a non-UUID string. The enricher must
    skip it rather than crash — other events with valid ids still
    resolve normally."""
    good = uuid4()
    events = [
        _make_event(chapter_id="not-a-uuid", ident="evt-bad"),
        _make_event(chapter_id=str(good), ident="evt-good"),
    ]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={good: "Chapter 2 — OK"},
    )
    await enrich_events_with_chapter_titles(events, book_client)
    assert events[0].chapter_title is None
    assert events[1].chapter_title == "Chapter 2 — OK"


# ── enrich_jobs_with_current_chapter_titles ───────────────────────


@pytest.mark.asyncio
async def test_enrich_jobs_empty_list_skips_network():
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock()
    await enrich_jobs_with_current_chapter_titles([], book_client)
    book_client.get_chapter_titles.assert_not_called()


@pytest.mark.asyncio
async def test_enrich_jobs_no_cursor_skips_network():
    """Jobs without current_cursor (newly-queued, or completed/failed
    jobs where cursor was cleared) — no network call."""
    jobs = [_make_job(cursor=None)]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock()
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    book_client.get_chapter_titles.assert_not_called()
    assert jobs[0].current_chapter_title is None


@pytest.mark.asyncio
async def test_enrich_jobs_chat_cursor_skipped():
    """Chat-scope cursors use ``last_pending_id``, not
    ``last_chapter_id``. Enricher leaves those untouched — book
    service can't resolve a chat-turn id as a chapter."""
    jobs = [_make_job(cursor={"scope": "chat", "last_pending_id": str(uuid4())})]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock()
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    book_client.get_chapter_titles.assert_not_called()
    assert jobs[0].current_chapter_title is None


@pytest.mark.asyncio
async def test_enrich_jobs_chapter_cursor_happy_path():
    cid = uuid4()
    jobs = [
        _make_job(cursor={"scope": "chapters", "last_chapter_id": str(cid)}),
    ]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={cid: "Chapter 12 — The Bridge Duel"},
    )
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    assert jobs[0].current_chapter_title == "Chapter 12 — The Bridge Duel"


@pytest.mark.asyncio
async def test_enrich_jobs_dedup_shared_chapter():
    """Two jobs paused on the same chapter → one BookClient call."""
    cid = uuid4()
    jobs = [
        _make_job(cursor={"last_chapter_id": str(cid)}),
        _make_job(cursor={"last_chapter_id": str(cid)}),
    ]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={cid: "Chapter 4 — Both Here"},
    )
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    assert jobs[0].current_chapter_title == "Chapter 4 — Both Here"
    assert jobs[1].current_chapter_title == "Chapter 4 — Both Here"
    call_ids = book_client.get_chapter_titles.await_args.args[0]
    assert len(call_ids) == 1


@pytest.mark.asyncio
async def test_enrich_jobs_malformed_chapter_id_in_cursor_skipped():
    """Defensive: cursor has last_chapter_id but it's a garbage string.
    Enricher skips that job cleanly + resolves the valid one."""
    good = uuid4()
    jobs = [
        _make_job(cursor={"last_chapter_id": "garbage"}, ident="00000000-0000-0000-0000-000000000001"),
        _make_job(cursor={"last_chapter_id": str(good)}, ident="00000000-0000-0000-0000-000000000002"),
    ]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(
        return_value={good: "Chapter 9 — OK"},
    )
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    assert jobs[0].current_chapter_title is None
    assert jobs[1].current_chapter_title == "Chapter 9 — OK"


@pytest.mark.asyncio
async def test_enrich_jobs_book_client_empty_dict_leaves_all_none():
    jobs = [_make_job(cursor={"last_chapter_id": str(uuid4())})]
    book_client = MagicMock()
    book_client.get_chapter_titles = AsyncMock(return_value={})
    await enrich_jobs_with_current_chapter_titles(jobs, book_client)
    assert jobs[0].current_chapter_title is None
