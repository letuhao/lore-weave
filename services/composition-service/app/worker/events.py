"""composition_jobs queue — the enqueue trigger seam (Phase 3 M4).

A job endpoint XADDs a ``{job_id, user_id, project_id}`` message here; the
background worker XREADGROUPs it and runs the job's LLM compute. Mirrors
lore-enrichment's resume-trigger stream + the platform ``loreweave:events:<x>``
convention. Best-effort enqueue: a transient Redis fault does NOT fail the create
(the job row persists; the stuck-job sweeper / a repeat submit re-drives it).
"""

from __future__ import annotations

import logging
from typing import Any

__all__ = [
    "COMPOSITION_JOBS_STREAM",
    "COMPOSITION_WORKER_GROUP",
    "STREAM_MAXLEN",
    "make_redis_producer",
    "enqueue_job",
]

logger = logging.getLogger("composition.worker.events")

#: The job-trigger stream (platform convention loreweave:events:<aggregate>).
COMPOSITION_JOBS_STREAM = "loreweave:events:composition_jobs"
#: The worker's consumer group.
COMPOSITION_WORKER_GROUP = "composition-worker"
#: Approximate XADD MAXLEN bound (mirrors the other platform streams).
STREAM_MAXLEN = 10000


class _AioredisProducer:
    """``redis.asyncio``-backed stream producer (lazy connect)."""

    def __init__(self, redis_url: str) -> None:
        self._url = redis_url
        self._redis: Any = None

    async def _ensure(self) -> Any:
        if self._redis is None:
            import redis.asyncio as aioredis  # local import — optional dep

            self._redis = aioredis.from_url(self._url, decode_responses=True)
        return self._redis

    async def xadd(self, stream: str, fields: dict[str, str], *, maxlen: int | None = None) -> str:
        r = await self._ensure()
        return await r.xadd(stream, fields, maxlen=maxlen, approximate=True)

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None


def make_redis_producer(redis_url: str) -> _AioredisProducer:
    return _AioredisProducer(redis_url)


async def enqueue_job(
    redis_url: str, *, job_id: str, user_id: str, project_id: str
) -> bool:
    """Best-effort XADD of a job trigger. Returns True on enqueue, False on a
    transient Redis fault (the job row still exists → re-driveable)."""
    producer = make_redis_producer(redis_url)
    try:
        await producer.xadd(
            COMPOSITION_JOBS_STREAM,
            {"job_id": job_id, "user_id": user_id, "project_id": project_id},
            maxlen=STREAM_MAXLEN,
        )
        return True
    except Exception:  # noqa: BLE001 — enqueue failure must not fail the create
        logger.warning("composition job %s enqueue failed (re-driveable)", job_id, exc_info=True)
        return False
    finally:
        await producer.aclose()
