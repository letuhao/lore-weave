"""K16.6b — Unit tests for the extraction job runner.

Tests the core process_job logic with mocked DB pool and HTTP clients.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from app.clients import BookClient, ChapterInfo, ExtractionResult, KnowledgeClient
from app.runner import JobRow, process_job, poll_and_run, _get_running_jobs


# ── Helpers ──────────────────────────────────────────────────────────


def _job(**overrides) -> JobRow:
    defaults = dict(
        job_id=uuid4(),
        user_id=uuid4(),
        project_id=uuid4(),
        scope="chapters",
        scope_range=None,
        status="running",
        llm_model="test-model",
        embedding_model="bge-m3",
        max_spend_usd=Decimal("10.00"),
        items_total=5,
        items_processed=0,
        current_cursor=None,
        cost_spent_usd=Decimal("0"),
    )
    defaults.update(overrides)
    return JobRow(**defaults)


def _ok_result(source_id: str = "ch-1") -> ExtractionResult:
    return ExtractionResult(
        source_id=source_id,
        entities_merged=2,
        relations_created=1,
        events_merged=1,
        facts_merged=3,
    )


def _error_result(retryable: bool = True) -> ExtractionResult:
    return ExtractionResult(
        source_id="ch-1",
        entities_merged=0,
        relations_created=0,
        events_merged=0,
        facts_merged=0,
        retryable=retryable,
        error="something broke",
    )


_TEST_BOOK_ID = uuid4()


def _mock_pool(book_id=_TEST_BOOK_ID):
    """Create a mock asyncpg pool.

    fetchval is called for both _get_project_book_id (returns UUID)
    and _refresh_job_status (returns str). We use side_effect to
    return book_id first, then 'running' for all subsequent calls.
    """
    pool = AsyncMock()
    pool.fetchval = AsyncMock(side_effect=[book_id, *["running"] * 100])
    # Default: try_spend succeeds
    pool.fetchrow = AsyncMock(return_value={"cost_spent_usd": Decimal("0.004"), "status": "running"})
    # Default: execute succeeds
    pool.execute = AsyncMock()
    # Default: no pending chat turns
    pool.fetch = AsyncMock(return_value=[])
    return pool


def _mock_knowledge_client(result=None):
    client = AsyncMock(spec=KnowledgeClient)
    client.extract_item = AsyncMock(return_value=result or _ok_result())
    return client


def _mock_book_client(chapters=None, text="Chapter text here."):
    client = AsyncMock(spec=BookClient)
    if chapters is None:
        chapters = [ChapterInfo(chapter_id="ch-1", title="Ch 1", sort_order=1)]
    client.list_chapters = AsyncMock(return_value=chapters)
    client.get_chapter_text = AsyncMock(return_value=text)
    return client


# ── process_job: chapters scope ──────────────────────────────────────


@pytest.mark.asyncio
async def test_process_job_chapters_success():
    """Happy path: one chapter extracted, job completed."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    # Should have called extract_item once
    kc.extract_item.assert_called_once()
    # Should have advanced cursor + recorded spending + completed job
    assert pool.execute.call_count >= 3


@pytest.mark.asyncio
async def test_process_job_chapters_records_spending_on_success():
    """D-K16.11-01: after each successful chapter, the worker bumps
    knowledge_projects.current_month_spent_usd + actual_cost_usd so
    the CostSummary card sees real production figures."""
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(3)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client(chapters=chapters)

    await process_job(pool, kc, bc, job)

    # Collect the SQL text of every execute call; count how many
    # target knowledge_projects with the monthly-spend + all-time
    # counter bumps. One per successful chapter.
    spending_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE knowledge_projects" in c.args[0]
        and "current_month_spent_usd" in c.args[0]
        and "actual_cost_usd" in c.args[0]
    ]
    assert len(spending_calls) == 3


@pytest.mark.asyncio
async def test_process_job_appends_log_on_chapter_success():
    """K19b.8: each successful chapter writes a job_logs row with
    level=info and an event=chapter_processed context tag."""
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(2)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client(chapters=chapters)

    await process_job(pool, kc, bc, job)

    log_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
    ]
    # 2 chapters → 2 info logs for success; no other kinds.
    assert len(log_calls) == 2
    for call in log_calls:
        # args: (sql, job_id, user_id, level, message, context_json)
        assert call.args[3] == "info"
        assert "processed" in call.args[4]


@pytest.mark.asyncio
async def test_process_job_appends_error_log_on_fatal_failure():
    """K19b.8: non-retryable extraction error writes an error-level log
    with event=failed before the job transitions to failed."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client(result=_error_result(retryable=False))
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    error_logs = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
        and c.args[3] == "error"
    ]
    assert len(error_logs) == 1


@pytest.mark.asyncio
async def test_process_job_chat_records_spending_on_success():
    """D-K16.11-01: chat-scope success path also records spending.
    Mirrors the chapters test — same two-counter update per item."""
    job = _job(scope="chat")
    pool = _mock_pool()
    # Seed 2 pending chat turns so the chat branch iterates twice.
    pool.fetch = AsyncMock(return_value=[
        {"pending_id": uuid4(), "aggregate_id": uuid4()},
        {"pending_id": uuid4(), "aggregate_id": uuid4()},
    ])
    kc = _mock_knowledge_client()
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    spending_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE knowledge_projects" in c.args[0]
        and "current_month_spent_usd" in c.args[0]
    ]
    assert len(spending_calls) == 2


@pytest.mark.asyncio
async def test_process_job_multiple_chapters():
    """Multiple chapters processed in order."""
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(3)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client(chapters=chapters)

    await process_job(pool, kc, bc, job)

    assert kc.extract_item.call_count == 3


@pytest.mark.asyncio
async def test_process_job_pause_detected():
    """Job paused mid-run — runner stops processing."""
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(5)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    # fetchval: book_id, then running (1st chapter), then paused (2nd)
    pool.fetchval = AsyncMock(side_effect=[_TEST_BOOK_ID, "running", "paused"])
    kc = _mock_knowledge_client()
    bc = _mock_book_client(chapters=chapters)

    await process_job(pool, kc, bc, job)

    # Only 1 chapter processed before pause detected
    assert kc.extract_item.call_count == 1


@pytest.mark.asyncio
async def test_process_job_cancel_detected():
    """Job cancelled — runner stops immediately."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    # fetchval: book_id, then cancelled
    pool.fetchval = AsyncMock(side_effect=[_TEST_BOOK_ID, "cancelled"])
    kc = _mock_knowledge_client()
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    kc.extract_item.assert_not_called()


@pytest.mark.asyncio
async def test_process_job_budget_auto_pause():
    """try_spend returns auto_paused — runner stops."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"cost_spent_usd": Decimal("10"), "status": "paused"},
    )
    kc = _mock_knowledge_client()
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    kc.extract_item.assert_not_called()


@pytest.mark.asyncio
async def test_process_job_permanent_error_fails_job():
    """Permanent extraction error → job transitions to failed."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client(result=_error_result(retryable=False))
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    # Should have called execute for fail_job + update_project
    fail_calls = [
        c for c in pool.execute.call_args_list
        if "failed" in str(c)
    ]
    assert len(fail_calls) >= 1


@pytest.mark.asyncio
async def test_process_job_retryable_error_stops_run_for_retry():
    """Retryable error — runner stops this run (retry on next poll).
    Cursor is updated with retry count but not advanced past the item."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client(result=_error_result(retryable=True))
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    # Only one extraction attempt this run
    kc.extract_item.assert_called_once()
    # Cursor should be updated with retry count (items_delta=0)
    cursor_calls = [
        c for c in pool.execute.call_args_list
        if "items_processed" in str(c)
    ]
    assert len(cursor_calls) >= 1


@pytest.mark.asyncio
async def test_process_job_no_book_id():
    """Project with no book_id — chapters scope returns empty."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client()
    bc.list_chapters = AsyncMock(return_value=None)

    await process_job(pool, kc, bc, job)

    kc.extract_item.assert_not_called()


# ── poll_and_run ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_no_jobs_returns_zero():
    pool = _mock_pool()
    pool.fetch = AsyncMock(return_value=[])
    kc = _mock_knowledge_client()
    bc = _mock_book_client()

    count = await poll_and_run(pool, kc, bc)
    assert count == 0


@pytest.mark.asyncio
async def test_process_job_chapter_text_unavailable_skips():
    """Chapter with no text — skipped, cursor advanced."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client(text=None)

    await process_job(pool, kc, bc, job)

    kc.extract_item.assert_not_called()  # skipped


# ── K16.7: backfill — items_total population ─────────────────────────


@pytest.mark.asyncio
async def test_backfill_sets_items_total_when_none():
    """When items_total is None, runner counts items and sets it."""
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(5)
    ]
    job = _job(scope="chapters", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client(chapters=chapters)

    await process_job(pool, kc, bc, job)

    # items_total should be set via _set_items_total (execute call)
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if "items_total" in str(c)
    ]
    assert len(set_total_calls) >= 1
    # All 5 chapters should be extracted
    assert kc.extract_item.call_count == 5


@pytest.mark.asyncio
async def test_backfill_skips_items_total_when_already_set():
    """When items_total is already set, runner does not overwrite it."""
    job = _job(scope="chapters", items_total=10)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client()

    await process_job(pool, kc, bc, job)

    # _set_items_total should NOT be called
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if "items_total = $3" in str(c)
    ]
    assert len(set_total_calls) == 0


@pytest.mark.asyncio
async def test_backfill_scope_all_counts_chapters_and_chat():
    """scope=all counts both chapters and pending chat turns."""
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(3)
    ]
    pending_rows = [
        {"pending_id": uuid4(), "event_id": uuid4(), "event_type": "chat.turn",
         "aggregate_type": "session", "aggregate_id": uuid4()}
        for _ in range(2)
    ]
    job = _job(scope="all", items_total=None)
    pool = _mock_pool()
    # fetch is called for _enumerate_pending_chat_turns (twice: once for
    # counting in backfill, once for actual processing)
    pool.fetch = AsyncMock(return_value=pending_rows)
    kc = _mock_knowledge_client()
    bc = _mock_book_client(chapters=chapters)

    await process_job(pool, kc, bc, job)

    # 3 chapters + 2 chat turns = 5 extract calls
    assert kc.extract_item.call_count == 5
