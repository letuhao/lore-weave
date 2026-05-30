"""worker-ai entry point.

Async poll loop that picks up running extraction jobs and processes
them. Not a web server — this is a background worker.

    python -m app.main
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
from loreweave_obs import setup_tracing

from app.clients import BookClient, GlossaryClient, KnowledgeClient
from app.config import settings
from app.llm_client import close_llm_client, get_llm_client
from app.runner import (
    consume_filter_reload_signal,
    hydrate_precision_filter_config_from_redis,
    poll_and_run,
)
from app.summary_consumer import consume_summary_stream

logger = logging.getLogger("worker-ai")


async def main() -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Phase 6c-γ — OpenTelemetry: instrument httpx so the loreweave_llm SDK
    # calls emit CLIENT spans. No app — worker-ai has no HTTP server. No-op
    # when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
    setup_tracing("worker-ai")

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
        # P3 D-P3-WORKER-AI-CONSUMER-WIRING: summarize-message is an
        # LLM + embed + persist round-trip; cold local models can run
        # minutes. Separate, longer timeout per
        # `feedback_polling_sdk_http_client_timeout_trap`.
        summarize_message_timeout_s=settings.summary_dispatch_timeout_s,
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

    async def _job_poll_loop() -> None:
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

    # P3 D-P3-WORKER-AI-CONSUMER-WIRING: run the extraction-job poll loop
    # AND the Redis Stream consumer for `extraction.summarize` in
    # parallel. asyncio.gather propagates cancellation to both tasks on
    # shutdown; either task crashing brings the worker down (no silent
    # half-running state).
    coroutines = [_job_poll_loop()]
    if settings.summary_consumer_enabled:
        coroutines.append(consume_summary_stream(
            knowledge_client,
            redis_url=settings.redis_url,
            consumer_group=settings.summary_consumer_group,
            consumer_name=settings.summary_consumer_name,
            block_ms=settings.summary_consumer_block_ms,
        ))
    else:
        logger.info("summary consumer disabled via config")

    # Cycle 73f — runtime filter config reload. Subscribes to Redis
    # pubsub; on each signal, re-reads the Redis config key + atomically
    # swaps module-level `_PRECISION_FILTER_CONFIG`. Resilient: SDK
    # subscriber has outer try/except with backoff. Skip gracefully if
    # redis_url is empty (dev/test without Redis).
    #
    # r3 H1 fold: hydrate first (one-shot Redis GET to seed cache from
    # any active ops-override) — without this, worker restart silently
    # reverts to env defaults regardless of Redis state. Symmetric with
    # KS lifespan hydrate (r2 H1 fold).
    if settings.redis_url:
        await hydrate_precision_filter_config_from_redis(settings.redis_url)
        coroutines.append(consume_filter_reload_signal(settings.redis_url))
        logger.info("cycle 73f: filter reload hydrate + subscriber started")
    else:
        logger.info("cycle 73f: filter reload subscriber skipped (no redis_url)")

    try:
        await asyncio.gather(*coroutines)
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
