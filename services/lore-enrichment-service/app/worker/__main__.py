"""Resume-worker entrypoint: `python -m app.worker` (F-C14-1/051).

Runs as a separate compose service (lore-enrichment-worker) from the SAME image
as the API (CMD override), so it shares the runner/store/assembly code. Flag-
gated by RESUME_CONSUMER_ENABLED (default true) like worker-ai's consumer.
"""

from __future__ import annotations

import asyncio
import logging
import os

from app.config import settings
from app.db.pool import close_pool, create_pool
from app.worker.resume_consumer import consume_resume_stream

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
logger = logging.getLogger("lore_enrichment.worker")


async def _main() -> None:
    if os.environ.get("RESUME_CONSUMER_ENABLED", "true").lower() == "false":
        logger.info("RESUME_CONSUMER_ENABLED=false — resume worker idle")
        while True:  # keep the container up but inert
            await asyncio.sleep(3600)

    pool = await create_pool(settings.database_url)
    logger.info("resume worker: pool up, starting consumer")
    try:
        await consume_resume_stream(pool=pool, redis_url=settings.redis_url)
    finally:
        await close_pool()


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    except KeyboardInterrupt:
        pass
