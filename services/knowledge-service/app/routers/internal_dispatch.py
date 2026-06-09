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
from app.clients.embedding_client import EmbeddingError, probe_embedding_dimension
from app.config import settings as app_settings
from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
from app.middleware.internal_auth import require_internal_token
from app.routers.public.extraction import (
    StartJobRequest,
    _delete_project_graph,
    _start_extraction_job_core,
    cancel_extraction_job,
)

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
    # S4a: the owning campaign, persisted on the extraction job + stamped onto
    # every provider job_meta by worker-ai for per-campaign cost attribution.
    campaign_id: UUID | None = None


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
    job = await _start_extraction_job_core(
        project_id, body, payload.user_id, projects_repo, jobs_repo, benchmark_repo,
        campaign_id=payload.campaign_id,
    )
    return DispatchResponse(job_id=job.job_id)


class SetCampaignModelsPayload(BaseModel):
    """S5b — a campaign applies its embedding/reranker picks to the chosen project
    (the project is SSOT for these). user_id is the asserted owner. A *_model_ref
    of None means 'not provided — leave unchanged'."""
    user_id: UUID
    embedding_model_source: str | None = None
    embedding_model_ref: UUID | None = None
    rerank_model_source: str | None = None
    rerank_model_ref: UUID | None = None
    # Required to change embedding on a project that already has a graph
    # (destructive: deletes the stale vectors before re-embedding).
    confirm_embedding_change: bool = False


class SetCampaignModelsResponse(BaseModel):
    project_id: UUID
    embedding_model: str | None
    embedding_changed: bool
    graph_deleted: bool
    rerank_model: str | None


@router.post("/{project_id}/set-campaign-models", response_model=SetCampaignModelsResponse)
async def set_campaign_models(
    project_id: UUID,
    payload: SetCampaignModelsPayload,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
) -> SetCampaignModelsResponse:
    """S5b — apply a campaign's embedding/reranker model picks to its project.

    Embedding is the hazard: changing it invalidates the project's existing vector
    space. We use `extraction_status == 'disabled'` as the 'no graph yet' signal:
    a fresh project sets the model freely; a project WITH a graph requires
    `confirm_embedding_change` (→ probe dim, delete graph, set). Reranker is applied
    directly (no re-embed needed). The embedding dimension is probed BEFORE any
    delete so a bad model leaves the graph intact (422)."""
    project = await projects_repo.get(payload.user_id, project_id)
    if project is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"code": "KNOW_PROJECT_NOT_FOUND", "message": "project not found"},
        )

    embedding_changed = False
    graph_deleted = False
    new_embedding = project.embedding_model

    if payload.embedding_model_ref is not None:
        new_model = str(payload.embedding_model_ref)
        if new_model != (project.embedding_model or ""):
            has_graph = project.extraction_status != "disabled"
            if has_graph and not payload.confirm_embedding_change:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail={
                        "code": "KNOW_EMBEDDING_CONFLICT",
                        "message": ("changing the embedding model deletes the project's "
                                    "existing knowledge graph; resubmit with confirm_embedding_change"),
                    },
                )
            # Probe the new model's dimension BEFORE any destructive delete.
            try:
                new_dim = await probe_embedding_dimension(payload.user_id, new_model)
            except EmbeddingError as exc:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": "KNOW_EMBEDDING_PROBE_FAILED", "message": f"embedding probe failed: {exc}"},
                )
            if new_dim not in SUPPORTED_PASSAGE_DIMS:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail={"code": "KNOW_EMBEDDING_DIM_UNSUPPORTED",
                            "message": f"embedding dimension {new_dim} has no :Passage vector index"},
                )
            if has_graph:
                if not app_settings.neo4j_uri:
                    raise HTTPException(
                        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                        detail={"code": "KNOW_NEO4J_UNAVAILABLE", "message": "Neo4j not configured"},
                    )
                await _delete_project_graph(payload.user_id, project_id)
                graph_deleted = True
            await projects_repo.set_extraction_state(
                payload.user_id, project_id,
                extraction_enabled=False, extraction_status="disabled",
                embedding_model=new_model, embedding_dimension=new_dim,
            )
            embedding_changed = True
            new_embedding = new_model

    new_rerank = project.rerank_model
    if payload.rerank_model_ref is not None:
        new_rerank = str(payload.rerank_model_ref)
        await projects_repo.set_rerank_model(
            payload.user_id, project_id,
            rerank_model=new_rerank,
            rerank_model_source=payload.rerank_model_source or "user_model",
        )

    return SetCampaignModelsResponse(
        project_id=project_id,
        embedding_model=new_embedding,
        embedding_changed=embedding_changed,
        graph_deleted=graph_deleted,
        rerank_model=new_rerank,
    )


class InternalCancelPayload(BaseModel):
    user_id: UUID


@router.post("/{project_id}/extraction/cancel", status_code=status.HTTP_200_OK)
async def dispatch_cancel_extraction(
    project_id: UUID,
    payload: InternalCancelPayload,
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    jobs_repo: ExtractionJobsRepo = Depends(get_extraction_jobs_repo),
) -> dict:
    """S3c-2: cancel a project's active extraction on behalf of a campaign
    (internal-token + asserted user_id). Reuses the public cancel core — a 404
    (no active job) is treated as success by the campaign caller."""
    job = await cancel_extraction_job(project_id, payload.user_id, projects_repo, jobs_repo)
    return {"job_id": str(job.job_id), "status": job.status}
