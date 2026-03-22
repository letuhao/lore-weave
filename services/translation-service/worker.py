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
"""
import asyncio
import json
import logging
from collections import Counter

import aio_pika

from app.config import settings
from app.database import create_pool, get_pool
from app.broker import connect_broker, publish, publish_event
from app.workers.coordinator import handle_job_message
from app.workers.chapter_worker import handle_chapter_message, _TransientError

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


async def main() -> None:
    pool = await create_pool(settings.database_url)
    log.info("DB pool ready")

    await _recover_stale_chapters(pool)

    # connect_broker() declares all exchanges, queues, and bindings
    await connect_broker()
    log.info("Broker connected, topology declared")

    # Separate connection for consuming — keeps publish and consume channels independent
    conn    = await aio_pika.connect_robust(settings.rabbitmq_url)
    channel = await conn.channel()
    await channel.set_qos(prefetch_count=1)

    job_queue     = await channel.get_queue("translation.jobs")
    chapter_queue = await channel.get_queue("translation.chapters")

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
            await handle_chapter_message(msg, get_pool(), publish_event, retry_count)
            log.info("Chapter worker: chapter %s done", chapter_id)
            await message.ack()

        except _TransientError as exc:
            # DB has already been updated to 'failed' by the handler before re-raising.
            # Republish as a new message with an incremented counter so the next worker
            # picks it up fresh. Ack the original to remove it from the queue.
            if retry_count < _MAX_TRANSIENT_RETRIES:
                log.warning(
                    "Chapter %s transient error (retry %d/%d): %s — republishing",
                    chapter_id, retry_count, _MAX_TRANSIENT_RETRIES, exc,
                )
                await channel.default_exchange.publish(
                    aio_pika.Message(
                        body=message.body,
                        delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                        content_type="application/json",
                        headers={**(message.headers or {}), "x-retry-count": retry_count + 1},
                    ),
                    routing_key="translation.chapters",
                )
            else:
                log.error(
                    "Chapter %s exceeded %d retries, abandoning: %s",
                    chapter_id, _MAX_TRANSIENT_RETRIES, exc,
                )
            # Always ack the original — retry (if any) is a new message
            await message.ack()

        except Exception as exc:
            # Permanent error — DB already marked failed. Ack and move on.
            log.error("Chapter %s permanent error: %s", chapter_id, exc)
            await message.ack()

    await job_queue.consume(on_job)
    await chapter_queue.consume(on_chapter)
    log.info("Worker ready — consuming translation.jobs and translation.chapters")

    await asyncio.Future()  # run forever


if __name__ == "__main__":
    asyncio.run(main())
