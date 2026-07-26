"""A1 / P-10 (spec 06 §Q2) — the "End my day" distiller trigger, CONSUMER side.

A producer XADDs an `assistant.distill` job carrying {user_id, book_id, entry_date, entry_zone,
language, model_source, model_ref}; this consumer runs the already-built distiller pipeline
(day-window read → map-reduce → diary-entry write) on a live stack. The distiller is a NON-agentic
LLM pipeline (map-reduce), so it is exempt from the MCP-first invariant — a Redis-stream job is the
right shape, mirroring the summary/extraction consumers.

Retry contract (BaseTerminalConsumer): `distill_and_write` returns a status dict; a RETRYABLE
compute/transport error leaves the message un-acked; every terminal state (written / no_entry /
oversized / kept / non-retryable error) acks. A malformed message is acked (dropped) so the PEL
never grows on poison. ⚠️ REDELIVERY TIMING (review LOW-3): the running loop reads only NEW
messages (`>`); an un-acked message is re-processed on the next worker RESTART's PEL drain, not
promptly on a live stack (no `sweep_once` override, no DLQ). So a retryable distill error is
retried on restart, and the catch-up SWEEP (P-10, built next) is what will re-drive an un-journaled
day live. The message is never DROPPED — just not promptly re-tried.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from loreweave_jobs import BaseTerminalConsumer

from app.distill_job import distill_and_write, make_distill_llm
from app.distiller import WINDOW_TOKENS, resolve_distill_window

if TYPE_CHECKING:
    from app.clients import (
        BookClient, ChatClient, KnowledgeClient, ProviderRegistryClient, UsageBillingClient,
    )
    from app.llm_client import LLMClient

__all__ = ["DistillConsumer", "DISTILL_STREAM_NAME", "run_one_distill_message"]

logger = logging.getLogger(__name__)

# Must match the producer's stream name — drift silently breaks delivery.
DISTILL_STREAM_NAME = "assistant.distill"

_REQUIRED_FIELDS = (
    "user_id", "book_id", "entry_date", "entry_zone", "language",
    "model_source", "model_ref",
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


class _DistillRetryable(Exception):
    """Internal — a retryable distill outcome; raised so the base leaves the message un-acked."""


async def run_one_distill_message(
    *,
    chat_client: "ChatClient",
    book_client: "BookClient",
    llm_client: "LLMClient",
    fields: dict,
    knowledge_client: "KnowledgeClient | None" = None,
    billing_client: "UsageBillingClient | None" = None,
    provider_client: "ProviderRegistryClient | None" = None,
    message_id: str = "(distill)",
) -> bool:
    """Decode one `assistant.distill` message + run the pipeline. Returns True to ACK.

    Malformed message → ACK (drop poison). A retryable distill error → return False (leave
    un-acked for redelivery). Any terminal state → ACK. Split out from the consumer class so it is
    unit-testable with fakes, no Redis."""
    try:
        p = {k: _decode(_get(fields, k)) for k in _REQUIRED_FIELDS}
        for k in _REQUIRED_FIELDS:
            if not p[k]:
                raise ValueError(f"missing required field {k!r}")
        trace_id = _decode(_get(fields, "trace_id")) or None
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("distill stream msg %s rejected as malformed: %s", message_id, exc)
        return True  # ACK to drop poison off the stream

    llm = make_distill_llm(
        llm_client,
        user_id=p["user_id"],
        model_source=p["model_source"],
        model_ref=p["model_ref"],
        trace_id=trace_id,
    )
    # B2 (D-DISTILL-WINDOW-MODEL-AWARE) — size the per-chunk window to the RESOLVED distill model's
    # context length so a small-context BYOK model doesn't overflow (a fixed 12k chunk + prompt + output
    # would error every map step). Best-effort: an unresolved/absent ctx keeps the 12k default (the seal).
    window = WINDOW_TOKENS
    if provider_client is not None:
        try:
            ctx_len = await provider_client.get_context_length(p["model_source"], p["model_ref"])
            window = resolve_distill_window(ctx_len)
            if window != WINDOW_TOKENS:
                logger.info("distill msg %s: model ctx=%s → window=%s (was %s)",
                            message_id, ctx_len, window, WINDOW_TOKENS)
        except Exception as exc:  # noqa: BLE001 — best-effort; fall back to the default window.
            logger.warning("distill msg %s: context-length resolve failed (%s) — using default window", message_id, exc)
    result = await distill_and_write(
        user_id=p["user_id"],
        book_id=p["book_id"],
        entry_date=p["entry_date"],
        entry_zone=p["entry_zone"],
        language=p["language"],
        llm=llm,
        chat_client=chat_client,
        book_client=book_client,
        knowledge_client=knowledge_client,
        billing_client=billing_client,
        window=window,
    )
    status = result.get("status")
    if status == "error" and result.get("retryable"):
        logger.warning(
            "distill msg %s retryable error (reason=%s) — leaving un-acked",
            message_id, result.get("reason"),
        )
        return False  # leave un-acked → base redelivers, then poison-acks
    # DBT-15 — carry reason/advisory in the log so an UNATTENDED model_no_output day (a reasoning
    # model producing empty diaries) is visible in worker logs, not silent.
    logger.info(
        "distill msg %s status=%s date=%s chapter=%s facts=%s reason=%s advisory=%s",
        message_id, status, p["entry_date"], result.get("chapter_id"), result.get("facts_found"),
        result.get("reason"), result.get("advisory"),
    )
    return True


class DistillConsumer(BaseTerminalConsumer):
    """`assistant.distill` consumer on the shared transport scaffold (XREADGROUP + ack + bounded
    retry + startup PEL drain). `start_id="0"` processes the backlog so an "End my day" clicked
    while the worker was down is still journaled on restart."""

    stream = DISTILL_STREAM_NAME
    start_id = "0"
    consumer_name_prefix = "distill"
    retry_prefix = "worker-ai:distill:retry"

    def __init__(
        self,
        redis_url: str,
        chat_client: "ChatClient",
        book_client: "BookClient",
        llm_client: "LLMClient",
        *,
        consumer_group: str,
        consumer_name: str | None = None,
        block_ms: int = 5000,
        knowledge_client: "KnowledgeClient | None" = None,
        billing_client: "UsageBillingClient | None" = None,
        provider_client: "ProviderRegistryClient | None" = None,
    ) -> None:
        self.group = consumer_group  # runtime group — set before the base validates it
        self.block_ms = block_ms
        super().__init__(redis_url, consumer_name=consumer_name)
        self._chat = chat_client
        self._book = book_client
        self._llm = llm_client
        self._knowledge = knowledge_client  # WS-2.3 — divert diary facts to the KG inbox (optional)
        self._billing = billing_client  # WS-2.8 — daily-cap degrade pre-check (optional)
        self._provider = provider_client  # B2 — resolve the distill model's context length (optional)

    async def handle(self, fields: dict) -> None:
        should_ack = await run_one_distill_message(
            chat_client=self._chat, book_client=self._book, llm_client=self._llm,
            knowledge_client=self._knowledge, billing_client=self._billing,
            provider_client=self._provider,
            fields=fields, message_id="(distill)",
        )
        if not should_ack:
            raise _DistillRetryable()  # retryable → base leaves it un-acked for redelivery
