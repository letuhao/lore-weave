"""K16.6b — Unit tests for the extraction job runner.

Tests the core process_job logic with mocked DB pool and HTTP clients.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
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
async def test_process_job_chapters_success():
    """Happy path: one chapter extracted, job completed."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

    kc.extract_item.assert_not_called()


@pytest.mark.asyncio
async def test_process_job_permanent_error_fails_job():
    """Permanent extraction error → job transitions to failed."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client(result=_error_result(retryable=False))
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()
    bc.list_chapters = AsyncMock(return_value=None)

    await process_job(pool, kc, bc, gc, job)

    kc.extract_item.assert_not_called()


# ── poll_and_run ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_poll_no_jobs_returns_zero():
    pool = _mock_pool()
    pool.fetch = AsyncMock(return_value=[])
    kc = _mock_knowledge_client()
    bc = _mock_book_client()
    gc = _mock_glossary_client()

    count = await poll_and_run(pool, kc, bc, gc)
    assert count == 0


@pytest.mark.asyncio
async def test_process_job_chapter_text_unavailable_skips():
    """Chapter with no text — skipped, cursor advanced."""
    job = _job(scope="chapters")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    bc = _mock_book_client(text=None)
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

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
    gc = _mock_glossary_client()

    await process_job(pool, kc, bc, gc, job)

    # 3 chapters + 2 chat turns = 5 extract calls
    assert kc.extract_item.call_count == 5


# ── process_job: glossary_sync scope (C12c-a) ────────────────────────


@pytest.mark.asyncio
async def test_process_job_glossary_sync_success():
    """C12c-a happy path: scope='glossary_sync' iterates glossary
    entities and calls knowledge_client.glossary_sync_entity per
    entity. No LLM extract_item calls."""
    job = _job(scope="glossary_sync")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    # Mirror the knowledge-service result wire for glossary-sync.
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    bc = _mock_book_client()
    gc = _mock_glossary_client(pages=[
        (
            [_glossary_entity("e1", "Alice"), _glossary_entity("e2", "Bob")],
            None,
        ),
    ])

    await process_job(pool, kc, bc, gc, job)

    # No LLM extract_item — only the two glossary sync calls.
    kc.extract_item.assert_not_called()
    assert kc.glossary_sync_entity.call_count == 2

    # Glossary endpoint called once (single page).
    gc.list_book_entities.assert_called_once()


@pytest.mark.asyncio
async def test_process_job_all_scope_includes_glossary():
    """C12c-a behaviour change: scope='all' now iterates glossary
    after chapters+chat. The TODO at line 621 is removed; a user
    who runs `all` gets chapters + chat + glossary end-to-end."""
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
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client(pages=[
        ([_glossary_entity("e1", "Arthur")], None),
    ])

    await process_job(pool, kc, bc, gc, job)

    # chapters + chat → 2 extract_item; glossary → 1 glossary_sync_entity.
    assert kc.extract_item.call_count == 2
    assert kc.glossary_sync_entity.call_count == 1


@pytest.mark.asyncio
async def test_process_job_items_total_includes_glossary():
    """C12c-a: when items_total is None (backfill), the pre-count
    covers chapters + chat + glossary pages."""
    chapters = [ChapterInfo(chapter_id=f"ch-{i}", title=f"Ch {i}", sort_order=i) for i in range(2)]
    job = _job(scope="all", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
    bc = _mock_book_client(chapters=chapters)
    gc = _mock_glossary_client(pages=[
        (
            [_glossary_entity(f"e{i}", f"Entity{i}") for i in range(3)],
            None,
        ),
    ])

    await process_job(pool, kc, bc, gc, job)

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
async def test_process_job_glossary_sync_empty_book_no_op():
    """C12c-a: glossary-service returning an empty first page ends
    the branch immediately. Job still completes (no items to sync
    is a valid terminal state)."""
    job = _job(scope="glossary_sync")
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock()
    bc = _mock_book_client()
    gc = _mock_glossary_client()  # default: empty page

    await process_job(pool, kc, bc, gc, job)

    kc.glossary_sync_entity.assert_not_called()
    kc.extract_item.assert_not_called()
    # Job completion sets status=complete.
    complete_calls = [
        c for c in pool.execute.call_args_list
        if isinstance(c.args[0], str)
        and "UPDATE extraction_jobs" in c.args[0]
        and "status = 'complete'" in c.args[0].replace('"', "'")
    ]
    assert len(complete_calls) == 1


@pytest.mark.asyncio
async def test_process_job_glossary_partial_enumeration_skips_items_total():
    """/review-impl LOW#5 — when glossary-service returns None on a
    later page, the enumerator returns the partial list + complete=False.
    The runner then MUST skip _set_items_total (or the bar would
    freeze at the wrong total). Any entities already fetched from
    earlier pages are still processed."""
    chapters: list[ChapterInfo] = []
    job = _job(scope="glossary_sync", items_total=None)
    pool = _mock_pool()
    kc = _mock_knowledge_client()
    kc.glossary_sync_entity = AsyncMock(
        side_effect=lambda **kwargs: _glossary_sync_ok(kwargs["glossary_entity_id"]),
    )
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

    await process_job(pool, kc, bc, gc, job)

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
async def test_process_job_glossary_retry_exhaustion_skips_entity():
    """/review-impl MED#3 — bounded retry. Retryable error for the
    same entity 3 times (persisted via cursor.retry_glossary_<id>)
    causes the entity to be SKIPPED on the 3rd attempt + cursor
    advances past it. Prevents infinite retry loops when
    glossary-service flaps on a specific entity."""
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
    bc = _mock_book_client(chapters=[])
    gc = _mock_glossary_client(pages=[
        ([_glossary_entity(entity_id, "Flaky")], None),
    ])

    await process_job(pool, kc, bc, gc, job)

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
