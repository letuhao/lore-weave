"""WS-3.7 — the weekly-rollup CONSUMER. A producer (chat, driven by the scheduler) XADDs an
`assistant.weekly_rollup` job {user_id, book_id, week_start, week_end, entry_zone, language,
model_source, model_ref}; this runs `roll_up_week` (recall the week's facts → reduce → a supplement
draft). Mirrors ReextractConsumer's transport + ack contract exactly.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from loreweave_jobs import BaseTerminalConsumer

from app.distill_job import make_distill_llm
from app.weekly_rollup_job import roll_up_week

if TYPE_CHECKING:
    from app.clients import BookClient, KnowledgeClient, UsageBillingClient
    from app.llm_client import LLMClient

__all__ = ["WeeklyRollupConsumer", "WEEKLY_ROLLUP_STREAM_NAME", "run_one_weekly_rollup_message"]

logger = logging.getLogger(__name__)

WEEKLY_ROLLUP_STREAM_NAME = "assistant.weekly_rollup"

_REQUIRED_FIELDS = (
    "user_id", "book_id", "week_start", "week_end", "entry_zone", "language",
    "model_source", "model_ref",
)


def _decode(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v) if v is not None else ""


def _get(fields: dict, key: str):
    if key in fields:
        return fields[key]
    return fields.get(key.encode("utf-8"))


class _WeeklyRetryable(Exception):
    """Internal — a retryable outcome; raised so the base leaves the message un-acked."""


async def run_one_weekly_rollup_message(
    *,
    knowledge_client: "KnowledgeClient",
    book_client: "BookClient",
    llm_client: "LLMClient",
    fields: dict,
    billing_client: "UsageBillingClient | None" = None,
    message_id: str = "(weekly)",
) -> bool:
    """Decode one message + run the rollup. Returns True to ACK. Malformed → ACK (drop poison); a
    retryable error → False; any terminal state → ACK."""
    try:
        p = {k: _decode(_get(fields, k)) for k in _REQUIRED_FIELDS}
        for k in _REQUIRED_FIELDS:
            if not p[k]:
                raise ValueError(f"missing required field {k!r}")
        trace_id = _decode(_get(fields, "trace_id")) or None
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("weekly-rollup msg %s rejected as malformed: %s", message_id, exc)
        return True

    llm = make_distill_llm(
        llm_client, user_id=p["user_id"], model_source=p["model_source"],
        model_ref=p["model_ref"], trace_id=trace_id,
    )
    result = await roll_up_week(
        user_id=p["user_id"], book_id=p["book_id"],
        week_start=p["week_start"], week_end=p["week_end"],
        entry_zone=p["entry_zone"], language=p["language"],
        llm=llm, knowledge_client=knowledge_client, book_client=book_client,
        billing_client=billing_client,
    )
    if result.get("status") == "error" and result.get("retryable"):
        logger.warning("weekly-rollup msg %s retryable error (%s) — un-acked", message_id, result.get("reason"))
        return False
    logger.info("weekly-rollup msg %s status=%s [%s..%s] facts=%s",
                message_id, result.get("status"), p["week_start"], p["week_end"],
                result.get("facts_summarized"))
    return True


class WeeklyRollupConsumer(BaseTerminalConsumer):
    stream = WEEKLY_ROLLUP_STREAM_NAME
    start_id = "0"
    consumer_name_prefix = "weekly-rollup"
    retry_prefix = "worker-ai:weekly-rollup:retry"

    def __init__(
        self, redis_url: str, knowledge_client: "KnowledgeClient", book_client: "BookClient",
        llm_client: "LLMClient", *, consumer_group: str, consumer_name: str | None = None,
        block_ms: int = 5000, billing_client: "UsageBillingClient | None" = None,
    ) -> None:
        self.group = consumer_group
        self.block_ms = block_ms
        super().__init__(redis_url, consumer_name=consumer_name)
        self._knowledge = knowledge_client
        self._book = book_client
        self._llm = llm_client
        self._billing = billing_client

    async def handle(self, fields: dict) -> None:
        should_ack = await run_one_weekly_rollup_message(
            knowledge_client=self._knowledge, book_client=self._book, llm_client=self._llm,
            billing_client=self._billing, fields=fields, message_id="(weekly)",
        )
        if not should_ack:
            raise _WeeklyRetryable()
