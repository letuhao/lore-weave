"""
Translation worker entry point.
Consumes from two queues on a single AMQP connection:
  - translation.jobs     → coordinator (fast fan-out, requeue on failure)
  - translation.chapters → chapter worker (long AI call, DLQ on permanent failure)

Retry strategy for translation.chapters:
  - Transient errors (_TransientError): publish a NEW message with x-retry-count incremented.
    We must republish rather than nack(requeue=True) because RabbitMQ does not allow mutating
    headers on re-queue; acking the original and publishing a new message is the only way to
    increment the counter reliably.
  - After _MAX_TRANSIENT_RETRIES exhausted, ack the original and let the chapter stay failed
    (DB was already updated by handle_chapter_message before raising).
  - Permanent errors (Exception): ack and leave DB state as failed (already updated by handler).

Decouple invariant (D-2B-DECOUPLE-FLAG-COUPLING):
  The decoupled translate path is split across TWO processes that BOTH gate on the
  SAME ``translation_decouple_enabled`` flag but carry INDEPENDENT env:
    - this worker (submits decoupled chapters that release immediately), and
    - the API container's lifespan (runs the resume consumer + the stuck-resume sweeper
      off the LLM terminal-event stream).
  The hard invariant: **decouple ON in the worker ⇒ the terminal-resume consumer MUST be
  running in the API container, else submitted chapters never resume and stall** until the
  2h stale-chapter sweep marks them failed. Compose wires the same env to both by
  convention, but that is NOT enforcement. ``_assert_decouple_consumer_reachable()`` makes
  the coupling loud at startup: when the flag is on it best-effort probes for the resume
  consumer group on the terminal stream and emits an actionable WARNING if it's absent
  (never fatal — a co-start race is benign and self-heals).
"""
import asyncio
import json
import logging
from collections import Counter
from contextlib import suppress

import aio_pika

from app.config import settings
from app.database import create_pool, get_pool
from app.llm_client import close_llm_client, get_llm_client
from app.migrate import run_migrations
from app.broker import (
    connect_broker,
    publish,
    publish_event,
    chapter_retry_queue_for_attempt,
)
from app.llm_client import set_campaign_id
from app import fair_sched
from app.workers.coordinator import handle_job_message
from app.workers.chapter_worker import handle_chapter_message, _TransientError
from app.workers.extraction_worker import handle_extraction_job
from app.workers.glossary_translate_worker import handle_glossary_translate_job

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

_MAX_TRANSIENT_RETRIES = 3


async def _recover_stale_chapters(pool) -> None:
    """
    On worker startup: find chapter_translations stuck in 'running' for > 2 hours and
    mark them failed. This handles the rare case where a worker crashed after acking
    the AMQP message but before writing the result to the DB.

    Normal worker restarts are covered by AMQP redelivery (unacked messages are
    automatically requeued when the consumer disconnects), so this only catches
    the narrow crash-after-ack window.

    After marking chapters failed we must also increment failed_chapters on the parent
    job and attempt finalization, otherwise those jobs stay stuck in 'running' forever.
    """
    stale = await pool.fetch("""
        UPDATE chapter_translations
        SET status = 'failed', error_message = 'worker_restart', finished_at = now()
        WHERE status = 'running'
          AND started_at < now() - interval '2 hours'
        RETURNING job_id
    """)
    if not stale:
        return

    log.warning("Startup recovery: reset %d stale running chapter(s) to failed", len(stale))

    for job_id, count in Counter(r["job_id"] for r in stale).items():
        # Increment the job counter to match what we just marked failed
        await pool.execute(
            "UPDATE translation_jobs SET failed_chapters = failed_chapters + $1 WHERE job_id = $2",
            count, job_id,
        )
        # Attempt finalization — only succeeds if this was the last outstanding chapter
        await pool.execute(
            """UPDATE translation_jobs
               SET status = CASE
                     WHEN completed_chapters > 0 THEN 'partial'
                     ELSE 'failed'
                   END,
                   finished_at = now()
               WHERE job_id = $1
                 AND status = 'running'
                 AND (completed_chapters + failed_chapters) = total_chapters""",
            job_id,
        )


async def _assert_decouple_consumer_reachable() -> None:
    """D-2B-DECOUPLE-FLAG-COUPLING — the worker (this process) and the resume consumer +
    sweeper (the API container's lifespan) BOTH gate on ``translation_decouple_enabled``,
    but they're SEPARATE containers with independent env. The dangerous mismatch is
    worker-ON / API-OFF: this worker submits decoupled chapters that release immediately,
    but with no consumer (and no sweeper) running, those chapters never resume → they
    stall until the 2h stale-chapter sweep marks them failed.

    Best-effort startup guard: if the decouple flag is on, check that the resume
    consumer group exists on the terminal stream (the API consumer creates it on
    startup). Absent ⇒ a loud WARNING naming the invariant. Never fatal — a co-start
    race (API not up yet) is benign and self-heals, and a Redis hiccup must not block
    the worker. The check documents + surfaces the coupling before default-on."""
    if not settings.translation_decouple_enabled:
        return
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(settings.redis_url, decode_responses=True, socket_timeout=5)
        try:
            groups = await r.xinfo_groups("loreweave:events:llm_job_terminal")
            present = any(g.get("name") == "translation-llm-resume" for g in groups)
        except aioredis.ResponseError:
            present = False  # stream/group not created yet
        finally:
            await r.aclose()
        if present:
            log.info("decouple consumer group 'translation-llm-resume' present — resume path is covered")
        else:
            log.warning(
                "TRANSLATION_DECOUPLE_ENABLED is ON in the worker but the 'translation-llm-resume' "
                "consumer group was NOT found on loreweave:events:llm_job_terminal. Submitted "
                "decoupled chapters will STALL unless the API container runs the resume consumer + "
                "sweeper with the SAME flag. Ensure TRANSLATION_DECOUPLE_ENABLED matches across "
                "BOTH containers. (Benign if the API is merely starting after this worker.)"
            )
    except Exception:  # noqa: BLE001 — a startup advisory must never block the worker
        log.warning("could not verify decouple consumer reachability (non-fatal)", exc_info=True)


async def main() -> None:
    pool = await create_pool(settings.database_url)
    log.info("DB pool ready")

    await run_migrations(pool)
    log.info("Migrations applied")

    await _recover_stale_chapters(pool)
    await _assert_decouple_consumer_reachable()

    # connect_broker() declares all exchanges, queues, and bindings
    await connect_broker()
    log.info("Broker connected, topology declared")

    # Phase 4c-β: loreweave_llm SDK wrapper for in-process Pass 2
    # translation. Construction errors (bad base_url, missing
    # internal_token) surface here at startup instead of at the first
    # AMQP message.
    llm_client = get_llm_client()
    log.info("LLM client ready (provider-registry SDK)")

    # Separate connection for consuming — keeps publish and consume channels independent
    conn    = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=1)

    job_queue        = await channel.get_queue("translation.jobs")
    chapter_queue    = await channel.get_queue("translation.chapters")
    extraction_queue = await channel.get_queue("extraction.jobs")
    glossary_translate_queue = await channel.get_queue("glossary_translate.jobs")

    async def on_job(message: aio_pika.IncomingMessage) -> None:
        # Coordinator is fast (< 1s). Use process() for simple ack-on-success / requeue-on-error.
        async with message.process(requeue=True):
            msg = json.loads(message.body)
            log.info("Coordinator: job %s (%d chapters)", msg["job_id"], len(msg["chapter_ids"]))
            await handle_job_message(msg, get_pool(), publish, publish_event)
            log.info("Coordinator: job %s fanned out", msg["job_id"])

    async def on_chapter(message: aio_pika.IncomingMessage) -> None:
        # Manual ack/nack required — we need to inspect the error type AFTER the handler
        # has already updated the DB, then decide whether to retry or not.
        # Using message.process() here would double-nack when an exception escapes.
        retry_count = int((message.headers or {}).get("x-retry-count", 0))
        msg = json.loads(message.body)
        chapter_id = msg.get("chapter_id", "?")

        try:
            log.info(
                "Chapter worker: job %s chapter %s (retry %d)",
                msg["job_id"], chapter_id, retry_count,
            )
            await handle_chapter_message(msg, get_pool(), publish_event, llm_client, retry_count)
            log.info("Chapter worker: chapter %s done", chapter_id)
            await message.ack()
            # P5 NOTE: the WFQ slot is released at the per-chapter TERMINAL inside
            # _check_job_completion (sync: during this handler; decoupled: later in the
            # llm_terminal_consumer when the LLM work actually finishes) — NOT here at
            # submit/ack time, so the per-owner cap bounds in-flight LLM concurrency.

        except _TransientError as exc:
            # DB has already been updated to 'failed' by the handler before re-raising.
            # Republish as a new message with an incremented counter so the next worker
            # picks it up fresh. Ack the original to remove it from the queue.
            if retry_count < _MAX_TRANSIENT_RETRIES:
                # S3b (G6): route the retry through a fixed-TTL backoff rung
                # (1s→2s→4s) instead of republishing immediately. The rung
                # dead-letters back to translation.chapters after its TTL, so a
                # flapping upstream gets graduated backoff, not a tight retry
                # loop. x-retry-count survives the dead-letter (headers carry).
                retry_queue = chapter_retry_queue_for_attempt(retry_count)
                log.warning(
                    "Chapter %s transient error (retry %d/%d): %s — backing off via %s",
                    chapter_id, retry_count, _MAX_TRANSIENT_RETRIES, exc, retry_queue,
                )
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                        headers={**(message.headers or {}), "x-retry-count": retry_count + 1},
                    ),
                    routing_key=retry_queue,
                )
            else:
                log.error(
                    "Chapter %s exceeded %d retries, abandoning: %s",
                    chapter_id, _MAX_TRANSIENT_RETRIES, exc,
                )
            # Always ack the original — retry (if any) is a new message. (P5 slot release
            # happened inside handle_chapter_message's _check_job_completion call.)
            await message.ack()

        except Exception as exc:
            # Permanent error — DB already marked failed. Ack and move on. (P5 slot
            # release happened inside handle_chapter_message's _check_job_completion.)
            log.error("Chapter %s permanent error: %s", chapter_id, exc)
            await message.ack()

    async def on_extraction(message: aio_pika.IncomingMessage) -> None:
        # S4a: this consumer shares the process + llm_client with on_chapter, which
        # binds a campaign_id contextvar. Extraction jobs are NOT campaign-owned, so
        # clear it here — defends against a chapter's campaign_id leaking into an
        # extraction LLM call (mis-attribution) regardless of whether the AMQP lib
        # isolates context per message-task.
        set_campaign_id(None)
        async with message.process(requeue=True):
            msg = json.loads(message.body)
            log.info("Extraction worker: job %s (%d chapters)", msg["job_id"], len(msg["chapter_ids"]))
            await handle_extraction_job(msg, get_pool(), publish, publish_event, llm_client)
            log.info("Extraction worker: job %s done", msg["job_id"])

    async def on_glossary_translate(message: aio_pika.IncomingMessage) -> None:
        set_campaign_id(None)
        async with message.process(requeue=True):
            msg = json.loads(message.body)
            log.info("Glossary translate worker: job %s", msg["job_id"])
            await handle_glossary_translate_job(msg, get_pool(), publish_event, llm_client)
            log.info("Glossary translate worker: job %s done", msg["job_id"])

    await job_queue.consume(on_job)
    await chapter_queue.consume(on_chapter)
    await extraction_queue.consume(on_extraction)
    await glossary_translate_queue.consume(on_glossary_translate)
    log.info(
        "Worker ready — consuming translation.jobs, translation.chapters, "
        "extraction.jobs, glossary_translate.jobs",
    )

    # P5 — fair scheduling: when enabled, the coordinator enqueues chapter units into
    # the per-owner WFQ and THIS loop releases them round-robin → translation.chapter.
    # (Safe across replicas — dispatch is atomic in Redis.)
    dispatcher_task = None
    if settings.p5_sched_enabled:
        dispatcher_task = asyncio.create_task(fair_sched.run_dispatcher(publish))

    try:
        await asyncio.Future()  # run forever
    finally:
        if dispatcher_task is not None:
            dispatcher_task.cancel()
            with suppress(asyncio.CancelledError, Exception):
                await dispatcher_task
        # Phase 4c-β: best-effort SDK client teardown on shutdown
        # signal. Process-exit cleanup would handle httpx connections
        # anyway, but close_llm_client() drains them more gracefully.
        await close_llm_client()


if __name__ == "__main__":
    asyncio.run(main())
