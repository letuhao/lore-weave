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
from app.clients.knowledge_client import KnowledgeClient, KnowledgeContractError
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


async def _ensure_pending_work(works: WorksRepo, user_id: UUID, book_id: UUID):
    """C16 (WG-3) greenfield degrade: return the (at-most-one) lazy null-project
    Work for this user+book, creating it if absent. Idempotent + race-safe: the
    partial-unique `(user,book) WHERE pending_project_backfill` index caps it at one,
    so a concurrent loser re-gets the existing row instead of 500-ing. Used by both
    the knowledge-DOWN (resolve unavailable) and create_project-OUTAGE paths."""
    existing = await works.get_pending_for_book(user_id, book_id)
    if existing is not None:
        return existing
    try:
        return await works.create_pending(user_id, book_id)
    except asyncpg.UniqueViolationError:
        racey = await works.get_pending_for_book(user_id, book_id)
        if racey is None:
            raise HTTPException(status_code=409, detail={"code": "WORK_CREATE_CONFLICT"})
        return racey


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


class WorkCreateBody(BaseModel):
    # C16/C23: `source_work_id` marks a DERIVATIVE (dị bản) Work. A derivative MUST
    # bind a real (NOT NULL) knowledge project_id — it is its own delta partition
    # (G2) and the knowledge timeline endpoint widens to ALL of a user's projects on
    # a null project_id (cross-project grounding leak). So the WG-3 lazy/null-project
    # degradation is GREENFIELD-ONLY; a derivative whose knowledge project can't be
    # created surfaces the failure instead of degrading. (The derivative create flow
    # itself is C23; this field is the forward-compatible guard hook.)
    source_work_id: UUID | None = None


@router.post("/books/{book_id}/work", status_code=201)
async def create_work_for_book(
    book_id: UUID,
    body: WorkCreateBody | None = None,
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    book: BookClient = Depends(get_book_client_dep),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Confirm-create a Work (idempotent). Ensures a book-typed knowledge
    project exists (resolve, else ProjectCreate), then get-or-creates the
    composition_work row. Returns the Work.

    C16 (WG-3) resilience: for a GREENFIELD work, a knowledge-service OUTAGE
    (down/timeout/5xx) during project creation no longer 502s — the Work is created
    with a lazy null `project_id` + a backfill marker so the writer can keep drafting
    + Generate (grounding degrades to the packer's empty/FTS fallback). A 4xx CONTRACT
    error still surfaces (no silent swallow). A DERIVATIVE work (`source_work_id`) is
    NEVER eligible for the null path (C23 guard)."""
    is_derivative = body is not None and body.source_work_id is not None
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
        # C16 (WG-3): knowledge-service is DOWN, so resolve couldn't even list the
        # book's projects. A DERIVATIVE still 502s (it needs its own real project —
        # C23 guard). For a GREENFIELD work the writer must NOT be wall-blocked by an
        # optional dependency: degrade to a lazy null-project Work (reuse an existing
        # pending row if a prior outage already made one) so drafting + Generate keep
        # working; a later setup retry (once knowledge recovers) backfills the real
        # project. This fully decouples writing from the knowledge-service outage.
        if is_derivative:
            raise HTTPException(status_code=502, detail={"code": "KNOWLEDGE_UNAVAILABLE"})
        return (await _ensure_pending_work(works, user_id, book_id)).model_dump(mode="json")
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
        # C16 (WG-3) error discrimination: a 4xx is a CONTRACT bug → surface it
        # (never degrade an auth/validation failure into a grounding-blind Work);
        # only an OUTAGE (None ← down/timeout/5xx) is eligible for graceful
        # degradation.
        try:
            created = await knowledge.create_project(book_id, name, bearer)
        except KnowledgeContractError:
            raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})

        if created is None or not created.get("project_id"):
            # Knowledge OUTAGE. A DERIVATIVE work MUST NOT take the null path
            # (C23 guard — it needs its own real project partition); surface instead.
            if is_derivative:
                raise HTTPException(status_code=502, detail={"code": "PROJECT_CREATE_FAILED"})
            # GREENFIELD: degrade to a lazy null-project Work so the writer keeps
            # drafting + Generate while knowledge recovers (backfilled by a later
            # setup retry, below).
            return (await _ensure_pending_work(works, user_id, book_id)).model_dump(mode="json")
        project_id = UUID(str(created["project_id"]))

        # C16 backfill seam: if a prior outage left a lazy pending Work for this
        # (user,book), stamp the freshly-created project onto it (clear the marker)
        # instead of spawning a second Work — knowledge has recovered.
        pending = await works.get_pending_for_book(user_id, book_id)
        if pending is not None and pending.id is not None:
            backfilled = await works.backfill_project(user_id, pending.id, project_id)
            if backfilled is not None:
                return backfilled.model_dump(mode="json")

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
