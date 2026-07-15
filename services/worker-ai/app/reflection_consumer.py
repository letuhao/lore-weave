"""D-REFLECTION-WIRE — the weekly-reflection CONSUMER. A producer (chat, driven by the
scheduler or on-demand) XADDs an `assistant.weekly_reflection` job {user_id, book_id,
week_start, week_end, entry_zone, language}; this runs `run_weekly_reflection` (recall →
SAFETY screen → deterministic detectors → render → write a 'reflection' draft). Mirrors
WeeklyRollupConsumer's transport + ack contract — but reflection is DETERMINISTIC (no LLM,
no model_ref, no billing).
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from loreweave_jobs import BaseTerminalConsumer

from app.reflection_job import run_weekly_reflection

if TYPE_CHECKING:
    from app.clients import BookClient, KnowledgeClient

__all__ = ["ReflectionConsumer", "REFLECTION_STREAM_NAME", "run_one_reflection_message"]

logger = logging.getLogger(__name__)

REFLECTION_STREAM_NAME = "assistant.weekly_reflection"

_REQUIRED_FIELDS = ("user_id", "book_id", "week_start", "week_end", "entry_zone", "language")


def _decode(v) -> str:
    if isinstance(v, bytes):
        return v.decode("utf-8")
    return str(v) if v is not None else ""


def _get(fields: dict, key: str):
    if key in fields:
        return fields[key]
    return fields.get(key.encode("utf-8"))


class _ReflectionRetryable(Exception):
    """Internal — a retryable outcome; raised so the base leaves the message un-acked."""


async def run_one_reflection_message(
    *,
    knowledge_client: "KnowledgeClient",
    book_client: "BookClient",
    fields: dict,
    message_id: str = "(reflection)",
) -> bool:
    """Decode one message + run the reflection. Returns True to ACK. Malformed → ACK (drop
    poison); a retryable error → False; any terminal state (reflected / safety_short_circuit) → ACK."""
    try:
        p = {k: _decode(_get(fields, k)) for k in _REQUIRED_FIELDS}
        for k in _REQUIRED_FIELDS:
            if not p[k]:
                raise ValueError(f"missing required field {k!r}")
    except (ValueError, TypeError, KeyError) as exc:
        logger.warning("reflection msg %s rejected as malformed: %s", message_id, exc)
        return True

    result = await run_weekly_reflection(
        user_id=p["user_id"], book_id=p["book_id"],
        week_start=p["week_start"], week_end=p["week_end"],
        entry_zone=p["entry_zone"], language=p["language"],
        knowledge_client=knowledge_client, book_client=book_client,
    )
    if result.get("status") == "error" and result.get("retryable"):
        logger.warning("reflection msg %s retryable error (%s) — un-acked", message_id, result.get("reason"))
        return False
    logger.info("reflection msg %s status=%s [%s..%s] patterns=%s",
                message_id, result.get("status"), p["week_start"], p["week_end"],
                result.get("patterns"))
    return True


class ReflectionConsumer(BaseTerminalConsumer):
    stream = REFLECTION_STREAM_NAME
    start_id = "0"
    consumer_name_prefix = "weekly-reflection"
    retry_prefix = "worker-ai:weekly-reflection:retry"

    def __init__(
        self, redis_url: str, knowledge_client: "KnowledgeClient", book_client: "BookClient",
        *, consumer_group: str, consumer_name: str | None = None, block_ms: int = 5000,
    ) -> None:
        self.group = consumer_group
        self.block_ms = block_ms
        super().__init__(redis_url, consumer_name=consumer_name)
        self._knowledge = knowledge_client
        self._book = book_client

    async def handle(self, fields: dict) -> None:
        should_ack = await run_one_reflection_message(
            knowledge_client=self._knowledge, book_client=self._book,
            fields=fields, message_id="(reflection)",
        )
        if not should_ack:
            raise _ReflectionRetryable()
