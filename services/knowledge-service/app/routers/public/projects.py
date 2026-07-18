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
import hashlib
import logging
import re
from datetime import datetime
from typing import Literal
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.clients.embedding_client import EmbeddingError, probe_embedding_dimension
from app.db.models import (
    Project,
    ProjectCreate,
    ProjectExtractionConfigUpdate,
    ProjectUpdate,
)
from app.db.neo4j import neo4j_session
from app.db.neo4j_helpers import purge_project
from app.db.neo4j_repos.passages import SUPPORTED_PASSAGE_DIMS
from app.db.pool import get_knowledge_pool
from app.db.repositories import VersionMismatchError
from app.db.repositories.event_text_translations import EventTextTranslationsRepo
from app.db.repositories.projects import (
    _PROJECT_SORT_COLUMNS,
    _PROJECT_STATUS_FILTERS,
    ProjectsRepo,
)
from app.auth.grant_deps import GrantLevel, require_project_grant
from app.clients.grant_client import GrantClient
from app.clients.book_client import BookClient
from app.deps import get_book_client, get_grant_client, get_projects_repo
from app.events.outbox_emit import config_adjustment_payload, emit_config_adjustment
from app.middleware.jwt_auth import get_current_user

# B2-B-b1 — the top-level extraction-config targets we diff + emit adjustments
# for. Order is stable so emitted events are deterministic.
_EXTRACTION_CONFIG_TARGETS = (
    "llm_model",
    "precision_filter",
    "entity_recovery",
    "writer_autocreate",
)


def _prompt_hash(text: str | None) -> str | None:
    """sha256 of a custom prompt's system text (or None). Used so the raw text
    never crosses to learning-service — only its identity (DESIGN Q5)."""
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()

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

logger = logging.getLogger(__name__)

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

# Cursor is "<filter_sig>|<sort_value>|<uuid>" base64url-encoded, where
# <filter_sig> is a stable hash over the FULL filter set the seek key was
# computed for: (sort_by, sort_dir, search, status). The whole filter set
# is bound — not just sort_by — because the seek predicate is only valid
# for the exact (column, direction, filtered population) it was issued
# for: flipping sort_dir flips the `<`/`>` comparison against a boundary
# computed for the opposite direction, and changing search/status moves
# the boundary into (or out of) a different filtered set. ANY mismatch is
# a 400 so a stale/3rd-party cursor can't silently skip or duplicate rows.
# base64url avoids the `+` in `+00:00` and the pipe separator colliding
# with URL parsing. The format is opaque to clients — they round-trip
# whatever the server returns without inspecting it.
_CURSOR_SEP = "|"


def _filter_sig(
    sort_by: str,
    sort_dir: str,
    search: str | None,
    status_filter: str | None,
    *,
    include_archived: bool,
    book_id: UUID | None,
    world_id: UUID | None = None,
) -> str:
    """Stable signature of the filter set a cursor's seek key is valid
    for. A short sha256 hex over the normalized
    (sort_by, sort_dir, search, status, include_archived, book_id) tuple
    — replaying a cursor under any different value yields a different
    signature and so a 400 on decode.

    EVERY param that shapes the ORDER BY (sort_by/sort_dir) OR the
    filtered population the seek boundary was computed against
    (search/status/include_archived/book_id) is bound: a flipped
    sort_dir mis-applies `<`/`>` against the opposite-direction
    boundary, and any population change (search/status/include_archived/
    book_id) moves the boundary into a different row set — either way
    silently skips or duplicates rows. The separator is NUL (which can't
    appear in any input: they're enum tokens / UUIDs / a user search the
    BE never NUL-injects) so distinct field boundaries can't collide
    (e.g. search='a|b' vs two fields).

    (The status param is named ``status_filter`` rather than ``status``
    so it does not shadow the module-level ``fastapi.status`` import.)"""
    payload = "\x00".join(
        (
            sort_by,
            sort_dir,
            search or "",
            status_filter or "",
            "1" if include_archived else "0",
            str(book_id) if book_id is not None else "",
            # G4: world_id shapes the filtered population (HOME hides world
            # projects; ?world_id returns one) so it must bind the seek key.
            str(world_id) if world_id is not None else "",
        )
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _encode_cursor(
    sort_by: str,
    sort_value: object,
    project_id: UUID,
    *,
    sort_dir: str,
    search: str | None,
    status_filter: str | None,
    include_archived: bool,
    book_id: UUID | None,
    world_id: UUID | None = None,
) -> str:
    # The sort value is serialized via str(); a datetime becomes its
    # isoformat (round-trips through _coerce_sort_value), a name/status
    # stays the raw string. UTF-8 (not ASCII): a `name`-sorted cursor can
    # carry non-ASCII project names (e.g. CJK titles) — encoding those
    # with ASCII raised UnicodeEncodeError and 500'd the list (live-smoke
    # caught this). base64url of the UTF-8 bytes keeps the wire ASCII-safe.
    sv = sort_value.isoformat() if isinstance(sort_value, datetime) else str(sort_value)
    sig = _filter_sig(
        sort_by, sort_dir, search, status_filter,
        include_archived=include_archived, book_id=book_id, world_id=world_id,
    )
    raw = f"{sig}{_CURSOR_SEP}{sv}{_CURSOR_SEP}{project_id}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _coerce_sort_value(sort_by: str, raw: str) -> object:
    """Type the cursor's stored sort value back to what the column needs.
    Text columns (name / extraction_status) stay strings; timestamp
    columns parse back to a tz-aware datetime."""
    _col, is_text = _PROJECT_SORT_COLUMNS[sort_by]
    if is_text:
        return raw
    return datetime.fromisoformat(raw)


def _decode_cursor(
    cursor: str,
    *,
    sort_by: str,
    sort_dir: str,
    search: str | None,
    status_filter: str | None,
    include_archived: bool,
    book_id: UUID | None,
    world_id: UUID | None = None,
) -> tuple[object, UUID]:
    """Parse a cursor string against the CURRENT filter set. Raises
    HTTPException(400) on malformed input OR a filter-set mismatch —
    clients must round-trip the server-issued value verbatim AND keep the
    same sort_by / sort_dir / search / status they requested it under.

    The filter signature is recomputed from the current request and
    compared against the one baked into the cursor; any drift (a flipped
    sort_dir, a changed search or status, a changed sort_by) is a 400 so
    a seek key computed for one filtered population is never mis-applied
    to another (which would skip or duplicate rows).

    Catches the UnicodeError parent so BOTH encode-side (non-ASCII input
    → `.encode('ascii')` fails) and decode-side (`urlsafe_b64decode`
    yielding non-ASCII bytes) errors land on the same 400 path.
    """
    try:
        # Re-pad to a multiple of 4 for urlsafe_b64decode. Decode the
        # payload as UTF-8 (paired with _encode_cursor) so a non-ASCII
        # name value round-trips intact. The outer cursor string itself
        # is still ASCII (base64url), so `.encode('ascii')` is safe.
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
        sig_token, value_str, uid_str = raw.split(_CURSOR_SEP, 2)
        if sig_token != _filter_sig(
            sort_by, sort_dir, search, status_filter,
            include_archived=include_archived, book_id=book_id, world_id=world_id,
        ):
            # The filter set changed mid-pagination — the old seek key is
            # invalid for the new population; the FE must restart from
            # page 1 under the new filters.
            raise ValueError("cursor filter-set mismatch")
        return _coerce_sort_value(sort_by, value_str), UUID(uid_str)
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


# C7-followup (KN-7): server-side narrowing. The sort/status enums are
# CLOSED allowlists exposed as Literals so FastAPI 422s an out-of-set
# value at the validation boundary (the repo also defends in depth).
ProjectSortBy = Literal["created_at", "updated_at", "name", "status"]
ProjectSortDir = Literal["asc", "desc"]
ProjectStatusFilter = Literal[
    "disabled", "building", "paused", "ready", "failed", "archived"
]


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    user_id: UUID = Depends(get_current_user),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = Query(default=None),
    include_archived: bool = Query(default=False),
    book_id: UUID | None = Query(
        default=None,
        description=(
            "C5 (ARCH-1): filter to projects linked to this book. The editor "
            "AI panel uses it to resolve a book's knowledge project (0 or 1 "
            "result in practice)."
        ),
    ),
    world_id: UUID | None = Query(
        default=None,
        description=(
            "G4: filter to a world's dedicated knowledge project (0 or 1 "
            "result). When omitted (and book_id is omitted), the HOME browse "
            "HIDES world-level projects so the bible/world project never shows "
            "as a phantom row."
        ),
    ),
    search: str | None = Query(
        default=None,
        max_length=200,
        description=(
            "C7-followup: case-insensitive substring match on project name. "
            "Server-side so the browser narrows across ALL projects, not just "
            "loaded cursor pages."
        ),
    ),
    sort_by: ProjectSortBy = Query(
        default="created_at",
        description=(
            "C7-followup: ordering key (closed allowlist). `status` sorts on "
            "the extraction lifecycle state."
        ),
    ),
    sort_dir: ProjectSortDir = Query(default="desc"),
    status_filter: ProjectStatusFilter | None = Query(
        default=None,
        alias="status",
        description=(
            "C7-followup: filter to one project state. The five extraction "
            "lifecycle values plus `archived` (the is_archived flag)."
        ),
    ),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> ProjectListResponse:
    # Defense in depth — the Literal already gates these, but assert the
    # closed sets so an internal drift (Literal vs repo allowlist) fails
    # loudly rather than silently SELECTing the wrong column.
    assert sort_by in _PROJECT_SORT_COLUMNS
    assert status_filter is None or status_filter in _PROJECT_STATUS_FILTERS

    cursor_value: object | None = None
    cursor_id: UUID | None = None
    if cursor:
        cursor_value, cursor_id = _decode_cursor(
            cursor,
            sort_by=sort_by,
            sort_dir=sort_dir,
            search=search,
            status_filter=status_filter,
            include_archived=include_archived,
            book_id=book_id,
            world_id=world_id,
        )

    rows = await repo.list(
        user_id,
        include_archived=include_archived,
        limit=limit,
        cursor_sort_value=cursor_value,
        cursor_project_id=cursor_id,
        book_id=book_id,
        world_id=world_id,
        search=search,
        sort_by=sort_by,
        sort_dir=sort_dir,
        status=status_filter,
    )

    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor: str | None = None
    if has_more and items:
        last = items[-1]
        # The cursor's sort value is the row's value on the active sort
        # column — created_at / updated_at / name / extraction_status.
        sort_value = getattr(
            last,
            "extraction_status" if sort_by == "status" else sort_by,
        )
        next_cursor = _encode_cursor(
            sort_by,
            sort_value,
            last.project_id,
            sort_dir=sort_dir,
            search=search,
            status_filter=status_filter,
            include_archived=include_archived,
            book_id=book_id,
            world_id=world_id,
        )

    return ProjectListResponse(items=items, next_cursor=next_cursor)


@router.post(
    "",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    responses={
        # Idempotent book-binding path (D-COMP-POST-WORK-RACE): an existing book
        # project is returned with 200 instead of a duplicate 201. Documented so
        # the OpenAPI contract matches the runtime override below.
        status.HTTP_200_OK: {"model": Project, "description": "Existing book project returned (idempotent)"},
    },
)
async def create_project(
    body: ProjectCreate,
    response: Response,
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
    grant: GrantClient = Depends(get_grant_client),
) -> Project:
    # E0-3 (decision Q4): creating a knowledge project FOR A BOOK is book-owner-only
    # — the project's user_id becomes the book owner, which is what makes
    # GrantOwner==owner-only hold across the project's lifecycle. A non-owner is
    # denied uniformly (404, no oracle). A book-less project (book_id=None) is a
    # personal project — any caller, who owns it.
    if body.book_id is not None and await grant.resolve_grant(body.book_id, user_id) != GrantLevel.OWNER:
        raise _not_found()
    # K7-review-R3: symmetric with patch_project. Pydantic's
    # ProjectName / ProjectDescription / ProjectInstructions caps gate
    # the public surface today, so the DB CHECK constraints can't fire
    # on this path in practice — but the asymmetry with PATCH was a
    # code smell, and any future loosening of the Pydantic caps would
    # crash POST with a 500 instead of a 422.
    try:
        # Idempotent for the book-binding path (D-COMP-POST-WORK-RACE): a repeat
        # or concurrent same-book book-project POST returns the existing project
        # (200) instead of a duplicate (201).
        project, created = await repo.create_or_get(user_id, body)
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"value out of bounds: {exc.constraint_name}",
        )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return project


class AssistantProjectCreate(BaseModel):
    """WS-1.4 — the body of POST /v1/knowledge/projects/assistant."""

    book_id: UUID
    name: str = "Work Assistant"


@router.post(
    "/assistant",
    response_model=Project,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_200_OK: {
            "model": Project,
            "description": "Existing assistant project returned (idempotent)",
        },
    },
)
async def provision_assistant_project(
    body: AssistantProjectCreate,
    response: Response,
    user_id: UUID = Depends(get_current_user),
    repo: ProjectsRepo = Depends(get_projects_repo),
    grant: GrantClient = Depends(get_grant_client),
    book_client: BookClient = Depends(get_book_client),
) -> Project:
    """WS-1.4 (spec 02 §Q2.2) — get-or-create the user's ONE assistant knowledge project,
    bound to their diary book. ``is_assistant=true`` + ``chat_turn_extraction_enabled=false``
    (fail-closed D6: the assistant's facts come once a day from the confirmed entry, never
    per chat turn).

    The diary must be OWNED by the caller — a non-owner is denied uniformly (404, no oracle),
    exactly like create_project's book-binding path. This prevents binding the assistant's
    memory to someone else's book.

    It must ALSO be an actual ``kind='diary'`` book (review-impl WS-1.4 M2). Ownership alone
    is not enough: binding the assistant project to a shareable NOVEL the caller owns would let
    a collaborator on that novel read the assistant's private extracted memory (knowledge
    authorizes project reads by resolve-to-owner on the project's book). Fail-closed — an
    unresolvable/non-diary book is refused with the same uniform 404 as a non-owner."""
    if await grant.resolve_grant(body.book_id, user_id) != GrantLevel.OWNER:
        raise _not_found()
    if await book_client.get_book_kind(body.book_id, user_id) != "diary":
        raise _not_found()
    project, created = await repo.get_or_create_assistant_project(
        user_id, body.book_id, body.name
    )
    response.status_code = status.HTTP_201_CREATED if created else status.HTTP_200_OK
    return project


@router.get("/{project_id}", response_model=Project)
async def get_project(
    project_id: UUID,
    response: Response,
    user_id: UUID = Depends(require_project_grant(GrantLevel.VIEW)),
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
    user_id: UUID = Depends(require_project_grant(GrantLevel.EDIT)),
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

    # D-EMB-MODEL-REF-04 — changing embedding_model on a project that
    # already has a graph would orphan the existing passages: they stay
    # in Neo4j tagged with the old model UUID while Mode-3 retrieval
    # queries the new model's vector space — silent zero-recall.
    # Route those changes through PUT /embedding-model?confirm=true
    # which deletes the stale graph first. First-time setup
    # (extraction_status='disabled') is fine because there is nothing
    # to orphan. Same-value sets are no-ops, also fine.
    if "embedding_model" in body.model_fields_set:
        current = await repo.get(user_id, project_id)
        if current is None:
            raise _not_found()
        if (
            body.embedding_model != current.embedding_model
            and current.extraction_status != "disabled"
        ):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    "embedding_model change on a project with a graph "
                    "requires deleting the stale vectors first — use "
                    "PUT /v1/knowledge/projects/{id}/embedding-model?confirm=true"
                ),
            )

    # D-EMB-MODEL-REF-03 — embedding_model is a provider-registry
    # user_model UUID. When it is being set to a value, probe the model
    # to derive its vector dimension and store the paired
    # embedding_dimension (the caller never knows the dimension). A
    # probe failure (provider unreachable / non-embedding model) → 422.
    if "embedding_model" in body.model_fields_set and body.embedding_model:
        try:
            dim = await probe_embedding_dimension(user_id, body.embedding_model)
        except EmbeddingError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"embedding model probe failed: {exc}",
            )
        if dim not in SUPPORTED_PASSAGE_DIMS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=(
                    f"embedding model has dimension {dim}, which has no "
                    f":Passage vector index (supported: {sorted(SUPPORTED_PASSAGE_DIMS)})"
                ),
            )
        body = body.model_copy(update={"embedding_dimension": dim})

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


class CaptureConsentUpdate(BaseModel):
    """A2 — the per-turn work-capture consent toggle body. Closed set (bool)."""

    enabled: bool


@router.put("/{project_id}/capture-consent", response_model=Project)
async def put_capture_consent(
    project_id: UUID,
    body: CaptureConsentUpdate,
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> Project:
    """A2 / D-R17 (spec 09) — the per-turn WORK-CAPTURE CONSENT toggle (`canon_capture_enabled`).
    OWNER-only: it is the user's own consent to have their real colleagues/projects captured, so a
    mere collaborator must not flip it. Fail-closed by default; this turns it on/off. Consumed by
    the chat-service capture gate via `project_enables` — the effective value is
    AND(deploy_ceiling, this), and turning it off stops capture on the next turn (E8). Idempotent."""
    updated = await repo.set_canon_capture_consent(user_id, project_id, enabled=body.enabled)
    if updated is None:
        raise _not_found()
    return updated


@router.put("/{project_id}/extraction-config", response_model=Project)
async def put_extraction_config(
    project_id: UUID,
    body: ProjectExtractionConfigUpdate,
    response: Response,
    if_match: str | None = Header(default=None, alias="If-Match"),
    user_id: UUID = Depends(require_project_grant(GrantLevel.EDIT)),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> Project:
    """B2-B-b1 — replace a project's per-novel extraction tuning (structural
    subset; raw-prompt editing is the separate b2 surface).

    Dedicated sub-resource (not generic PATCH) because the write has side
    effects: it drives the extraction pipeline AND emits a `config_adjusted`
    analytics event per changed target. PUT semantics: the body REPLACES the
    stored config; omit a sub-object to drop that override. Out-of-subset keys
    are rejected by the model's `extra='forbid'` → 422. If-Match required (428);
    version mismatch → 412 with the current row.
    """
    expected_version = _parse_if_match(if_match)
    if expected_version is None:
        raise HTTPException(
            status_code=status.HTTP_428_PRECONDITION_REQUIRED,
            detail="If-Match header required — GET the row first to obtain an ETag",
        )

    current = await repo.get(user_id, project_id)
    if current is None:
        raise _not_found()

    # New config = the non-None, non-empty fields of the body (PUT replace).
    raw = body.model_dump(exclude_none=True)
    new_config = {k: v for k, v in raw.items() if v}
    old_config = current.extraction_config or {}
    # Track 4 P2 (review MED): the L3 rerank knobs are managed by a DIFFERENT
    # surface (model pickers / direct API), not the FE structural-config editor —
    # so an editor save that simply doesn't know these keys must not silently
    # clear them. PUT-replace applies to the sections the editor owns; these two
    # are preserved when OMITTED, and cleared only by an explicit empty value.
    for _k in ("rerank_model", "cross_encoder_rerank_model"):
        if _k not in raw and _k in old_config:
            new_config[_k] = old_config[_k]

    try:
        updated = await repo.update_extraction_config(
            user_id, project_id, new_config, expected_version=expected_version,
        )
    except VersionMismatchError as exc:
        assert isinstance(exc.current, Project)
        return JSONResponse(
            status_code=status.HTTP_412_PRECONDITION_FAILED,
            content=exc.current.model_dump(mode="json"),
            headers={"ETag": _etag(exc.current.version)},
        )
    if updated is None:
        raise _not_found()

    # Emit one best-effort config_adjusted event per changed STRUCTURAL target
    # (analytics; never fails the edit — DESIGN Q3).
    for target in _EXTRACTION_CONFIG_TARGETS:
        before = old_config.get(target)
        after = new_config.get(target)
        if before != after:
            await emit_config_adjustment(
                aggregate_id=str(project_id),
                payload=config_adjustment_payload(
                    user_id=str(user_id),
                    project_id=str(project_id),
                    actor_id=str(user_id),
                    target=target,
                    before_structural=before,
                    after_structural=after,
                ),
            )

    # B2-B-b2 — raw-prompt targets: emit per changed op with a CONTENT-HASH of
    # the system text (never the raw text — DESIGN Q5 redact-by-default).
    old_prompts = old_config.get("prompts") or {}
    new_prompts = new_config.get("prompts") or {}
    for op in sorted(set(old_prompts) | set(new_prompts)):
        before_sys = (old_prompts.get(op) or {}).get("system")
        after_sys = (new_prompts.get(op) or {}).get("system")
        if before_sys != after_sys:
            await emit_config_adjustment(
                aggregate_id=str(project_id),
                payload=config_adjustment_payload(
                    user_id=str(user_id),
                    project_id=str(project_id),
                    actor_id=str(user_id),
                    target=f"prompts.{op}",
                    before_content_hash=_prompt_hash(before_sys),
                    after_content_hash=_prompt_hash(after_sys),
                ),
            )

    response.headers["ETag"] = _etag(updated.version)
    return updated


@router.post(
    "/{project_id}/archive",
    response_model=Project,
)
async def archive_project(
    project_id: UUID,
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
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
    user_id: UUID = Depends(require_project_grant(GrantLevel.OWNER)),
    repo: ProjectsRepo = Depends(get_projects_repo),
) -> None:
    deleted = await repo.delete(user_id, project_id)
    if not deleted:
        raise _not_found()
    # D-KNOWLEDGE-PROJECT-DELETE-NEO4J-ORPHAN: the Postgres delete above is the
    # authoritative owner-gated op; now best-effort purge the project's Neo4j graph
    # (all nodes carry project_id) + its per-project summary vector indexes so a
    # delete no longer orphans the graph. A Neo4j fault must NOT fail the delete —
    # the row is already gone (re-sweep can reclaim a stray orphan); log + move on.
    try:
        async with neo4j_session() as session:
            purged = await purge_project(session, str(project_id))
        logger.info(
            "purged neo4j for deleted project %s: %s nodes, %s indexes",
            project_id, purged["nodes_deleted"], purged["indexes_dropped"],
        )
    except Exception:  # noqa: BLE001 — best-effort; the Postgres delete is authoritative
        logger.warning(
            "neo4j purge for deleted project %s failed — graph orphaned, re-sweep owed",
            project_id, exc_info=True,
        )
    # KG-TL M3 (AC-T7) — purge the project's on-demand event-text translation
    # cache so it leaves no orphans after the graph partition is deleted. Same
    # best-effort posture: a failure must not fail the authoritative delete.
    try:
        cache_repo = EventTextTranslationsRepo(get_knowledge_pool())
        removed = await cache_repo.delete_for_project(project_id=project_id)
        if removed:
            logger.info(
                "purged %s event-text translation rows for deleted project %s",
                removed, project_id,
            )
    except Exception:  # noqa: BLE001 — best-effort cache cleanup
        logger.warning(
            "event-text translation cache purge for project %s failed — orphans owed",
            project_id, exc_info=True,
        )
