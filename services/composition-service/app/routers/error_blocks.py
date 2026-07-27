"""Error-blocks router — the AUTHOR's half of atom-edit Phase D.

The co-writer reaches error blocks through MCP; the browser cannot, so it reaches them here. Both
surfaces sit on the same repo and the same E0 gate. (The design originally specified only the MCP
path — the FE surface was added at SEAL once that omission was caught.)

Access mirrors canon.py exactly (25 PM-8): the E0 book grant is resolved BEFORE any repo call,
VIEW for reads and EDIT for writes. Marking is EDIT, not VIEW — a mark is authoring input that
drives a prose change, so it belongs to whoever may change the prose. By-id routes resolve the
block's own project first and gate on ITS book, so the gate can never check a different book than
the row it mutates.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from app.db.models import ErrorBlockKind
from app.db.pool import get_pool
from app.db.repositories import VersionMismatchError
from app.db.repositories.error_blocks import (
    DuplicateErrorBlockError,
    ErrorBlocksRepo,
)
from app.db.repositories.works import WorksRepo
from app.deps import get_error_blocks_repo, get_grant_client_dep, get_works_repo
from app.engine.cowrite import SELECTION_MAX_CHARS
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")


class ErrorBlockCreate(BaseModel):
    """A new mark. The span triple (offsets + quote + fingerprint) arrives together and is
    thereafter immutable — see the repo's `_UPDATABLE_COLUMNS` note."""
    start_offset: int = Field(ge=0)
    end_offset: int = Field(gt=0)
    quote: str = Field(min_length=1, max_length=SELECTION_MAX_CHARS)
    source_fingerprint: str = Field(min_length=1, max_length=128)
    kind: ErrorBlockKind
    note: str = Field(min_length=1, max_length=4000)
    desired: str | None = Field(default=None, max_length=4000)
    draft_version: int | None = None
    job_id: UUID | None = None


class ErrorBlockPatch(BaseModel):
    """Edits the FINDING only. The span is not patchable — moving an offset without the quote and
    the fingerprint would split the anchor triple and leave the block describing other prose."""
    kind: ErrorBlockKind | None = None
    note: str | None = Field(default=None, min_length=1, max_length=4000)
    desired: str | None = Field(default=None, max_length=4000)


class ErrorBlockClose(BaseModel):
    resolution: str | None = Field(default=None, max_length=2000)
    proposal_id: str | None = Field(default=None, max_length=64)


async def _gate_book(grant: GrantClient, book_id: UUID, caller: UUID, need: GrantLevel) -> None:
    """E0-4c book-grant chokepoint → HTTP (mirrors canon._gate_book). none→404 (no oracle),
    under-tier→403."""
    try:
        await authorize_book(grant, book_id, caller, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


async def _require_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID, need: GrantLevel,
) -> None:
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    await _gate_book(grant, work.book_id, user_id, need)


async def _block_project_id(block_id: UUID) -> UUID:
    """PM-8 scope-bootstrap for by-id routes: the ids-only `project_id` of a block, un-scoped.
    Anti-oracle — ids or 404, never row content."""
    row = await get_pool().fetchrow(
        "SELECT project_id FROM chapter_error_block WHERE id = $1", block_id,
    )
    if row is None:
        raise HTTPException(status_code=404, detail="error block not found")
    return row["project_id"]


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


@router.get("/works/{project_id}/chapters/{chapter_id}/error-blocks")
async def list_error_blocks(
    project_id: UUID,
    chapter_id: UUID,
    status: str | None = None,
    include_archived: bool = False,
    limit: int = 200,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """The author's marks on a chapter.

    `open_count` is the TRUE number still wanting attention and is never capped by `limit`, so a
    caller showing a page cannot silently under-report how much is outstanding.
    """
    await _require_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    items, open_count = await blocks.list_for_chapter(
        project_id, chapter_id, status=status,
        include_archived=include_archived, limit=max(1, min(limit, 500)),
    )
    return {
        "blocks": [b.model_dump(mode="json") for b in items],
        "open_count": open_count,
    }


@router.post("/works/{project_id}/chapters/{chapter_id}/error-blocks", status_code=201)
async def create_error_block(
    project_id: UUID,
    chapter_id: UUID,
    body: ErrorBlockCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Mark a span of wrong prose. EDIT tier — a mark drives a prose change."""
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    if body.end_offset <= body.start_offset:
        raise HTTPException(status_code=400, detail={
            "code": "ERROR_BLOCK_SPAN_INVALID",
            "start_offset": body.start_offset, "end_offset": body.end_offset,
        })
    try:
        block = await blocks.create(
            project_id, created_by=user_id,
            target_kind="draft_job" if body.job_id else "chapter_draft",
            chapter_id=None if body.job_id else chapter_id,
            job_id=body.job_id, draft_version=body.draft_version,
            start_offset=body.start_offset, end_offset=body.end_offset,
            quote=body.quote, source_fingerprint=body.source_fingerprint,
            kind=body.kind, note=body.note, desired=body.desired,
        )
    except DuplicateErrorBlockError:
        # 409, not a silent success: a double-submit and a deliberate second mark are
        # indistinguishable here, and pretending the write happened would be the silent no-op.
        raise HTTPException(status_code=409, detail={
            "code": "ERROR_BLOCK_DUPLICATE",
            "message": "an identical open mark already exists on this span",
        })
    return block.model_dump(mode="json")


@router.patch("/error-blocks/{block_id}")
async def patch_error_block(
    block_id: UUID,
    body: ErrorBlockPatch,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    project_id = await _block_project_id(block_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    patch = body.model_dump(exclude_unset=True)
    try:
        block = await blocks.update(project_id, block_id, patch,
                                    expected_version=_parse_if_match(if_match))
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={
            "code": "ERROR_BLOCK_VERSION_CONFLICT",
            "current": exc.current.model_dump(mode="json"),
        })
    if block is None:
        raise HTTPException(status_code=404, detail="error block not found")
    return block.model_dump(mode="json")


@router.post("/error-blocks/{block_id}/resolve", status_code=200)
async def resolve_error_block(
    block_id: UUID,
    body: ErrorBlockClose,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Close a block as fixed. Separate from `dismiss` because 'we fixed it' and 'this is fine
    actually' are different facts about the prose, and the eval-gate reads them differently."""
    return await _close(block_id, "resolved", body, user_id, works, blocks, grant)


@router.post("/error-blocks/{block_id}/dismiss", status_code=200)
async def dismiss_error_block(
    block_id: UUID,
    body: ErrorBlockClose,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Close a block as won't-fix."""
    return await _close(block_id, "dismissed", body, user_id, works, blocks, grant)


async def _close(
    block_id: UUID, status: str, body: ErrorBlockClose, user_id: UUID,
    works: WorksRepo, blocks: ErrorBlocksRepo, grant: GrantClient,
) -> dict[str, Any]:
    project_id = await _block_project_id(block_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    block = await blocks.set_status(
        project_id, block_id, status,
        proposal_id=body.proposal_id, resolution=body.resolution,
    )
    if block is None:
        raise HTTPException(status_code=404, detail="error block not found")
    return block.model_dump(mode="json")


@router.delete("/error-blocks/{block_id}", status_code=200)
async def delete_error_block(
    block_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """Soft-archive (the canon_rule precedent). A resolved block is correction history the
    eval-gate wants, so nothing here hard-deletes."""
    project_id = await _block_project_id(block_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    block = await blocks.archive(project_id, block_id)
    if block is None:
        raise HTTPException(status_code=404, detail="error block not found")
    return block.model_dump(mode="json")


@router.post("/error-blocks/{block_id}/restore", status_code=200)
async def restore_error_block(
    block_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    blocks: ErrorBlocksRepo = Depends(get_error_blocks_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """The UNDO the DELETE promises — an archived block is otherwise unlistable."""
    project_id = await _block_project_id(block_id)
    await _require_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    block = await blocks.restore(project_id, block_id)
    if block is None:
        raise HTTPException(status_code=404, detail="error block not found")
    return block.model_dump(mode="json")
