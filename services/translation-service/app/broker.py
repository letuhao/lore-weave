import json
import aio_pika
from .config import settings

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_jobs_exchange: aio_pika.abc.AbstractExchange | None = None
_events_exchange: aio_pika.abc.AbstractExchange | None = None

# S3b (G6) — exponential-backoff retry ladder for transient chapter failures.
# One fixed-TTL rung per retry attempt (matches worker _MAX_TRANSIENT_RETRIES=3):
# 1s → 2s → 4s. The worker publishes a transient retry to the rung for its
# attempt; the rung's x-message-ttl delays it, then it dead-letters back to
# `translation.chapters` for a fresh pickup. Plugin-free (stock RabbitMQ).
# Per-rung FIXED ttl (not per-message) avoids the head-of-line-blocking gotcha
# where a long-TTL message at the queue head stalls shorter ones behind it.
CHAPTER_RETRY_DELAYS_MS = (1000, 2000, 4000)


def chapter_retry_queue_name(delay_ms: int) -> str:
    return f"translation.chapters.retry.{delay_ms}"


def chapter_retry_queue_for_attempt(retry_count: int) -> str:
    """Rung for the message's CURRENT retry_count (0-based). Clamps to the last
    rung so a count beyond the ladder still gets the max delay."""
    idx = min(retry_count, len(CHAPTER_RETRY_DELAYS_MS) - 1)
    return chapter_retry_queue_name(CHAPTER_RETRY_DELAYS_MS[idx])


async def connect_broker() -> None:
    global _connection, _channel, _jobs_exchange, _events_exchange
    _connection = await aio_pika.connect_robust(settings.rabbitmq_url)
    _channel = await _connection.channel()

    # Declare exchanges and cache references — avoids a passive-declare round-trip on every publish
    _jobs_exchange = await _channel.declare_exchange(
        "loreweave.jobs", aio_pika.ExchangeType.DIRECT, durable=True
    )
    _events_exchange = await _channel.declare_exchange(
        "loreweave.events", aio_pika.ExchangeType.TOPIC, durable=True
    )

    # Declare queues
    jobs_q = await _channel.declare_queue("translation.jobs", durable=True)
    chapters_q = await _channel.declare_queue(
        "translation.chapters",
        durable=True,
        arguments={
            "x-dead-letter-exchange": "",
            "x-dead-letter-routing-key": "translation.chapters.dlq",
            "x-message-ttl": 86_400_000,  # 24 hours
        },
    )
    await _channel.declare_queue("translation.chapters.dlq", durable=True)

    # S3b — backoff retry rungs. Each holds a transient retry for its fixed TTL,
    # then dead-letters back to translation.chapters (default exchange → queue
    # name) for a fresh pickup. Declared idempotently; args must stay stable.
    for _delay in CHAPTER_RETRY_DELAYS_MS:
        await _channel.declare_queue(
            chapter_retry_queue_name(_delay),
            durable=True,
            arguments={
                "x-message-ttl": _delay,
                "x-dead-letter-exchange": "",
                "x-dead-letter-routing-key": "translation.chapters",
            },
        )

    # Extraction job queue
    extraction_q = await _channel.declare_queue("extraction.jobs", durable=True)
    glossary_translate_q = await _channel.declare_queue("glossary_translate.jobs", durable=True)

    # Bind queues to the jobs exchange — routing key must match what publishers use
    await jobs_q.bind(_jobs_exchange, routing_key="translation.job")
    await chapters_q.bind(_jobs_exchange, routing_key="translation.chapter")
    await extraction_q.bind(_jobs_exchange, routing_key="extraction.job")
    await glossary_translate_q.bind(_jobs_exchange, routing_key="glossary_translate.job")


async def close_broker() -> None:
    if _connection:
        await _connection.close()


async def publish(routing_key: str, body: dict) -> None:
    assert _jobs_exchange is not None, "Broker not connected"
    await _jobs_exchange.publish(
        aio_pika.Message(
            # ML-5: ensure_ascii=False keeps CJK/Vietnamese prose in job bodies as
            # UTF-8 on the wire; the default (True) inflates it 2-3x to \uXXXX escapes.
            body=json.dumps(body, ensure_ascii=False).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=routing_key,
    )


async def publish_event(user_id: str, event: dict) -> None:
    assert _events_exchange is not None, "Broker not connected"
    await _events_exchange.publish(
        aio_pika.Message(
            # ML-5: ensure_ascii=False keeps CJK/Vietnamese prose in event bodies as
            # UTF-8 on the wire; the default (True) inflates it 2-3x to \uXXXX escapes.
            body=json.dumps({**event, "user_id": user_id}, ensure_ascii=False).encode(),
            content_type="application/json",
        ),
        routing_key=f"user.{user_id}",
    )
