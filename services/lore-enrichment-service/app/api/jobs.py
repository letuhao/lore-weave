"""Jobs router (RAID C14) — the end-to-end P1 enrichment job runner.

C3 froze these routes as 501 stubs; C14 implements ``POST /jobs`` (run a P1
enrichment job over a project's under-described LOCATIONs) and the read/list
routes. The lifecycle actions (pause/resume/cancel) remain status reads over the
persisted ``enrichment_job`` row — the runner pauses ITSELF on a cost-cap breach
(autonomous, M5); an explicit author pause/resume/cancel rides the same C8 state
machine and is surfaced here.

H0 (LOCKED): a job ONLY ever produces QUARANTINED proposals (origin='enrichment',
confidence<1.0, review_status='proposed'). Promotion to canon is the separate
author-only ``/proposals/{id}/promote`` path (C13) — a job never canonizes.

The runner is assembled (``app.jobs.assembly``) from the real C10/C11/C12/C13
components; the generation + embedding models are resolved via provider-registry
by ``model_ref`` (NO hardcoded model names).
"""

from __future__ import annotations

import logging
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from loreweave_jobs import emit_job_event
from pydantic import BaseModel, Field

from app.api.principal import Principal, require_principal
from app.clients.model_name import resolve_model_name
from app.config import settings
from app.db.book_profile import NEUTRAL_PROFILE, BookProfile, get_book_profile
from app.deps import get_db
from app.gaps.model import Gap, resolve_dimensions
from app.jobs import fair_sched
from app.jobs.assembly import build_live_runner
from app.jobs.events import LORE_ENRICHMENT_RESUME_STREAM, make_redis_producer
from app.jobs.job_events import JOB_KIND, JOB_SERVICE, canonical_status, job_error
from app.jobs.job_request import save_job_request
from app.jobs.proposal_store import PgProposalStore
from app.jobs.state_machine import (
    IllegalTransitionError,
    JobRecord,
    JobState,
    JobStateMachine,
    PauseReason,
)
from app.strategies.base import StrategyContext, Technique
from app.strategies.registry import InactiveStrategyError, UnknownStrategyError

router = APIRouter(prefix="/v1/lore-enrichment/jobs", tags=["jobs"])
logger = logging.getLogger("lore_enrichment.jobs")


# ── request / response bodies ────────────────────────────────────────────────


class GapTarget(BaseModel):
    """One under-described entity to enrich (the canon entity + its faithful
    name). The runner derives the MISSING dimensions via the C7 engine; the demo
    seeds sparse LOCATIONs so all dimensions are missing."""

    canonical_name: str = Field(min_length=1)
    target_ref: str | None = None
    entity_kind: str = "location"
    mention_count: int = Field(default=1, ge=0)
    # which dimensions ARE already present in canon (default: none → all missing).
    present_dimensions: list[str] = Field(default_factory=list)


class CreateJobBody(BaseModel):
    project_id: UUID
    embedding_model_ref: UUID  # provider-registry user_model id (the embed model)
    generation_model_ref: UUID  # provider-registry user_model id (the gen model)
    targets: list[GapTarget] = Field(min_length=1)
    # Optional glossary book scope for the C12 contradiction check (C3/F-C12-1):
    # when set, the runner reads the entity's authored canon to detect (and
    # auto-reject) a generated fact that NEGATES canon. Absent → contradiction
    # degrades honestly (no false-green); back-compatible.
    book_id: UUID | None = None
    # Which enrichment TECHNIQUE drives the job. Default 'retrieval' (the P1 demo
    # path, unchanged). A P2/P3 technique (e.g. 'fabrication') is gate-enforced
    # END-TO-END: the runner resolves the pipeline through the gate-aware factory,
    # which REFUSES it (409) while the live eval gate is LOCKED (DEFERRED-054).
    technique: str = Field(default=Technique.RETRIEVAL.value)
    # Cost guardrail (C8); aligns with the frozen contract's max_spend_tokens. The
    # reserved eval-cost line (M5) is held back from this cap.
    max_spend_tokens: float | None = Field(default=None, ge=0.0)
    eval_reserve_fraction: float = Field(default=0.15, ge=0.0, lt=1.0)
    top_k: int = Field(default=5, ge=1, le=20)


def _gap_from_target(t: GapTarget, profile: BookProfile = NEUTRAL_PROFILE) -> Gap | None:
    """Build a C7 :class:`Gap` from a target (de-bias C1, KB3 — multi-kind).

    Derives present/missing from the KIND's OWN dimension table via
    ``resolve_dimensions`` (the SAME profile-localized resolution detect/generation
    use — review #3, so an English book's en labels match), GENERIC fallback for an
    unmodeled kind (NEVER a 400/skip), NOT the hardcoded LOCATION ``Dimension`` enum.
    ``present_dimensions`` may be stable ids or (localized) labels — both map to the
    stable id, mirroring ``coverages_from_rows``. Returns None for a fully-described
    entity (no missing dimension)."""
    kind = (t.entity_kind or "").strip() or "location"
    table = resolve_dimensions(
        kind, language=profile.language, overrides=profile.dimension_overrides
    )  # kind's real dims, profile-localized; GENERIC for unknown (no 400)
    ids = {s.dimension for s in table}
    label_to_id = {s.label: s.dimension for s in table}
    present_set = {
        d if d in ids else label_to_id[d]
        for d in t.present_dimensions
        if d in ids or d in label_to_id
    }
    present = tuple(s.dimension for s in table if s.dimension in present_set)
    missing = tuple(s.dimension for s in table if s.dimension not in present_set)
    if not missing:
        return None
    return Gap(
        entity_kind=kind,
        canonical_name=t.canonical_name,
        target_ref=t.target_ref,
        mention_count=t.mention_count,
        present_dimensions=present,
        missing_dimensions=missing,
    )


# ── create + run a P1 job ────────────────────────────────────────────────────


@router.post("", status_code=status.HTTP_202_ACCEPTED)
async def create_job(
    body: CreateJobBody,
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Run a P1 enrichment job over the requested under-described LOCATIONs.

    DEMO / TEST-ONLY — NOT the production entry point. This runs the full pipeline
    SYNCHRONOUSLY in-process and returns the outcome (job state, quarantined
    proposals, cost), which is convenient for the e2e gate-refusal tests and the
    c14/live-smoke scripts but holds the HTTP connection for the whole multi-gap
    LLM run. The PRODUCTION path is asynchronous and worker-driven:
    ``POST /v1/lore-enrichment/projects/{book_id}/auto-enrich`` (and compose)
    create the row + persist the request + XADD a trigger, and the resume worker
    re-drives it via ``redrive_one`` (M1 per-job claim + M2 cancel/pause parity +
    M3 retry all apply there). No frontend or sibling service calls THIS route;
    keep it for the demo/gate coverage, don't wire new callers to it.

    H0: every proposal is quarantined regardless of path.
    """
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required"
        )
    user_id = principal.user_id

    # Validate the requested technique up-front (400 on an unknown key) so an
    # obvious typo never reaches the gate-aware factory.
    try:
        technique = Technique(body.technique)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unknown technique {body.technique!r}",
        )

    # de-bias C1 (#3): resolve the book profile so the gap builder localizes the
    # dimension table the SAME way detect/generation do (per-book round-trip).
    job_profile = await get_book_profile(pool, body.book_id)
    gaps: list[Gap] = []
    for t in body.targets:
        gap = _gap_from_target(t, job_profile)
        if gap is not None:
            gaps.append(gap)
    if not gaps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no gaps to enrich (all targets fully described)",
        )

    # P5 — per-owner concurrent-job cap (the noisy-neighbor fix for the synchronous
    # in-process runner). Claimed BEFORE the job row is created so a 429 leaves no orphan
    # row; released on every exit path below (gate-refused raises + the run's finally). At
    # cap → 429. Off ⇒ (True, None) ⇒ no cap. Fail-open on a redis blip.
    _p5_allowed, _p5_token = await fair_sched.try_acquire_job(user_id)
    if not _p5_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"you already have {settings.p5_owner_cap} enrichment job(s) running — "
                "wait for one to finish, then retry"
            ),
        )

    # Persist the job row first so the runner + the event stream both key on the
    # real DB job id (event correlation). The job row records the REQUESTED
    # technique — a gate-refused fabrication job is then visible as a failed row
    # carrying technique='fabrication' (auditable refusal, not a silent drop).
    store = PgProposalStore(pool)
    # P4 (D-JOBS-P4-LORE-MODEL) — resolve the generation model NAME OUT-OF-TX (network I/O;
    # H1) so the create event carries the human name for the Jobs GUI. Best-effort: None on
    # failure; the projection's COALESCE keeps it across the later status events.
    _model_name = await resolve_model_name("user_model", str(body.generation_model_ref))
    db_job_id = await store.create_job(
        user_id=str(user_id),
        project_id=str(body.project_id),
        book_id=str(body.book_id) if body.book_id else None,
        technique=technique.value,
        entity_kind="location",
        max_spend=body.max_spend_tokens,
        estimated_cost=0.0,
        model_name=_model_name,
    )
    # Persist the request so a cost-cap-paused job can be RE-DRIVEN by the resume
    # worker (F-C14-1/051). Stores only the request shape (targets + model_ref
    # UUIDs + params + acting user) — never enriched content.
    await save_job_request(
        pool=pool,
        job_id=UUID(db_job_id),
        request={**body.model_dump(mode="json"), "user_id": str(user_id)},
    )
    # Build the runner THROUGH the gate-aware factory: a P2/P3 technique while the
    # live eval gate is LOCKED raises InactiveStrategyError here — the job is
    # REFUSED (gate enforced end-to-end, DEFERRED-054). We mark the job failed
    # (auditable) and surface a 409, never silently activating fabrication.
    try:
        bundle = await build_live_runner(
            pool=pool,
            job_id=db_job_id,
            user_id=str(user_id),
            project_id=str(body.project_id),
            embedding_model_ref=str(body.embedding_model_ref),
            cost_cap=body.max_spend_tokens,
            eval_reserve_fraction=body.eval_reserve_fraction,
            top_k=body.top_k,
            technique=technique.value,
            book_id=str(body.book_id) if body.book_id else None,
        )
    except InactiveStrategyError as exc:
        await store.mark_job_status(
            job_id=db_job_id,
            status="failed",
            error_message=f"refused: technique {technique.value!r} gate-locked ({exc})",
        )
        await fair_sched.release_job(user_id, _p5_token)  # P5 — free the slot on gate-refusal
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"technique {technique.value!r} is gate-locked for this project — "
                "the enrichment eval gate has not cleared (run the eval first)"
            ),
        )
    except UnknownStrategyError as exc:
        await store.mark_job_status(
            job_id=db_job_id, status="failed", error_message=str(exc)
        )
        await fair_sched.release_job(user_id, _p5_token)  # P5 — free the slot on bad-strategy
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    try:
        context = StrategyContext(
            user_id=str(user_id),
            project_id=str(body.project_id),
            model_ref=str(body.generation_model_ref),
            # de-bias C1: the per-book profile (resolved once above) makes the
            # prompt builders + dimension resolver book-aware (NEUTRAL when unset).
            profile=job_profile,
        )
        outcome = await bundle.runner.run_job(
            job_id=db_job_id, gaps=gaps, context=context, entity_kind="location"
        )
    finally:
        await bundle.aclose()
        # P5 — release the per-owner job slot once the synchronous run ends (success OR
        # exception). The lease TTL backstops a crash before this runs.
        await fair_sched.release_job(user_id, _p5_token)

    return {
        "job_id": outcome.job_id,
        "status": outcome.final_state,
        "proposals_total": len(outcome.proposals),
        "proposals": [
            {
                "proposal_id": p.proposal_id,
                "canonical_name": p.canonical_name,
                "origin": p.origin,
                "technique": p.technique,
                "review_status": p.review_status,
                "confidence": p.confidence,
                "pending_validation": p.pending_validation,
                "dimensions": list(p.dimensions.keys()),
            }
            for p in outcome.proposals
        ],
        "skipped_gaps": outcome.skipped_gaps,
        "estimated_cost": outcome.estimated_cost,
        "spent": outcome.spent,
        "paused_at_gap": outcome.paused_at_gap,
        "error": outcome.error,
    }


# ── read / list ──────────────────────────────────────────────────────────────


@router.get("")
async def list_jobs(
    project_id: UUID | None = Query(None),
    book_id: UUID | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """List the caller's jobs scoped by ``book_id`` (the book anchor the GUI passes)
    and/or ``project_id`` (the general scope). At least one is required."""
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required"
        )
    if project_id is None and book_id is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="one of project_id or book_id is required",
        )
    params = [principal.user_id]
    preds = ["user_id=$1"]
    if project_id is not None:
        params.append(project_id)
        preds.append(f"project_id=${len(params)}")
    if book_id is not None:
        params.append(book_id)
        preds.append(f"book_id=${len(params)}")
    where = " AND ".join(preds)
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM enrichment_job WHERE {where}", *params
        )
        rows = await conn.fetch(
            f"""SELECT job_id, project_id, status, technique, entity_kind, book_id, proposals_total,
                      estimated_cost_tokens, actual_cost_tokens, max_spend_tokens,
                      error_message, created_at
               FROM enrichment_job
               WHERE {where}
               ORDER BY created_at DESC LIMIT ${len(params)+1} OFFSET ${len(params)+2}""",
            *params, limit, offset,
        )
    return {
        "items": [_job_row(r) for r in rows],
        "total": int(total or 0),
        "limit": limit,
        "offset": offset,
    }


@router.get("/{job_id}")
async def get_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required"
        )
    async with pool.acquire() as conn:
        r = await conn.fetchrow(
            """SELECT job_id, project_id, status, technique, entity_kind, book_id, proposals_total,
                      estimated_cost_tokens, actual_cost_tokens, max_spend_tokens,
                      error_message, created_at
               FROM enrichment_job
               WHERE user_id=$1 AND project_id=$2 AND job_id=$3""",
            principal.user_id, project_id, job_id,
        )
    if r is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
        )
    return _job_row(r)


def _job_row(r: asyncpg.Record) -> dict:
    return {
        "job_id": str(r["job_id"]),
        "project_id": str(r["project_id"]),
        "status": r["status"],
        "technique": r["technique"],
        "entity_kind": r["entity_kind"],
        "book_id": str(r["book_id"]) if r["book_id"] is not None else None,
        "proposals_total": r["proposals_total"],
        "estimated_cost": float(r["estimated_cost_tokens"]),
        "actual_cost": float(r["actual_cost_tokens"]),
        "max_spend": float(r["max_spend_tokens"]) if r["max_spend_tokens"] is not None else None,
        "error_message": r["error_message"],
        "created_at": r["created_at"].isoformat(),
    }


# ── lifecycle actions (C8 state machine over the persisted job row) ───────────
#
# The runner pauses itself on a cost-cap breach (M5, autonomous). These routes
# expose the explicit author transitions on the same C8 DAG: cancel a queued/
# paused job, or pause/resume a job. They mutate ONLY the job's lifecycle status
# (never a proposal's H0 markers). An illegal transition → 409.
#
# SCOPE (honest, WARN-1): these transitions flip the persisted ``status`` ONLY —
# they do NOT re-drive the pipeline. ``resume`` therefore marks a paused job
# ``running`` but does not itself re-process the remaining gaps (the original
# request's targets + model_refs are not persisted on the job row, so the runner
# cannot be rebuilt here). Re-running a job IS safe, though: the per-gap
# idempotent persist (UNIQUE(job_id, gap_ref)) prevents DUPLICATE proposals and
# ``build_live_runner(spent_so_far=...)`` (seeded from ``actual_cost_tokens`` via
# :func:`load_spent_so_far`) prevents DOUBLE-CHARGING the budget on a re-run.
# Full auto-resume (re-drive only the not-yet-persisted gaps from a single
# resume call) is tracked as a deferral — see SESSION_PATCH D-C14-FULL-RESUME.

async def load_spent_so_far(
    *, pool: asyncpg.Pool, job_id: UUID
) -> float:
    """Read what a prior run already spent (``actual_cost_tokens``) so a re-run can
    seed its budget and NOT reset to 0 / double-spend (WARN-1)."""
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT actual_cost_tokens FROM enrichment_job WHERE job_id=$1", job_id
        )
    return float(v) if v is not None else 0.0


async def _transition_job(
    *, action: str, job_id: UUID, project_id: UUID,
    principal: Principal, pool: asyncpg.Pool,
) -> dict:
    """Apply an author lifecycle action through the C8 state machine.

    ``start`` walks pending→estimating→running; ``resume`` paused→running;
    ``pause`` running→paused; ``cancel`` →cancelled. Any move illegal from the
    current persisted state raises 409 (the C8 machine refuses it).

    These mutate the persisted ``status`` ONLY — they do NOT re-drive the
    pipeline (see the module note above on resume scope, WARN-1)."""
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required"
        )
    async with pool.acquire() as conn:
        # M2/HIGH-1: read-modify-write under a row lock so the control transition is
        # atomic vs the runner's CAS lifecycle writes. SELECT … FOR UPDATE holds the
        # row for the txn: a concurrent runner UPDATE on the same row blocks until we
        # commit, then re-evaluates its `WHERE status='running'` guard against the new
        # status — so neither writer can clobber the other (e.g. a cancel landing as
        # the runner completes ends 'cancelled', and the runner's complete no-ops).
        async with conn.transaction():  # SELECT FOR UPDATE + UPDATE + emit atomic
            r = await conn.fetchrow(
                """SELECT status FROM enrichment_job
                   WHERE user_id=$1 AND project_id=$2 AND job_id=$3
                   FOR UPDATE""",
                principal.user_id, project_id, job_id,
            )
            if r is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
                )
            record = JobRecord(job_id=str(job_id), state=JobState(r["status"]))
            machine = JobStateMachine(record)
            try:
                if action == "pause":
                    await machine.pause(reason=PauseReason.MANUAL)
                elif action == "cancel":
                    await machine.cancel()
                elif action == "resume":
                    await machine.resume()
                else:  # start: pending → estimating → running
                    if record.state is JobState.PENDING:
                        await machine.estimate()
                    await machine.start()
            except IllegalTransitionError as exc:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail=str(exc)
                )
            await conn.execute(
                "UPDATE enrichment_job SET status=$4, updated_at=now() "
                "WHERE user_id=$1 AND project_id=$2 AND job_id=$3",
                principal.user_id, project_id, job_id, record.state.value,
            )
            # Unified Job Control Plane P1 — emit the author lifecycle transition on the
            # SAME conn as the UPDATE (H1). A non-canonical state (estimating) is skipped;
            # 'start' walks pending→estimating→running and emits only the final 'running'.
            cstatus = canonical_status(record.state.value)
            if cstatus is not None:
                await emit_job_event(
                    conn, service=JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(principal.user_id), kind=JOB_KIND, status=cstatus,
                    error=job_error(record.error_message) if cstatus == "failed" else None,
                )
    return {"job_id": str(job_id), "status": record.state.value}


@router.post("/{job_id}/start")
async def start_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    return await _transition_job(
        action="start", job_id=job_id, project_id=project_id,
        principal=principal, pool=pool,
    )


@router.post("/{job_id}/pause")
async def pause_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    return await _transition_job(
        action="pause", job_id=job_id, project_id=project_id,
        principal=principal, pool=pool,
    )


async def _compensate_stuck_running(
    pool: asyncpg.Pool, *, job_id: UUID, owner_user_id, project_id: UUID, to_status: str
) -> str:
    """Roll a control flip back when its re-drive enqueue FAILED (/review-impl MED-1).

    resume/retry flip the row to 'running' BEFORE the XADD (the worker's run_job
    pre-flight bails on a still-'paused' row, so the flip must precede the trigger).
    If the XADD then fails there is no worker trigger AND no stranded-running sweeper
    for enrichment_job → the job would be stuck 'running' and NOT re-triggerable
    (resume 409s unless paused, retry 409s unless failed). So roll the flip back to
    its prior state (``to_status`` = 'paused' for resume / 'failed' for retry),
    GUARDED on the row still being 'running' (a racing worker that already advanced
    it is never clobbered) + emit, so the action stays available. Best-effort: if
    THIS also fails the row is left 'running' (operator-recoverable). Returns the
    resulting status string."""
    try:
        async with pool.acquire() as conn:
            async with conn.transaction():  # rollback UPDATE + emit atomic (H1)
                row = await conn.fetchrow(
                    "UPDATE enrichment_job SET status=$4, updated_at=now() "
                    "WHERE user_id=$1 AND project_id=$2 AND job_id=$3 AND status='running' "
                    "RETURNING error_message",
                    owner_user_id, project_id, job_id, to_status,
                )
                if row is None:
                    return "running"  # a worker already advanced it — leave it be
                cstatus = canonical_status(to_status)
                if cstatus is not None:
                    await emit_job_event(
                        conn, service=JOB_SERVICE, job_id=str(job_id),
                        owner_user_id=str(owner_user_id), kind=JOB_KIND, status=cstatus,
                        error=job_error(row["error_message"]) if cstatus == "failed" else None,
                    )
        return to_status
    except Exception:  # noqa: BLE001 — best-effort rollback; leave running if it fails
        logger.warning(
            "enqueue-failure rollback for job %s failed (left running — operator-recoverable)",
            job_id, exc_info=True,
        )
        return "running"


@router.post("/{job_id}/resume", status_code=status.HTTP_202_ACCEPTED)
async def resume_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Resume a cost-cap-paused job (F-C14-1/051).

    Flips paused→running (C8) AND enqueues a resume trigger on the Redis stream;
    the background resume worker re-drives the job, skipping already-done gaps
    (no re-spend). Non-blocking — returns 202 once enqueued. An illegal
    transition (e.g. not paused) → 409 from the C8 machine before any enqueue."""
    result = await _transition_job(
        action="resume", job_id=job_id, project_id=project_id,
        principal=principal, pool=pool,
    )
    # Enqueue the re-drive trigger. On failure, roll the paused→running flip BACK to
    # 'paused' so the job stays re-triggerable (a flipped-but-un-enqueued job is stuck
    # 'running' with no worker trigger + no sweeper, and a repeat resume 409s — MED-1).
    producer = make_redis_producer(settings.redis_url)
    try:
        await producer.xadd(
            LORE_ENRICHMENT_RESUME_STREAM,
            {
                "job_id": str(job_id),
                "project_id": str(project_id),
                "user_id": str(principal.user_id),
            },
            maxlen=10000,
        )
        result["resume"] = "enqueued"
    except Exception:  # noqa: BLE001 — enqueue failure must not 500 a flipped job
        logger.warning("resume enqueue failed for job %s — rolling back to paused", job_id, exc_info=True)
        result["status"] = await _compensate_stuck_running(
            pool, job_id=job_id, owner_user_id=principal.user_id,
            project_id=project_id, to_status="paused",
        )
        result["resume"] = "enqueue_failed"
    finally:
        await producer.aclose()
    return result


@router.post("/{job_id}/cancel")
async def cancel_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    return await _transition_job(
        action="cancel", job_id=job_id, project_id=project_id,
        principal=principal, pool=pool,
    )


@router.post("/{job_id}/retry", status_code=status.HTTP_202_ACCEPTED)
async def retry_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    """Retry a FAILED enrichment job (D-JOBS-P4-RETRY-LORE).

    Re-drives the SAME job_id over the live async path (resume stream → the
    re-drive worker), which SKIPS already-done gaps (UNIQUE(job_id,gap_ref) +
    skip_gap_refs → no re-spend) and re-runs the rest. Flips failed→running +
    emits the transition for immediate feedback (mirroring resume), then enqueues.

    Idempotent + concurrency-safe: the failed→running CAS makes a double-retry a
    no-op (only a genuinely failed, owner-scoped row transitions); the M1 per-job
    advisory claim makes a retry-while-already-running a safe worker no-op. An
    illegal retry (not failed) → 409; not owned/found → 404 (never a cross-tenant
    oracle). Unlike the C8 manual transitions this is NOT a state-machine move
    (failed is terminal there) — retry RESURRECTS via a re-run, exactly like the
    knowledge/video-gen retries (D-JOBS-P4-RETRY)."""
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required"
        )
    async with pool.acquire() as conn:
        async with conn.transaction():  # CAS UPDATE + emit_job_event atomic (H1)
            row = await conn.fetchrow(
                """UPDATE enrichment_job SET status='running', updated_at=now()
                   WHERE user_id=$1 AND project_id=$2 AND job_id=$3 AND status='failed'
                   RETURNING user_id""",
                principal.user_id, project_id, job_id,
            )
            if row is not None:
                await emit_job_event(
                    conn, service=JOB_SERVICE, job_id=str(job_id),
                    owner_user_id=str(principal.user_id), kind=JOB_KIND, status="running",
                )
    if row is None:
        # The CAS didn't match: disambiguate owner-scoped (404 unknown/not-owned vs
        # 409 not-failed) — never leak existence across tenants.
        cur = await pool.fetchval(
            "SELECT status FROM enrichment_job WHERE user_id=$1 AND project_id=$2 AND job_id=$3",
            principal.user_id, project_id, job_id,
        )
        if cur is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="job not found"
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"job not retryable from status '{cur}' (only 'failed')",
        )
    # Enqueue the re-drive. On failure, roll the failed→running flip BACK to 'failed'
    # so the job stays retryable (a flipped-but-un-enqueued job is stuck 'running' with
    # no worker trigger + no sweeper, and a repeat retry 409s — MED-1).
    result = {"job_id": str(job_id), "status": "running"}
    producer = make_redis_producer(settings.redis_url)
    try:
        await producer.xadd(
            LORE_ENRICHMENT_RESUME_STREAM,
            {
                "job_id": str(job_id),
                "project_id": str(project_id),
                "user_id": str(principal.user_id),
            },
            maxlen=10000,
        )
        result["retry"] = "enqueued"
    except Exception:  # noqa: BLE001 — enqueue failure must not 500 a flipped job
        logger.warning("retry enqueue failed for job %s — rolling back to failed", job_id, exc_info=True)
        result["status"] = await _compensate_stuck_running(
            pool, job_id=job_id, owner_user_id=principal.user_id,
            project_id=project_id, to_status="failed",
        )
        result["retry"] = "enqueue_failed"
    finally:
        await producer.aclose()
    return result
