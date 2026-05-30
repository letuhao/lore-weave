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

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.api.principal import Principal, require_principal
from app.deps import get_db
from app.gaps.model import Dimension, EntityKind, Gap
from app.jobs.assembly import build_live_runner
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
    # Which enrichment TECHNIQUE drives the job. Default 'retrieval' (the P1 demo
    # path, unchanged). A P2/P3 technique (e.g. 'fabrication') is gate-enforced
    # END-TO-END: the runner resolves the pipeline through the gate-aware factory,
    # which REFUSES it (409) while the live eval gate is LOCKED (DEFERRED-054).
    technique: str = Field(default=Technique.RETRIEVAL.value)
    # Cost guardrail (C8); aligns with the frozen contract's max_spend_usd. The
    # reserved eval-cost line (M5) is held back from this cap.
    max_spend_usd: float | None = Field(default=None, ge=0.0)
    eval_reserve_fraction: float = Field(default=0.15, ge=0.0, lt=1.0)
    top_k: int = Field(default=5, ge=1, le=20)


def _gap_from_target(t: GapTarget) -> Gap | None:
    """Build a C7 :class:`Gap` from a target. Returns None for a fully-described
    entity (no missing dimension) — it is not a gap."""
    try:
        kind = EntityKind(t.entity_kind)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"unsupported entity_kind {t.entity_kind!r}",
        )
    present = tuple(
        d for d in Dimension if d.value in set(t.present_dimensions)
    )
    missing = tuple(d for d in Dimension if d not in set(present))
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

    Synchronous for the demo: the full pipeline runs and the outcome (job state,
    quarantined proposals, cost) is returned. H0: every proposal is quarantined.
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

    gaps: list[Gap] = []
    for t in body.targets:
        gap = _gap_from_target(t)
        if gap is not None:
            gaps.append(gap)
    if not gaps:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="no gaps to enrich (all targets fully described)",
        )

    # Persist the job row first so the runner + the event stream both key on the
    # real DB job id (event correlation). The job row records the REQUESTED
    # technique — a gate-refused fabrication job is then visible as a failed row
    # carrying technique='fabrication' (auditable refusal, not a silent drop).
    store = PgProposalStore(pool)
    db_job_id = await store.create_job(
        user_id=str(user_id),
        project_id=str(body.project_id),
        technique=technique.value,
        entity_kind="location",
        max_spend=body.max_spend_usd,
        estimated_cost=0.0,
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
            cost_cap=body.max_spend_usd,
            eval_reserve_fraction=body.eval_reserve_fraction,
            top_k=body.top_k,
            technique=technique.value,
        )
    except InactiveStrategyError as exc:
        await store.mark_job_status(
            job_id=db_job_id,
            status="failed",
            error_message=f"refused: technique {technique.value!r} gate-locked ({exc})",
        )
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
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)
        )
    try:
        context = StrategyContext(
            user_id=str(user_id),
            project_id=str(body.project_id),
            model_ref=str(body.generation_model_ref),
        )
        outcome = await bundle.runner.run_job(
            job_id=db_job_id, gaps=gaps, context=context, entity_kind="location"
        )
    finally:
        await bundle.aclose()

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
    project_id: UUID = Query(...),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    if principal.user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="auth required"
        )
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM enrichment_job WHERE user_id=$1 AND project_id=$2",
            principal.user_id, project_id,
        )
        rows = await conn.fetch(
            """SELECT job_id, status, technique, entity_kind, proposals_total,
                      estimated_cost_usd, actual_cost_usd, max_spend_usd,
                      error_message, created_at
               FROM enrichment_job
               WHERE user_id=$1 AND project_id=$2
               ORDER BY created_at DESC LIMIT $3 OFFSET $4""",
            principal.user_id, project_id, limit, offset,
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
            """SELECT job_id, status, technique, entity_kind, proposals_total,
                      estimated_cost_usd, actual_cost_usd, max_spend_usd,
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
        "status": r["status"],
        "technique": r["technique"],
        "entity_kind": r["entity_kind"],
        "proposals_total": r["proposals_total"],
        "estimated_cost": float(r["estimated_cost_usd"]),
        "actual_cost": float(r["actual_cost_usd"]),
        "max_spend": float(r["max_spend_usd"]) if r["max_spend_usd"] is not None else None,
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
# ``build_live_runner(spent_so_far=...)`` (seeded from ``actual_cost_usd`` via
# :func:`load_spent_so_far`) prevents DOUBLE-CHARGING the budget on a re-run.
# Full auto-resume (re-drive only the not-yet-persisted gaps from a single
# resume call) is tracked as a deferral — see SESSION_PATCH D-C14-FULL-RESUME.

async def load_spent_so_far(
    *, pool: asyncpg.Pool, job_id: UUID
) -> float:
    """Read what a prior run already spent (``actual_cost_usd``) so a re-run can
    seed its budget and NOT reset to 0 / double-spend (WARN-1)."""
    async with pool.acquire() as conn:
        v = await conn.fetchval(
            "SELECT actual_cost_usd FROM enrichment_job WHERE job_id=$1", job_id
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
        r = await conn.fetchrow(
            """SELECT status FROM enrichment_job
               WHERE user_id=$1 AND project_id=$2 AND job_id=$3""",
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


@router.post("/{job_id}/resume")
async def resume_job(
    job_id: UUID,
    project_id: UUID = Query(...),
    principal: Principal = Depends(require_principal),
    pool: asyncpg.Pool = Depends(get_db),
) -> dict:
    return await _transition_job(
        action="resume", job_id=job_id, project_id=project_id,
        principal=principal, pool=pool,
    )


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
