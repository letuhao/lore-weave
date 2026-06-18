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
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.workers.extraction_worker import _run_extraction_job


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
