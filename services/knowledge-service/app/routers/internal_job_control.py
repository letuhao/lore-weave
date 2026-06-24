"""Internal job-control endpoint — Unified Job Control Plane P3.

`POST /internal/knowledge/jobs/{job_id}/{action}` (action ∈ cancel|pause|resume)
— the `job_id`-keyed control surface the central **jobs-service** routes user
control actions to. jobs-service has already verified the caller owns the job
(against its projection) + that the action is valid for the job's state; THIS
endpoint **re-verifies ownership on the actual `extraction_jobs` row** (spec M4 —
never trust the projection's possibly-stale owner) by loading via the
owner-scoped `ExtractionJobsRepo.get(owner, job_id)` (→ 404 if not owned/found),
then reuses the K16.4 transition (`_validate_or_409` + `update_status`) and the
project-state mirror. Internal-token + asserted `owner_user_id` in the body;
S2S only, never gateway-exposed.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from loreweave_jobs import JobStatus
from pydantic import BaseModel

from app.db.repositories.extraction_jobs import ExtractionJobsRepo, _canonical_job_status
from app.db.repositories.wiki_gen_jobs import WikiGenJobsRepo

# Canonical JobStatus values — a reconcile row whose status isn't one of these (the
# reserved `summarizing`) is skipped rather than shipped as an unparseable status.
_CANONICAL_STATUSES = frozenset(s.value for s in JobStatus)
from app.db.repositories.benchmark_runs import BenchmarkRunsRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_benchmark_runs_repo,
    get_extraction_jobs_repo,
    get_extraction_wake,
    get_knowledge_pool,
    get_projects_repo,
)
from app.jobs.extraction_wake import ExtractionWakeFn
from app.jobs.wiki_gen_enqueue import enqueue_wiki_gen  # wiki resume re-enqueue (parity w/ native)
from app.routers.internal_wiki import _redis  # shared lazy redis client for the wiki-gen XADD
from app.middleware.internal_auth import require_internal_token
from app.middleware.trace_id import trace_id_var
from app.routers.public.extraction import (
    StartJobRequest,
    _start_extraction_job_core,
    _validate_or_409,
)

router = APIRouter(
    prefix="/internal/knowledge/jobs",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


@router.get("")
async def reconcile_jobs(
    since: datetime = Query(..., description="ISO-8601 — rows updated at/after this"),
    limit: int = Query(1000, ge=1, le=5000, description="page cap — the sweeper's _PAGE_LIMIT"),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> dict:
    """Reconcile SOURCE (Unified Job Control Plane H1 backstop): extraction jobs updated
    since `since` (oldest-first, capped at `limit`), in canonical `JobEvent` payload shape,
    for the jobs-service sweep to upsert. Internal-token (router dep); ALL owners.

    A row whose native status has no canonical JobStatus (the reserved `summarizing`, which
    maps to itself — no writer today) is SKIPPED rather than shipped as a status the sweeper
    can't parse (matches the live consumer's no-op-on-unparseable behavior).

    UNIONs two knowledge job families that both federate to service='knowledge', kept apart
    by `kind`: `extraction` (knowledge-graph build) + `wiki_gen` (batch wiki generation,
    D-JOBS-WIKI-GEN-UNWIRED). EACH source independently fetches up to `limit` rows
    (`updated_at >= since`), then both are merged oldest-first and the merged list is capped
    at `limit`. The cap is a SOFT page bound, not a loss: a dropped (newer) row has
    occurred_at ≥ the last returned row, and `since` is inclusive, so the next sweep re-fetches
    it — the watermark stays monotone across both families. (Sustained extraction backlog
    >`limit` could delay a wiki row's BACKSTOP heal, never its visibility — the live emit
    stream is the primary path; `D-JOBS-WIKI-GEN-RECONCILE-INDEX` tracks the index.)"""
    # Each entry is (sort_dt, payload). Sort on the real datetime (NOT the isoformat string)
    # so a future source emitting a different tz-offset can't misorder the merge.
    merged: list[tuple[datetime | None, dict]] = []

    rows = await jobs_repo.list_since(since, limit=limit)
    for j in rows:
        status = _canonical_job_status(j.status)
        if status not in _CANONICAL_STATUSES:  # e.g. 'summarizing' — not a JobStatus
            continue
        merged.append((j.updated_at, {
            "service": "knowledge", "job_id": str(j.job_id), "owner_user_id": str(j.user_id),
            "kind": "extraction", "status": status,
            "parent_job_id": None, "detail_status": None,
            "progress": ({"done": j.items_processed, "total": j.items_total}
                         if j.items_total else None),
            "title": None,
            # P4 — carry the cumulative cost (reliable, on the row). model + params are
            # NOT on the row (resolved-NAME needs a per-row provider lookup the sweep
            # can't afford), so this backstop leaves them None — the projection's
            # COALESCE keeps whatever the live 'running' event set (best-effort heal).
            "cost_usd": (float(j.cost_spent_usd) if j.cost_spent_usd is not None else None),
            "error": ({"code": "extraction_failed", "message": (j.error_message or "")[:500]}
                      if j.status == "failed" else None),
            "occurred_at": j.updated_at.isoformat() if j.updated_at else None,
        }))
    # wiki-gen UNION — list_since already maps `complete`→`completed` (all wiki statuses
    # are canonical), so no skip-filter is needed here.
    wiki_repo = WikiGenJobsRepo(get_knowledge_pool())
    for w in await wiki_repo.list_since(since, limit=limit):
        cost = w["cost_spent_usd"]
        merged.append((w["updated_at"], {
            "service": "knowledge", "job_id": str(w["job_id"]),
            "owner_user_id": str(w["user_id"]), "kind": "wiki_gen", "status": w["status"],
            "parent_job_id": None, "detail_status": None, "progress": None, "title": None,
            "cost_usd": (float(cost) if cost is not None else None),
            "error": ({"code": "wiki_gen_failed", "message": (w["error_message"] or "")[:500]}
                      if w["native_status"] == "failed" else None),
            "occurred_at": w["updated_at"].isoformat() if w["updated_at"] else None,
        }))
    # Merge oldest-first by datetime (None sorts first, harmless) + cap (soft page bound).
    merged.sort(key=lambda e: (e[0] is not None, e[0]))
    return {"jobs": [payload for _dt, payload in merged[:limit]]}

# action → (target canonical status, pause_reason, project extraction_status mirror,
#           project extraction_enabled). Mirrors the K16.4 public pause/resume/cancel.
_ACTIONS = {
    "cancel": ("cancelled", None, "disabled", False),
    "pause": ("paused", "user", "paused", True),
    "resume": ("running", None, "building", True),
}


class JobControlPayload(BaseModel):
    # The asserted OWNER (jobs-service forwards the verified JWT sub). Re-checked
    # against the row here — M4.
    owner_user_id: UUID
    # The job KIND (D-JOBS-SECONDARY-KIND-CONTROL) — knowledge hosts BOTH `extraction`
    # (extraction_jobs) and `wiki_gen` (wiki_gen_jobs). None ⇒ extraction (back-compat for an
    # older jobs-service). control_extraction_job dispatches wiki_gen to the wiki repo.
    kind: str | None = None


class JobControlResponse(BaseModel):
    job_id: UUID
    status: str


@router.post("/{job_id}/{action}", response_model=JobControlResponse)
async def control_extraction_job(
    job_id: UUID,
    action: str,
    payload: JobControlPayload,
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    benchmark_repo: BenchmarkRunsRepo = Depends(get_benchmark_runs_repo),
    extraction_wake: ExtractionWakeFn = Depends(get_extraction_wake),
) -> JobControlResponse:
    # wiki_gen dispatch (D-JOBS-SECONDARY-KIND-CONTROL) — knowledge's batch wiki-gen producer.
    # Native control: cancel a not-yet-running job (pending|paused) + resume (paused). A
    # running wiki job is NOT cancellable (the orchestrator doesn't poll mid-loop —
    # D-WIKI-M7B-RUNNING-CANCEL). The repo methods are owner-blind, so re-verify owner here (M4).
    if payload.kind == "wiki_gen":
        return await _control_wiki_gen_job(job_id, action, payload.owner_user_id)
    # D-JOBS-P4-RETRY-KNOWLEDGE — re-submit a failed extraction job as a fresh one.
    if action == "retry":
        return await _retry_extraction_job_core(
            job_id, payload.owner_user_id,
            jobs_repo, projects_repo, benchmark_repo, extraction_wake,
        )
    if action not in _ACTIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNKNOWN_ACTION", "message": f"unknown action: {action}"},
        )
    target, pause_reason, proj_status, proj_enabled = _ACTIONS[action]

    # M4 — re-verify ownership on the row: get() is owner-scoped, so a job not
    # owned by the asserted user simply isn't found (404, never a cross-tenant act).
    job = await jobs_repo.get(payload.owner_user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )

    trace_id = trace_id_var.get()
    _validate_or_409(job.status, target, trace_id=trace_id, pause_reason=pause_reason)
    updated = await jobs_repo.update_status(payload.owner_user_id, job_id, target)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_CHANGED", "message": "job status changed concurrently"},
        )
    # Mirror to the project so the FE reflects the new state (advisory; the job
    # row is the SoT — same non-atomic note as the K16.4 public cancel).
    await projects_repo.set_extraction_state(
        payload.owner_user_id, job.project_id,
        extraction_enabled=proj_enabled, extraction_status=proj_status,
    )
    return JobControlResponse(job_id=updated.job_id, status=updated.status)


async def _control_wiki_gen_job(job_id: UUID, action: str, owner_user_id: UUID) -> JobControlResponse:
    """Cancel|resume a wiki-gen job via the WikiGenJobsRepo (which emits the transition,
    Slice C). The repo cancel/resume are owner-BLIND + status-guarded (cancel: pending|paused
    → cancelled; resume: paused → pending), so re-verify ownership on the row first (M4 — a
    job not owned by the asserted user → 404, never a cross-tenant act). A guarded mutation
    that flips nothing (e.g. cancel on a running/terminal job) → 409."""
    if action not in ("cancel", "resume"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "JOBS_UNKNOWN_ACTION", "message": f"wiki_gen supports cancel|resume, not {action}"},
        )
    repo = WikiGenJobsRepo(get_knowledge_pool())
    job = await repo.get(job_id)
    if job is None or job.user_id != owner_user_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    ok = await (repo.cancel(job_id) if action == "cancel" else repo.resume(job_id))
    if not ok:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_STATUS_CHANGED",
                    "message": f"wiki_gen job not {action}able in status '{job.status}'"},
        )
    if action == "resume":
        # CRITICAL: mirror the native resume_wiki_gen_job — flipping paused→pending is NOT
        # enough; the consumer is event-driven, so without re-enqueuing the job sits in
        # pending until a process-restart drain picks it up. Re-enqueue so it re-drives now
        # (skip-done handles partial progress).
        await enqueue_wiki_gen(_redis(), str(job_id))
    return JobControlResponse(job_id=job_id, status="cancelled" if action == "cancel" else "pending")


async def _retry_extraction_job_core(
    job_id: UUID,
    owner_user_id: UUID,
    jobs_repo: ExtractionJobsRepo,
    projects_repo: ProjectsRepo,
    benchmark_repo: BenchmarkRunsRepo,
    extraction_wake: ExtractionWakeFn,
) -> JobControlResponse:
    """D-JOBS-P4-RETRY-KNOWLEDGE — re-submit a FAILED extraction job as a FRESH job (new
    job_id), reusing the failed row's scope/models/range/targets. Mirrors translation's
    `_retry_job_core`: owner-scoped (404 if not owned — `get` is owner-scoped), 409 unless
    `failed` (retry is only offered there), 409 if campaign-managed (the campaign saga
    re-dispatches its own failed stages + owns the spend — a standalone user retry would
    detach + risk double-spend).

    The failed row carries EVERY `StartJobRequest` field, so we reconstruct it and run the
    full `_start_extraction_job_core` — which RE-VALIDATES the K17.9 benchmark + monthly-budget
    gates (a retry that can no longer pass them 409s, exactly like a fresh start), creates +
    starts the job, emits the 'running' lifecycle event, and best-effort wakes worker-ai. The
    failed row stays as history. campaign_id is NOT carried (standalone re-run)."""
    job = await jobs_repo.get(owner_user_id, job_id)
    if job is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "JOBS_NOT_FOUND", "message": "job not found"},
        )
    if job.status != "failed":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_NOT_RETRYABLE",
                    "message": f"only a failed job can be retried (status='{job.status}')"},
        )
    if job.campaign_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"code": "JOBS_CAMPAIGN_MANAGED",
                    "message": "this extraction job is managed by its campaign — "
                               "retry the campaign, not the job"},
        )
    body = StartJobRequest(
        scope=job.scope,
        scope_range=job.scope_range,
        llm_model=job.llm_model,
        embedding_model=job.embedding_model,
        max_spend_usd=job.max_spend_usd,
        items_total=job.items_total,
        targets=job.targets,
        concurrency_level=job.concurrency_level,
        pinned_glossary_entity_ids=job.pinned_entity_ids,
    )
    new_job = await _start_extraction_job_core(
        job.project_id, body, owner_user_id,
        projects_repo, jobs_repo, benchmark_repo,
        extraction_wake=extraction_wake,
    )
    return JobControlResponse(job_id=new_job.job_id, status=new_job.status)
