"""video-gen terminal-event worker entrypoint: `python -m app.worker` (Phase 3 M5).

Runs as a separate compose service (video-gen-worker) from the SAME image as the
API (CMD override), sharing the router's download/store + record_usage helpers.
Flag-gated by VIDEO_GEN_DECOUPLE_ENABLED (default false → idle, so the container
stays healthy but inert until the decoupled path is turned on).
"""

from __future__ import annotations

import asyncio
import logging

from loreweave_llm import Client
from loreweave_obs import setup_logging

from app.config import settings
from app.db.migrate import run_migrations
from app.db.pool import close_pool, create_pool
from app.routers.generate import bootstrap_minio
from app.worker.consumer import VideoGenTerminalConsumer

setup_logging("video-gen-service")  # P2·A2a — shared JSON logging + dual trace ids
logger = logging.getLogger("video-gen.worker")


async def _main() -> None:
    if not settings.video_gen_decouple_enabled:
        logger.info("VIDEO_GEN_DECOUPLE_ENABLED=false — worker idle")
        while True:  # keep the container up but inert
            await asyncio.sleep(3600)

    # The consumer downloads finished videos into MinIO — bootstrap the bucket
    # (best-effort; ensure_bucket_ready self-heals on the first store).
    bootstrap_minio()
    pool = await create_pool(settings.video_gen_db_url)
    await run_migrations(pool)
    sdk = Client(
        base_url=settings.provider_registry_internal_url,
        auth_mode="internal",
        internal_token=settings.internal_service_token,
    )
    consumer = VideoGenTerminalConsumer(settings.redis_url, pool, sdk)
    logger.info("video-gen worker: pool up, starting consumer + sweeper")
    consumer_task = asyncio.create_task(consumer.run())
    sweeper_task = asyncio.create_task(
        consumer.run_sweeper(
            interval_s=settings.video_gen_job_sweep_secs,
            timeout_s=settings.video_gen_job_sweep_timeout_secs,
            batch=20,
        )
    )
    try:
        await consumer_task
    finally:
        await consumer.stop()
        for task in (consumer_task, sweeper_task):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        await sdk.aclose()
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
