"""Internal dispatch endpoint — Auto-Draft Factory S1 (decision A).

`POST /internal/translation/dispatch-job` lets a trusted internal caller
(campaign-service) create a translation job ON BEHALF OF a user, over an
internal-token call carrying the VERIFIED `user_id` in the body — NOT a minted
user-JWT. Ownership is re-verified against the asserted `user_id` (defense in
depth) before reusing the exact same job-create core as the public route.

Mounted under `/internal/*` → reachable service-to-service inside the cluster
only; the gateway proxies `/v1/*`, never `/internal/*`.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel

from ..config import settings as app_settings
from ..deps import get_db
from ..models import CreateJobPayload
from .jobs import _verify_book_owner, _resolve_and_create_job, _cancel_job_core

router = APIRouter(prefix="/internal/translation", tags=["internal"])


async def require_internal_token(
    x_internal_token: str | None = Header(default=None),
) -> None:
    if (
        not app_settings.internal_service_token
        or x_internal_token != app_settings.internal_service_token
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"code": "TRANSL_INVALID_INTERNAL_TOKEN", "message": "invalid internal token"},
        )


class InternalDispatchPayload(BaseModel):
    user_id: UUID
    book_id: UUID
    chapter_ids: list[UUID]
    target_language: str | None = None
    model_source: str | None = None
    model_ref: UUID | None = None
    # S5b: per-campaign V3 verifier model (null → falls back to the translator,
    # per v3/orchestrator.py _verifier_model). CreateJobPayload already overlays
    # + persists + publishes these; we just forward them.
    verifier_model_source: str | None = None
    verifier_model_ref: UUID | None = None
    # S5b-eval: per-campaign translation eval-judge model. Rides through to the
    # translation.quality event (not used by the worker) so learning's M7d-2
    # fidelity judge uses the campaign's chosen model.
    eval_judge_model_source: str | None = None
    eval_judge_model_ref: UUID | None = None
    # D-FACTORY-V3-PIPELINE: the Auto-Draft Factory IS the V3 quality pipeline
    # (Translator→Verifier→Corrector + the M7a `translation.quality` emit that the
    # eval stage + S5b-eval judge depend on). This endpoint is campaign-only, so it
    # defaults to 'v3' — without it the job runs the book/user default (usually v2),
    # the verifier never runs, no `translation.quality` fires, and the campaign's
    # eval stage + eval_fidelity_score never engage. Overridable if a campaign ever
    # needs v2.
    pipeline_version: str | None = "v3"
    # S2: default-skip idempotency applies here too (the campaign driver relies
    # on it — re-dispatching an already-translated chapter must not re-spend).
    force_retranslate: bool = False
    # S4a: the owning campaign, threaded into the job + every provider job_meta.
    campaign_id: UUID | None = None


class DispatchResponse(BaseModel):
    job_id: UUID


@router.post(
    "/dispatch-job",
    response_model=DispatchResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require_internal_token)],
)
async def dispatch_job(
    payload: InternalDispatchPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> DispatchResponse:
    if not payload.chapter_ids:
        raise HTTPException(
            status_code=422,
            detail={"code": "TRANSL_NO_CHAPTERS", "message": "chapter_ids is empty"},
        )
    user_id = str(payload.user_id)
    # Re-verify the asserted user actually owns the book (defense in depth — the
    # internal token authenticates the SERVICE, this confirms the USER claim).
    await _verify_book_owner(payload.book_id, user_id)
    # model_source + model_ref are a pair (CreateJobPayload enforces it). When the
    # campaign supplies no model_ref, leave BOTH unset so the job falls back to the
    # user's saved translation settings rather than 422-ing on a half-override.
    model_source = payload.model_source if payload.model_ref else None
    # Same pairing rule for the verifier override: keep both unset on a half-override.
    verifier_model_source = payload.verifier_model_source if payload.verifier_model_ref else None
    eval_judge_model_source = payload.eval_judge_model_source if payload.eval_judge_model_ref else None
    job = await _resolve_and_create_job(
        db,
        payload.book_id,
        CreateJobPayload(
            chapter_ids=payload.chapter_ids,
            target_language=payload.target_language,
            model_source=model_source,
            model_ref=payload.model_ref,
            verifier_model_source=verifier_model_source,
            verifier_model_ref=payload.verifier_model_ref,
            eval_judge_model_source=eval_judge_model_source,
            eval_judge_model_ref=payload.eval_judge_model_ref,
            pipeline_version=payload.pipeline_version,  # D-FACTORY-V3-PIPELINE (default 'v3')
            force_retranslate=payload.force_retranslate,
        ),
        user_id,
        campaign_id=payload.campaign_id,
    )
    return DispatchResponse(job_id=job.job_id)


class InternalCancelPayload(BaseModel):
    user_id: UUID


@router.post(
    "/jobs/{job_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
    dependencies=[Depends(require_internal_token)],
)
async def dispatch_cancel(
    job_id: UUID,
    payload: InternalCancelPayload,
    db: asyncpg.Pool = Depends(get_db),
) -> None:
    """S3c-2: cancel a translation job on behalf of a campaign (internal-token +
    asserted user_id). Reuses the public cancel core — owner-scoped (404 if not
    owned), 409 if already terminal (the campaign treats both as success)."""
    await _cancel_job_core(db, job_id, str(payload.user_id))
