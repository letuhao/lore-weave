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


def _make_pool(job_status="running", finalization_row=None, claim_row="__default__"):
    db = AsyncMock()
    db.execute = AsyncMock()
    db.fetchval = AsyncMock(return_value=job_status)   # cancellation/pause check
    # B2 guarded claim: the worker now claims the chapter via
    # `UPDATE chapter_translations … RETURNING id` (returns None ⇒ claim lost). The same
    # acquired-conn fetchrow later runs the job finalize (`UPDATE translation_jobs …`).
    # Discriminate by query so the happy path claims a row AND finalize tests still drive
    # `finalization_row`. A test can pass claim_row=None to exercise the claim-lost path.
    _claim = FakeRecord({"id": uuid4()}) if claim_row == "__default__" else claim_row

    async def _fetchrow(query, *a, **k):
        if "chapter_translations" in query and "RETURNING id" in query:
            return _claim
        return finalization_row
    db.fetchrow = AsyncMock(side_effect=_fetchrow)
    # `_process_chapter` persists inside `async with db.transaction():`. An
    # unconfigured AsyncMock attribute returns a coroutine (not an async CM),
    # so give transaction() a synchronous factory returning an async CM.
    _tx = AsyncMock()
    _tx.__aenter__ = AsyncMock(return_value=db)
    _tx.__aexit__ = AsyncMock(return_value=False)
    db.transaction = MagicMock(return_value=_tx)
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


@pytest.mark.asyncio
async def test_chapter_worker_drops_unit_when_job_paused():
    """B2 (D-JOBS-P3-TRANSLATION-PAUSE): a paused job dispatches no new chapter work.
    The worker must NOT call book-service/AImust NOT fail the chapter, and MUST release
    the P5 slot (the chapter stays pending for resume)."""
    pool, db = _make_pool(job_status="paused")
    publish_event = AsyncMock()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter", new_callable=AsyncMock) as mock_translate, \
         patch("app.workers.chapter_worker.fair_sched.release_chapter_lease",
               new_callable=AsyncMock) as mock_release:
        mock_http = MagicMock()
        mock_http.get = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    mock_http.get.assert_not_called()
    mock_translate.assert_not_called()
    mock_release.assert_awaited_once()  # slot freed
    # NOT failed: no chapter-failed UPDATE ran (the chapter is left pending for resume).
    db.execute.assert_not_called()


@pytest.mark.asyncio
async def test_chapter_worker_skips_duplicate_when_claim_lost():
    """B2 guarded claim: a duplicate unit (a resume re-drive racing a still-parked WFQ
    unit) finds the chapter already running → the claim UPDATE returns no row → the worker
    must skip (no book-service/AI) and release the slot, NOT double-translate."""
    pool, _ = _make_pool(job_status="running", claim_row=None)  # claim returns None
    publish_event = AsyncMock()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter", new_callable=AsyncMock) as mock_translate, \
         patch("app.workers.chapter_worker.fair_sched.release_chapter_lease",
               new_callable=AsyncMock) as mock_release:
        mock_http = MagicMock()
        mock_http.get = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_http)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    mock_http.get.assert_not_called()
    mock_translate.assert_not_called()
    mock_release.assert_awaited_once()


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


# ── Block pipeline total-failure guard (TR-4 regression) ──────────────────────

@pytest.mark.asyncio
async def test_block_pipeline_total_failure_marks_chapter_failed():
    """TR-4 regression: if the block pipeline translates 0 of N translatable
    blocks (the LLM step failed for every batch), the chapter MUST be marked
    failed — NOT silently persisted as 'completed' with all-original blocks
    (which made the matrix show 完了 for an untranslated chapter)."""
    from app.workers.chapter_worker import _PermanentError, handle_chapter_message

    pool, db = _make_pool()
    publish_event = AsyncMock()
    msg = _chapter_msg(target_language="ja")

    block_body = {
        "original_language": "en",
        "body": {"content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello."}]},
        ]},
        "text_content": "Hello.",
    }
    book_resp = MagicMock(spec=httpx.Response)
    book_resp.status_code = 200
    book_resp.is_success = True
    book_resp.raise_for_status = MagicMock()
    book_resp.json.return_value = block_body
    original_blocks = block_body["body"]["content"]

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock,
               return_value=(original_blocks, 0, 0, 0, 1, {})):  # 0/1 translated → total failure
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=book_resp))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        with pytest.raises(_PermanentError):
            await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    # The chapter row was marked failed (NOT completed); a chapter_done event fired.
    all_sql = " ".join(c.args[0] for c in db.execute.call_args_list)
    assert "failed" in all_sql
    assert "status='completed'" not in all_sql
    events = [c.args[1].get("event") for c in publish_event.call_args_list]
    assert "job.chapter_done" in events


@pytest.mark.asyncio
async def test_block_pipeline_partial_success_still_completes():
    """Counterpart: a PARTIAL block result (some translated) must still complete
    — only a TOTAL failure (0 translated) trips the guard."""
    from app.workers.chapter_worker import handle_chapter_message

    pool, db = _make_pool()
    msg = _chapter_msg(target_language="ja")
    block_body = {
        "original_language": "en",
        "body": {"content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello."}]},
        ]},
        "text_content": "Hello.",
    }
    book_resp = MagicMock(spec=httpx.Response)
    book_resp.status_code = 200
    book_resp.is_success = True
    book_resp.raise_for_status = MagicMock()
    book_resp.json.return_value = block_body
    translated_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "こんにちは。"}]}]

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock,
               return_value=(translated_blocks, 10, 8, 1, 1, {0: "こんにちは。"})):  # 1/1 translated
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=book_resp))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    all_sql = " ".join(c.args[0] for c in db.execute.call_args_list)
    assert "completed" in all_sql


@pytest.mark.asyncio
async def test_block_pipeline_auto_active_gated_on_unresolved_high():
    """M5b (review-impl): the completion auto-activate must NOT publish a
    verifier-flagged version. The INSERT guards on unresolved_high_count=0 so a
    flagged-only chapter leaves no active version (reader sees 'not translated'
    until manual ack). Asserts the guard is present in the auto-active SQL."""
    from app.workers.chapter_worker import handle_chapter_message

    pool, db = _make_pool()
    msg = _chapter_msg(target_language="ja")
    block_body = {
        "original_language": "en",
        "body": {"content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello."}]},
        ]},
        "text_content": "Hello.",
    }
    book_resp = MagicMock(spec=httpx.Response)
    book_resp.status_code = 200
    book_resp.is_success = True
    book_resp.raise_for_status = MagicMock()
    book_resp.json.return_value = block_body
    translated_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "こんにちは。"}]}]

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock,
               return_value=(translated_blocks, 10, 8, 1, 1, {0: "こんにちは。"})):
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=book_resp))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    auto_active = [
        c for c in db.execute.call_args_list
        if "active_chapter_translation_versions" in c.args[0]
    ]
    assert auto_active, "auto-active INSERT must run at completion"
    assert "unresolved_high_count" in auto_active[0].args[0], \
        "auto-active must be gated on the quality rollup (M5b)"
    # Promote-on-completion (2026-06-14): a clean version is published even over an
    # existing active one (DO UPDATE), guarded so it never clobbers a human edit.
    sql = auto_active[0].args[0]
    assert "DO UPDATE" in sql, "completion must promote the clean version (DO UPDATE)"
    assert "authored_by" in sql and "<> 'human'" in sql, \
        "promote must be guarded so it never clobbers a human-edited active version"


async def _run_completion(msg):
    """Drive a block-pipeline completion and return the auto-active INSERT SQL."""
    from app.workers.chapter_worker import handle_chapter_message
    pool, db = _make_pool()
    block_body = {
        "original_language": "en",
        "body": {"content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello."}]},
        ]},
        "text_content": "Hello.",
    }
    book_resp = MagicMock(spec=httpx.Response)
    book_resp.status_code = 200
    book_resp.is_success = True
    book_resp.raise_for_status = MagicMock()
    book_resp.json.return_value = block_body
    translated_blocks = [{"type": "paragraph", "content": [{"type": "text", "text": "こんにちは。"}]}]
    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock,
               return_value=(translated_blocks, 10, 8, 1, 1, {0: "こんにちは。"})):
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=book_resp))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)
        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)
    auto = [c for c in db.execute.call_args_list
            if "active_chapter_translation_versions" in c.args[0]]
    assert auto, "auto-active INSERT must run at completion"
    return auto[0].args[0]


@pytest.mark.asyncio
async def test_campaign_job_autonomous_publish_promotes_over_existing():
    """A campaign (no-human) job PROMOTES the clean version to active even over an
    existing one (DO UPDATE) — gated on unresolved_high_count=0 (the SELECT WHERE)
    and on the current active not being a human edit (the DO UPDATE WHERE)."""
    sql = await _run_completion(_chapter_msg(target_language="ja", campaign_id=str(uuid4())))
    assert "DO UPDATE" in sql, "campaign job must auto-republish (promote-on-completion)"
    assert "chapter_translation_id = EXCLUDED" in sql
    assert "unresolved_high_count" in sql, "still gated on the quality rollup"
    assert "authored_by" in sql and "<> 'human'" in sql, "must not clobber a human edit"


@pytest.mark.asyncio
async def test_non_campaign_job_auto_promotes_with_human_guard():
    """2026-06-14: interactive single re-translation now also promotes a clean new
    version to active (DO UPDATE), so a re-translation to a stronger model takes
    effect without a manual publish — but never clobbers a human-edited active
    version (authored_by guard)."""
    sql = await _run_completion(_chapter_msg(target_language="ja"))  # no campaign_id
    assert "DO UPDATE" in sql and "DO NOTHING" not in sql, \
        "interactive job must promote-on-completion (no longer first-write-wins)"
    assert "authored_by" in sql and "<> 'human'" in sql, \
        "interactive promote must be guarded against clobbering a human edit"


# ── TD1: cross-chapter memo wiring (M0) ───────────────────────────────────────

@pytest.mark.asyncio
async def test_block_pipeline_saves_nonempty_memo():
    """TD1 regression: the block pipeline must persist a NON-EMPTY cross-chapter
    memo. Before the fix the memo was derived from the always-None
    translated_body_text, so block-pipeline chapters silently saved no memo at all
    (the INSERT INTO translation_chapter_memos never ran)."""
    from app.workers.chapter_worker import handle_chapter_message

    pool, db = _make_pool()
    msg = _chapter_msg(target_language="ja")
    block_body = {
        "original_language": "en",
        "body": {"content": [
            {"type": "paragraph", "content": [{"type": "text", "text": "Hello."}]},
        ]},
        "text_content": "Hello.",
    }
    book_resp = MagicMock(spec=httpx.Response)
    book_resp.status_code = 200
    book_resp.is_success = True
    book_resp.raise_for_status = MagicMock()
    book_resp.json.return_value = block_body
    translated_blocks = [
        {"type": "paragraph",
         "content": [{"type": "text", "text": "こんにちは。今日はいい天気です。"}]},
    ]

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker._get_model_context_window",
               new_callable=AsyncMock, return_value=8192), \
         patch("app.workers.session_translator.translate_chapter_blocks",
               new_callable=AsyncMock,
               return_value=(translated_blocks, 10, 8, 1, 1,
                             {0: "こんにちは。今日はいい天気です。"})):  # 1/1 translated
        mock_cls.return_value.__aenter__ = AsyncMock(
            return_value=_patched_book_http(book_resp=book_resp))
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    memo_calls = [
        c for c in db.execute.call_args_list
        if "translation_chapter_memos" in c.args[0]
    ]
    assert memo_calls, "block pipeline must save a chapter memo (TD1)"
    # _save_chapter_memo args: (sql, book_id, chapter_index, target_language, story_summary)
    story_summary = memo_calls[0].args[4]
    assert story_summary and story_summary.strip(), \
        "memo story_summary must be non-empty for the block pipeline"


@pytest.mark.asyncio
async def test_text_pipeline_still_saves_memo():
    """Parity: the text pipeline keeps saving its memo from translated_body_text."""
    from app.workers.chapter_worker import handle_chapter_message

    pool, db = _make_pool()
    msg = _chapter_msg()

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, return_value=("Translated body. Second sentence.", 10, 8)):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        await handle_chapter_message(msg, pool, AsyncMock(), MagicMock(), retry_count=0)

    memo_calls = [
        c for c in db.execute.call_args_list
        if "translation_chapter_memos" in c.args[0]
    ]
    assert memo_calls, "text pipeline must save a chapter memo"
    assert memo_calls[0].args[4].strip(), "memo story_summary must be non-empty"


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
async def test_check_job_completion_emits_event_when_winner(monkeypatch):
    """Winner of the atomic UPDATE must emit job.status_changed with final status."""
    # P1: the finalize UPDATE now also RETURNs owner_user_id + emits a JobEvent in
    # the same tx; patch the SDK emit so this test stays focused on publish_event.
    monkeypatch.setattr("app.workers.chapter_worker.emit_job_event", AsyncMock())
    pool, db = _make_pool(finalization_row=FakeRecord({
        "status": "completed",
        "completed_chapters": 3,
        "failed_chapters": 0,
        "owner_user_id": uuid4(),
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
async def test_check_job_completion_partial_status(monkeypatch):
    """partial: completed > 0 and failed > 0."""
    monkeypatch.setattr("app.workers.chapter_worker.emit_job_event", AsyncMock())
    pool, db = _make_pool(finalization_row=FakeRecord({
        "status": "partial",
        "completed_chapters": 2,
        "failed_chapters": 1,
        "owner_user_id": uuid4(),
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
async def test_check_job_completion_all_failed_status(monkeypatch):
    """failed: completed = 0, all chapters failed."""
    monkeypatch.setattr("app.workers.chapter_worker.emit_job_event", AsyncMock())
    pool, db = _make_pool(finalization_row=FakeRecord({
        "status": "failed",
        "completed_chapters": 0,
        "failed_chapters": 3,
        "owner_user_id": uuid4(),
    }))
    publish_event = AsyncMock()
    msg = _chapter_msg()

    from app.workers.chapter_worker import _check_job_completion
    await _check_job_completion(pool, UUID(msg["job_id"]), msg["user_id"], msg, publish_event)

    payload = publish_event.call_args.args[1]["payload"]
    assert payload["status"] == "failed"


# ── bug #34: mid-flight cancel routes to a clean stop (not a failure) ──────────

@pytest.mark.asyncio
async def test_chapter_worker_threads_cancel_check_into_translate():
    """bug #34 — _process_chapter builds a cancel_check closure and threads it into
    the (v2) translate_chapter call so an in-flight LLM call can be aborted on cancel."""
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

    cc = mock_translate.call_args.kwargs.get("cancel_check")
    assert cc is not None and callable(cc)
    # The fake pool's fetchval returns the job_status ('running') → not cancelled.
    assert await cc() is False


@pytest.mark.asyncio
async def test_cancel_check_closure_is_fail_soft_on_read_error():
    """bug #34 — the cancel_check closure must NEVER spuriously cancel a healthy job:
    any DB read exception returns False."""
    pool, db = _make_pool(job_status="running")  # healthy job — not cancelled at start
    publish_event = AsyncMock()
    msg = _chapter_msg()
    captured = {}

    async def _capture(*a, **k):
        captured["cc"] = k.get("cancel_check")
        return ("Translated body.", 10, 8)

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter", side_effect=_capture):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    cc = captured["cc"]
    # Make the next DB read blow up → closure must swallow + return False.
    db.fetchval = AsyncMock(side_effect=RuntimeError("db down"))
    assert await cc() is False


@pytest.mark.asyncio
async def test_chapter_worker_cancelled_error_is_clean_stop_not_failure():
    """bug #34 — a _CancelledError from the translator (user cancelled mid-flight) ends
    the chapter as a clean job_cancelled outcome: chapter marked failed with reason
    'job_cancelled', a chapter_done event emitted, and NO re-raise (the message is ACKed)."""
    pool, db = _make_pool()
    publish_event = AsyncMock()
    msg = _chapter_msg()

    from app.workers.chapter_worker import _CancelledError

    with patch("app.workers.chapter_worker.httpx.AsyncClient") as mock_cls, \
         patch("app.workers.chapter_worker.translate_chapter",
               new_callable=AsyncMock, side_effect=_CancelledError("cancelled")):
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=_patched_book_http())
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        from app.workers.chapter_worker import handle_chapter_message
        # Must NOT raise — a user-cancel is a clean stop, not an error to re-deliver.
        await handle_chapter_message(msg, pool, publish_event, MagicMock(), retry_count=0)

    # chapter was marked failed with reason job_cancelled (mirrors the start-cancel branch).
    # _fail_chapter_idempotent runs the UPDATE...RETURNING via db.fetchval.
    failed_update_args = [
        c.args for c in db.fetchval.call_args_list
        if len(c.args) > 0 and isinstance(c.args[0], str) and "status='failed'" in c.args[0]
    ]
    assert failed_update_args, "expected a status='failed' UPDATE for the cancelled chapter"
    assert any("job_cancelled" in str(a) for a in failed_update_args)
    # chapter_done event emitted with job_cancelled.
    done = [c.args[1] for c in publish_event.call_args_list
            if c.args[1].get("event") == "job.chapter_done"]
    assert done and done[0]["payload"]["error_message"] == "job_cancelled"
