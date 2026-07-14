"""A1 / P-10 (spec 06 §Q2) — the "End my day" distiller trigger, PRODUCER side.

XADDs an `assistant.distill` job (FLAT fields, matching worker-ai's DistillConsumer._REQUIRED_FIELDS)
to Redis; worker-ai consumes it and runs the map-reduce → diary-entry pipeline. The distiller is a
non-agentic LLM pipeline, so a Redis-stream job is the right shape (not an MCP tool).
"""
from __future__ import annotations

import logging
from typing import Any

from app.config import settings

logger = logging.getLogger(__name__)

# MUST match worker-ai app/distill_consumer.DISTILL_STREAM_NAME — drift silently breaks delivery.
DISTILL_STREAM = "assistant.distill"
# MUST match worker-ai app/reextract_consumer.REEXTRACT_STREAM_NAME.
REEXTRACT_STREAM = "assistant.reextract"

_redis: Any = None


def _get_redis() -> Any:
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis
        _redis = aioredis.from_url(settings.redis_url, decode_responses=True)
    return _redis


async def enqueue_distill(
    *,
    user_id: str,
    book_id: str,
    entry_date: str,
    entry_zone: str,
    language: str,
    model_source: str,
    model_ref: str,
    trace_id: str | None = None,
) -> str:
    """Enqueue one "End my day" distill job. Returns the Redis message id. Raises on a Redis error
    (the caller decides whether to 5xx — a lost enqueue means the day is silently never journaled,
    so unlike best-effort analytics this must NOT be swallowed)."""
    fields = {
        "user_id": user_id,
        "book_id": book_id,
        "entry_date": entry_date,
        "entry_zone": entry_zone,
        "language": language,
        "model_source": model_source,
        "model_ref": model_ref,
    }
    if trace_id:
        fields["trace_id"] = trace_id
    r = _get_redis()
    msg_id = await r.xadd(DISTILL_STREAM, fields, maxlen=10000, approximate=True)
    logger.info("enqueued assistant.distill user=%s book=%s date=%s msg=%s",
                user_id, book_id, entry_date, msg_id)
    return msg_id if isinstance(msg_id, str) else str(msg_id)


async def enqueue_reextract(
    *,
    user_id: str,
    book_id: str,
    entry_date: str,
    body: str,
    language: str,
    model_source: str,
    model_ref: str,
    trace_id: str | None = None,
) -> str:
    """WS-2.6a legs 2+3 (D17) — enqueue a CORRECTION re-extract job. Carries the corrected entry `body`
    (the same bytes the caller amended in book-service, so the worker needs no read-back and the
    re-extract is race-free) + the distill model. worker-ai's ReextractConsumer re-extracts the facts to
    the inbox (leg 2) and invalidates the day's superseded facts (leg 3). Returns the Redis message id;
    RAISES on a Redis error — a lost enqueue means the correction never reconciles (recall keeps showing
    the wrong fact), so the caller must surface it, not swallow it."""
    fields = {
        "user_id": user_id,
        "book_id": book_id,
        "entry_date": entry_date,
        "body": body,
        "language": language,
        "model_source": model_source,
        "model_ref": model_ref,
    }
    if trace_id:
        fields["trace_id"] = trace_id
    r = _get_redis()
    msg_id = await r.xadd(REEXTRACT_STREAM, fields, maxlen=10000, approximate=True)
    logger.info("enqueued assistant.reextract user=%s book=%s date=%s msg=%s",
                user_id, book_id, entry_date, msg_id)
    return msg_id if isinstance(msg_id, str) else str(msg_id)
