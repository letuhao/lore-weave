"""composition batch-job worker entrypoint: `python -m app.worker` (Phase 3 M4).

Runs as a separate compose service (composition-worker) from the SAME image as the
API (CMD override), sharing the engine/repo/clients. Flag-gated by
COMPOSITION_WORKER_ENABLED (default false → idle, so the container stays healthy but
inert until the worker path is turned on).
"""

from __future__ import annotations

import asyncio
import logging

from app.config import settings
from app.db.pool import close_pool, create_pool, get_pool
from app.logging_config import setup_logging
from app.events.consumer import CHAPTER_STREAM, CompositionEventConsumer
from app.events.parts_mirror_consumer import BOOK_STREAM, PartsMirrorConsumer
from app.worker.job_consumer import CompositionJobConsumer

setup_logging(settings.log_level)  # P2·A2a — shared JSON logging (composition-service)
logger = logging.getLogger("composition.worker")


async def _main() -> None:
    if not settings.composition_worker_enabled:
        logger.info("COMPOSITION_WORKER_ENABLED=false — worker idle")
        while True:  # keep the container up but inert
            await asyncio.sleep(3600)

    await create_pool(settings.composition_db_url)
    pool = get_pool()
    logger.info("composition worker: pool up, starting consumer + sweeper")
    # consumer_name="worker-1" preserves the prior PEL consumer identity (was a literal,
    # not hostname-based) so a redeploy doesn't orphan in-flight pending entries.
    consumer = CompositionJobConsumer(settings.redis_url, pool, consumer_name="worker-1")
    sweeper = asyncio.create_task(
        consumer.run_sweeper(
            interval_s=settings.composition_job_sweep_secs,
            timeout_s=settings.composition_job_sweep_timeout_secs,
            batch=20,
        )
    )

    # SC11 Phase 2 — composition's FIRST domain-event consumer. book-service says "this chapter's
    # spec back-links may have changed"; we re-read that chapter and reconcile the written-verdict
    # mirror. Runs alongside the job consumer, on its own stream + group.
    mirror = CompositionEventConsumer(
        settings.redis_url, pool,
        book_base_url=settings.book_internal_url,
        jwt_secret=settings.jwt_secret,
        consumer_name="worker-1",
    )
    mirror_task = asyncio.create_task(mirror.run())
    logger.info("written-verdict mirror: consuming %s", CHAPTER_STREAM)

    # C-merge C2 — the manuscript-parts → structure_node mirror. Its own stream + group; deleted at C4.
    parts_mirror = PartsMirrorConsumer(
        settings.redis_url, pool,
        book_base_url=settings.book_internal_url,
        internal_token=settings.internal_service_token,
        consumer_name="worker-1",
    )
    parts_mirror_task = asyncio.create_task(parts_mirror.run())
    logger.info("parts mirror: consuming %s", BOOK_STREAM)

    try:
        await consumer.run()
    finally:
        sweeper.cancel()
        mirror_task.cancel()
        parts_mirror_task.cancel()
        await consumer.close()
        await mirror.close()
        await parts_mirror.close()
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
