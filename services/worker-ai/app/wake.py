"""FD-22 — interruptible poll wait via the extraction.wake Redis Stream.

worker-ai's poll loop normally sleeps ``poll_interval_s`` between cycles. This
lets a knowledge-service wake signal cut that sleep short so a freshly started
extraction job is picked up ~immediately instead of up to ``poll_interval_s``
later.

The poll remains the **source-of-truth** (it claims jobs atomically); the wake
is a best-effort interrupt. Any Redis fault (init, XREAD, outage) degrades to a
plain ``asyncio.sleep`` — i.e. today's pure-polling behavior — so this is purely
additive latency reduction with full graceful degradation.

No consumer group on purpose: a group would split wakes across replicas, but we
want EVERY worker replica to wake and run its own (atomic) poll. Reading with
``$``/tail-follow fans the wake out to all replicas; the atomic claim in
``poll_and_run`` still guarantees exactly one processes each job.
"""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis

logger = logging.getLogger("worker-ai.wake")

__all__ = ["WakeWaiter"]


class WakeWaiter:
    """Holds the redis client + stream tail position across poll cycles.

    ``wait(timeout_s)`` blocks on ``XREAD BLOCK`` up to ``timeout_s``, returning
    ``True`` if a wake arrived (poll now) or ``False`` on timeout (normal poll).
    Degrades to ``asyncio.sleep`` on any error so a Redis outage silently reverts
    to polling.
    """

    def __init__(self, redis_url: str, stream: str) -> None:
        self._stream = stream
        # "$" = new messages only — no cold-start replay of stale wakes. After
        # the first read we follow the tail by concrete id so a wake arriving
        # mid-job-processing isn't missed.
        self._last_id = "$"
        try:
            self._redis: aioredis.Redis | None = aioredis.from_url(redis_url)
        except Exception:  # noqa: BLE001
            logger.warning("wake: redis init failed — falling back to polling", exc_info=True)
            self._redis = None

    async def wait(self, timeout_s: float) -> bool:
        """Block up to ``timeout_s`` for a wake. Returns True if woken."""
        if self._redis is None:
            await asyncio.sleep(timeout_s)
            return False
        try:
            # max(1, …): Redis XREAD BLOCK 0 means "block forever". A config
            # with poll_interval_s<=0 would otherwise hang the loop until a wake
            # arrives, stalling multi-item drain. Floor at 1ms so the wait always
            # has a finite ceiling (degrades to a tight poll, never a hang).
            resp = await self._redis.xread(
                {self._stream: self._last_id},
                block=max(1, int(timeout_s * 1000)),
                count=1,
            )
        except aioredis.TimeoutError:
            # redis-py 8: an idle blocking XREAD raises TimeoutError instead of
            # returning [] (the 5.x behavior this was written against). This is the
            # NORMAL no-wake timeout — treat it like an empty resp (return False →
            # normal poll), NOT a Redis fault. Without this the generic handler
            # below logs a traceback EVERY idle cycle and sleeps a second
            # timeout_s, doubling poll latency and defeating the wake interrupt.
            # Mirrors the extract/summary terminal consumers' TimeoutError handling.
            return False
        except Exception:  # noqa: BLE001 — degrade to sleep on any Redis fault
            logger.warning("wake: XREAD failed — sleeping instead", exc_info=True)
            await asyncio.sleep(timeout_s)
            return False
        if not resp:
            return False  # block timed out with no wake → normal poll
        # resp = [(stream, [(id, fields), ...])]; advance the tail to the last id
        # so the next wait only sees newer wakes (and catches any that arrived
        # while we were processing a job).
        _stream, entries = resp[-1]
        if entries:
            last = entries[-1][0]
            self._last_id = last.decode() if isinstance(last, bytes) else str(last)
        return True

    async def aclose(self) -> None:
        if self._redis is not None:
            try:
                await self._redis.aclose()
            except Exception:  # noqa: BLE001
                pass
