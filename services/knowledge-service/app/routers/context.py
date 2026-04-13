"""POST /internal/context/build — builds a memory block for chat-service.

Sits under the /internal/* route prefix so the existing
require_internal_token dependency gates access. Trusts the caller's
user_id and project_id (chat-service validates JWT + project ownership
before issuing this call).

The endpoint is deliberately thin: request validation → repo + client
dependency injection → builder dispatch → response marshalling. All
the heavy lifting is in app.context.*.

Dependencies are supplied via FastAPI Depends so tests can override
them with `app.dependency_overrides[...]` instead of monkey-patching
module globals.
"""

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field

from app.clients.glossary_client import GlossaryClient
from app.clients.glossary_client import get_glossary_client as _get_glossary_client_singleton
from app.context.builder import ProjectNotFound, build_context
from app.db.pool import get_knowledge_pool
from app.db.repositories.projects import ProjectsRepo
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
    return SummariesRepo(get_knowledge_pool())


async def get_projects_repo() -> ProjectsRepo:
    return ProjectsRepo(get_knowledge_pool())


async def get_glossary_client() -> GlossaryClient:
    return _get_glossary_client_singleton()


# ── request / response models ──────────────────────────────────────────────


class ContextBuildRequest(BaseModel):
    user_id: UUID
    session_id: UUID | None = None
    project_id: UUID | None = None
    # User's current message — used as the glossary FTS query in Mode 2.
    # 4k char cap fits legitimate chat turns without giving callers a
    # silent DoS knob.
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
    summaries_repo: SummariesRepo = Depends(get_summaries_repo),
    projects_repo: ProjectsRepo = Depends(get_projects_repo),
    glossary_client: GlossaryClient = Depends(get_glossary_client),
) -> ContextBuildResponse:
    try:
        built = await build_context(
            summaries_repo,
            projects_repo,
            glossary_client,
            user_id=req.user_id,
            project_id=req.project_id,
            message=req.message,
        )
    except ProjectNotFound:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    except NotImplementedError as exc:
        # Mode 3 (full extraction) is Track 2 scope. chat-service gets
        # a clear 501 and falls back to plain replay.
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
