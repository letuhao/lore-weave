"""WS-2.6a legs 2+3 (spec — D17 memory amendment) — the CORRECTION re-extract CONSUMER.

A producer (chat-service, driven by the gateway `POST /v1/assistant/correct`) XADDs an
`assistant.reextract` job carrying {user_id, book_id, entry_date, language, model_source, model_ref,
body}; this consumer re-extracts the corrected entry's facts and reconciles the day's graph
(`reextract_and_reconcile`). Mirrors DistillConsumer's transport contract exactly.

Retry contract (BaseTerminalConsumer): a RETRYABLE compute/transport error leaves the message
un-acked; every terminal state (reconciled / no_facts / paused / non-retryable error) acks. A malformed
message is acked (dropped) so the PEL never grows on poison. The `body` carries the corrected entry
text the gateway just amended (race-free: the same bytes it sent to book-service's amend), so the
worker needs no book-service read to know what the corrected day says.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from loreweave_jobs import BaseTerminalConsumer

from app.distill_job import make_distill_llm
from app.reextract_job import reextract_and_reconcile

if TYPE_CHECKING:
    from app.clients import KnowledgeClient, UsageBillingClient
    from app.llm_client import LLMClient

__all__ = ["ReextractConsumer", "REEXTRACT_STREAM_NAME", "run_one_reextract_message"]

logger = logging.getLogger(__name__)

# Must match the producer's stream name — drift silently breaks delivery.
REEXTRACT_STREAM_NAME = "assistant.reextract"

_REQUIRED_FIELDS = (
    "user_id", "book_id", "entry_date", "language", "model_source", "model_ref", "body",
)


def _decode(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v) if v is not None else ""


def _get(fields: dict, key: str):
    """Read `key` tolerating bytes-keyed (real Redis) and str-keyed (decoded) dicts."""
    if key in fields:
        return fields[key]
    return fields.get(key.encode("utf-8"))


class _ReextractRetryable(Exception):
    """Internal — a retryable re-extract outcome; raised so the base leaves the message un-acked."""


async def run_one_reextract_message(
    *,
    knowledge_client: "KnowledgeClient",
    llm_client: "LLMClient",
    fields: dict,
    billing_client: "UsageBillingClient | None" = None,
    message_id: str = "(reextract)",
) -> bool:
    """Decode one `assistant.reextract` message + run legs 2+3. Returns True to ACK.

    Malformed message → ACK (drop poison). A retryable error → return False (leave un-acked for
    redelivery). Any terminal state → ACK. Split out from the consumer class so it is unit-testable
    with fakes, no Redis."""
    try:
        p = {k: _decode(_get(fields, k)) for k in _REQUIRED_FIELDS}
        # Every field except body must be non-empty; an empty body is a caller bug (a correction always
        # has text — book-service's amend rejects an empty body), so treat it as poison, not a retry.
        for k in _REQUIRED_FIELDS:
            if not p[k]:
                raise ValueError(f"missing required field {k!r}")
        trace_id = _decode(_get(fields, "trace_id")) or None
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("reextract stream msg %s rejected as malformed: %s", message_id, exc)
        return True  # ACK to drop poison off the stream

    llm = make_distill_llm(
        llm_client,
        user_id=p["user_id"],
        model_source=p["model_source"],
        model_ref=p["model_ref"],
        trace_id=trace_id,
    )
    result = await reextract_and_reconcile(
        user_id=p["user_id"],
        book_id=p["book_id"],
        entry_date=p["entry_date"],
        body=p["body"],
        llm=llm,
        knowledge_client=knowledge_client,
        billing_client=billing_client,
    )
    status = result.get("status")
    if status == "error" and result.get("retryable"):
        logger.warning(
            "reextract msg %s retryable error (reason=%s) — leaving un-acked",
            message_id, result.get("reason"),
        )
        return False  # leave un-acked → base redelivers, then poison-acks
    logger.info(
        "reextract msg %s status=%s date=%s queued=%s invalidated=%s reason=%s",
        message_id, status, p["entry_date"], result.get("facts_queued"),
        result.get("facts_invalidated"), result.get("reason"),
    )
    return True


class ReextractConsumer(BaseTerminalConsumer):
    """`assistant.reextract` consumer on the shared transport scaffold (XREADGROUP + ack + bounded
    retry + startup PEL drain). `start_id="0"` processes the backlog so a correction submitted while
    the worker was down is still reconciled on restart."""

    stream = REEXTRACT_STREAM_NAME
    start_id = "0"
    consumer_name_prefix = "reextract"
    retry_prefix = "worker-ai:reextract:retry"

    def __init__(
        self,
        redis_url: str,
        knowledge_client: "KnowledgeClient",
        llm_client: "LLMClient",
        *,
        consumer_group: str,
        consumer_name: str | None = None,
        block_ms: int = 5000,
        billing_client: "UsageBillingClient | None" = None,
    ) -> None:
        self.group = consumer_group  # runtime group — set before the base validates it
        self.block_ms = block_ms
        super().__init__(redis_url, consumer_name=consumer_name)
        self._knowledge = knowledge_client
        self._llm = llm_client
        self._billing = billing_client  # WS-2.8 — daily-cap degrade pre-check (optional)

    async def handle(self, fields: dict) -> None:
        should_ack = await run_one_reextract_message(
            knowledge_client=self._knowledge, llm_client=self._llm,
            billing_client=self._billing, fields=fields, message_id="(reextract)",
        )
        if not should_ack:
            raise _ReextractRetryable()  # retryable → base leaves it un-acked for redelivery
