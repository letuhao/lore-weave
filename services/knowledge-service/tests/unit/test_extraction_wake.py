"""FD-22 — tests for the extraction-start wake producer.

The wake is best-effort (the job is already running when it fires), so the two
load-bearing properties are: (1) it XADDs the right stream/fields with a capped
MAXLEN, and (2) a Redis fault is swallowed, never propagated to the start route.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

from app.jobs.extraction_wake import (
    EXTRACTION_WAKE_STREAM,
    make_redis_extraction_wake,
    noop_extraction_wake,
)


def test_stream_name_matches_consumer_constant():
    # Worker-ai's `extraction_wake_stream` default MUST equal this.
    assert EXTRACTION_WAKE_STREAM == "extraction.wake"


async def test_noop_wake_does_nothing():
    # Disabled / no-redis fallback returns None without touching anything.
    assert await noop_extraction_wake(job_id=uuid4(), project_id=uuid4()) is None


async def test_redis_wake_xadds_stream_fields_and_capped_maxlen():
    fake = MagicMock()
    fake.xadd = AsyncMock(return_value=b"1-0")
    with patch("app.jobs.extraction_wake.aioredis.from_url", return_value=fake):
        wake = make_redis_extraction_wake("redis://test/0")

    jid, pid = uuid4(), uuid4()
    await wake(job_id=jid, project_id=pid)

    fake.xadd.assert_awaited_once()
    args, kwargs = fake.xadd.call_args
    assert args[0] == EXTRACTION_WAKE_STREAM
    assert args[1] == {"job_id": str(jid), "project_id": str(pid)}
    # Transient interrupt, not a durable queue → approximate MAXLEN cap.
    assert kwargs.get("approximate") is True
    assert kwargs.get("maxlen") and kwargs["maxlen"] > 0


async def test_redis_wake_swallows_xadd_failure():
    # Best-effort: a Redis fault must NOT propagate (the job is already running;
    # worker-ai's poll loop still picks it up within poll_interval_s).
    fake = MagicMock()
    fake.xadd = AsyncMock(side_effect=ConnectionError("redis down"))
    with patch("app.jobs.extraction_wake.aioredis.from_url", return_value=fake):
        wake = make_redis_extraction_wake("redis://test/0")

    assert await wake(job_id=uuid4(), project_id=uuid4()) is None
    fake.xadd.assert_awaited_once()
