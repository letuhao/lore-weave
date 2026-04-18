"""worker-ai entry point.

Async poll loop that picks up running extraction jobs and processes
them. Not a web server — this is a background worker.

    python -m app.main
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from app.clients import BookClient, KnowledgeClient
from app.config import settings
from app.runner import poll_and_run

logger = logging.getLogger("worker-ai")


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    logger.info("worker-ai starting (poll_interval=%.1fs)", settings.poll_interval_s)

    pool = await asyncpg.create_pool(
        settings.knowledge_db_url,
        min_size=2,
        max_size=5,
        command_timeout=30,
    )

    knowledge_client = KnowledgeClient(
        base_url=settings.knowledge_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.extract_item_timeout_s,
    )
    book_client = BookClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.book_client_timeout_s,
    )

    try:
        while True:
            try:
                count = await poll_and_run(pool, knowledge_client, book_client)
                if count > 0:
                    logger.info("Poll cycle: processed %d job(s)", count)
            except Exception:
                logger.exception("Poll cycle error (will retry)")

            await asyncio.sleep(settings.poll_interval_s)
    except asyncio.CancelledError:
        logger.info("worker-ai shutting down")
    finally:
        await knowledge_client.aclose()
        await book_client.aclose()
        await pool.close()
        logger.info("worker-ai stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
