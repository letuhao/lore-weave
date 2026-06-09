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
from .jobs import _verify_book_owner, _resolve_and_create_job

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
    # S2: default-skip idempotency applies here too (the campaign driver relies
    # on it — re-dispatching an already-translated chapter must not re-spend).
    force_retranslate: bool = False


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
    job = await _resolve_and_create_job(
        db,
        payload.book_id,
        CreateJobPayload(
            chapter_ids=payload.chapter_ids,
            target_language=payload.target_language,
            model_source=model_source,
            model_ref=payload.model_ref,
            force_retranslate=payload.force_retranslate,
        ),
        user_id,
    )
    return DispatchResponse(job_id=job.job_id)
