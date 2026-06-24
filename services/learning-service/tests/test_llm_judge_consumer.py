"""P1 — LLMJudgeConsumer wiring (Unified Job Control Plane).

The consumer is now a thin BaseTerminalConsumer subclass; these prove its `handle`/
`sweep_once` hooks are actually wired to `decoupled_judge` and that the base
ack/retry path behaves (no internal ack left in the migrated handle). The base
transport itself is unit-tested in the SDK; here we cover the subclass seam."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.events import llm_judge_consumer as c


def _consumer():
    return c.LLMJudgeConsumer("redis://x", MagicMock(), AsyncMock())


@pytest.mark.asyncio
async def test_handle_loads_fetches_resumes_and_acks():
    consumer = _consumer()
    consumer._sdk.get_job = AsyncMock(return_value=MagicMock())
    r = AsyncMock()
    with patch.object(c.decoupled_judge, "load_for_job",
                      new=AsyncMock(return_value=("row-1", "biller-9"))) as load, \
         patch.object(c.decoupled_judge, "resume", new=AsyncMock()) as resume:
        await consumer._process_msg(r, "1-0", {"job_id": str(uuid4()), "owner_user_id": "u"})
    load.assert_awaited_once()
    consumer._sdk.get_job.assert_awaited_once()
    resume.assert_awaited_once()
    r.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_no_job_id_acks_without_loading():
    consumer = _consumer()
    r = AsyncMock()
    with patch.object(c.decoupled_judge, "load_for_job", new=AsyncMock()) as load:
        await consumer._process_msg(r, "1-0", {})
    load.assert_not_awaited()
    r.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_handle_no_matching_row_acks_and_skips_resume():
    consumer = _consumer()
    r = AsyncMock()
    with patch.object(c.decoupled_judge, "load_for_job", new=AsyncMock(return_value=None)), \
         patch.object(c.decoupled_judge, "resume", new=AsyncMock()) as resume:
        await consumer._process_msg(r, "1-0", {"job_id": str(uuid4())})
    resume.assert_not_awaited()
    r.xack.assert_awaited_once()  # foreign/finalized job → ack-ignore


@pytest.mark.asyncio
async def test_handle_error_leaves_unacked_below_max():
    consumer = _consumer()
    consumer._sdk.get_job = AsyncMock(return_value=MagicMock())
    r = AsyncMock()
    r.incr = AsyncMock(return_value=1)  # below max_retries → redelivered
    with patch.object(c.decoupled_judge, "load_for_job", new=AsyncMock(return_value=("row", "b"))), \
         patch.object(c.decoupled_judge, "resume", new=AsyncMock(side_effect=RuntimeError("boom"))):
        await consumer._process_msg(r, "1-0", {"job_id": str(uuid4())})
    r.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_sweep_once_delegates_to_decoupled_judge():
    consumer = _consumer()
    with patch.object(c.decoupled_judge, "sweep_once",
                      new=AsyncMock(return_value=2)) as sweep:
        n = await consumer.sweep_once(timeout_s=900, batch=10)
    assert n == 2
    sweep.assert_awaited_once()
