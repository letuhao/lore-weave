"""worker-ai entry point.

Async poll loop that picks up running extraction jobs and processes
them. Not a web server — this is a background worker.

    python -m app.main
"""

from __future__ import annotations

import asyncio
import logging

import asyncpg
from loreweave_obs import setup_logging, setup_tracing

from app.clients import (
    BookClient,
    ChatClient,
    GlossaryClient,
    KnowledgeClient,
    ProviderRegistryClient,
    UsageBillingClient,
)
from app.config import settings
from app.llm_client import close_llm_client, get_llm_client
from app.metrics import start_metrics_server
from app.runner import (
    consume_filter_reload_signal,
    hydrate_precision_filter_config_from_redis,
    poll_and_run,
    sweep_stalled_jobs,
)
from app.summary_consumer import SummaryConsumer
from app.wake import WakeWaiter

logger = logging.getLogger("worker-ai")


async def main() -> None:
    setup_logging("worker-ai", level=settings.log_level)  # P2·A2a — shared JSON logging

    # Phase 6c-γ — OpenTelemetry: instrument httpx so the loreweave_llm SDK
    # calls emit CLIENT spans. No app — worker-ai has no HTTP server. No-op
    # when OTEL_EXPORTER_OTLP_ENDPOINT is unset.
    setup_tracing("worker-ai")

    logger.info("worker-ai starting (poll_interval=%.1fs)", settings.poll_interval_s)

    # Cycle 73h — Prometheus /metrics endpoint (daemon thread, runs
    # alongside asyncio loop). No-op when METRICS_PORT=0.
    start_metrics_server(settings.metrics_port)

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
    # FD-2 — chat-service client: fetch a chat turn's text so the chat drain branch
    # extracts real knowledge (was a text="" no-op).
    chat_client = ChatClient(
        base_url=settings.chat_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.chat_client_timeout_s,
    )
    # C12c-a: client for the scope='glossary_sync' branch + all-scope tail.
    glossary_client = GlossaryClient(
        base_url=settings.glossary_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.glossary_client_timeout_s,
    )
    # FD-27 — provider-registry model-info client for the once-per-job
    # reasoning-model advisory (best-effort; failures degrade the advisory off).
    provider_client = ProviderRegistryClient(
        base_url=settings.provider_registry_internal_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.provider_registry_client_timeout_s,
    )
    # WS-2.8 — usage-billing client for the distiller's daily-cap degrade pre-check (fail-open).
    usage_billing_client = UsageBillingClient(
        base_url=settings.usage_billing_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.usage_billing_client_timeout_s,
    )
    # Phase 4b-γ — loreweave_llm SDK wrapper for in-process Pass 2
    # extraction. Touched here so SDK construction errors (bad
    # base_url, missing internal_token) surface at startup rather
    # than at the first job.
    llm_client = get_llm_client()

    # FD-22 — block on the knowledge-service wake stream between poll cycles so
    # a freshly started job is picked up immediately. None (disabled / no
    # redis_url) → plain sleep. The poll body is unchanged: the wake only
    # shortens the wait, the atomic claim in poll_and_run still owns correctness.
    wake_waiter: WakeWaiter | None = None
    if settings.extraction_wake_enabled and settings.redis_url:
        wake_waiter = WakeWaiter(settings.redis_url, settings.extraction_wake_stream)
        logger.info("FD-22: extraction wake enabled (stream=%s)", settings.extraction_wake_stream)
    else:
        logger.info("FD-22: extraction wake disabled — plain polling")

    async def _job_poll_loop() -> None:
        while True:
            try:
                count = await poll_and_run(
                    pool, knowledge_client, llm_client,
                    book_client, glossary_client, chat_client, provider_client,
                )
                if count > 0:
                    logger.info("Poll cycle: processed %d job(s)", count)
                # gap #3 — generic stall backstop (cheap indexed query; only acts on
                # jobs with no progress past the generous threshold, so safe per cycle).
                _stalled = await sweep_stalled_jobs(
                    pool, stall_minutes=settings.extraction_stall_minutes,
                )
                if _stalled:
                    logger.warning("stall sweep: failed %d stalled extraction job(s)", _stalled)
            except Exception:
                logger.exception("Poll cycle error (will retry)")

            if wake_waiter is not None:
                if await wake_waiter.wait(settings.poll_interval_s):
                    logger.debug("FD-22: woke on extraction signal — polling now")
            else:
                await asyncio.sleep(settings.poll_interval_s)

    # P3 D-P3-WORKER-AI-CONSUMER-WIRING: run the extraction-job poll loop
    # AND the Redis Stream consumer for `extraction.summarize` in
    # parallel. asyncio.gather propagates cancellation to both tasks on
    # shutdown; either task crashing brings the worker down (no silent
    # half-running state).
    coroutines = [_job_poll_loop()]
    if settings.summary_consumer_enabled:
        _summary_consumer = SummaryConsumer(
            settings.redis_url,
            knowledge_client,
            consumer_group=settings.summary_consumer_group,
            consumer_name=settings.summary_consumer_name,
            block_ms=settings.summary_consumer_block_ms,
        )
        coroutines.append(_summary_consumer.run())
    else:
        logger.info("summary consumer disabled via config")

    # A1 / P-10 (spec 06 §Q2) — the "End my day" distiller trigger. Consumes `assistant.distill`
    # jobs and runs the built distiller pipeline (day-window read → map-reduce → diary-entry write)
    # with the real chat/book clients + the provider-gateway LLM adapter. Config-gated so it is inert
    # until an assistant is provisioned to enqueue.
    if settings.distill_consumer_enabled:
        from app.distill_consumer import DistillConsumer
        _distill_consumer = DistillConsumer(
            settings.redis_url,
            chat_client,
            book_client,
            llm_client,
            consumer_group=settings.distill_consumer_group,
            consumer_name=settings.distill_consumer_name,
            block_ms=settings.summary_consumer_block_ms,
            knowledge_client=knowledge_client,  # WS-2.3 — divert distilled facts to the KG inbox
            billing_client=usage_billing_client,  # WS-2.8 — daily-cap degrade pre-check
        )
        coroutines.append(_distill_consumer.run())
        logger.info("A1: assistant.distill consumer started (group=%s)", settings.distill_consumer_group)
    else:
        logger.info("distill consumer disabled via config")

    # LLM re-arch Phase 2b WX-T3b — decoupled-extraction terminal-event consumer.
    # Started only when the decouple flag is on (inert otherwise — no decoupled
    # chunks exist so every event would ack+ignore). Drives entity→trio→persist off
    # loreweave:events:llm_job_terminal for chapters the runner released.
    if settings.extraction_decouple_enabled and settings.redis_url:
        _extract_consumer_name = f"{settings.summary_consumer_name}-extract"
        if settings.extraction_consumer_use_sdk:
            # Unified Job Control Plane P1 — the migrated path on the shared base. Same
            # group/consumer_name (PEL continuity) + the verbatim fold/sweep; flip only
            # after a live extraction E2E (money-path, default OFF).
            from app.llm_extract_consumer import ExtractTerminalConsumer
            _extract_consumer = ExtractTerminalConsumer(
                settings.redis_url, pool, knowledge_client, llm_client,
                consumer_name=_extract_consumer_name,
                block_ms=settings.summary_consumer_block_ms,
            )
            coroutines.append(_extract_consumer.run())
            logger.info("WX-T3b: decoupled-extraction consumer started (SDK base)")
            if settings.extraction_resume_sweep_interval_s > 0:
                coroutines.append(_extract_consumer.run_sweeper(
                    interval_s=settings.extraction_resume_sweep_interval_s,
                    timeout_s=settings.extraction_resume_sweep_timeout_s,
                    batch=settings.extraction_resume_sweep_batch,
                ))
                logger.info("WX Wave 1b: decoupled-extraction resume sweeper started (SDK base)")
        else:
            from app.llm_extract_consumer import (
                consume_llm_terminal_stream,
                run_resume_sweeper,
            )
            coroutines.append(consume_llm_terminal_stream(
                pool, knowledge_client, llm_client,
                redis_url=settings.redis_url,
                consumer_name=_extract_consumer_name,
                block_ms=settings.summary_consumer_block_ms,
            ))
            logger.info("WX-T3b: decoupled-extraction consumer started")
            # WX Wave 1b — the stuck-resume sweeper (runtime backstop for a stranded
            # resume_state: consumer poison, lost terminal event, or a submit→persist gap).
            if settings.extraction_resume_sweep_interval_s > 0:
                coroutines.append(run_resume_sweeper(
                    pool, knowledge_client, llm_client,
                    interval_s=settings.extraction_resume_sweep_interval_s,
                    timeout_s=settings.extraction_resume_sweep_timeout_s,
                    batch=settings.extraction_resume_sweep_batch,
                ))
                logger.info("WX Wave 1b: decoupled-extraction resume sweeper started")

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
        await chat_client.aclose()
        await glossary_client.aclose()
        await provider_client.aclose()
        await usage_billing_client.aclose()
        if wake_waiter is not None:
            await wake_waiter.aclose()
        await pool.close()
        logger.info("worker-ai stopped")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
