"""POST /internal/context/build — builds a memory block for chat-service.

Sits under the /internal/* route prefix so the existing
require_internal_token dependency gates access. Trusts the caller's
user_id and project_id (chat-service validates JWT + project ownership
before issuing this call).

The endpoint is deliberately thin: request validation → repo dependency
injection → builder dispatch → response marshalling. All the heavy
lifting is in app.context.*.

Repositories are supplied via FastAPI `Depends(...)` so tests can
override them with `app.dependency_overrides[get_summaries_repo]`
instead of monkey-patching module globals.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.context.builder import build_context
from app.db.pool import get_knowledge_pool
from app.db.repositories.summaries import SummariesRepo
from app.middleware.internal_auth import require_internal_token

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/internal/context",
    tags=["Internal"],
    dependencies=[Depends(require_internal_token)],
)


# ── dependency-injection helpers ────────────────────────────────────────────


async def get_summaries_repo() -> SummariesRepo:
    """FastAPI dependency returning a SummariesRepo bound to the live pool.

    Tests substitute this via `app.dependency_overrides[get_summaries_repo]`
    without touching the module-level `_knowledge_pool` global.
    """
    return SummariesRepo(get_knowledge_pool())


# ── request / response models ──────────────────────────────────────────────


class ContextBuildRequest(BaseModel):
    user_id: UUID
    session_id: UUID | None = None
    project_id: UUID | None = None
    # User's current message — unused in Mode 1, consumed by Mode 2+ for
    # glossary FTS. 4k char cap fits legitimate chat turns without giving
    # callers a silent DoS knob.
    message: str = Field(default="", max_length=4000)


class ContextBuildResponse(BaseModel):
    # from_attributes=True lets model_validate read fields off the builder's
    # BuiltContext dataclass directly, so the router never has to hand-copy
    # fields from one shape to the other.
    model_config = ConfigDict(from_attributes=True)

    mode: str
    context: str
    recent_message_count: int
    token_count: int


@router.post("/build", response_model=ContextBuildResponse)
async def build(
    req: ContextBuildRequest,
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> ContextBuildResponse:
    try:
        built = await build_context(repo, req.user_id, req.project_id)
    except NotImplementedError as exc:
        # K4a only implements Mode 1. Mode 2 lands in K4b; until then
        # chat-service gets a clear 501 and falls back to plain replay.
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=str(exc),
        )
    except Exception as exc:
        logger.exception("context build failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="context build failed",
        )
    return ContextBuildResponse.model_validate(built)
