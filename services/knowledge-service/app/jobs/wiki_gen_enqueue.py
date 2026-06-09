"""wiki-llm M6 — wiki-gen job stream (enqueue side).

The trigger XADDs a job_id to ``loreweave:events:wiki-gen``; the flag-gated
consumer (`wiki_gen_processor`) drains it and runs the orchestrator. The stream is
just the durable wake-up signal — the truth is the ``wiki_gen_jobs`` row (its
``items_done`` drives skip-on-resume), so a lost message degrades to "re-trigger
to resume", never to a corrupt run.
"""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

__all__ = ["WIKI_GEN_STREAM", "enqueue_wiki_gen"]

WIKI_GEN_STREAM = "loreweave:events:wiki-gen"

logger = logging.getLogger(__name__)


async def enqueue_wiki_gen(client: aioredis.Redis, job_id: str) -> str:
    """XADD a job_id to the wiki-gen stream; returns the message id (for logs)."""
    msg_id = await client.xadd(WIKI_GEN_STREAM, {"job_id": job_id})
    msg_id_str = msg_id.decode("utf-8") if isinstance(msg_id, bytes) else str(msg_id)
    logger.info("wiki-gen.enqueue job=%s msg_id=%s", job_id, msg_id_str)
    return msg_id_str
