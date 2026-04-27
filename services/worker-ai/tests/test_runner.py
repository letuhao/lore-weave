"""K16.6b — Unit tests for the extraction job runner.

Tests the core process_job logic with mocked DB pool and HTTP clients.

Phase 4b-gamma: extract_item HTTP call was replaced by an in-process
LLM run + thin /persist-pass2 POST. Tests now patch
`app.runner._extract_and_persist` (the runner-helper that wraps both
steps) instead of mocking `KnowledgeClient.extract_item` directly.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.clients import (
    BookClient, ChapterInfo, ExtractionResult,
    GlossaryClient, GlossaryEntity, GlossaryPage, GlossarySyncResult,
    KnowledgeClient,
)
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


def _mock_knowledge_client():
    """Mock KnowledgeClient. Phase 4b-gamma: extract_item is gone; the
    runner's _extract_and_persist helper internally calls
    knowledge_client.persist_pass2. Tests patch _extract_and_persist at
    the runner level so this client mock is passive (only used by the
    glossary_sync path which still goes through glossary_sync_entity).
    """
    client = AsyncMock(spec=KnowledgeClient)
    client.persist_pass2 = AsyncMock(return_value=_ok_result())
    return client


def _mock_llm_client():
    """Phase 4b-gamma: LLMClient is required by process_job/poll_and_run
    but is never invoked in tests because _extract_and_persist is
    patched. A MagicMock placeholder is enough."""
    return MagicMock()


def _mock_book_client(chapters=None, text="Chapter text here."):
    client = AsyncMock(spec=BookClient)
    if chapters is None:
        chapters = [ChapterInfo(chapter_id="ch-1", title="Ch 1", sort_order=1)]
    client.list_chapters = AsyncMock(return_value=chapters)
    client.get_chapter_text = AsyncMock(return_value=text)
    return client


def _mock_glossary_client(pages=None):
    """C12c-a — mock GlossaryClient. Default returns a single empty
    page. `pages` is a list of (items, next_cursor) tuples returned
    in order via side_effect.
    """
    client = AsyncMock(spec=GlossaryClient)
    if pages is None:
        client.list_book_entities = AsyncMock(
            return_value=GlossaryPage(items=(), next_cursor=None),
        )
    else:
        client.list_book_entities = AsyncMock(
            side_effect=[
                GlossaryPage(items=tuple(items), next_cursor=nc)
                for items, nc in pages
            ],
        )
    return client


def _glossary_entity(entity_id: str, name: str = "Alice") -> GlossaryEntity:
    return GlossaryEntity(
        entity_id=entity_id,
        name=name,
        kind_code="character",
        aliases=(),
        short_description=None,
    )


def _glossary_sync_ok(entity_id: str) -> GlossarySyncResult:
    return GlossarySyncResult(
        glossary_entity_id=entity_id,
        action="created",
        canonical_name="alice",
    )


# ── process_job: chapters scope ──────────────────────────────────────


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chapters_success(mock_extract_persist):
    """Happy path: one chapter extracted, job completed."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # Should have called _extract_and_persist once
    mock_extract_persist.assert_called_once()
    # Should have advanced cursor + recorded spending + completed job
    assert pool.execute.call_count >= 3


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chapters_records_spending_on_success(mock_extract_persist):
    """D-K16.11-01: after each successful chapter, the worker bumps
    knowledge_projects.current_month_spent_usd + actual_cost_usd so
    the CostSummary card sees real production figures."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(3)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

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
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_appends_log_on_chapter_success(mock_extract_persist):
    """K19b.8: each successful chapter writes a job_logs row with
    level=info and an event=chapter_processed context tag."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(2)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

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
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_appends_error_log_on_fatal_failure(mock_extract_persist):
    """K19b.8: non-retryable extraction error writes an error-level log
    with event=failed before the job transitions to failed."""
    mock_extract_persist.return_value = _error_result(retryable=False)
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    error_logs = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
        and c.args[3] == "error"
    ]
    assert len(error_logs) == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chat_records_spending_on_success(mock_extract_persist):
    """D-K16.11-01: chat-scope success path also records spending.
    Mirrors the chapters test — same two-counter update per item."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chat")
    pool = _mock_pool()
    # Seed 2 pending chat turns so the chat branch iterates twice.
    pool.fetch = AsyncMock(return_value=[
        {"pending_id": uuid4(), "aggregate_id": uuid4()},
        {"pending_id": uuid4(), "aggregate_id": uuid4()},
    ])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    spending_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE knowledge_projects" in c.args[0]
        and "current_month_spent_usd" in c.args[0]
    ]
    assert len(spending_calls) == 2


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_multiple_chapters(mock_extract_persist):
    """Multiple chapters processed in order."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(3)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    assert mock_extract_persist.call_count == 3


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_pause_detected(mock_extract_persist):
    """Job paused mid-run — runner stops processing."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(5)
    ]
    job = _job(scope="chapters")
    pool = _mock_pool()
    # fetchval: book_id, then running (1st chapter), then paused (2nd)
    pool.fetchval = AsyncMock(side_effect=[_TEST_BOOK_ID, "running", "paused"])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # Only 1 chapter processed before pause detected
    assert mock_extract_persist.call_count == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_cancel_detected(mock_extract_persist):
    """Job cancelled — runner stops immediately."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    # fetchval: book_id, then cancelled
    pool.fetchval = AsyncMock(side_effect=[_TEST_BOOK_ID, "cancelled"])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    mock_extract_persist.assert_not_called()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_budget_auto_pause(mock_extract_persist):
    """try_spend returns auto_paused — runner stops."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    pool.fetchrow = AsyncMock(
        return_value={"cost_spent_usd": Decimal("10"), "status": "paused"},
    )
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    mock_extract_persist.assert_not_called()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_permanent_error_fails_job(mock_extract_persist):
    """Permanent extraction error → job transitions to failed."""
    mock_extract_persist.return_value = _error_result(retryable=False)
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # Should have called execute for fail_job + update_project
    fail_calls = [
        c for c in pool.execute.call_args_list
        if "failed" in str(c)
    ]
    assert len(fail_calls) >= 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_retryable_error_stops_run_for_retry(mock_extract_persist):
    """Retryable error — runner stops this run (retry on next poll).
    Cursor is updated with retry count but not advanced past the item."""
    mock_extract_persist.return_value = _error_result(retryable=True)
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # Only one extraction attempt this run
    mock_extract_persist.assert_called_once()
    # Cursor should be updated with retry count (items_delta=0)
    cursor_calls = [
        c for c in pool.execute.call_args_list
        if "items_processed" in str(c)
    ]
    assert len(cursor_calls) >= 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_no_book_id(mock_extract_persist):
    """Project with no book_id — chapters scope returns empty."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()
    bc.list_chapters = AsyncMock(return_value=None)

    await process_job(pool, kc, llm, bc, gc, job)

    mock_extract_persist.assert_not_called()


# ── poll_and_run ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_no_jobs_returns_zero():
    pool = _mock_pool()
    pool.fetch = AsyncMock(return_value=[])
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    count = await poll_and_run(pool, kc, llm, bc, gc)
    assert count == 0


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_chapter_text_unavailable_skips(mock_extract_persist):
    """Chapter with no text — skipped, cursor advanced."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(text=None)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    mock_extract_persist.assert_not_called()  # skipped


# ── K16.7: backfill — items_total population ─────────────────────────


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_backfill_sets_items_total_when_none(mock_extract_persist):
    """When items_total is None, runner counts items and sets it."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [
        ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i)
        for i in range(5)
    ]
    job = _job(scope="chapters", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # items_total should be set via _set_items_total (execute call)
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if "items_total" in str(c)
    ]
    assert len(set_total_calls) >= 1
    # All 5 chapters should be extracted
    assert mock_extract_persist.call_count == 5


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_backfill_skips_items_total_when_already_set(mock_extract_persist):
    """When items_total is already set, runner does not overwrite it."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="chapters", items_total=10)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # _set_items_total should NOT be called
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if "items_total = $3" in str(c)
    ]
    assert len(set_total_calls) == 0


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_backfill_scope_all_counts_chapters_and_chat(mock_extract_persist):
    """scope=all counts both chapters and pending chat turns."""
    mock_extract_persist.return_value = _ok_result()
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
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client()

    await process_job(pool, kc, llm, bc, gc, job)

    # 3 chapters + 2 chat turns = 5 extract calls
    assert mock_extract_persist.call_count == 5


# ── process_job: glossary_sync scope (C12c-a) ────────────────────────


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_sync_success(mock_extract_persist):
    """C12c-a happy path: scope='glossary_sync' iterates glossary
    entities and calls knowledge_client.glossary_sync_entity per
    entity. No LLM extract calls."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="glossary_sync")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    # Mirror the knowledge-service result wire for glossary-sync.
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client(pages=[
        (
            [_glossary_entity("e1", "Alice"), _glossary_entity("e2", "Bob")],
            None,
        ),
    ])

    await process_job(pool, kc, llm, bc, gc, job)

    # No LLM extract — only the two glossary sync calls.
    mock_extract_persist.assert_not_called()
    assert kc.glossary_sync_entity.call_count == 2

    # Glossary endpoint called once (single page).
    gc.list_book_entities.assert_called_once()


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_all_scope_includes_glossary(mock_extract_persist):
    """C12c-a behaviour change: scope='all' now iterates glossary
    after chapters+chat. The TODO at line 621 is removed; a user
    who runs `all` gets chapters + chat + glossary end-to-end."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [ChapterInfo(chapter_id="ch-1", title="Ch 1", sort_order=1)]
    job = _job(scope="all")
    pool = _mock_pool()
    # Return one pending chat turn to exercise the chat branch too.
    pending_rows = [{
        "pending_id": uuid4(),
        "event_id": uuid4(),
        "event_type": "chat.turn.created",
        "aggregate_type": "chat_turn",
        "aggregate_id": uuid4(),
    }]
    pool.fetch = AsyncMock(return_value=pending_rows)
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client(pages=[
        ([_glossary_entity("e1", "Arthur")], None),
    ])

    await process_job(pool, kc, llm, bc, gc, job)

    # chapters + chat → 2 _extract_and_persist; glossary → 1 glossary_sync_entity.
    assert mock_extract_persist.call_count == 2
    assert kc.glossary_sync_entity.call_count == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_items_total_includes_glossary(mock_extract_persist):
    """C12c-a: when items_total is None (backfill), the pre-count
    covers chapters + chat + glossary pages."""
    mock_extract_persist.return_value = _ok_result()
    chapters = [ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i) for i in range(2)]
    job = _job(scope="all", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client(pages=[
        (
            [_glossary_entity(f"e{i}", f"Entity{i}") for i in range(3)],
            None,
        ),
    ])

    await process_job(pool, kc, llm, bc, gc, job)

    # _set_items_total sends an UPDATE with SET items_total = $X.
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "items_total" in c.args[0]
    ]
    assert len(set_total_calls) == 1
    # Total = 2 chapters + 0 pending + 3 glossary = 5.
    # The bound value is at position [1] after the SQL string; skip
    # past user_id/job_id to reach the total arg.
    call = set_total_calls[0]
    assert 5 in call.args, f"expected total=5 in args, got {call.args}"


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_sync_empty_book_no_op(mock_extract_persist):
    """C12c-a: glossary-service returning an empty first page ends
    the branch immediately. Job still completes (no items to sync
    is a valid terminal state)."""
    mock_extract_persist.return_value = _ok_result()
    job = _job(scope="glossary_sync")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock()
    llm = _mock_llm_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()  # default: empty page

    await process_job(pool, kc, llm, bc, gc, job)

    kc.glossary_sync_entity.assert_not_called()
    mock_extract_persist.assert_not_called()
    # Job completion sets status=complete.
    complete_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "status = 'complete'" in c.args[0].replace('"', "'")
    ]
    assert len(complete_calls) == 1


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_partial_enumeration_skips_items_total(mock_extract_persist):
    """/review-impl LOW#5 — when glossary-service returns None on a
    later page, the enumerator returns the partial list + complete=False.
    The runner then MUST skip _set_items_total (or the bar would
    freeze at the wrong total). Any entities already fetched from
    earlier pages are still processed."""
    mock_extract_persist.return_value = _ok_result()
    chapters: list[ChapterInfo] = []
    job = _job(scope="glossary_sync", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=chapters)
    # Page 1 returns 2 entities with next_cursor="p2"; page 2 returns
    # None (glossary-service flake). Enumerator keeps page 1's entities
    # and reports complete=False.
    gc = AsyncMock(spec=GlossaryClient)
    gc.list_book_entities = AsyncMock(
        side_effect=[
            GlossaryPage(
                items=(_glossary_entity("e1", "Alpha"), _glossary_entity("e2", "Bravo")),
                next_cursor="p2",
            ),
            None,  # mid-enumeration failure
        ],
    )

    await process_job(pool, kc, llm, bc, gc, job)

    # 2 entities synced (page 1 survived).
    assert kc.glossary_sync_entity.call_count == 2
    # items_total SHOULD NOT be set — complete=False gates it.
    set_total_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "items_total" in c.args[0]
    ]
    assert len(set_total_calls) == 0, f"expected no items_total update on partial enum, got {len(set_total_calls)}"


@pytest.mark.asyncio
@patch("app.runner._extract_and_persist", new_callable=AsyncMock)
async def test_process_job_glossary_retry_exhaustion_skips_entity(mock_extract_persist):
    """/review-impl MED#3 — bounded retry. Retryable error for the
    same entity 3 times (persisted via cursor.retry_glossary_<id>)
    causes the entity to be SKIPPED on the 3rd attempt + cursor
    advances past it. Prevents infinite retry loops when
    glossary-service flaps on a specific entity."""
    mock_extract_persist.return_value = _ok_result()
    entity_id = "e1"
    # Simulate third attempt — cursor already has retry count 2.
    job = _job(
        scope="glossary_sync",
        current_cursor={f"retry_glossary_{entity_id}": 2, "scope": "glossary_sync"},
    )
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        return_value=GlossarySyncResult(
            glossary_entity_id=entity_id,
            action="",
            canonical_name="",
            retryable=True,
            error="glossary-service 502",
        ),
    )
    llm = _mock_llm_client()
    bc = _mock_book_client(chapters=[])
    gc = _mock_glossary_client(pages=[
        ([_glossary_entity(entity_id, "Flaky")], None),
    ])

    await process_job(pool, kc, llm, bc, gc, job)

    # One attempt this run — reaches retry count 3 == _MAX_RETRIES_PER_ITEM
    # → skipped. Error log with retry_exhausted event emitted.
    retry_exhausted_logs = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "INSERT INTO job_logs" in c.args[0]
        and c.args[3] == "error"
        and "retry_exhausted" in str(c.args[5])
    ]
    assert len(retry_exhausted_logs) == 1, \
        f"expected 1 retry_exhausted log, got {len(retry_exhausted_logs)}"


# ── Phase 4b-γ /review-impl MED#1 — _extract_and_persist helper ────


def _entity_candidate(name: str = "Kai", kind: str = "person") -> "LLMEntityCandidate":
    """Build a real library candidate for helper tests so ExtractionResult
    flow + persist_pass2 kwargs can be asserted concretely."""
    from loreweave_extraction.extractors.entity import LLMEntityCandidate
    return LLMEntityCandidate(
        name=name, kind=kind, aliases=[],
        confidence=0.9,
        canonical_name=name.lower(),
        canonical_id="a" * 32,
    )


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_happy_path_calls_persist_with_candidates(
    mock_extract,
):
    """Phase 4b-γ /review-impl MED#1 — verify _extract_and_persist
    threads candidates from extract_pass2 into knowledge_client.persist_pass2
    with the right kwargs. Locks the bridge contract that all 23
    runner tests bypass via @patch."""
    from loreweave_extraction.pass2 import Pass2Candidates
    from app.runner import _extract_and_persist

    candidates = Pass2Candidates(
        entities=[_entity_candidate("Kai")],
        relations=[],
        events=[],
        facts=[],
    )
    mock_extract.return_value = candidates
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock(return_value=_ok_result())
    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()

    result = await _extract_and_persist(
        knowledge_client=kc,
        llm_client=_mock_llm_client(),
        user_id=user_id,
        project_id=project_id,
        source_type="chapter",
        source_id="ch-1",
        job_id=job_id,
        model_ref="qwen-test",
        text="Some chapter text.",
    )

    assert result.error is None
    assert result.entities_merged == 2  # from _ok_result
    kc.persist_pass2.assert_awaited_once()
    persist_kwargs = kc.persist_pass2.call_args.kwargs
    assert persist_kwargs["user_id"] == user_id
    assert persist_kwargs["project_id"] == project_id
    assert persist_kwargs["source_type"] == "chapter"
    assert persist_kwargs["source_id"] == "ch-1"
    assert persist_kwargs["job_id"] == job_id
    assert persist_kwargs["extraction_model"] == "qwen-test"
    assert len(persist_kwargs["entities"]) == 1
    assert persist_kwargs["entities"][0].name == "Kai"
    # extract_pass2 received user_id/project_id as STRINGS (library contract)
    extract_kwargs = mock_extract.call_args.kwargs
    assert extract_kwargs["user_id"] == str(user_id)
    assert extract_kwargs["project_id"] == str(project_id)
    assert extract_kwargs["text"] == "Some chapter text."


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_provider_exhausted_is_retryable(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — ExtractionError(stage='provider_exhausted')
    surfaces as ExtractionResult(retryable=True) so the runner retries
    the item per its _MAX_RETRIES_PER_ITEM logic. Persist endpoint
    is NOT called on this path (no candidates to write)."""
    from loreweave_extraction.errors import ExtractionError
    from app.runner import _extract_and_persist

    mock_extract.side_effect = ExtractionError(
        "transient retry exhausted",
        stage="provider_exhausted",
    )
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock()

    result = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen-test", text="text",
    )

    assert result.retryable is True
    assert result.error is not None
    assert "provider_exhausted" in result.error
    kc.persist_pass2.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_provider_stage_is_not_retryable(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — non-transient provider failure
    (stage='provider') is NOT retryable; runner will fail the job."""
    from loreweave_extraction.errors import ExtractionError
    from app.runner import _extract_and_persist

    mock_extract.side_effect = ExtractionError(
        "invalid api key", stage="provider",
    )
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock()

    result = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen-test", text="text",
    )

    assert result.retryable is False
    kc.persist_pass2.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_cancelled_stage_is_not_retryable(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — operator-initiated LLM cancel
    (stage='cancelled') is NOT retryable. Runner treats this as a
    non-retryable error → fails the whole extraction job. Same
    behavior as the legacy extract-item path."""
    from loreweave_extraction.errors import ExtractionError
    from app.runner import _extract_and_persist

    mock_extract.side_effect = ExtractionError(
        "operator cancelled job", stage="cancelled",
    )
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock()

    result = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        model_ref="qwen-test", text="text",
    )

    assert result.retryable is False
    assert "cancelled" in result.error
    kc.persist_pass2.assert_not_awaited()


@pytest.mark.asyncio
@patch("app.runner.extract_pass2", new_callable=AsyncMock)
async def test_extract_and_persist_empty_text_still_persists(mock_extract):
    """Phase 4b-γ /review-impl MED#1 — empty text → library
    short-circuits to empty Pass2Candidates → persist_pass2 STILL
    called with empty lists (idempotent source-row upsert).
    Matches the legacy extract-item path's behavior for chat_turn
    placeholders that don't fetch text from chat-service yet."""
    from loreweave_extraction.pass2 import Pass2Candidates
    from app.runner import _extract_and_persist

    mock_extract.return_value = Pass2Candidates()  # all 4 lists empty
    kc = AsyncMock(spec=KnowledgeClient)
    kc.persist_pass2 = AsyncMock(return_value=_ok_result(source_id="turn-1"))

    result = await _extract_and_persist(
        knowledge_client=kc, llm_client=_mock_llm_client(),
        user_id=uuid4(), project_id=uuid4(),
        source_type="chat_turn", source_id="turn-1", job_id=uuid4(),
        model_ref="qwen-test", text="",
    )

    assert result.error is None
    kc.persist_pass2.assert_awaited_once()
    persist_kwargs = kc.persist_pass2.call_args.kwargs
    assert persist_kwargs["entities"] == []
    assert persist_kwargs["relations"] == []
    assert persist_kwargs["events"] == []
    assert persist_kwargs["facts"] == []


# ── Phase 4b-γ /review-impl MED#2 — KnowledgeClient.persist_pass2 wire ──


@pytest.mark.asyncio
async def test_knowledge_client_persist_pass2_posts_correct_body_shape():
    """Phase 4b-γ /review-impl MED#2 — verify the wire format sent to
    /internal/extraction/persist-pass2 matches server-side
    PersistPass2Request schema. Catches a future library field rename
    or JSON-key change that would silently 422 in production."""
    import httpx
    from loreweave_extraction.extractors.entity import LLMEntityCandidate

    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["method"] = request.method
        captured["headers"] = dict(request.headers)
        captured["body"] = request.read().decode()
        return httpx.Response(200, json={
            "source_id": "ch-1",
            "entities_merged": 1,
            "relations_created": 0,
            "events_merged": 0,
            "facts_merged": 0,
            "evidence_edges": 0,
            "duration_seconds": 0.5,
        })

    transport = httpx.MockTransport(handler)
    client = KnowledgeClient(
        base_url="http://test-host:8092",
        internal_token="dev_token",
        timeout_s=30.0,
    )
    # Replace the underlying httpx client with a MockTransport-backed one
    await client._http.aclose()
    client._http = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0),
        headers={"X-Internal-Token": "dev_token"},
    )

    user_id = uuid4()
    project_id = uuid4()
    job_id = uuid4()
    entity = LLMEntityCandidate(
        name="Kai", kind="person", aliases=["K"],
        confidence=0.9, canonical_name="kai",
        canonical_id="a" * 32,
    )

    result = await client.persist_pass2(
        user_id=user_id,
        project_id=project_id,
        source_type="chapter",
        source_id="ch-1",
        job_id=job_id,
        extraction_model="qwen-test",
        entities=[entity],
        relations=[],
        events=[],
        facts=[],
    )

    await client.aclose()

    # Wire-format assertions (the meat of MED#2)
    import json as _json
    assert captured["url"].endswith("/internal/extraction/persist-pass2")
    assert captured["method"] == "POST"
    assert captured["headers"].get("x-internal-token") == "dev_token"
    body = _json.loads(captured["body"])
    assert body["user_id"] == str(user_id)
    assert body["project_id"] == str(project_id)
    assert body["source_type"] == "chapter"
    assert body["source_id"] == "ch-1"
    assert body["job_id"] == str(job_id)
    assert body["extraction_model"] == "qwen-test"
    assert isinstance(body["entities"], list) and len(body["entities"]) == 1
    assert body["entities"][0]["name"] == "Kai"
    assert body["entities"][0]["kind"] == "person"
    assert body["entities"][0]["canonical_id"] == "a" * 32
    assert body["entities"][0]["confidence"] == 0.9
    assert body["entities"][0]["aliases"] == ["K"]
    assert body["relations"] == []
    assert body["events"] == []
    assert body["facts"] == []

    # Response was parsed correctly
    assert result.entities_merged == 1
    assert result.error is None


@pytest.mark.asyncio
async def test_knowledge_client_persist_pass2_502_returns_retryable_error():
    """Phase 4b-γ /review-impl MED#2 — 5xx from server surfaces as
    ExtractionResult(retryable=True) so the runner's retry logic
    fires. Locks the contract for transient knowledge-service
    failures (Neo4j hiccup, deploy mid-extraction)."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, text="upstream gone")

    transport = httpx.MockTransport(handler)
    client = KnowledgeClient(
        base_url="http://test-host:8092",
        internal_token="dev_token",
        timeout_s=30.0,
    )
    await client._http.aclose()
    client._http = httpx.AsyncClient(
        transport=transport,
        timeout=httpx.Timeout(30.0),
        headers={"X-Internal-Token": "dev_token"},
    )

    result = await client.persist_pass2(
        user_id=uuid4(), project_id=uuid4(),
        source_type="chapter", source_id="ch-1", job_id=uuid4(),
        extraction_model="qwen-test",
        entities=[], relations=[], events=[], facts=[],
    )

    await client.aclose()

    assert result.retryable is True
    assert result.error is not None
    assert "502" in result.error
