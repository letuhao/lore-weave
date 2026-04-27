"""
Unit tests for chapter_worker — Plan §4.2.

Architecture note (post-session_translator refactor):
  chapter_worker is responsible for:
    1. Cancellation check (before any work)
    2. Fetching chapter body from book-service (httpx GET, finite timeout)
    3. Delegating AI translation to translate_chapter() in session_translator
    4. Writing translated_body to DB
    5. Emitting job.chapter_done + job.status_changed events

  AI timeout / JWT / billing / model errors are now tested in
  test_session_translator.py.

Covers:
- Happy path: chapter processed, DB written, events emitted
- Book-service client uses finite read timeout (not unlimited)
- Job cancellation check (skip processing if cancelled)
- Book-service errors: 404 → PermanentError, network → TransientError
- translate_chapter errors propagate correctly
- _fail_chapter_idempotent: no double counter increment
- _check_job_completion: atomic finalization, only winner emits event
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID, uuid4

import httpx

from tests.conftest import FakeRecord


# ── Helpers ───────────────────────────────────────────────────────────────────

class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        pass


def _make_pool(job_status="running", finalization_row=None):
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetchval = AsyncMock(return_value=job_status)   # cancellation check
    db.fetchrow = AsyncMock(return_value=finalization_row)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    # session_translator calls pool.fetchrow / pool.execute directly (no acquire)
    pool.fetchrow = AsyncMock(return_value={"id": uuid4()})
    pool.execute  = AsyncMock()
    return pool, db


def _chapter_msg(**overrides):
    base = {
        "job_id":              str(uuid4()),
        "chapter_id":          str(uuid4()),
        "chapter_index":       0,
        "total_chapters":      1,
        "book_id":             str(uuid4()),
        "user_id":             "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        "model_source":        "platform_model",
        "model_ref":           str(uuid4()),
        "system_prompt":       "Translate faithfully.",
        "user_prompt_tpl":     "Translate from {source_language} to {target_language}:\n{chapter_text}",
        "target_language":     "vi",
        "chunk_size_tokens":   2000,
        "invoke_timeout_secs": 300,
        "compact_model_source": None,
        "compact_model_ref":   None,
    }
    return {**base, **overrides}


def _book_resp(body="In the beginning..."):
    r = MagicMock(spec=httpx.Response)
    r.status_code = 200
    r.is_success = True
    r.raise_for_status = MagicMock()
    r.json.return_value = {"original_language": "en", "body": {}, "text_content": body}
    return r


def _patched_book_http(book_resp=None):
    """Returns a mock HTTP client for the book-service call only."""
    mock_http = MagicMock()
    mock_http.get = AsyncMock(return_value=book_resp or _book_resp())
    return mock_http


# ── Happy path ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chapter_worker_writes_translated_body_to_db():
    """Successful processing must write translated_body with status='completed'."""
    pool, db = _make_pool()
    publish_event = AsyncMock()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Translated body.", 10, 8)):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    all_sql = " ".join(c.args[0] for c in db.execute.call_args_list)
    assert "completed" in all_sql
    assert "translated_body" in all_sql


@pytest.mark.asyncio
async def test_chapter_worker_emits_chapter_done_event():
    """Plan §4.2: worker must emit job.chapter_done after each chapter finishes."""
    pool, _ = _make_pool()
    publish_event = AsyncMock()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Translated body.", 10, 8)):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    events = [c.args[1]["event"] for c in publish_event.call_args_list]
    assert "job.chapter_done" in events


@pytest.mark.asyncio
async def test_chapter_worker_calls_translate_chapter():
    """translate_chapter must be called with chapter body and msg — handoff to session_translator."""
    pool, _ = _make_pool()
    publish_event = AsyncMock()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Translated body.", 10, 8)) as mock_translate:
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    mock_translate.assert_called_once()
    call_kwargs = mock_translate.call_args.kwargs
    assert call_kwargs["chapter_text"] == "In the beginning..."
    assert call_kwargs["msg"] is msg


# ── Plan §5: HTTP timeout ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chapter_worker_book_service_uses_finite_read_timeout():
    """Book-service GET must use a finite read timeout — not unlimited."""
    pool, _ = _make_pool()
    publish_event = AsyncMock()
    msg = _chapter_msg()
    captured: list = []

    def _capture_client(*args, **kwargs):
        captured.append(kwargs.get("timeout"))
        m = MagicMock()
        m.__aenter__ = AsyncMock(return_value=_patched_book_http())
        m.__aexit__ = AsyncMock(return_value=False)
        return m

    with patch("app.workers.chapter_worker.httpx.AsyncClient", side_effect=_capture_client), \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Translated body.", 10, 8)):
        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    # First AsyncClient call is for book-service; it must use httpx.Timeout (not a plain float)
    assert captured, "httpx.AsyncClient must be called at least once"
    book_timeout = captured[0]
    assert isinstance(book_timeout, httpx.Timeout), \
        f"book-service timeout must be httpx.Timeout, got {type(book_timeout)}"
    assert book_timeout.read is not None and book_timeout.read > 0, \
        "book-service read timeout must be finite (not None)"


@pytest.mark.asyncio
async def test_chapter_worker_connect_timeout_is_set():
    """Connect timeout must be finite — fast fail if book-service unreachable."""
    pool, _ = _make_pool()
    captured: list = []

    def _capture_client(*args, **kwargs):
        captured.append(kwargs.get("timeout"))
        m = MagicMock()
        m.__aenter__ = AsyncMock(return_value=_patched_book_http())
        m.__aexit__ = AsyncMock(return_value=False)
        return m

    with patch("app.workers.chapter_worker.httpx.AsyncClient", side_effect=_capture_client), \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Translated body.", 10, 8)):
        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(_chapter_msg(), pool, AsyncMock(), MagicMock(), retry_count=0)

    book_timeout = captured[0]
    assert isinstance(book_timeout, httpx.Timeout)
    assert book_timeout.connect is not None and book_timeout.connect > 0


# ── Cancellation check ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chapter_worker_skips_ai_call_when_job_cancelled():
    """Plan §4.2: if job status='cancelled', worker must not call book-service or AI."""
    pool, _ = _make_pool(job_status="cancelled")
    publish_event = AsyncMock()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock) as mock_translate:
        mock_http = MagicMock()
        mock_http.get = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    mock_http.get.assert_not_called()
    mock_translate.assert_not_called()


# ── Error taxonomy ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_chapter_not_found_raises_permanent_error():
    """404 from book-service → _PermanentError (retry won't fix missing chapter)."""
    pool, _ = _make_pool()
    msg = _chapter_msg()
    not_found = MagicMock(spec=httpx.Response)
    not_found.status_code = 404
    not_found.raise_for_status = MagicMock()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls:
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=not_found)
        )
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import _PermanentError, handle_chapter_message
        with pytest.raises(_PermanentError):
            await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)


@pytest.mark.asyncio
async def test_billing_rejected_raises_permanent_error():
    """402 from translate_chapter (via session_translator) → propagated as _PermanentError."""
    from app.workers.chapter_worker import _PermanentError
    pool, _ = _make_pool()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock,
               side_effect=_PermanentError("billing_rejected")):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        with pytest.raises(_PermanentError):
            await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)


@pytest.mark.asyncio
async def test_model_not_found_raises_permanent_error():
    """404 for model ref (via session_translator) → propagated as _PermanentError."""
    from app.workers.chapter_worker import _PermanentError
    pool, _ = _make_pool()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock,
               side_effect=_PermanentError("model_not_found")):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        with pytest.raises(_PermanentError):
            await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)


@pytest.mark.asyncio
async def test_book_service_connection_error_raises_transient_error():
    """Network error to book-service → _TransientError (safe to retry)."""
    pool, _ = _make_pool()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls:
        mock_http = MagicMock()
        mock_http.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import _TransientError, handle_chapter_message
        with pytest.raises(_TransientError):
            await handle_chapter_message(_chapter_msg(), pool, AsyncMock(), MagicMock(), retry_count=0)


@pytest.mark.asyncio
async def test_provider_5xx_raises_transient_error():
    """5xx from translate_chapter (via session_translator) → propagated as _TransientError."""
    from app.workers.chapter_worker import _TransientError
    pool, _ = _make_pool()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock,
               side_effect=_TransientError("provider_503")):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        with pytest.raises(_TransientError):
            await handle_chapter_message(_chapter_msg(), pool, AsyncMock(), MagicMock(), retry_count=0)


# ── _fail_chapter_idempotent ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_fail_chapter_idempotent_increments_counter_on_first_call():
    """First failure: fetchval returns chapter_id → counter incremented."""
    pool, db = _make_pool()
    job_id = uuid4()
    chapter_id = uuid4()
    db.fetchval = AsyncMock(return_value=chapter_id)   # UPDATE returned row

    from app.workers.chapter_worker import _fail_chapter_idempotent
    await _fail_chapter_idempotent(pool, job_id, chapter_id, "test_reason")

    db.execute.assert_called_once()
    sql = db.execute.call_args.args[0]
    assert "failed_chapters" in sql


@pytest.mark.asyncio
async def test_fail_chapter_idempotent_skips_counter_when_already_failed():
    """Second call: fetchval returns None (row already failed) → no counter increment."""
    pool, db = _make_pool()
    job_id = uuid4()
    chapter_id = uuid4()
    db.fetchval = AsyncMock(return_value=None)   # WHERE status != 'failed' matched nothing

    from app.workers.chapter_worker import _fail_chapter_idempotent
    await _fail_chapter_idempotent(pool, job_id, chapter_id, "test_reason")

    db.execute.assert_not_called()


# ── _check_job_completion (atomic finalization) ───────────────────────────────

@pytest.mark.asyncio
async def test_check_job_completion_emits_event_when_winner():
    """Winner of the atomic UPDATE must emit job.status_changed with final status."""
    pool, db = _make_pool(finalization_row=FakeRecord({
        "status": "completed",
        "completed_chapters": 3,
        "failed_chapters": 0,
    }))
    publish_event = AsyncMock()
    msg = _chapter_msg()

    from app.workers.chapter_worker import _check_job_completion
    await _check_job_completion(pool, UUID(msg["job_id"]), msg["user_id"], msg, publish_event)

    publish_event.assert_called_once()
    event = publish_event.call_args.args[1]
    assert event["event"] == "job.status_changed"
    assert event["payload"]["status"] == "completed"
    assert event["payload"]["completed_chapters"] == 3


@pytest.mark.asyncio
async def test_check_job_completion_no_event_when_not_winner():
    """Non-winner (UPDATE returned no row) must NOT emit any event — prevents duplicates."""
    pool, db = _make_pool(finalization_row=None)
    publish_event = AsyncMock()
    msg = _chapter_msg()

    from app.workers.chapter_worker import _check_job_completion
    await _check_job_completion(pool, UUID(msg["job_id"]), msg["user_id"], msg, publish_event)

    publish_event.assert_not_called()


@pytest.mark.asyncio
async def test_check_job_completion_partial_status():
    """partial: completed > 0 and failed > 0."""
    pool, db = _make_pool(finalization_row=FakeRecord({
        "status": "partial",
        "completed_chapters": 2,
        "failed_chapters": 1,
    }))
    publish_event = AsyncMock()
    msg = _chapter_msg()

    from app.workers.chapter_worker import _check_job_completion
    await _check_job_completion(pool, UUID(msg["job_id"]), msg["user_id"], msg, publish_event)

    payload = publish_event.call_args.args[1]["payload"]
    assert payload["status"] == "partial"
    assert payload["completed_chapters"] == 2
    assert payload["failed_chapters"] == 1


@pytest.mark.asyncio
async def test_check_job_completion_all_failed_status():
    """failed: completed = 0, all chapters failed."""
    pool, db = _make_pool(finalization_row=FakeRecord({
        "status": "failed",
        "completed_chapters": 0,
        "failed_chapters": 3,
    }))
    publish_event = AsyncMock()
    msg = _chapter_msg()

    from app.workers.chapter_worker import _check_job_completion
    await _check_job_completion(pool, UUID(msg["job_id"]), msg["user_id"], msg, publish_event)

    payload = publish_event.call_args.args[1]["payload"]
    assert payload["status"] == "failed"
