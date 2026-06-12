"""Resume-worker entrypoint: `python -m app.worker` (F-C14-1/051).

Runs as a separate compose service (lore-enrichment-worker) from the SAME image
as the API (CMD override), so it shares the runner/store/assembly code. Flag-
gated by RESUME_CONSUMER_ENABLED (default true) like worker-ai's consumer.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.compose.compose_task import run_compose_task_sweeper
from app.config import settings
from app.db.pool import close_pool, create_pool
from app.worker.heartbeat import heartbeat_loop
from app.worker.reaper import reaper_loop
from app.worker.resume_consumer import consume_resume_stream

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lore_enrichment.worker")


async def _main() -> None:
    # LE-062: a background heartbeat task drives the compose liveness check (the
    # worker has no HTTP server). Started in BOTH branches so even an inert
    # (consumer-disabled) container reports healthy rather than a false unhealthy.
    heartbeat = asyncio.create_task(heartbeat_loop())

    if os.environ.get("RESUME_CONSUMER_ENABLED", "true").lower() == "false":
        logger.info("RESUME_CONSUMER_ENABLED=false — resume worker idle")
        try:
            while True:  # keep the container up but inert
                await asyncio.sleep(3600)
        finally:
            heartbeat.cancel()
        return

    pool = await create_pool(settings.database_url)
    logger.info("resume worker: pool up, starting consumer")
    # Reaper (D-COMPOSE-S3-UPLOAD-REAPER / D-COMPOSE-CONTEXT-CORPUS-SCOPE): a
    # periodic best-effort cleanup of stale uploads / orphan objects / ephemeral
    # corpora. Runs concurrently with the resume consumer; cancelled on shutdown.
    reaper = (
        asyncio.create_task(reaper_loop(pool))
        if settings.reaper_enabled
        else None
    )
    # Compose-task stuck sweeper (D-M2-COMPOSE-TASK-RACE / D-M2-COMPOSE-TASK-SWEEPER):
    # re-drives enrichment_compose_task rows stranded in ('pending','running') past the
    # timeout (a redis-miss at submit, or a worker crash mid-compute). Runs concurrently
    # with the resume consumer; the idempotent FOR-UPDATE claim makes the two safe.
    # interval<=0 disables it (run_compose_task_sweeper returns immediately).
    compose_sweeper = asyncio.create_task(
        run_compose_task_sweeper(
            pool,
            interval_s=settings.compose_task_sweep_interval_s,
            timeout_s=settings.compose_task_sweep_timeout_s,
            batch=settings.compose_task_sweep_batch,
        )
    )
    try:
        await consume_resume_stream(pool=pool, redis_url=settings.redis_url)
    finally:
        heartbeat.cancel()
        if reaper is not None:
            reaper.cancel()
        compose_sweeper.cancel()
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
