"""Internal dispatch endpoint — Auto-Draft Factory S1 (decision A).

`POST /internal/knowledge/projects/{project_id}/dispatch-extraction` lets a
trusted internal caller (campaign-service) start an extraction job ON BEHALF OF
a user, over an internal-token call carrying the VERIFIED `user_id` in the body
— NOT a minted user-JWT.

It REUSES the public `start_extraction_job` core wholesale (so the benchmark
gate, budget checks, and active-job guard all still apply); it only supplies the
project's already-configured `embedding_model` and the campaign's LLM model_ref,
then delegates. The knowledge runner does not yet honour `chapter_range`
(D-K16.2-02b → S2); the range is forwarded for when it does.

Mounted under `/internal/*` (X-Internal-Token) → S2S only; never gateway-exposed.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.db.repositories.benchmark_runs import BenchmarkRunsRepo
from app.db.repositories.extraction_jobs import ExtractionJobsRepo
from app.db.repositories.projects import ProjectsRepo
from app.deps import (
    get_benchmark_runs_repo,
    get_extraction_jobs_repo,
    get_projects_repo,
)
from app.middleware.internal_auth import require_internal_token
from app.routers.public.extraction import StartJobRequest, start_extraction_job

router = APIRouter(
    prefix="/internal/knowledge/projects",
    tags=["internal"],
    dependencies=[Depends(require_internal_token)],
)


class InternalExtractionPayload(BaseModel):
    user_id: UUID
    scope: str = "chapters"
    chapter_from: int | None = None
    chapter_to: int | None = None
    # Accepted for forward-compat but currently unused: knowledge extraction is
    # always BYOK `user_model` (StartJobRequest has no model_source field), so
    # only `model_ref` (the extraction LLM) is forwarded as `llm_model`.
    model_source: str | None = None
    model_ref: UUID | None = None


class DispatchResponse(BaseModel):
    job_id: UUID


@router.post(
    "/{project_id}/dispatch-extraction",
    response_model=DispatchResponse,
    status_code=status.HTTP_201_CREATED,
)
async def dispatch_extraction(
    project_id: UUID,
    payload: InternalExtractionPayload,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
    benchmark_repo: BenchmarkRunsRepo = Depends(get_benchmark_runs_repo),
) -> DispatchResponse:
    # Asserted-user ownership is enforced by ProjectsRepo.get(user_id, …) — a
    # project not owned by the asserted user simply isn't found.
    project = await projects_repo.get(payload.user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "KNOW_PROJECT_NOT_FOUND", "message": "project not found"},
        )
    if not project.embedding_model:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "KNOW_NO_EMBEDDING_MODEL",
                    "message": "project has no embedding_model configured"},
        )
    if payload.model_ref is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail={"code": "KNOW_NO_LLM_MODEL",
                    "message": "model_ref (extraction LLM) is required"},
        )

    scope_range = None
    if payload.chapter_from is not None and payload.chapter_to is not None:
        scope_range = {"chapter_range": [payload.chapter_from, payload.chapter_to]}

    body = StartJobRequest(
        scope=payload.scope,
        scope_range=scope_range,
        llm_model=str(payload.model_ref),
        embedding_model=project.embedding_model,
    )
    job = await start_extraction_job(
        project_id, body, payload.user_id, projects_repo, jobs_repo, benchmark_repo,
    )
    return DispatchResponse(job_id=job.job_id)
