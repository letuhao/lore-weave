"""FD-22 — extraction-start wake signal (Redis Stream).

Producer-side: the extraction start route XADDs a content-free wake to the
``extraction.wake`` stream after a job transitions to ``running``. worker-ai's
poll loop blocks on this stream (``XREAD BLOCK``), so it picks the job up
~immediately instead of waiting up to ``poll_interval_s``.

**Wake-over-poll, NOT a job-payload queue:** the worker's poll cycle stays the
source-of-truth (it claims + transitions jobs atomically). The wake only
shortens the sleep, so a lost OR duplicate wake is harmless and a full Redis
outage degrades cleanly to pure polling. Best-effort: a failed XADD NEVER fails
the start request (the job is already running).

Mirrors the ``summary_enqueue.py`` producer DI shape (a ``Protocol`` fn the
route takes via ``Depends``; prod wires the redis-backed default, tests inject
a mock).
"""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

__all__ = [
    "EXTRACTION_WAKE_STREAM",
    "ExtractionWakeFn",
    "make_redis_extraction_wake",
    "noop_extraction_wake",
]

#: Redis Stream worker-ai's poll loop blocks on for an early wake.
EXTRACTION_WAKE_STREAM = "extraction.wake"

#: The wake is a transient interrupt, not a durable queue — cap stream growth.
#: An approximate MAXLEN keeps XADD O(1) while bounding memory.
_WAKE_STREAM_MAXLEN = 100


class ExtractionWakeFn(Protocol):
    """Injected into the start route. Prod = redis-backed; tests = a mock."""

    async def __call__(self, *, job_id: UUID, project_id: UUID) -> None:
        ...


async def noop_extraction_wake(*, job_id: UUID, project_id: UUID) -> None:
    """Disabled / no-redis fallback — does nothing. The worker's poll loop
    still picks the job up within ``poll_interval_s`` (no behavioral loss)."""
    return None


def make_redis_extraction_wake(redis_url: str) -> ExtractionWakeFn:
    """Build the redis-backed wake emitter (one client per worker process)."""
    client = aioredis.from_url(redis_url)

    async def _wake(*, job_id: UUID, project_id: UUID) -> None:
        # Best-effort: the job is already running; the wake is pure latency
        # optimization. A Redis fault must NOT fail the start request — the
        # worker's poll loop still picks the job up within poll_interval_s.
        try:
            await client.xadd(
                EXTRACTION_WAKE_STREAM,
                {"job_id": str(job_id), "project_id": str(project_id)},
                maxlen=_WAKE_STREAM_MAXLEN,
                approximate=True,
            )
        except Exception:  # noqa: BLE001 — best-effort wake; poll is the fallback
            logger.warning(
                "extraction wake XADD failed job_id=%s (poll fallback active)",
                job_id, exc_info=True,
            )

    return _wake
