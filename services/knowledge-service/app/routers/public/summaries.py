"""K7.3 — Summaries endpoints under /v1/knowledge/.

Three routes:
  - GET   /v1/knowledge/summaries                       → list user's summaries
  - PATCH /v1/knowledge/summaries/global                → upsert L0 (global bio)
  - PATCH /v1/knowledge/projects/{project_id}/summary   → upsert L1 (project)

Empty content is allowed and persisted as an empty row — does NOT
delete. K7d owns user-data deletion; K7c owns content edits only.

Cross-user / nonexistent project_id on the project-summary PATCH
collapses to 404 per KSA §6.4 (don't leak existence). Because
knowledge_summaries has no FK to knowledge_projects, we explicitly
ownership-check the project via ProjectsRepo.get before upserting —
otherwise an attacker could plant orphan summary rows under a
project_id they don't own.
"""

from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.db.models import Summary, SummaryContent
from app.db.repositories import VersionMismatchError
from app.db.repositories.summaries import SummariesRepo
from app.deps import get_summaries_repo
from app.middleware.jwt_auth import get_current_user
from app.routers.public.projects import _etag, _parse_if_match

__all__ = ["router"]

router = APIRouter(
    prefix="/v1/knowledge",
    tags=["public"],
    dependencies=[Depends(get_current_user)],
)


# ── request / response models ─────────────────────────────────────────────


class SummaryUpdate(BaseModel):
    # SummaryContent is Annotated[str, max_length=50000]. Empty string
    # is intentionally allowed — see module docstring.
    content: SummaryContent


class SummariesListResponse(BaseModel):
    # `global` is a Python keyword; alias lets the JSON field be
    # `global` while the attribute is `global_`. populate_by_name
    # lets test code construct via either spelling.
    model_config = ConfigDict(populate_by_name=True)

    global_: Summary | None = Field(default=None, alias="global")
    projects: list[Summary] = Field(default_factory=list)


# ── helpers ───────────────────────────────────────────────────────────────


def _check_violation(exc: asyncpg.CheckViolationError) -> HTTPException:
    """DB CHECK constraint hit — Pydantic should have caught it first,
    but defense-in-depth: surface as 422 not 500."""
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=f"value out of bounds: {exc.constraint_name}",
    )


# ── endpoints ─────────────────────────────────────────────────────────────


@router.get("/summaries", response_model=SummariesListResponse)
async def list_summaries(
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> SummariesListResponse:
    rows = await repo.list_for_user(user_id)
    global_row: Summary | None = None
    projects: list[Summary] = []
    for row in rows:
        if row.scope_type == "global":
            # Schema invariant: at most one global row per user
            # (UNIQUE on (user_id, scope_type, scope_id) with
            # scope_id IS NULL). Defensive: keep the first.
            if global_row is None:
                global_row = row
        elif row.scope_type == "project":
            projects.append(row)
        # session/entity scopes are Track 2 — silently skipped.
    return SummariesListResponse(global_=global_row, projects=projects)


def _version_mismatch_response(current: Summary) -> JSONResponse:
    """412 envelope for a Summary version conflict. Body is the current
    row so the client can refresh its baseline in one round-trip."""
    return JSONResponse(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        content=current.model_dump(mode="json", by_alias=True),
        headers={"ETag": _etag(current.version)},
    )


@router.patch("/summaries/global", response_model=Summary)
async def update_global_summary(
    body: SummaryUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> Summary:
    # D-K8-03: strict If-Match. The FIRST save (no prior row) is
    # allowed without a version check — INSERT path always succeeds
    # and there's nothing to race against. Subsequent saves MUST
    # send a version. The FE reads summary.version from the GET
    # /v1/knowledge/summaries list body and derives the ETag.
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        # Allow only when there's no prior row (first-save case).
        existing = await repo.get(user_id, "global", None)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail=(
                    "If-Match header required — read summary.version from "
                    "GET /v1/knowledge/summaries and send it back"
                ),
            )
    try:
        result = await repo.upsert(
            user_id, "global", None, body.content, expected_version=expected_version
        )
    except VersionMismatchError as exc:
        assert isinstance(exc.current, Summary)
        return _version_mismatch_response(exc.current)
    except asyncpg.CheckViolationError as exc:
        raise _check_violation(exc)
    response.headers["ETag"] = _etag(result.version)
    return result


@router.patch(
    "/projects/{project_id}/summary",
    response_model=Summary,
)
async def update_project_summary(
    project_id: UUID,
    body: SummaryUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
    repo: SummariesRepo = Depends(get_summaries_repo),
) -> Summary:
    # Ownership + upsert in a single CTE — atomic, no TOCTOU window,
    # one pool acquisition. Returns None if the user does not own the
    # project (cross-user OR nonexistent), which we collapse to 404
    # per KSA §6.4 don't-leak-existence rule.

    # D-K8-03: same strict-If-Match contract as the global route.
    # First-save is allowed unconditionally; subsequent saves must
    # carry a version.
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        existing = await repo.get(user_id, "project", project_id)
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_428_PRECONDITION_REQUIRED,
                detail=(
                    "If-Match header required — read summary.version from "
                    "GET /v1/knowledge/summaries and send it back"
                ),
            )
    try:
        result = await repo.upsert_project_scoped(
            user_id, project_id, body.content, expected_version=expected_version
        )
    except VersionMismatchError as exc:
        assert isinstance(exc.current, Summary)
        return _version_mismatch_response(exc.current)
    except asyncpg.CheckViolationError as exc:
        raise _check_violation(exc)
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="project not found",
        )
    response.headers["ETag"] = _etag(result.version)
    return result
