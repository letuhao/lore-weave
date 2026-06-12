"""composition batch-job consumer (Phase 3 M4 — mirrors lore-enrichment resume).

XREADGROUP the composition_jobs stream → load the job → run its LLM compute →
write result/status. Idempotent for at-least-once redelivery (completed → skip; a
crash mid-run leaves 'running' → redelivery recomputes; the job's idempotency_key +
base_revision_id guard duplicate side effects). ACK on a terminal/business outcome
or an unrecoverable message; leave un-ACKed on a transient infra error (PEL
redelivers). A stuck-job sweeper re-drives rows idle past a timeout (lost trigger /
consumer crash) — the runtime backstop since a Redis stream gives no post-ACK redelivery.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg
import redis.asyncio as aioredis

from app.clients.knowledge_client import get_knowledge_client
from app.clients.llm_client import LLMClient, get_llm_client
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.worker.events import COMPOSITION_JOBS_STREAM, COMPOSITION_WORKER_GROUP
from app.worker.operations import (
    SUPPORTED_OPERATIONS,
    UnsupportedOperationError,
    run_decompose,
    run_stitch,
)

__all__ = [
    "run_job",
    "dispatch_job_message",
    "consume_jobs_stream",
    "sweep_once",
]

logger = logging.getLogger("composition.worker.job_consumer")

#: business failures the compute raises — a bad LLM output / upstream error is a
#: TERMINAL job outcome (mark failed + ACK), NOT an infra error to redeliver.
_BUSINESS_ERRORS = (UnsupportedOperationError, ValueError, KeyError)

_ACTIVE = ("pending", "running")


async def _ensure_group(client: aioredis.Redis, stream: str, group: str) -> None:
    try:
        await client.xgroup_create(name=stream, groupname=group, id="0", mkstream=True)
        logger.info("created consumer group %s on %s", group, stream)
    except aioredis.ResponseError as exc:
        if "BUSYGROUP" not in str(exc):
            raise


async def run_job(
    pool: asyncpg.Pool, llm: LLMClient, *, job_id: str, user_id: str
) -> str:
    """Run ONE composition job to terminal. Idempotent: a 'completed' job returns
    immediately; a crash mid-run left 'running' → recompute + overwrite. A business
    failure marks 'failed' + returns (ACK); an infra error propagates (un-ACK)."""
    repo = GenerationJobsRepo(pool)
    uid = UUID(user_id)
    job = await repo.get(uid, UUID(job_id))
    if job is None:
        logger.warning("composition job %s not found — dropping", job_id)
        return "not_found"
    if job.status == "completed":
        return "already_completed"
    if job.status in ("failed", "cancelled"):
        # A terminal-failed/cancelled job re-triggered (sweeper/dup) — leave it.
        return f"already_{job.status}"

    await repo.update_status(uid, UUID(job_id), "running")
    try:
        result = await _run_operation(pool, llm, job)
    except _BUSINESS_ERRORS as exc:
        logger.info("composition job %s (%s) failed: %s", job_id, job.operation, exc)
        await repo.update_status(
            uid, UUID(job_id), "failed",
            result={"error": str(exc)},
        )
        return "failed"

    await repo.update_status(uid, UUID(job_id), "completed", result=result)
    return "completed"


async def _run_operation(pool: asyncpg.Pool, llm: LLMClient, job) -> dict:
    """Dispatch by operation. The op's bearer-authenticated context was resolved
    into job.input by the endpoint; user_id/project_id come off the job row. Ops
    needing knowledge (canon-reflect) grab the internal-auth singleton lazily."""
    if job.operation == "decompose_preview":
        return await run_decompose(llm, user_id=str(job.user_id), input=job.input or {})
    if job.operation == "stitch_chapter":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.user_id))
        inp.setdefault("project_id", str(job.project_id))
        return await run_stitch(pool, llm, get_knowledge_client(), input=inp)
    raise UnsupportedOperationError(job.operation)


async def dispatch_job_message(
    pool: asyncpg.Pool, llm: LLMClient, *, fields: dict
) -> None:
    """Route ONE stream message to run_job. A business failure is handled inside
    run_job (marks failed) and returns; only an infra error propagates (un-ACK)."""
    await run_job(
        pool, llm,
        job_id=fields.get("job_id", ""),
        user_id=fields.get("user_id", ""),
    )


async def consume_jobs_stream(
    *,
    pool: asyncpg.Pool,
    redis_url: str,
    consumer_name: str = "worker-1",
    block_ms: int = 5000,
) -> None:
    """Long-running consumer. Cancel-safe: shutdown raises CancelledError from
    xreadgroup; the finally closes the Redis client."""
    client = aioredis.from_url(redis_url, decode_responses=True)
    llm = get_llm_client()
    stream = COMPOSITION_JOBS_STREAM
    try:
        await _ensure_group(client, stream, COMPOSITION_WORKER_GROUP)
        logger.info(
            "composition worker started group=%s name=%s stream=%s",
            COMPOSITION_WORKER_GROUP, consumer_name, stream,
        )
        while True:
            try:
                resp = await client.xreadgroup(
                    groupname=COMPOSITION_WORKER_GROUP,
                    consumername=consumer_name,
                    streams={stream: ">"},
                    count=1,
                    block=block_ms,
                )
            except asyncio.CancelledError:
                raise
            except aioredis.RedisError as exc:
                logger.debug("composition worker XREADGROUP retry: %s", exc)
                await asyncio.sleep(1.0)
                continue
            if not resp:
                continue
            for _stream, messages in resp:
                for message_id, fields in messages:
                    ack = True
                    try:
                        await dispatch_job_message(pool, llm, fields=fields)
                    except Exception:  # noqa: BLE001 — transient infra → redeliver
                        logger.warning(
                            "composition job msg %s failed; leaving un-ACKed for redelivery",
                            message_id, exc_info=True,
                        )
                        ack = False
                    if ack:
                        await client.xack(stream, COMPOSITION_WORKER_GROUP, message_id)
    finally:
        await client.aclose()


async def sweep_once(pool: asyncpg.Pool, *, timeout_secs: int, batch: int = 20) -> int:
    """Re-drive jobs stranded in an active state past the timeout (a lost trigger /
    a consumer crash before ACK — a Redis stream gives no post-ACK redelivery). Only
    operations the worker supports are re-driven; re-runs go through the idempotent
    run_job. Returns the count re-driven."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=max(0, timeout_secs))
    llm = get_llm_client()
    async with pool.acquire() as c:
        rows = await c.fetch(
            """
            SELECT id, user_id FROM generation_job
            WHERE status = ANY($1::text[]) AND updated_at <= $2
              AND operation = ANY($3::text[])
            ORDER BY updated_at
            LIMIT $4
            """,
            list(_ACTIVE), cutoff, list(SUPPORTED_OPERATIONS), batch,
        )
    for r in rows:
        try:
            await run_job(pool, llm, job_id=str(r["id"]), user_id=str(r["user_id"]))
        except Exception:  # noqa: BLE001 — a sweep failure must not kill the loop
            logger.warning("composition sweep re-drive failed for %s", r["id"], exc_info=True)
    return len(rows)


async def run_sweeper(pool: asyncpg.Pool, *, interval_secs: int, timeout_secs: int) -> None:
    """Periodic stuck-job sweep. interval_secs <= 0 disables it."""
    if interval_secs <= 0:
        return
    while True:
        try:
            n = await sweep_once(pool, timeout_secs=timeout_secs)
            if n:
                logger.info("composition sweeper re-drove %d stuck job(s)", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            logger.warning("composition sweeper iteration failed", exc_info=True)
        await asyncio.sleep(interval_secs)
