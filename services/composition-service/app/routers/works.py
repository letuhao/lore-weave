"""Work resolve + CRUD router (composition-service, M3).

GET /books/{book_id}/work wires the M2 `resolve_work` (§6.2) into a real
endpoint — forwarding the caller's JWT to knowledge-service (user-scoped, so
ownership is enforced server-side). GET/PATCH /works/{project_id} expose the
WorksRepo with If-Match optimistic concurrency (412 on a stale version).

POST /books/{book_id}/work (M8) confirm-creates a Work: ensure a book-typed
knowledge project exists (resolve, else ProjectCreate), then get-or-create the
composition_work row (idempotent).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, field_validator

from app.clients.book_client import BookClient, BookClientError
from app.engine.assembly import ASSEMBLY_MODES
from app.clients.knowledge_client import KnowledgeClient
from app.db.models import WorkStatus
from app.db.repositories import VersionMismatchError
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep,
    get_grant_client_dep,
    get_knowledge_client_dep,
    get_works_repo,
)
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError
from app.work_resolution import WorkResolution, resolve_work

router = APIRouter(prefix="/v1/composition")


class WorkResolutionResponse(BaseModel):
    status: str
    work: dict[str, Any] | None = None
    candidates: list[dict[str, Any]] = []
    book_project_id: UUID | None = None
    book_project_ids: list[UUID] = []


class WorkPatch(BaseModel):
    active_template_id: UUID | None = None
    status: WorkStatus | None = None
    settings: dict[str, Any] | None = None

    @field_validator("settings")
    @classmethod
    def _validate_known_setting_enums(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        """Settings is a free-form JSONB blob, but a few keys are closed enums the
        engine keys on — validate them at the PATCH boundary so a bad value 422s
        here rather than being stored and silently coerced at read time (B1)."""
        if v is not None and "assembly_mode" in v and v["assembly_mode"] not in ASSEMBLY_MODES:
            raise ValueError(f"assembly_mode must be one of {list(ASSEMBLY_MODES)}")
        return v


def _serialize_resolution(res: WorkResolution) -> WorkResolutionResponse:
    return WorkResolutionResponse(
        status=res.status,
        work=res.work.model_dump(mode="json") if res.work else None,
        candidates=[w.model_dump(mode="json") for w in res.works],
        book_project_id=res.book_project_id,
        book_project_ids=list(res.book_project_ids),
    )


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP. none→404 (no oracle), under→403.
    composition_work stays per-user; this gates whether the caller may use
    composition on the book at the operation's tier."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


@router.get("/books/{book_id}/work", response_model=WorkResolutionResponse)
async def get_work_for_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> WorkResolutionResponse:
    # E0-4c: read-pack tier → VIEW grant on the book.
    await _gate_book(grant, book_id, user_id, GrantLevel.VIEW)
    res = await resolve_work(
        user_id, book_id, bearer=bearer, works_repo=works, knowledge_client=knowledge,
    )
    return _serialize_resolution(res)


@router.post("/books/{book_id}/work", status_code=201)
async def create_work_for_book(
    book_id: UUID,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Confirm-create a Work (idempotent). Ensures a book-typed knowledge
    project exists (resolve, else ProjectCreate), then get-or-creates the
    composition_work row. Returns the Work."""
    # E0-4c: creating a work is an authoring (write) action → EDIT grant. Then
    # fetch the book for its title (get_book returns the row for any grantee
    # post-E0-2). composition_work itself is per-user (caller-keyed below).
    await _gate_book(grant, book_id, user_id, GrantLevel.EDIT)
    try:
        book_obj = await book.get_book(book_id, bearer)
    except BookClientError:
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})
    if book_obj is None:
        raise HTTPException(status_code=404, detail="book not found")

    res = await resolve_work(
        user_id, book_id, bearer=bearer, works_repo=works, knowledge_client=knowledge,
    )
    if res.status == "unavailable":
        raise HTTPException(status_code=502, detail={"code": "KNOWLEDGE_UNAVAILABLE"})
    # Already a Work → idempotent return (pick the first if several marked).
    if res.status == "found":
        return res.work.model_dump(mode="json")  # type: ignore[union-attr]
    if res.status == "candidates":
        return res.works[0].model_dump(mode="json")

    # Determine the knowledge project to bind to.
    if res.status == "unmarked_single":
        project_id = res.book_project_id
    elif res.status == "unmarked_candidates":
        project_id = res.book_project_ids[0]
    else:  # none → create a book-typed knowledge project
        name = book_obj.get("title") or f"Book {book_id}"
        created = await knowledge.create_project(book_id, name, bearer)
        if created is None or not created.get("project_id"):
            raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})
        project_id = UUID(str(created["project_id"]))

    # Get-or-create the composition_work row. The get-then-create is not atomic,
    # so a concurrent same-project POST can lose the PK race — catch the unique
    # violation and re-get (atomic get-or-create). (The duplicate-knowledge-project
    # race — two first-POSTs each creating a book project — was resolved cy6/LOOM-48
    # knowledge-side: create_project now dedupes via ProjectsRepo.create_or_get under
    # a per-(user,book) advisory lock, so both POSTs resolve to the SAME project_id
    # and this unique-violation catch dedupes the work row.)
    existing = await works.get(user_id, project_id)  # type: ignore[arg-type]
    if existing is not None:
        return existing.model_dump(mode="json")
    try:
        work = await works.create(user_id, project_id, book_id)  # type: ignore[arg-type]
    except asyncpg.UniqueViolationError:
        racey = await works.get(user_id, project_id)  # type: ignore[arg-type]
        if racey is None:
            raise HTTPException(status_code=409, detail={"code": "WORK_CREATE_CONFLICT"})
        return racey.model_dump(mode="json")
    return work.model_dump(mode="json")


@router.get("/works/{project_id}")
async def get_work(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    # E0-4c: the work row is the caller's own (per-user predicate above); still
    # require VIEW on its book so a revoked collaborator can't read stale work.
    await _gate_book(grant, work.book_id, user_id, GrantLevel.VIEW)
    return work.model_dump(mode="json")


@router.patch("/works/{project_id}")
async def patch_work(
    project_id: UUID,
    patch: WorkPatch,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    # E0-4c: patching the authoring context is a write → EDIT on the work's book.
    # Resolve the caller's own work first (per-user) to get its book_id.
    existing = await works.get(user_id, project_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="work not found")
    await _gate_book(grant, existing.book_id, user_id, GrantLevel.EDIT)
    expected_version = _parse_if_match(if_match)
    patch_dict = patch.model_dump(exclude_unset=True)
    try:
        updated = await works.update(
            user_id, project_id, patch_dict, expected_version=expected_version,
        )
    except VersionMismatchError as exc:
        raise HTTPException(
            status_code=412,
            detail={"code": "WORK_VERSION_CONFLICT", "current": exc.current.model_dump(mode="json")},
        )
    if updated is None:
        raise HTTPException(status_code=404, detail="work not found")
    return updated.model_dump(mode="json")
