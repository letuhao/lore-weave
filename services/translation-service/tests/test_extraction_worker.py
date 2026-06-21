"""Extraction worker — runaway-fix regression tests.

Covers the two bugs behind a glossary-extraction job that "ran for days and
ignored cancel":
  1. cancel-safe claim — a cancelled/terminal job is NOT clobbered back to
     'running'; the handler settles + returns so the AMQP message is ACKed
     (stops the redelivery loop).
  2. resume-from-checkpoint — chapters already finished on a prior delivery are
     skipped (no re-spent LLM), and completed/failed seed from the checkpoint so
     the job converges to a terminal state instead of restarting at 0 forever.
"""
import logging
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from loreweave_llm.models import Job

from app.workers import extraction_worker as ew
from app.workers.extraction_worker import _run_extraction_job
from app.workers.extraction_prompt import ParseStats


class _AcquireCM:
    def __init__(self, db):
        self._db = db

    async def __aenter__(self):
        return self._db

    async def __aexit__(self, *_):
        return False


def _pool(db):
    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(db))
    return pool


@pytest.mark.asyncio
async def test_cancelled_job_is_not_clobbered_and_does_no_work():
    # claim UPDATE matches nothing (job is cancelling/terminal) → fetchval None
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=None)
    db.execute = AsyncMock()
    db.fetch = AsyncMock(return_value=[])
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])) as known, \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()) as proc:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [str(uuid4()), str(uuid4())]},
            uuid4(), "u", _pool(db), publish, publish_event, MagicMock(),
        )

    known.assert_not_awaited()   # never fetched known entities → never started the run
    proc.assert_not_awaited()    # never processed a chapter → no LLM spend
    # settled the 'cancelling' row to a terminal 'cancelled' (not re-armed to running).
    # The settle is now a guarded `fetchval … RETURNING job_id` (so the worker only emits
    # 'cancelled' when it actually flipped a cancelling row, not for an already-terminal job).
    assert any("status='cancelled'" in str(c.args[0]) for c in db.fetchval.await_args_list)
    # emitted a cancelled status event
    assert any(
        c.args[1].get("payload", {}).get("status") == "cancelled"
        for c in publish_event.await_args_list
    )
    # CRUCIALLY: the claim UPDATE is guarded (won't run a cancelled job)
    claim_sql = db.fetchval.await_args_list[0].args[0]
    assert "status NOT IN" in claim_sql and "RETURNING job_id" in claim_sql


@pytest.mark.asyncio
async def test_resume_skips_completed_chapters_and_finalizes():
    jid = uuid4()
    c1, c2 = str(uuid4()), str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim succeeds
    db.fetch = AsyncMock(return_value=[
        {"chapter_id": c1, "status": "completed", "it": 100, "ot": 50},
        {"chapter_id": c2, "status": "completed", "it": 200, "ot": 80},
    ])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()) as proc, \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()) as emit:
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1, c2]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    proc.assert_not_awaited()  # both chapters already done on a prior delivery → no work
    # finalized: the terminal UPDATE ran with status='completed' (failed==0)
    finals = [c for c in db.execute.await_args_list if "SET status=$2, finished_at=now()" in str(c.args[0])]
    assert finals and finals[-1].args[2] == "completed"
    # Unified Job Control Plane (D-JOBS-GLOSSARY-EXTRACT-UNWIRED): emitted running on claim
    # + completed on finalize, as kind='glossary_extraction'.
    emitted = [c.kwargs.get("status") for c in emit.await_args_list]
    assert "running" in emitted and "completed" in emitted
    assert all(c.kwargs.get("kind") == "glossary_extraction" for c in emit.await_args_list)


@pytest.mark.asyncio
async def test_job_terminal_emits_batch_summary_rollup():
    # OBS/M2 (INV-O14): the job-terminal notification carries a per-status rollup derived
    # from the extraction_batch_outcomes SSOT, so a truncated/rejected batch is visible.
    jid = uuid4()
    c1 = str(uuid4())
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=jid)  # claim succeeds
    db.fetch = AsyncMock(side_effect=[
        # 1) resume checkpoint: c1 already completed on a prior delivery.
        [{"chapter_id": c1, "status": "completed", "it": 10, "ot": 5}],
        # 2) the finalize rollup query over extraction_batch_outcomes.
        [{"status": "ok", "n": 3}, {"status": "truncated", "n": 1}],
    ])
    db.execute = AsyncMock()
    publish, publish_event = AsyncMock(), AsyncMock()

    with patch("app.workers.extraction_worker.fetch_known_entities", new=AsyncMock(return_value=[])), \
         patch("app.workers.extraction_worker._process_extraction_chapter", new=AsyncMock()), \
         patch("app.workers.extraction_worker.emit_job_event_safe", new=AsyncMock()):
        await _run_extraction_job(
            {"book_id": "b", "chapter_ids": [c1]},
            jid, "u", _pool(db), publish, publish_event, MagicMock(),
        )

    terminal = [
        c.args[1]["payload"] for c in publish_event.await_args_list
        if c.args[1].get("payload", {}).get("status") in ("completed", "completed_with_errors", "failed")
    ]
    assert terminal, "no terminal status_changed event emitted"
    assert terminal[-1]["batch_summary"] == {"ok": 3, "truncated": 1}


# ── M0 (extraction pipeline FND): finish_reason consumption ───────────────


def _http_cm_returning(chapter_json: dict):
    """A patched httpx.AsyncClient() context manager whose .get() returns a
    200 with the given chapter JSON (the book-service chapter fetch)."""
    resp = MagicMock()
    resp.status_code = 200
    resp.json = MagicMock(return_value=chapter_json)
    client = AsyncMock()
    client.get = AsyncMock(return_value=resp)
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=client)
    cm.__aexit__ = AsyncMock(return_value=False)
    return cm


def _sdk_job(finish_reason: str | None):
    """A terminal chat Job as the gateway returns it — finish_reason lives
    INSIDE result (the aggregator stamps it there); the SDK property reads it."""
    result: dict = {
        "messages": [{"role": "assistant", "content": "[]"}],
        "usage": {"input_tokens": 10, "output_tokens": 20},
    }
    if finish_reason is not None:
        result["finish_reason"] = finish_reason
    return Job(
        job_id=str(uuid4()), operation="chat", status="completed",
        result=result, submitted_at="2026-06-21T00:00:00Z",
    )


async def _run_one_chapter_batch(finish_reason: str | None, entities: list[dict],
                                 *, prepare_texts: list[str] | None = None):
    """Drive _process_extraction_chapter through ONE batch with a stubbed LLM
    result carrying `finish_reason`, and stubbed parse → `entities`. Returns
    (result, post_mock) so callers can assert the M1 writeback contract.

    prepare_texts: optional 2-element [initial, recheck] so a test can simulate the
    M1 content-hash drift precondition (initial != recheck → stale skip)."""
    db = AsyncMock()
    db.fetchval = AsyncMock(return_value=uuid4())  # owner_user_id resolve
    llm = MagicMock()
    llm.submit_and_wait = AsyncMock(return_value=_sdk_job(finish_reason))
    post = AsyncMock(return_value={"created": len(entities), "updated": 0, "skipped": 0})

    if prepare_texts is not None:
        prepare_mock = MagicMock(side_effect=prepare_texts)
    else:
        prepare_mock = MagicMock(return_value="some chapter text")

    with patch.object(ew.httpx, "AsyncClient",
                      return_value=_http_cm_returning({"title": "Ch1", "content": "text"})), \
         patch.object(ew, "prepare_chapter_text", new=prepare_mock), \
         patch.object(ew, "plan_kind_batches", return_value=[["character"]]), \
         patch.object(ew, "build_known_entities_context", return_value=""), \
         patch.object(ew, "build_extraction_prompt", return_value={}), \
         patch.object(ew, "build_system_prompt", return_value="sys"), \
         patch.object(ew, "build_user_prompt", return_value="usr"), \
         patch.object(ew, "thinking_llm_fields", return_value={}), \
         patch.object(ew, "parse_and_validate_with_stats",
                      return_value=(entities, ParseStats(raw_count=len(entities), parse_ok=True))), \
         patch.object(ew, "_persist_batch_outcomes", new=AsyncMock()), \
         patch.object(ew, "post_extracted_entities", new=post):
        result = await ew._process_extraction_chapter(
            job_id=uuid4(), book_id="b", chapter_id=uuid4(), chapter_index=0,
            extraction_profile={"character": {}}, kinds_metadata=[], known_entities=[],
            source_language="zh", model_source="user_model", model_ref=str(uuid4()),
            max_entities_per_kind=10, thinking_enabled=False, pool=_pool(db), llm_client=llm,
        )
        return result, post


@pytest.mark.asyncio
async def test_process_chapter_records_truncation_and_warns(caplog):
    # finish_reason=length → batch recorded truncated=True + a loud WARNING so
    # output-token truncation is no longer invisible (architecture §8.3 / the
    # 26-scenario data-loss bug).
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    result, _ = await _run_one_chapter_batch(
        "length", [{"name": "张若尘", "kind_code": "character", "status": "created"}],
    )
    bfr = result["batch_finish_reasons"]
    assert len(bfr) == 1
    assert bfr[0]["finish_reason"] == "length"
    assert bfr[0]["truncated"] is True
    assert bfr[0]["kinds"] == ["character"]
    assert any("TRUNCATED" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_process_chapter_records_clean_finish_no_warning(caplog):
    # finish_reason=stop → recorded, NOT truncated, no warning. Also exercises the
    # 0-entities early-return path still surfacing batch_finish_reasons.
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    result, _ = await _run_one_chapter_batch("stop", [])  # empty parse → early return
    bfr = result["batch_finish_reasons"]
    assert len(bfr) == 1
    assert bfr[0]["finish_reason"] == "stop"
    assert bfr[0]["truncated"] is False
    assert not any("TRUNCATED" in r.getMessage() for r in caplog.records)


@pytest.mark.asyncio
async def test_process_chapter_passes_writeback_idempotency_fields():
    # M1 — the per-chapter writeback carries the two-ledger fields so glossary can
    # dedupe it: chapter_id, a content_hash, an owner-scoped writeback_key.
    _, post = await _run_one_chapter_batch(
        "stop", [{"name": "张若尘", "kind_code": "character", "status": "created"}],
    )
    post.assert_awaited_once()
    kw = post.await_args.kwargs
    assert kw.get("chapter_id"), "writeback must carry chapter_id"
    assert len(kw.get("content_hash") or "") == 64, "content_hash must be a sha256 hex digest"
    assert len(kw.get("writeback_key") or "") == 64, "writeback_key must be a sha256 hex digest"
    assert kw.get("owner_user_id"), "writeback must carry owner_user_id (tenancy)"


@pytest.mark.asyncio
async def test_process_chapter_skips_stale_writeback_on_source_drift(caplog):
    # M1 (INV-C4) — if the chapter text changes between the initial fetch and the
    # post-extraction re-check, the entities are stale: skip the writeback entirely.
    caplog.set_level(logging.WARNING, logger="app.workers.extraction_worker")
    result, post = await _run_one_chapter_batch(
        "stop", [{"name": "张若尘", "kind_code": "character", "status": "created"}],
        prepare_texts=["original chapter text", "EDITED chapter text"],
    )
    assert result.get("stale_skipped") is True
    assert result["created"] == 0
    post.assert_not_awaited()  # nothing written back
    assert any("DRIFTED" in r.getMessage() for r in caplog.records)
