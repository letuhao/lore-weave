import json
import aio_pika
from .config import settings

_connection: aio_pika.abc.AbstractRobustConnection | None = None
_channel: aio_pika.abc.AbstractChannel | None = None
_jobs_exchange: aio_pika.abc.AbstractExchange | None = None
_events_exchange: aio_pika.abc.AbstractExchange | None = None


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

    # Extraction job queue
    extraction_q = await _channel.declare_queue("extraction.jobs", durable=True)

    # Bind queues to the jobs exchange — routing key must match what publishers use
    await jobs_q.bind(_jobs_exchange, routing_key="translation.job")
    await chapters_q.bind(_jobs_exchange, routing_key="translation.chapter")
    await extraction_q.bind(_jobs_exchange, routing_key="extraction.job")


async def close_broker() -> None:
    if _connection:
        await _connection.close()


async def publish(routing_key: str, body: dict) -> None:
    assert _jobs_exchange is not None, "Broker not connected"
    await _jobs_exchange.publish(
        aio_pika.Message(
            body=json.dumps(body).encode(),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
        ),
        routing_key=routing_key,
    )


async def publish_event(user_id: str, event: dict) -> None:
    assert _events_exchange is not None, "Broker not connected"
    await _events_exchange.publish(
        aio_pika.Message(
            body=json.dumps({**event, "user_id": user_id}).encode(),
            content_type="application/json",
        ),
        routing_key=f"user.{user_id}",
    )
