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
from app.services.plan_pass_service import UpstreamStale
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
_BUSINESS_ERRORS = (
    UnsupportedOperationError, ValueError, KeyError, PlanForgeLLMError,
    # 27 PF-5. "Your upstream is stale/unaccepted" is the most ORDINARY condition in the compiler —
    # it is the gate doing its job, not an infrastructure fault. It must fail the job cleanly and
    # ACK. Left out of this tuple it would propagate as infra, the message would be un-ACKed, and
    # the broker would redeliver a pass that is *correctly* refusing to run — forever.
    UpstreamStale,
)

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


#: pass_id → the artifact key its proposable entities live under (27 PF-7). Only these two passes
#: touch the glossary at all.
_SEED_ENTITY_KEY = {"cast": "cast", "world": "entities"}


async def _propose_pass_seed(
    pool: asyncpg.Pool, job, run, pass_id: str, artifact,
) -> UUID | None:
    """Open the glossary seed proposal for a pass that produced glossary-bound entities (PF-7)."""
    key = _SEED_ENTITY_KEY.get(pass_id)
    if key is None:
        return None
    entities = artifact.content.get(key) or []
    if not entities:
        # Nothing to seed is a legitimate outcome (a degraded pass returns []). No proposal is
        # opened — and for `cast` that means acceptance will refuse, which is correct: you cannot
        # accept a cast that does not exist.
        return None

    from app.clients.book_client import get_book_client
    from app.clients.glossary_client import get_glossary_client
    from app.db.repositories.plan_bootstrap_proposals import PlanBootstrapProposalsRepo
    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.services.bootstrap_service import BootstrapService

    try:
        svc = BootstrapService(
            PlanBootstrapProposalsRepo(pool), PlanRunsRepo(pool),
            get_book_client(), get_glossary_client(), GenerationJobsRepo(pool),
        )
        proposal = await svc.propose_seed(
            job.created_by, run.book_id, run.id, pass_id, entities,
        )
    except Exception:  # noqa: BLE001 — advisory: never fail an expensive, already-saved artifact
        logger.warning(
            "plan_pass: could not open the glossary seed proposal for pass '%s' (run %s) — the "
            "artifact is saved; the pass will refuse acceptance until a seed proposal exists",
            pass_id, run.id, exc_info=True,
        )
        return None
    logger.info(
        "plan_pass: pass '%s' (run %s) opened glossary seed proposal %s with %d entit(ies)",
        pass_id, run.id, proposal.id, len(proposal.diff.get("new_glossary_entities", [])),
    )
    return proposal.id


async def _finalize_plan_pass_job(
    pool: asyncpg.Pool, job, result: dict, terminal_status: str,
) -> None:
    """27 V2-C2 — persist a finished pass: save its artifact, then record it in `pass_state`.

    Ordering matters. We save the artifact FIRST and only then point `pass_state` at it, so a crash
    between the two leaves an orphan artifact that nothing references — the pass simply reads as
    "not done" and a re-run redoes it (costing tokens, not correctness). The other order would
    record a pointer to an artifact that does not exist, and every downstream pass would resolve
    its input to nothing while the ledger insisted the pass was complete.

    A FAILED pass records `status:"failed"` and NO artifact pointer. `record_pass` leaves untouched
    fields alone, so a failure never wipes the pointer a previous successful run recorded — the last
    good artifact stays resolvable, and freshness (which is derived) reports the truth on its own.
    """
    inp = job.input or {}
    if _worker_op(job) != "plan_pass":
        return
    run_id_raw, book_id_raw = inp.get("run_id"), inp.get("book_id")
    pass_id = result.get("pass_id") or inp.get("pass_id")
    if not run_id_raw or not book_id_raw or not pass_id:
        return

    from app.db.repositories.plan_runs import PlanRunsRepo
    from app.services.plan_pass_service import default_decision, record_pass

    runs = PlanRunsRepo(pool)
    book_id, run_id = UUID(str(book_id_raw)), UUID(str(run_id_raw))
    run = await runs.get_for_book(book_id, run_id)
    if run is None:
        logger.warning("plan_pass finalize: run %s not found for book %s", run_id, book_id)
        return

    if terminal_status != "completed":
        state = record_pass(
            run, pass_id, status="failed", job_id=job.id,
            params=result.get("params") or inp.get("params") or {},
        )
        await runs.update_run(book_id, run_id, pass_state=state)
        return

    artifact = await runs.save_artifact(
        job.created_by, run_id, result["output_kind"], result.get("artifact") or {},
    )

    # PF-7 — passes 2 and 3 do not seed the glossary; they PROPOSE. The author's canon is only ever
    # mutated through the bootstrap quarantine, so there is ONE approval mechanism, not two. And
    # because accepting `cast` requires this proposal to be APPLIED, the blocking gate (PF-6) and
    # the mutation gate (PF-7) are the same gate — they cannot disagree.
    #
    # Advisory, deliberately: a proposal that fails to write must NOT fail the pass. The artifact is
    # already saved and is the expensive part; the seed can be re-proposed. Swallowing the error
    # would be the silent-success bug, so it is logged AND the pass is left with no
    # `bootstrap_proposal_id` — which is exactly what makes `cast`'s acceptance refuse later, with a
    # message that names the missing proposal instead of pretending everything is fine.
    proposal_id = await _propose_pass_seed(pool, job, run, pass_id, artifact)

    state = record_pass(
        run, pass_id, status="completed", artifact_id=artifact.id, job_id=job.id,
        input_fingerprint=result.get("input_fingerprint"),
        params=result.get("params") or {},
        bootstrap_proposal_id=proposal_id,
        # Advisory ⇒ `auto` (accepted, still reviewable). BLOCKING (`cast`, `beats`) ⇒ `pending`:
        # the pass is DONE, but the compiler stops here until a human decides. That is PF-6, and it
        # is the difference between "the plan proceeded" and "the plan proceeded past the two
        # questions only the author can answer".
        decision=default_decision(pass_id),
    )
    await runs.update_run(book_id, run_id, pass_state=state)


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
        await _finalize_plan_pass_job(pool, job, {"error": str(exc)}, "failed")
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
    await _finalize_plan_pass_job(pool, job, result, "completed")
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
    if op == "plan_pass":
        # 27 V2-C2 — one op, seven passes (`input['pass_id']`). The compute is here; the artifact
        # + `pass_state` write is in `_finalize_plan_pass_job`.
        from app.worker.operations import run_plan_pass
        return await run_plan_pass(
            pool, llm, user_id=str(job.created_by), input=job.input or {},
            cancel_check=cancel_check)
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
            job_id=str(job.id),  # IX-8 snapshot provenance (generation_job_id)
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
