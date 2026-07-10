"""Style & Voice router (composition-service, LOOM T3.5).

Per-scope prose-style steering (Density/Pace, 0-100, scoped work|chapter|scene) and
per-character voice tags. Both are authoring config the packer threads into the
draft prompts (density/pace via the most-specific scope; voice for present
characters only). Access is the E0 book grant (25 PM-8): every route resolves
the Work by project and gates VIEW (reads) / EDIT (writes) on its book — an
unknown project / no-grant caller is a 404 (no existence oracle).
"""

from __future__ import annotations

from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, StringConstraints

from app.db.models import StyleScope
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
from app.db.repositories.works import WorksRepo
from app.deps import (get_grant_client_dep, get_style_profile_repo,
                      get_voice_profile_repo, get_works_repo)
from app.grant_client import GrantClient, GrantLevel
from app.grant_deps import InsufficientGrant, authorize_book
from app.middleware.jwt_auth import get_current_user
from app.packer.pack import OwnershipError

router = APIRouter(prefix="/v1/composition")

_Tag = Annotated[str, StringConstraints(min_length=1, max_length=40)]


async def _gate_work(
    works: WorksRepo, grant: GrantClient, user_id: UUID, project_id: UUID,
    need: GrantLevel,
) -> None:
    """Resolve the Work by project (un-user-scoped — 25 PM-9) and gate the
    caller's E0 grant on its book (PM-8). none→404 (no oracle), under-tier→403."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    try:
        await authorize_book(grant, work.book_id, user_id, need)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")


# ── style profiles ──

class StyleProfileBody(BaseModel):
    scope_type: StyleScope
    scope_id: UUID
    density: int = Field(ge=0, le=100)
    pace: int = Field(ge=0, le=100)


@router.get("/works/{project_id}/style-profiles")
async def list_style_profiles(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    style: StyleProfileRepo = Depends(get_style_profile_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    rows = await style.list_all(project_id)
    return {"items": [r.model_dump(mode="json") for r in rows]}


@router.put("/works/{project_id}/style-profile")
async def put_style_profile(
    project_id: UUID,
    body: StyleProfileBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    style: StyleProfileRepo = Depends(get_style_profile_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    row = await style.upsert(
        project_id, body.scope_type, body.scope_id, body.density, body.pace,
        created_by=user_id)
    return row.model_dump(mode="json")


@router.delete("/works/{project_id}/style-profile")
async def delete_style_profile(
    project_id: UUID,
    scope_type: StyleScope = Query(...),
    scope_id: UUID = Query(...),
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    style: StyleProfileRepo = Depends(get_style_profile_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    removed = await style.delete(project_id, scope_type, scope_id)
    return {"removed": removed}


# ── voice profiles ──

class VoiceProfileBody(BaseModel):
    entity_id: UUID
    entity_name: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    # capped count + per-tag length so a runaway client can't bloat the prompt
    tags: list[_Tag] = Field(default_factory=list, max_length=20)


@router.get("/works/{project_id}/voice-profiles")
async def list_voice_profiles(
    project_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    voice: VoiceProfileRepo = Depends(get_voice_profile_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_work(works, grant, user_id, project_id, GrantLevel.VIEW)
    rows = await voice.list_all(project_id)
    return {"items": [r.model_dump(mode="json") for r in rows]}


@router.put("/works/{project_id}/voice-profiles")
async def put_voice_profile(
    project_id: UUID,
    body: VoiceProfileBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    voice: VoiceProfileRepo = Depends(get_voice_profile_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    row = await voice.upsert(
        project_id, body.entity_id, body.entity_name, list(body.tags),
        created_by=user_id)
    return row.model_dump(mode="json")


@router.delete("/works/{project_id}/voice-profiles/{entity_id}")
async def delete_voice_profile(
    project_id: UUID,
    entity_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    voice: VoiceProfileRepo = Depends(get_voice_profile_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    await _gate_work(works, grant, user_id, project_id, GrantLevel.EDIT)
    removed = await voice.delete(project_id, entity_id)
    return {"removed": removed}
