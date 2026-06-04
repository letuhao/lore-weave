"""Grounding preview router (composition-service, M4).

GET /works/{project_id}/scenes/{node_id}/grounding → the packed context for a
target scene (the Grounding panel preview, M8; also the M6 engine's retrieve
step). Loads the Work + node (user-scoped → 404), then runs the packer, which
enforces the A1 (project scope) + SEC2 (book ownership) chokepoints. C3a:
`grounding_available=false` + a warning when no knowledge graph backs the scene.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query

from app.clients.book_client import BookClient, BookClientError
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.config import settings
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep, get_canon_rules_repo, get_glossary_client_dep,
    get_knowledge_client_dep, get_outline_repo, get_scene_links_repo, get_works_repo,
)
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.packer.pack import OwnershipError, PackRequest, pack

router = APIRouter(prefix="/v1/composition")


@router.get("/works/{project_id}/scenes/{node_id}/grounding")
async def get_grounding(
    project_id: UUID,
    node_id: UUID,
    guide: str = Query(default=""),
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
) -> dict[str, Any]:
    work = await works.get(user_id, project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    node = await outline.get_node(user_id, node_id)
    if node is None or str(node.project_id) != str(project_id):
        raise HTTPException(status_code=404, detail="scene not found")

    req = PackRequest(
        user_id=user_id, project_id=project_id, book_id=work.book_id,
        node=node.model_dump(mode="python"), bearer=bearer, guide=guide,
        settings=work.settings,
    )
    try:
        pc = await pack(
            req, book=book, glossary=glossary, knowledge=knowledge,
            canon_repo=canon, outline_repo=outline, scene_links_repo=scene_links,
            budget_tokens=settings.pack_token_budget,
        )
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except BookClientError:
        # book-service unreachable during the SEC2 owns_book check (or sort-order
        # resolve) → upstream-down, not our bug.
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})

    return {
        "blocks": pc.blocks,
        "prompt": pc.prompt,
        "profile": {
            "source_language": pc.profile.source_language,
            "voice": pc.profile.voice,
            "structure_pref": pc.profile.structure_pref,
        },
        "token_count": pc.token_count,
        "dropped_count": pc.dropped_count,
        "l4_dropped_no_position": pc.l4_dropped_no_position,
        "grounding_available": pc.grounding_available,
        "over_budget": pc.over_budget,
        "warnings": pc.warnings,
    }
