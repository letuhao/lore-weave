"""Outline + Scene-Graph router (§5) — tree, nodes, scene-links.

Reuses the M2 OutlineRepo / SceneLinksRepo (incl. the M2-closure ownership +
reparent-cycle guards, which surface as ReferenceViolationError → 400 here, and
If-Match VersionMismatchError → 412). The /works/{project_id}/* routes verify
the Work exists (user-scoped 404) before mutating its tree.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel

from app.db.models import LinkKind, NodeKind, NodeStatus
from app.db.repositories import ReferenceViolationError, VersionMismatchError
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo
from app.deps import get_outline_repo, get_scene_links_repo, get_works_repo
from app.middleware.jwt_auth import get_current_user

router = APIRouter(prefix="/v1/composition")


class NodeCreate(BaseModel):
    kind: NodeKind
    parent_id: UUID | None = None
    rank: str | None = None
    title: str = ""
    pov_entity_id: UUID | None = None
    present_entity_ids: list[UUID] = []
    goal: str = ""
    beat_role: str | None = None
    status: NodeStatus = "empty"
    chapter_id: UUID | None = None
    tension: int | None = None
    story_order: int | None = None
    synopsis: str = ""


class NodePatch(BaseModel):
    parent_id: UUID | None = None
    rank: str | None = None
    title: str | None = None
    pov_entity_id: UUID | None = None
    present_entity_ids: list[UUID] | None = None
    goal: str | None = None
    beat_role: str | None = None
    status: NodeStatus | None = None
    chapter_id: UUID | None = None
    tension: int | None = None
    story_order: int | None = None
    synopsis: str | None = None


class SceneLinkCreate(BaseModel):
    from_node_id: UUID
    to_node_id: UUID
    kind: LinkKind = "setup_payoff"   # Literal → bad value is 422, not a 500 CheckViolation
    label: str = ""


def _parse_if_match(if_match: str | None) -> int | None:
    if if_match is None:
        return None
    try:
        return int(if_match.strip().strip('"'))
    except ValueError:
        raise HTTPException(status_code=400, detail="If-Match must be an integer version")


async def _require_work(works: WorksRepo, user_id: UUID, project_id: UUID) -> None:
    if await works.get(user_id, project_id) is None:
        raise HTTPException(status_code=404, detail="work not found")


@router.get("/works/{project_id}/outline")
async def get_outline(
    project_id: UUID,
    include_archived: bool = False,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
) -> dict[str, Any]:
    await _require_work(works, user_id, project_id)
    nodes = await outline.list_tree(user_id, project_id, include_archived=include_archived)
    links = await scene_links.list_by_project(user_id, project_id)
    return {
        "nodes": [n.model_dump(mode="json") for n in nodes],
        "scene_links": [l.model_dump(mode="json") for l in links],
    }


@router.get("/works/{project_id}/chapters/{chapter_id}/publish-gate")
async def get_publish_gate(
    project_id: UUID,
    chapter_id: UUID,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
) -> dict[str, Any]:
    """M9 chapter-gate: is the chapter publishable? `can_publish` is True only
    when ALL the chapter's composition scenes are status='done' (OI-1 — no
    unreviewed scene canonized). The FE gates the (CM-FE) Publish affordance on
    this. Verifies the Work exists (user-scoped 404) first."""
    await _require_work(works, user_id, project_id)
    return await outline.chapter_scene_gate(user_id, project_id, chapter_id)


@router.post("/works/{project_id}/outline/nodes", status_code=201)
async def create_node(
    project_id: UUID,
    body: NodeCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
) -> dict[str, Any]:
    await _require_work(works, user_id, project_id)
    try:
        node = await outline.create_node(
            user_id, project_id, kind=body.kind, parent_id=body.parent_id, rank=body.rank,
            title=body.title, pov_entity_id=body.pov_entity_id,
            present_entity_ids=body.present_entity_ids, goal=body.goal,
            beat_role=body.beat_role, status=body.status, chapter_id=body.chapter_id,
            tension=body.tension, story_order=body.story_order, synopsis=body.synopsis,
        )
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    except asyncpg.CheckViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "CONSTRAINT", "detail": str(exc)})
    return node.model_dump(mode="json")


@router.patch("/outline/nodes/{node_id}")
async def patch_node(
    node_id: UUID,
    body: NodePatch,
    user_id: UUID = Depends(get_current_user),
    outline: OutlineRepo = Depends(get_outline_repo),
    if_match: str | None = Header(default=None, alias="If-Match"),
) -> dict[str, Any]:
    patch = body.model_dump(exclude_unset=True)
    expected_version = _parse_if_match(if_match)
    # A scene committing (status → 'done') routes through the commit-aware path,
    # which emits composition.scene_committed atomically with the status write
    # (M9 / §3.1). Every other patch keeps the plain self-acquiring update.
    try:
        if patch.get("status") == "done":
            node = await outline.update_node_commit_aware(
                user_id, node_id, patch, expected_version=expected_version,
            )
        else:
            node = await outline.update_node(
                user_id, node_id, patch, expected_version=expected_version,
            )
    except VersionMismatchError as exc:
        raise HTTPException(status_code=412, detail={"code": "NODE_VERSION_CONFLICT",
                                                     "current": exc.current.model_dump(mode="json")})
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump(mode="json")


@router.delete("/outline/nodes/{node_id}", status_code=200)
async def delete_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    outline: OutlineRepo = Depends(get_outline_repo),
) -> dict[str, Any]:
    node = await outline.archive_node(user_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found")
    return node.model_dump(mode="json")


@router.post("/outline/nodes/{node_id}/restore", status_code=200)
async def restore_node(
    node_id: UUID,
    user_id: UUID = Depends(get_current_user),
    outline: OutlineRepo = Depends(get_outline_repo),
) -> dict[str, Any]:
    """T1.1b — un-archive a node (inverse of DELETE). Restores the node's archived
    subtree + archived ancestor chain so it reconnects to a visible root. 404 if
    the node doesn't exist / isn't ours / wasn't archived."""
    node = await outline.restore_node(user_id, node_id)
    if node is None:
        raise HTTPException(status_code=404, detail="node not found or not archived")
    return node.model_dump(mode="json")


@router.post("/works/{project_id}/scene-links", status_code=201)
async def create_scene_link(
    project_id: UUID,
    body: SceneLinkCreate,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
) -> dict[str, Any]:
    await _require_work(works, user_id, project_id)
    try:
        link = await scene_links.create(user_id, project_id, body.from_node_id, body.to_node_id,
                                        kind=body.kind, label=body.label)
    except ReferenceViolationError as exc:
        raise HTTPException(status_code=400, detail={"code": "BAD_REFERENCE", "detail": exc.message})
    except asyncpg.UniqueViolationError:
        raise HTTPException(status_code=409, detail={"code": "SCENE_LINK_EXISTS"})
    return link.model_dump(mode="json")


@router.delete("/scene-links/{link_id}", status_code=204)
async def delete_scene_link(
    link_id: UUID,
    user_id: UUID = Depends(get_current_user),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
) -> None:
    if not await scene_links.delete(user_id, link_id):
        raise HTTPException(status_code=404, detail="scene-link not found")
