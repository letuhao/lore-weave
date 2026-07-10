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
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone
from uuid import UUID

import asyncpg

from loreweave_jobs import BaseTerminalConsumer

from app.clients.knowledge_client import get_knowledge_client
from app.clients.llm_client import LLMClient, get_llm_client
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.engine.plan_forge.llm import PlanForgeLLMError
from app.worker.events import COMPOSITION_JOBS_STREAM, COMPOSITION_WORKER_GROUP
from app.worker.operations import (
    SUPPORTED_OPERATIONS,
    UnsupportedOperationError,
    run_chapter_generate,
    run_decompose,
    run_generate,
    run_plan_pipeline,
    run_plan_forge_propose,
    run_plan_forge_refine,
    run_promise_coverage,
    run_quality_report,
    run_selection_edit,
    run_self_heal_propose,
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
_BUSINESS_ERRORS = (UnsupportedOperationError, ValueError, KeyError, PlanForgeLLMError)

_ACTIVE = ("pending", "running")


async def _finalize_plan_forge_job(
    pool: asyncpg.Pool, job, result: dict, terminal_status: str,
) -> None:
    run_id_raw = (job.input or {}).get("run_id")
    book_id_raw = (job.input or {}).get("book_id")
    if not run_id_raw or not book_id_raw:
        return
    op = (job.input or {}).get("worker_op") or job.operation
    if op not in ("plan_forge_propose", "plan_forge_refine"):
        return
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.db.repositories.works import WorksRepo
    from app.services.plan_forge_service import PlanForgeService

    svc = PlanForgeService(
        PlanRunsRepo(pool), GenerationJobsRepo(pool), WorksRepo(pool),
    )
    job_for_apply = job
    if terminal_status == "failed":
        job_for_apply = job.model_copy(update={"status": "failed", "result": result})
    else:
        job_for_apply = job.model_copy(update={"status": "completed", "result": result})
    await svc.apply_job_outcome(
        job.created_by, UUID(str(book_id_raw)), UUID(str(run_id_raw)),
        job_for_apply, result,
    )


async def run_job(
    pool: asyncpg.Pool, llm: LLMClient, *, job_id: str, user_id: str
) -> str:
    """Run ONE composition job to terminal. Idempotent: a 'completed' job returns
    immediately; a crash mid-run left 'running' → recompute + overwrite. A business
    failure marks 'failed' + returns (ACK); an infra error propagates (un-ACK).

    `user_id` is the enqueue-message actor kept for the AMQP field contract; the
    job runs AS its ROW's actor (`job.created_by` — F7: a sweeper re-drive keeps
    spend attribution on the original caller), never as the message field."""
    del user_id  # row-authoritative actor (job.created_by); field kept for the wire shape
    repo = GenerationJobsRepo(pool)
    job = await repo.get(UUID(job_id))
    if job is None:
        logger.warning("composition job %s not found — dropping", job_id)
        return "not_found"
    if job.status == "completed":
        return "already_completed"
    if job.status in ("failed", "cancelled"):
        # A terminal-failed/cancelled job re-triggered (sweeper/dup) — leave it.
        return f"already_{job.status}"

    await repo.update_status(UUID(job_id), "running")

    async def cancel_check() -> bool:
        # bug #34 — immediate-cancel: abort the in-flight LLM call the moment the
        # cancel endpoint CAS-sets generation_job.status='cancelled'. Fail-soft: any
        # DB/read error returns False so a transient blip never spuriously cancels a
        # healthy job (the engine LLM calls just continue).
        try:
            row = await repo.get(UUID(job_id))
        except Exception:  # noqa: BLE001 — read failure must not cancel a live job
            return False
        return row is not None and row.status == "cancelled"

    try:
        result = await _run_operation(pool, llm, job, cancel_check=cancel_check)
    except _BUSINESS_ERRORS as exc:
        logger.info("composition job %s (%s) failed: %s", job_id, job.operation, exc)
        await repo.update_status(
            UUID(job_id), "failed",
            result={"error": str(exc)},
        )
        await _finalize_plan_forge_job(pool, job, {"error": str(exc)}, "failed")
        return "failed"

    # W5 (D-MOTIF-CONFORMANCE-ENGINE-WIRING): an op may return a critic-merge patch
    # under `_critic` (currently `generate`'s motif_conformance dim). Pop it OUT of the
    # result blob and stamp it onto the job's `critic` column (the COALESCE-safe
    # update_status path) — None leaves the existing critic untouched.
    critic_patch = result.pop("_critic", None) if isinstance(result, dict) else None
    await repo.update_status(
        UUID(job_id), "completed", result=result, critic=critic_patch,
    )
    await _finalize_plan_forge_job(pool, job, result, "completed")
    return "completed"


def _worker_op(job) -> str:
    """The canonical worker-op id. For decompose/stitch it equals the job's
    ``operation`` column; generate carries the user's free-form prose op there
    ("draft_scene", …) so its canonical id lives in ``input['worker_op']``."""
    return (job.input or {}).get("worker_op") or job.operation


async def _run_operation(
    pool: asyncpg.Pool, llm: LLMClient, job, *,
    cancel_check: Callable[[], Awaitable[bool]] | None = None,
) -> dict:
    """Dispatch by worker-op. The op's bearer-authenticated context was resolved
    into job.input by the endpoint; user_id/project_id come off the job row. Ops
    needing knowledge (canon-reflect) grab the internal-auth singleton lazily.
    `cancel_check` is threaded into each blocking-LLM op so an in-flight call aborts
    on cancel (bug #34); selection_edit streams via the SDK — a different abort path."""
    op = _worker_op(job)
    if op == "decompose_preview":
        return await run_decompose(
            llm, user_id=str(job.created_by), input=job.input or {}, cancel_check=cancel_check)
    if op == "plan_pipeline":
        inp = dict(job.input or {})
        inp.setdefault("project_id", str(job.project_id))
        return await run_plan_pipeline(
            pool, llm, user_id=str(job.created_by), input=inp, cancel_check=cancel_check)
    if op == "stitch_chapter":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        inp.setdefault("project_id", str(job.project_id))
        return await run_stitch(pool, llm, get_knowledge_client(), input=inp, cancel_check=cancel_check)
    if op == "generate":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        inp.setdefault("project_id", str(job.project_id))
        return await run_generate(pool, llm, get_knowledge_client(), input=inp, cancel_check=cancel_check)
    if op == "chapter_generate":
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        inp.setdefault("project_id", str(job.project_id))
        return await run_chapter_generate(
            pool, llm, get_knowledge_client(), input=inp, cancel_check=cancel_check)
    if op == "selection_edit":
        # No knowledge / pool needed — the endpoint pre-built the message list.
        # cancel_check is NOT threaded here: selection_edit drains stream_draft via
        # the raw SDK (engine/cowrite), which has its own abort path (not submit_and_wait).
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        return await run_selection_edit(llm, input=inp)
    if op == "self_heal_propose":
        # No pool/knowledge — the endpoint persisted the chapter text + canon; this just
        # runs the cheap-stack in propose mode (the human review-gate consumes the result).
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        return await run_self_heal_propose(
            llm, user_id=str(job.created_by), input=inp, cancel_check=cancel_check)
    if op == "quality_report":
        # No pool/knowledge — the endpoint persisted the chapter text + canon; this runs the
        # two advisory judges (critic + promise audit) and returns a read-only report.
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        return await run_quality_report(
            llm, user_id=str(job.created_by), input=inp, cancel_check=cancel_check)
    if op == "promise_coverage":
        # No pool/knowledge — the endpoint rendered the outline plan + assembled the book prose;
        # this scores the book against the spec's tracked-promise set (read-only coverage).
        inp = dict(job.input or {})
        inp.setdefault("user_id", str(job.created_by))
        return await run_promise_coverage(
            llm, user_id=str(job.created_by), input=inp, cancel_check=cancel_check)
    if op == "plan_forge_propose":
        return await run_plan_forge_propose(
            llm, user_id=str(job.created_by), input=job.input or {}, cancel_check=cancel_check)
    if op == "plan_forge_refine":
        return await run_plan_forge_refine(
            llm, user_id=str(job.created_by), input=job.input or {}, cancel_check=cancel_check)
    # ── Wave-2 motif ops (W2-F0 frozen dispatch seam) ─────────────────────────────
    # The Tier-W confirm effects (routers/actions.py) already stamp the full input
    # envelope; each handler lives in its WS-owned engine module (lazy import keeps
    # the worker's top-level surface small + the seam frozen — a WS fills its module
    # body, never this dispatch).
    if op == "mine_motifs":
        from app.engine.motif_mine import run_mine_motifs
        return await run_mine_motifs(
            pool, llm, get_knowledge_client(),
            user_id=str(job.created_by), input=job.input or {},
        )
    if op == "analyze_reference":
        from app.engine.motif_deconstruct import run_analyze_reference
        return await run_analyze_reference(
            pool, llm, user_id=str(job.created_by), input=job.input or {},
        )
    if op == "conformance_run":
        from app.engine.motif_conformance_run import run_conformance_run
        return await run_conformance_run(
            pool, llm, get_knowledge_client(),
            user_id=str(job.created_by), project_id=str(job.project_id), input=job.input or {},
        )
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
    count = 1  # heavy LLM jobs — one-at-a-time for fair multi-replica distribution
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
            SELECT id, created_by FROM generation_job
            WHERE status = ANY($1::text[]) AND updated_at <= $2
              AND (operation = ANY($3::text[]) OR input->>'worker_op' = ANY($3::text[]))
            ORDER BY updated_at
            LIMIT $4
            """,
            list(_ACTIVE), cutoff, list(SUPPORTED_OPERATIONS), batch,
        )
    for r in rows:
        try:
            await run_job(pool, llm, job_id=str(r["id"]), user_id=str(r["created_by"]))
        except Exception:  # noqa: BLE001 — a sweep failure must not kill the loop
            logger.warning("composition sweep re-drive failed for %s", r["id"], exc_info=True)
    return len(rows)
