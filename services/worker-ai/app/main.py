"""worker-ai entry point.

Async poll loop that picks up running extraction jobs and processes
them. Not a web server — this is a background worker.

    python -m app.main
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg

from app.clients import BookClient, GlossaryClient, KnowledgeClient
from app.config import settings
from app.llm_client import close_llm_client, get_llm_client
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
        # Phase 4b-γ: persist-pass2 is a thin Neo4j-write endpoint —
        # bounded latency. The legacy 120s extract_item_timeout_s no
        # longer gates the LLM stage (worker-ai runs LLM in-process
        # via the SDK with no overall wall-clock cap).
        timeout_s=settings.persist_pass2_timeout_s,
    )
    book_client = BookClient(
        base_url=settings.book_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.book_client_timeout_s,
    )
    # C12c-a: client for the scope='glossary_sync' branch + all-scope tail.
    glossary_client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.glossary_client_timeout_s,
    )
    # Phase 4b-γ — loreweave_llm SDK wrapper for in-process Pass 2
    # extraction. Touched here so SDK construction errors (bad
    # base_url, missing internal_token) surface at startup rather
    # than at the first job.
    llm_client = get_llm_client()

    try:
        while True:
            try:
                count = await poll_and_run(
                    pool, knowledge_client, llm_client,
                    book_client, glossary_client,
                )
                if count > 0:
                    logger.info("Poll cycle: processed %d job(s)", count)
            except Exception:
                logger.exception("Poll cycle error (will retry)")

            await asyncio.sleep(settings.poll_interval_s)
    except asyncio.CancelledError:
        logger.info("worker-ai shutting down")
    finally:
        await close_llm_client()
        await knowledge_client.aclose()
        await book_client.aclose()
        await glossary_client.aclose()
        await pool.close()
        logger.info("worker-ai stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
