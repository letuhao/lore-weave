"""P3 D-P3-WORKER-AI-CONSUMER-WIRING — Redis Stream consumer for
extraction.summarize.

Pairs with knowledge-service's `/internal/extraction/summarize-message`
endpoint. Loop:

  1. XREADGROUP from `extraction.summarize` (consumer group).
  2. For each message: deserialize fields → POST to knowledge-service.
  3. On 200 (or non-retryable error response): XACK the message.
  4. On retryable error: leave un-ACKed; Redis re-delivers via PEL
     after `XAUTOCLAIM` or the next consumer restart.

Group creation is idempotent (`MKSTREAM`) so the stream and the group
both materialize on first run.

Lifecycle: the consumer task runs concurrently with the existing
extraction-job poll loop via `asyncio.gather` in `app.main`. A
`CancelledError` propagates from shutdown and the loop exits cleanly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

import redis.asyncio as aioredis

if TYPE_CHECKING:
    from app.clients import KnowledgeClient

__all__ = ["consume_summary_stream", "SUMMARY_STREAM_NAME"]

logger = logging.getLogger(__name__)

# Must match SUMMARY_STREAM_NAME in knowledge-service's
# app/jobs/summary_enqueue.py — drift would silently break delivery.
SUMMARY_STREAM_NAME = "extraction.summarize"

# Required string-typed fields on every stream message.
_REQUIRED_FIELDS = (
    "level", "node_path", "node_id", "book_id",
    "user_id", "job_id", "model_ref", "embedding_model_uuid",
    "embedding_dimension",
)


def _decode_field(v) -> str:
    """Redis returns bytes by default; tolerate bytes or str."""
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v) if v is not None else ""


def _get_field(fields: dict, key: str):
    """Read `key` from fields tolerating both bytes-keyed (real Redis)
    and string-keyed (decoded) dicts."""
    if key in fields:
        return fields[key]
    return fields.get(key.encode("utf-8"))


async def _ensure_consumer_group(
    client: aioredis.Redis, stream: str, group: str,
) -> None:
    """Idempotently create the consumer group (MKSTREAM bootstraps the
    stream if no producer has XADDed yet)."""
    try:
        await client.xgroup_create(
            name=stream, groupname=group, id="0", mkstream=True,
        )
        logger.info("Created consumer group %s on %s", group, stream)
    except aioredis.ResponseError as exc:
        # BUSYGROUP = already exists — expected on every restart.
        if "BUSYGROUP" in str(exc):
            logger.debug("Consumer group %s exists on %s", group, stream)
            return
        raise


async def _dispatch_one_message(
    *,
    knowledge_client: "KnowledgeClient",
    fields: dict,
    message_id: str,
) -> bool:
    """Decode + POST one message; return True if the caller should XACK.

    Validation failures (malformed message) → XACK (not retryable —
    re-delivery would just re-fail). Transient HTTP errors → leave
    un-ACKed so the PEL surfaces the message on next claim.
    """
    try:
        payload = {k: _decode_field(_get_field(fields, k)) for k in _REQUIRED_FIELDS}
        # project_id is optional (may be empty for legacy paths).
        project_id_raw = _get_field(fields, "project_id")
        payload["project_id"] = (
            _decode_field(project_id_raw) if project_id_raw is not None else ""
        )
        # Numeric fields — tolerate missing/empty.
        payload["embedding_dimension"] = int(payload["embedding_dimension"] or "0")
        payload["retry_at_epoch"] = float(
            _decode_field(_get_field(fields, "retry_at_epoch")) or "0"
        )
        payload["retried_n"] = int(
            _decode_field(_get_field(fields, "retried_n")) or "0"
        )
        if payload["embedding_dimension"] <= 0:
            raise ValueError(
                f"embedding_dimension must be > 0, got {payload['embedding_dimension']}"
            )
        for k in _REQUIRED_FIELDS:
            if k == "embedding_dimension":
                continue
            if not payload[k]:
                raise ValueError(f"missing required field {k!r}")
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning(
            "summary stream msg %s rejected as malformed: %s",
            message_id, exc,
        )
        return True  # ACK to drop poison messages off the stream

    result = await knowledge_client.process_summarize_message(**payload)

    if result.error:
        if result.retryable:
            logger.warning(
                "summary msg %s retryable error: %s",
                message_id, result.error,
            )
            return False  # leave un-ACKed
        logger.error(
            "summary msg %s non-retryable error: %s",
            message_id, result.error,
        )
        # Drop poison off the stream so the PEL doesn't grow forever.
        return True

    logger.info(
        "summary msg %s processed level=%s node=%s cache_hit=%s "
        "race_winner=%s re_enqueued=%s",
        message_id, result.level, result.node_id,
        result.cache_hit, result.race_winner, result.re_enqueued,
    )
    return True


async def consume_summary_stream(
    knowledge_client: "KnowledgeClient",
    *,
    redis_url: str,
    consumer_group: str,
    consumer_name: str,
    block_ms: int = 5000,
    stream: str = SUMMARY_STREAM_NAME,
) -> None:
    """Long-running consumer task.

    Cancel-safe: shutdown raises `CancelledError` from `xreadgroup`;
    the finally-block closes the Redis client.
    """
    client = aioredis.from_url(redis_url)
    try:
        await _ensure_consumer_group(client, stream, consumer_group)
        logger.info(
            "summary consumer started group=%s name=%s stream=%s",
            consumer_group, consumer_name, stream,
        )
        while True:
            try:
                # Read new (>) messages first; the PEL handler below
                # picks up anything we left un-ACKed last cycle.
                resp = await client.xreadgroup(
                    groupname=consumer_group,
                    consumername=consumer_name,
                    streams={stream: ">"},
                    count=10,
                    block=block_ms,
                )
            except asyncio.CancelledError:
                raise
            except aioredis.RedisError as exc:
                logger.warning(
                    "summary consumer XREADGROUP failed (will retry): %s", exc,
                )
                # Backoff so a flapping Redis doesn't spin the loop.
                await asyncio.sleep(1.0)
                continue

            if not resp:
                continue

            for _stream_name, messages in resp:
                for message_id, fields in messages:
                    message_id_str = (
                        message_id.decode("utf-8")
                        if isinstance(message_id, bytes)
                        else str(message_id)
                    )
                    try:
                        should_ack = await _dispatch_one_message(
                            knowledge_client=knowledge_client,
                            fields=fields,
                            message_id=message_id_str,
                        )
                    except asyncio.CancelledError:
                        raise
                    except Exception:
                        # Unhandled error — leave un-ACKed for retry,
                        # log + continue to next message.
                        logger.exception(
                            "summary consumer dispatch crashed on msg %s",
                            message_id_str,
                        )
                        should_ack = False

                    if should_ack:
                        try:
                            await client.xack(stream, consumer_group, message_id)
                        except aioredis.RedisError as exc:
                            logger.warning(
                                "summary consumer XACK failed for %s: %s",
                                message_id_str, exc,
                            )

    except asyncio.CancelledError:
        logger.info("summary consumer cancelled, shutting down")
        raise
    finally:
        await client.aclose()
