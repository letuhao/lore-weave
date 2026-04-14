"""K7.2 — Projects CRUD endpoints under /v1/knowledge/projects.

Every route is JWT-authenticated via the router-level
`dependencies=[Depends(get_current_user)]`, AND every route also takes
`user_id: UUID = Depends(get_current_user)` so it can pass the id to
the repo. The two declarations are intentionally redundant: the
router-level dep ensures FastAPI returns 401 before any route logic
runs (so a missing JWT can't accidentally fall through to a route
that forgot the parameter), and the per-route dep keeps the user_id
in scope for downstream calls.

Cross-user access returns 404 (not 403) per KSA §6.4 — we deliberately
don't leak the existence of project_ids that belong to someone else.
The repo enforces user_id filtering, so a cross-user lookup naturally
returns None which we map to 404.
"""

import base64
import re
from datetime import datetime
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.db.models import Project, ProjectCreate, ProjectUpdate
from app.db.repositories import VersionMismatchError
from app.db.repositories.projects import ProjectsRepo
from app.deps import get_projects_repo
from app.middleware.jwt_auth import get_current_user

# D-K8-03: accept `If-Match: W/"<version>"` or `If-Match: "<version>"`
# or even the bare integer. Strict about the quoted form but tolerant
# enough that a curl caller can send plain numbers without surprises.
_IF_MATCH_PATTERN = re.compile(r'^(?:W/)?"?(\d+)"?$')


def _parse_if_match(header_value: str | None) -> int | None:
    """Return the integer version from an If-Match header, or None
    if the header is missing. Raises 400 on a malformed header so we
    don't silently fall through to the strict 428 path."""
    if header_value is None:
        return None
    m = _IF_MATCH_PATTERN.match(header_value.strip())
    if m is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="If-Match header must be a weak ETag with an integer version",
        )
    return int(m.group(1))


def _etag(version: int) -> str:
    """Weak ETag for a versioned row. Weak because the row has more
    state than just the version (updated_at, denormalized stats, etc.)
    — two serializations of the same version are *semantically*
    equal but not necessarily byte-identical."""
    return f'W/"{version}"'

__all__ = ["router"]

router = APIRouter(
    prefix="/v1/knowledge/projects",
    tags=["public"],
    dependencies=[Depends(get_current_user)],
)


# ── response envelopes ────────────────────────────────────────────────────


class ProjectListResponse(BaseModel):
    items: list[Project]
    next_cursor: str | None = Field(
        default=None,
        description=(
            "Opaque cursor for the next page. Pass back as ?cursor=… on "
            "the next request. Null when there are no more pages."
        ),
    )


# ── cursor helpers ────────────────────────────────────────────────────────

# Cursor is "<iso8601>|<uuid>" base64url-encoded so neither the `+`
# in `+00:00` nor the pipe separator collides with URL parsing. The
# format is opaque to clients — they should round-trip whatever the
# server returns without inspecting it.
_CURSOR_SEP = "|"


def _encode_cursor(created_at: datetime, project_id: UUID) -> str:
    raw = f"{created_at.isoformat()}{_CURSOR_SEP}{project_id}".encode("ascii")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _decode_cursor(cursor: str) -> tuple[datetime, UUID]:
    """Parse a cursor string. Raises HTTPException(400) on malformed
    input — clients must round-trip the server-issued value verbatim.

    Catches the UnicodeError parent so BOTH encode-side (non-ASCII
    input → `.encode('ascii')` fails) and decode-side (`urlsafe_b64decode`
    yielding non-ASCII bytes) errors land on the same 400 path.
    Previously only UnicodeDecodeError was caught, so a cursor like
    `?cursor=café` produced a 500 with a traceback.
    """
    try:
        # Re-pad to a multiple of 4 for urlsafe_b64decode.
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("ascii")
        ts_str, uid_str = raw.split(_CURSOR_SEP, 1)
        return datetime.fromisoformat(ts_str), UUID(uid_str)
    except (ValueError, UnicodeError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="invalid cursor",
        )


def _not_found() -> HTTPException:
    """Uniform 404 — does not distinguish 'not yours' from 'not exist'."""
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="project not found",
    )


# ── endpoints ─────────────────────────────────────────────────────────────


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user_id: UUID = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> ProjectListResponse:
    cursor_ts: datetime | None = None
    cursor_id: UUID | None = None
    if cursor:
        cursor_ts, cursor_id = _decode_cursor(cursor)

    rows = await repo.list(
        user_id,
        include_archived=include_archived,
        limit=limit,
        cursor_created_at=cursor_ts,
        cursor_project_id=cursor_id,
    )

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        next_cursor = _encode_cursor(last.created_at, last.project_id)

    return ProjectListResponse(items=items, next_cursor=next_cursor)


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
)
async def create_project(
    body: ProjectCreate,
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> Project:
    # K7-review-R3: symmetric with patch_project. Pydantic's
    # ProjectName / ProjectDescription / ProjectInstructions caps gate
    # the public surface today, so the DB CHECK constraints can't fire
    # on this path in practice — but the asymmetry with PATCH was a
    # code smell, and any future loosening of the Pydantic caps would
    # crash POST with a 500 instead of a 422.
    try:
        return await repo.create(user_id, body)
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"value out of bounds: {exc.constraint_name}",
        )


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    response: Response,
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> Project:
    project = await repo.get(user_id, project_id)
    if project is None:
        raise _not_found()
    # D-K8-03: hand the client an ETag so it can send it back on
    # the next PATCH. Weak form because the row carries more state
    # than just the version counter (updated_at, stat counters).
    response.headers["ETag"] = _etag(project.version)
    return project


@router.patch("/{project_id}", response_model=Project)
async def patch_project(
    project_id: UUID,
    body: ProjectUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> Project:
    # K-CLEAN-3: PATCH accepts is_archived=false (restore) but
    # rejects is_archived=true so the dedicated POST /archive
    # endpoint stays the only archiving path. POST /archive
    # collapses three failure modes (not found / cross-user /
    # already archived) into a single 404 so the endpoint is not
    # an oracle for project existence; allowing PATCH to archive
    # would create a parallel path that bypasses that hardening.
    if body.is_archived is True:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="use POST /v1/knowledge/projects/{id}/archive to archive a project",
        )

    # D-K8-03: strict If-Match — a PATCH that does not name the
    # version it expects to patch is rejected with 428 Precondition
    # Required. The FE is expected to have GET'd the row and read
    # the ETag response header; any PATCH without If-Match is
    # almost certainly a stale client that hasn't been updated.
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header required — GET the row first to obtain an ETag",
        )

    try:
        updated = await repo.update(
            user_id, project_id, body, expected_version=expected_version
        )
    except VersionMismatchError as exc:
        # 412 body is the current row so the FE can refresh its
        # baseline without a second GET. ETag header also refreshed
        # so the client can immediately retry with the new value.
        assert isinstance(exc.current, Project)
        return JSONResponse(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            content=exc.current.model_dump(mode="json"),
            headers={"ETag": _etag(exc.current.version)},
        )
    except asyncpg.CheckViolationError as exc:
        # Length CHECK constraints (K7 D-K1-02 cleanup) — Pydantic
        # already gates the public surface, but defense-in-depth means
        # we surface the DB error as a 422 not a 500.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"value out of bounds: {exc.constraint_name}",
        )
    if updated is None:
        raise _not_found()
    response.headers["ETag"] = _etag(updated.version)
    return updated


@router.post(
    "/{project_id}/archive",
    response_model=Project,
)
async def archive_project(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> Project:
    """One-shot archive. Returns 404 if the project does not exist,
    is cross-user, OR is already archived — three cases collapsed
    into a single response so the endpoint is not an oracle for
    project existence.

    Not idempotent: a second call returns 404. Unarchive is K8
    frontend territory (direct PATCH is_archived) and isn't exposed
    by Track 1.
    """
    archived = await repo.archive(user_id, project_id)
    if archived is None:
        raise _not_found()
    return archived


@router.delete(
    "/{project_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_project(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> None:
    deleted = await repo.delete(user_id, project_id)
    if not deleted:
        raise _not_found()
