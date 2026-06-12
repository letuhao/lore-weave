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
from app.worker.job_consumer import consume_jobs_stream, run_sweeper

logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("composition.worker")


async def _main() -> None:
    if not settings.composition_worker_enabled:
        logger.info("COMPOSITION_WORKER_ENABLED=false — worker idle")
        while True:  # keep the container up but inert
            await asyncio.sleep(3600)

    await create_pool(settings.composition_db_url)
    pool = get_pool()
    logger.info("composition worker: pool up, starting consumer + sweeper")
    sweeper = asyncio.create_task(
        run_sweeper(
            pool,
            interval_secs=settings.composition_job_sweep_secs,
            timeout_secs=settings.composition_job_sweep_timeout_secs,
        )
    )
    try:
        await consume_jobs_stream(pool=pool, redis_url=settings.redis_url)
    finally:
        sweeper.cancel()
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
