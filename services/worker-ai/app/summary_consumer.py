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

import logging
from typing import TYPE_CHECKING

from loreweave_jobs import BaseTerminalConsumer

if TYPE_CHECKING:
    from app.clients import KnowledgeClient

__all__ = ["SummaryConsumer", "SUMMARY_STREAM_NAME"]

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


class _SummaryRetryable(Exception):
    """Internal — a retryable summary dispatch outcome. Raised from ``handle`` so the base
    consumer leaves the message un-acked for redelivery (then bounded-retry → poison-ack)."""


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
        # E0-3 2a-2 — optional BYOK billing identity. Forward redis → HTTP so
        # the /summarize-message endpoint bills the collaborator's key. Absent
        # (old messages / owner-triggered) → "" ⇒ legacy owner path.
        for _bk in ("billing_user_id", "billing_llm_model", "billing_embedding_model"):
            _bv = _get_field(fields, _bk)
            payload[_bk] = _decode_field(_bv) if _bv is not None else ""
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


class SummaryConsumer(BaseTerminalConsumer):
    """extraction.summarize consumer on the shared transport scaffold. ``start_id="0"``
    (process the backlog). The business fold ``_dispatch_one_message`` returns whether to
    ack (success / malformed-poison-drop / non-retryable error) → ``handle`` returns → the
    base acks; a RETRYABLE error → ``handle`` raises ``_SummaryRetryable`` → the base leaves
    it un-acked for redelivery (bounded retry then poison-ack).

    Behaviour note: summaries are re-derivable, so a bounded drop after ``max_retries`` on a
    persistently-failing message is acceptable — and the base adds the startup PEL drain
    this hand-rolled consumer lacked (it previously never re-drove un-acked messages)."""

    stream = SUMMARY_STREAM_NAME
    start_id = "0"
    consumer_name_prefix = "summary"
    retry_prefix = "worker-ai:summary:retry"

    def __init__(
        self,
        redis_url: str,
        knowledge_client: "KnowledgeClient",
        *,
        consumer_group: str,
        consumer_name: str | None = None,
        block_ms: int = 5000,
    ) -> None:
        self.group = consumer_group   # runtime group — set before the base validates it
        self.block_ms = block_ms
        super().__init__(redis_url, consumer_name=consumer_name)
        self._kc = knowledge_client

    async def handle(self, fields: dict) -> None:
        should_ack = await _dispatch_one_message(
            knowledge_client=self._kc, fields=fields, message_id="(summary)",
        )
        if not should_ack:
            raise _SummaryRetryable()  # retryable → leave un-acked (base redelivery)
