"""FD-22 — tests for WakeWaiter (interruptible poll wait).

The wake only shortens the poll sleep; the poll stays the source-of-truth. So
the load-bearing properties are: a message wakes (True) + advances the tail, a
block-timeout returns False, and ANY Redis fault degrades to a plain sleep
(False) — never raises — so a Redis outage silently reverts to pure polling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.wake import WakeWaiter


def _waiter(*, xread_return=None, xread_error=None) -> tuple[WakeWaiter, MagicMock]:
    fake = MagicMock()
    fake.xread = AsyncMock(return_value=xread_return, side_effect=xread_error)
    with patch("app.wake.aioredis.from_url", return_value=fake):
        w = WakeWaiter("redis://test/0", "extraction.wake")
    return w, fake


@pytest.mark.asyncio
async def test_wait_true_and_advances_tail_on_message():
    w, fake = _waiter(
        xread_return=[(b"extraction.wake", [(b"5-0", {b"job_id": b"j"})])]
    )
    assert await w.wait(0.01) is True
    # Tail advanced so the next wait only sees newer wakes (catches any that
    # arrive while a job is being processed).
    assert w._last_id == "5-0"
    fake.xread.assert_awaited_once()


@pytest.mark.asyncio
async def test_wait_false_on_block_timeout():
    w, _ = _waiter(xread_return=[])  # XREAD BLOCK returned no message
    assert await w.wait(0.01) is False
    assert w._last_id == "$"  # tail unchanged


@pytest.mark.asyncio
async def test_wait_degrades_to_sleep_on_xread_error():
    w, _ = _waiter(xread_error=ConnectionError("redis down"))
    # Must NOT raise; degrades to sleep + returns False (pure polling).
    assert await w.wait(0.0) is False


@pytest.mark.asyncio
async def test_wait_sleeps_when_redis_init_fails():
    # Redis init raised → no client → plain sleep, never True.
    with patch("app.wake.aioredis.from_url", side_effect=ConnectionError("no redis")):
        w = WakeWaiter("redis://bad/0", "extraction.wake")
    assert w._redis is None
    assert await w.wait(0.0) is False


@pytest.mark.asyncio
async def test_wait_never_blocks_forever_on_zero_timeout():
    """review-impl MED #1 — poll_interval_s<=0 must NOT become XREAD BLOCK 0
    (block forever). The block ms is floored at 1 so a 0 timeout degrades to a
    tight finite poll, never a hang."""
    w, fake = _waiter(xread_return=[])
    assert await w.wait(0.0) is False
    _, kwargs = fake.xread.call_args
    assert kwargs["block"] >= 1


def test_default_stream_matches_producer_literal():
    """review-impl MED #2 — pin the worker's default stream to the literal the
    knowledge producer (EXTRACTION_WAKE_STREAM) also pins to. Two independent
    constants across services; without a pin on each side a one-sided rename
    silently kills the wake (worker blocks on a stream nobody writes). This test
    + the knowledge-side test fail loudly if either drifts."""
    from app.config import Settings
    assert Settings().extraction_wake_stream == "extraction.wake"
