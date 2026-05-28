"""P3 — async summary-job enqueueing (D3 + D9 + M4 re-enqueue).

Producer-side: pass2_orchestrator calls `enqueue_summary` after writing
per-chapter Pass2WriteResult. Consumer: summary_processor (worker-ai)
reads the `extraction.summarize` Redis Stream.

Protocol-based for testability — orchestrator takes `enqueue: SummaryEnqueueFn`
and the test can inject a mock; production wires the redis-backed default.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Literal, Protocol
from uuid import UUID

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

__all__ = [
    "SUMMARY_STREAM_NAME",
    "SummarizeMessage",
    "SummaryEnqueueFn",
    "make_redis_summary_enqueue",
]

# Redis Stream the summary_processor consumer-group reads from.
SUMMARY_STREAM_NAME = "extraction.summarize"


@dataclass
class SummarizeMessage:
    """Per spec D3 stream message shape."""
    level: Literal["chapter", "part", "book"]
    node_path: str          # "book/part-1/chapter-3"
    node_id: str            # chapter_id | part_id | book_id (UUID string)
    book_id: str
    user_id: str
    project_id: str
    job_id: str             # extraction job lifecycle parent
    model_ref: str          # LLM model for summarize_level
    embedding_model_uuid: str
    embedding_dimension: int
    retry_at_epoch: float = 0.0   # M4 re-enqueue: skip until this time
    retried_n: int = 0            # M4 retry budget

    def to_redis_fields(self) -> dict[str, str]:
        """Serialize for XADD (Redis Stream field values are strings)."""
        return {
            "level": self.level,
            "node_path": self.node_path,
            "node_id": self.node_id,
            "book_id": self.book_id,
            "user_id": self.user_id,
            "project_id": self.project_id,
            "job_id": self.job_id,
            "model_ref": self.model_ref,
            "embedding_model_uuid": self.embedding_model_uuid,
            "embedding_dimension": str(self.embedding_dimension),
            "retry_at_epoch": str(self.retry_at_epoch),
            "retried_n": str(self.retried_n),
        }

    @classmethod
    def from_redis_fields(cls, fields: dict) -> "SummarizeMessage":
        """Deserialize from XREAD message values dict."""
        # Redis returns bytes by default; tolerate both bytes + str.
        def _s(k: str) -> str:
            v = fields.get(k)
            if isinstance(v, bytes):
                return v.decode("utf-8")
            return str(v) if v is not None else ""

        return cls(
            level=_s("level"),  # type: ignore[arg-type]
            node_path=_s("node_path"),
            node_id=_s("node_id"),
            book_id=_s("book_id"),
            user_id=_s("user_id"),
            project_id=_s("project_id"),
            job_id=_s("job_id"),
            model_ref=_s("model_ref"),
            embedding_model_uuid=_s("embedding_model_uuid"),
            embedding_dimension=int(_s("embedding_dimension") or "0"),
            retry_at_epoch=float(_s("retry_at_epoch") or "0"),
            retried_n=int(_s("retried_n") or "0"),
        )


class SummaryEnqueueFn(Protocol):
    """Caller injects this to pass2_orchestrator. Default impl uses Redis;
    tests pass a mock that records messages without touching Redis."""

    async def __call__(self, message: SummarizeMessage) -> str:
        """XADD the message + return Redis stream message ID."""
        ...


def make_redis_summary_enqueue(redis_url: str) -> SummaryEnqueueFn:
    """Build a default redis-backed enqueue function.

    Production wiring: knowledge-service lifespan creates the redis client
    once, passes to extraction routes via deps. Each call XADDs to the
    SUMMARY_STREAM_NAME stream.
    """
    client = aioredis.from_url(redis_url)

    async def _enqueue(message: SummarizeMessage) -> str:
        fields = message.to_redis_fields()
        msg_id = await client.xadd(SUMMARY_STREAM_NAME, fields)  # type: ignore[arg-type]
        # XADD returns bytes msg_id like b'1234567890-0'; decode for logs.
        msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
        logger.info(
            "summary.enqueue level=%s path=%s msg_id=%s",
            message.level, message.node_path, msg_id_str,
        )
        return msg_id_str

    return _enqueue


def now_epoch() -> float:
    """Helper for retry_at_epoch — epoch seconds (float)."""
    return time.time()
