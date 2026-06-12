"""Phase 2b-T2 — at-least-once correctness for the decoupled-resume path.

The pure state machine is covered in test_decoupled_translate. Here we lock the two
load-bearing invariants the relay's at-least-once delivery depends on:

  (A) _finalize_chapter is idempotent — a duplicate FINAL terminal event (the row is
      already 'completed') must NOT double-increment the job counter, re-insert the
      active version, or re-emit the outbox event.
  (B) the consumer dedups superseded / foreign jobs — a terminal event whose job_id
      no longer matches any chapter's provider_job_id is acked + ignored (no resume).
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events import llm_terminal_consumer as c
from app.workers import chapter_worker


class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        pass


def _make_db(update_tag: str):
    """A pool whose acquired connection's first execute() (the guarded UPDATE)
    returns `update_tag` ('UPDATE 1' = we finalized, 'UPDATE 0' = duplicate)."""
    db = AsyncMock()
    db.execute = AsyncMock(return_value=update_tag)
    _tx = AsyncMock()
    _tx.__aenter__ = AsyncMock(return_value=db)
    _tx.__aexit__ = AsyncMock(return_value=False)
    db.transaction = MagicMock(return_value=_tx)
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    pool.execute = AsyncMock()
    pool.fetchrow = AsyncMock(return_value={"id": uuid4()})
    return pool, db


def _msg() -> dict:
    return {
        "job_id": str(uuid4()), "chapter_id": str(uuid4()), "user_id": "u",
        "book_id": str(uuid4()), "target_language": "vi", "pipeline_version": "v2",
        "chapter_index": 0,
    }


@pytest.mark.asyncio
async def test_finalize_idempotent_on_duplicate_skips_counter_but_finalizes_job():
    """(A) UPDATE 0 ⇒ already finalized ⇒ no counter increment, no active-version
    insert, no outbox event, no per-chapter telemetry (quality/memo) — BUT the
    job-level finalization STILL runs (review-impl finding 1): if the first delivery
    crashed after the status commit but before _check_job_completion, the redelivery
    must finalize the job, not leave it stuck 'running'."""
    pool, db = _make_db("UPDATE 0")
    publish_event = AsyncMock()
    with patch.object(chapter_worker, "_insert_outbox_event", new=AsyncMock()) as outbox, \
         patch.object(chapter_worker, "_emit_chapter_done", new=AsyncMock()) as done, \
         patch.object(chapter_worker, "_check_job_completion", new=AsyncMock()) as check, \
         patch.object(chapter_worker, "_save_chapter_memo", new=AsyncMock()) as memo, \
         patch.object(chapter_worker, "_emit_translation_quality", new=AsyncMock()) as quality:
        m = _msg()
        await chapter_worker._finalize_chapter(
            pool=pool, publish_event=publish_event, msg=m,
            job_id=uuid4(), chapter_id=uuid4(), user_id="u",
            chapter_translation_id=uuid4(), pipeline_version="v2",
            chapter_index=0, target_language="vi", source_lang="zh",
            chapter_text="src", translated_body_text="body",
            translated_body_json=None, translated_body_format="text",
            memo_text="body", input_tokens=1, output_tokens=1,
        )
    # exactly ONE execute (the guarded UPDATE) — counter/active inserts skipped
    assert db.execute.await_count == 1
    outbox.assert_not_awaited()
    # per-chapter telemetry skipped on a duplicate (no double-emit)
    quality.assert_not_awaited()
    memo.assert_not_awaited()
    # job-level finalization runs ALWAYS (idempotent) — closes the crash-stall gap
    done.assert_awaited_once()
    check.assert_awaited_once()


@pytest.mark.asyncio
async def test_finalize_runs_full_path_when_update_applied():
    """(A) UPDATE 1 ⇒ we are the finalizer ⇒ counter + active + outbox + emits run."""
    pool, db = _make_db("UPDATE 1")
    publish_event = AsyncMock()
    with patch.object(chapter_worker, "_insert_outbox_event", new=AsyncMock()) as outbox, \
         patch.object(chapter_worker, "_emit_chapter_done", new=AsyncMock()) as done, \
         patch.object(chapter_worker, "_check_job_completion", new=AsyncMock()) as check, \
         patch.object(chapter_worker, "_save_chapter_memo", new=AsyncMock()), \
         patch.object(chapter_worker, "_emit_translation_quality", new=AsyncMock()):
        await chapter_worker._finalize_chapter(
            pool=pool, publish_event=publish_event, msg=_msg(),
            job_id=uuid4(), chapter_id=uuid4(), user_id="u",
            chapter_translation_id=uuid4(), pipeline_version="v2",
            chapter_index=0, target_language="vi", source_lang="zh",
            chapter_text="src", translated_body_text="body",
            translated_body_json=None, translated_body_format="text",
            memo_text="body", input_tokens=1, output_tokens=1,
        )
    # UPDATE + counter + active-version INSERT = 3 execute calls on the conn
    assert db.execute.await_count == 3
    outbox.assert_awaited_once()
    done.assert_awaited_once()
    check.assert_awaited_once()


@pytest.mark.asyncio
async def test_load_for_job_none_for_unknown_or_bad_id():
    """(B) no matching provider_job_id ⇒ None (consumer will ack+ignore)."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)
    assert await c._load_for_job(pool, str(uuid4())) is None
    # non-uuid wire value never hits the DB
    assert await c._load_for_job(pool, "not-a-uuid") is None


@pytest.mark.asyncio
async def test_handle_acks_and_skips_resume_when_no_row():
    """(B) a foreign/superseded terminal event acks WITHOUT calling resume."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=None)  # _load_for_job → None
    consumer = c.LLMTerminalConsumer("redis://x", pool, MagicMock(), AsyncMock())
    r = AsyncMock()
    with patch.object(c.decoupled_translate, "resume", new=AsyncMock()) as resume:
        await consumer._handle(r, "1-0", {"job_id": str(uuid4()), "status": "completed"})
    resume.assert_not_awaited()
    r.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_resumes_and_acks_for_decoupled_chapter():
    """(B) a terminal event for a decoupled chapter loads state, fetches the job,
    drives resume(), then acks. Campaign attribution is bound for the resumed
    submit and cleared afterward."""
    ct_id = uuid4()
    m = _msg()
    m["campaign_id"] = "camp-9"
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"id": ct_id, "resume_state": {"msg": m, "source_lang": "zh"}})
    sdk = AsyncMock()
    sdk.get_job = AsyncMock(return_value=MagicMock(status="completed"))
    llm_client = MagicMock()
    llm_client.sdk = sdk
    consumer = c.LLMTerminalConsumer("redis://x", pool, llm_client, AsyncMock())
    r = AsyncMock()
    with patch.object(c.decoupled_translate, "resume", new=AsyncMock()) as resume, \
         patch.object(c, "set_campaign_id") as set_camp:
        await consumer._handle(r, "1-0", {"job_id": m["job_id"], "owner_user_id": "u", "status": "completed"})
    resume.assert_awaited_once()
    sdk.get_job.assert_awaited_once()
    r.xack.assert_awaited_once()
    # bound the campaign for the resumed submit, then cleared in finally
    assert set_camp.call_args_list[0].args[0] == "camp-9"
    assert set_camp.call_args_list[-1].args[0] is None


# ── Wave 2a — stuck-resume sweeper ───────────────────────────────────────────

def _sdk_job(terminal: bool):
    j = MagicMock()
    j.is_terminal = MagicMock(return_value=terminal)
    return j


def _sweep_consumer(rows, *, terminal=True, get_job_error=False):
    pool = MagicMock()
    pool.fetch = AsyncMock(return_value=rows)
    sdk = AsyncMock()
    if get_job_error:
        sdk.get_job = AsyncMock(side_effect=RuntimeError("transient"))
    else:
        sdk.get_job = AsyncMock(return_value=_sdk_job(terminal))
    llm_client = MagicMock()
    llm_client.sdk = sdk
    return c.LLMTerminalConsumer("redis://x", pool, llm_client, AsyncMock())


def _stranded_row():
    return {"id": uuid4(), "provider_job_id": uuid4(),
            "resume_state": {"msg": {"user_id": "u"}, "mode": "block"}}


@pytest.mark.asyncio
async def test_sweep_redrives_a_terminal_job():
    consumer = _sweep_consumer([_stranded_row()], terminal=True)
    with patch.object(consumer, "_resume_loaded", new=AsyncMock()) as redrive:
        n = await consumer.sweep_once(timeout_s=900, batch=20)
    assert n == 1
    redrive.assert_awaited_once()


@pytest.mark.asyncio
async def test_sweep_leaves_inflight_job_alone():
    consumer = _sweep_consumer([_stranded_row()], terminal=False)  # slow ≠ stuck
    with patch.object(consumer, "_resume_loaded", new=AsyncMock()) as redrive:
        n = await consumer.sweep_once(timeout_s=900, batch=20)
    assert n == 0
    redrive.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_continues_past_get_job_error():
    consumer = _sweep_consumer([_stranded_row()], get_job_error=True)
    with patch.object(consumer, "_resume_loaded", new=AsyncMock()) as redrive:
        n = await consumer.sweep_once(timeout_s=900, batch=20)
    assert n == 0
    redrive.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_query_filters_on_resume_and_idle():
    captured = {}

    async def fetch(sql, *args):
        captured["sql"] = sql
        captured["args"] = args
        return []

    consumer = _sweep_consumer([])
    consumer._pool.fetch = fetch
    await consumer.sweep_once(timeout_s=900, batch=20)
    sql = captured["sql"]
    assert "resume_state IS NOT NULL" in sql
    assert "provider_job_id IS NOT NULL" in sql
    assert "make_interval" in sql and "updated_at <" in sql
    assert "status NOT IN ('completed', 'failed')" in sql
    assert captured["args"] == (900, 20)
