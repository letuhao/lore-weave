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

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from loreweave_jobs import BaseTerminalConsumer

from app.clients.knowledge_client import get_knowledge_client
from app.clients.llm_client import LLMClient, get_llm_client
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.worker.events import COMPOSITION_JOBS_STREAM, COMPOSITION_WORKER_GROUP
from app.worker.operations import (
    SUPPORTED_OPERATIONS,
    UnsupportedOperationError,
    run_chapter_generate,
    run_decompose,
    run_generate,
    run_selection_edit,
    run_stitch,
)

__all__ = [
    "run_job",
    "dispatch_job_message",
    "sweep_once",
    "CompositionJobConsumer",
]

logger = logging.getLogger("composition.worker.job_consumer")

#: business failures the compute raises — a bad LLM output / upstream error is a
#: TERMINAL job outcome (mark failed + ACK), NOT an infra error to redeliver.
_BUSINESS_ERRORS = (UnsupportedOperationError, ValueError, KeyError)

_ACTIVE = ("pending", "running")


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


def _worker_op(job) -> str:
    """The canonical worker-op id. For decompose/stitch it equals the job's
    ``operation`` column; generate carries the user's free-form prose op there
    ("draft_scene", …) so its canonical id lives in ``input['worker_op']``."""
    return (job.input or {}).get("worker_op") or job.operation


async def _run_operation(pool: asyncpg.Pool, llm: LLMClient, job) -> dict:
    """Dispatch by worker-op. The op's bearer-authenticated context was resolved
    into job.input by the endpoint; user_id/project_id come off the job row. Ops
    needing knowledge (canon-reflect) grab the internal-auth singleton lazily."""
    op = _worker_op(job)
    if op == "decompose_preview":
        return await run_decompose(llm, user_id=str(job.user_id), input=job.input or {})
    if op == "stitch_chapter":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.user_id))
        inp.setdefault("project_id", str(job.project_id))
        return await run_stitch(pool, llm, get_knowledge_client(), input=inp)
    if op == "generate":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.user_id))
        inp.setdefault("project_id", str(job.project_id))
        return await run_generate(pool, llm, get_knowledge_client(), input=inp)
    if op == "chapter_generate":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.user_id))
        inp.setdefault("project_id", str(job.project_id))
        return await run_chapter_generate(pool, llm, get_knowledge_client(), input=inp)
    if op == "selection_edit":
        # No knowledge / pool needed — the endpoint pre-built the message list.
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.user_id))
        return await run_selection_edit(llm, input=inp)
    raise UnsupportedOperationError(op)


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


class CompositionJobConsumer(BaseTerminalConsumer):
    """composition batch-job consumer on the shared transport scaffold. Single
    job-request stream at ``start_id="0"`` (process the backlog). Business fold = the
    module-level ``run_job`` (idempotent; a business failure is marked 'failed' + acked
    INSIDE run_job → ``handle`` returns → ack; only an infra error raises → the base leaves
    it un-acked for redelivery). The DB-row ``sweep_once`` is the runtime backstop a Redis
    stream's no-post-ACK-redelivery needs."""

    stream = COMPOSITION_JOBS_STREAM
    group = COMPOSITION_WORKER_GROUP
    start_id = "0"
    consumer_name_prefix = "composition-worker"
    retry_prefix = "composition:job:retry"

    def __init__(self, redis_url: str, pool: asyncpg.Pool, *, consumer_name: str | None = None) -> None:
        super().__init__(redis_url, consumer_name=consumer_name)
        self._pool = pool
        self._llm = get_llm_client()

    async def handle(self, fields: dict) -> None:
        await dispatch_job_message(self._pool, self._llm, fields=fields)

    async def sweep_once(self, *, timeout_s: int, batch: int) -> int:
        # NOTE: the bare name `sweep_once` resolves (LEGB) to the module-level function
        # below, NOT this method — so this is delegation, not recursion.
        return await sweep_once(self._pool, timeout_secs=timeout_s, batch=batch)


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
              AND (operation = ANY($3::text[]) OR input->>'worker_op' = ANY($3::text[]))
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
