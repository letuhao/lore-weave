"""Grounding preview router (composition-service, M4).

GET /works/{project_id}/scenes/{node_id}/grounding → the packed context for a
target scene (the Grounding panel preview, M8; also the M6 engine's retrieve
step). Loads the Work + node (project-scoped → 404), then runs the packer, which
enforces the A1 (project scope) + E0 book-grant (25 PM-8) chokepoints. C3a:
`grounding_available=false` + a warning when no knowledge graph backs the scene.
The pin PUT gates EDIT on the book grant explicitly (it does not run the packer).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, StringConstraints

from app.clients.book_client import BookClient, BookClientError
from app.clients.embedding_client import EmbeddingClient
from app.clients.glossary_client import GlossaryClient
from app.clients.knowledge_client import KnowledgeClient
from app.config import settings
from app.db.models import GroundingItemType
from app.db.repositories.canon_rules import CanonRulesRepo
from app.db.repositories.derivatives import DerivativesRepo
from app.db.repositories.generation_jobs import GenerationJobsRepo
from app.db.repositories.grounding_pins import GroundingPinsRepo
from app.db.repositories.outline import OutlineRepo
from app.db.repositories.references import ReferencesRepo
from app.db.repositories.scene_links import SceneLinksRepo
from app.db.repositories.style_voice import StyleProfileRepo, VoiceProfileRepo
from app.db.repositories.works import WorksRepo
from app.deps import (
    get_book_client_dep, get_canon_rules_repo, get_derivatives_repo,
    get_embedding_client_dep, get_generation_jobs_repo, get_glossary_client_dep,
    get_grounding_pins_repo, get_knowledge_client_dep, get_motif_application_repo_opt,
    get_motif_repo_opt, get_outline_repo,
    get_references_repo, get_scene_links_repo, get_structure_repo,
    get_style_profile_repo, get_voice_profile_repo, get_works_repo,
)
from app.db.repositories.structure import StructureRepo
from app.db.repositories.motif_application import MotifApplicationRepo
from app.db.repositories.motif_repo import MotifRepo
from app.deps import get_grant_client_dep
from app.grant_client import GrantClient, GrantLevel
from app.middleware.jwt_auth import get_bearer_token, get_current_user
from app.grant_deps import InsufficientGrant, authorize_book
from app.packer.pack import OwnershipError, PackRequest, build_derivative_context, pack

router = APIRouter(prefix="/v1/composition")


class GroundingPinBody(BaseModel):
    """T3.4 — set or clear the per-scene steering for one addressable grounding
    item. `action='none'` clears (returns the item to default budget behavior)."""
    item_type: GroundingItemType
    # capped to match SceneGroundingPin.item_id (200) so a too-long id is rejected
    # at the boundary (422) rather than 500-ing on the RETURNING-row revalidation.
    item_id: Annotated[str, StringConstraints(min_length=1, max_length=200)]
    action: Literal["pin", "exclude", "none"]


@router.get("/works/{project_id}/scenes/{node_id}/grounding")
async def get_grounding(
    project_id: UUID,
    node_id: UUID,
    guide: str = Query(default=""),
    user_id: UUID = Depends(get_current_user),
    bearer: str = Depends(get_bearer_token),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    structures: StructureRepo | None = Depends(get_structure_repo),
    motif_apps: MotifApplicationRepo | None = Depends(get_motif_application_repo_opt),  # X-7 motif lens
    motifs: MotifRepo | None = Depends(get_motif_repo_opt),  # X-7 motif lens
    scene_links: SceneLinksRepo = Depends(get_scene_links_repo),
    canon: CanonRulesRepo = Depends(get_canon_rules_repo),
    book: BookClient = Depends(get_book_client_dep),
    glossary: GlossaryClient = Depends(get_glossary_client_dep),
    knowledge: KnowledgeClient = Depends(get_knowledge_client_dep),
    jobs: GenerationJobsRepo = Depends(get_generation_jobs_repo),
    derivatives: DerivativesRepo = Depends(get_derivatives_repo),
    grounding_pins: GroundingPinsRepo = Depends(get_grounding_pins_repo),
    style_profiles: StyleProfileRepo = Depends(get_style_profile_repo),
    voice_profiles: VoiceProfileRepo = Depends(get_voice_profile_repo),
    references: ReferencesRepo = Depends(get_references_repo),
    embedder: EmbeddingClient = Depends(get_embedding_client_dep),
) -> dict[str, Any]:
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    node = await outline.get_node(node_id)
    if node is None or str(node.project_id) != str(project_id):
        raise HTTPException(status_code=404, detail="scene not found")

    # C25 — resolve the dị bản two-project merge inputs (base project + branch +
    # fresh overrides). Empty for a non-derivative Work.
    deriv = await build_derivative_context(
        work, works_repo=works, derivatives_repo=derivatives)
    req = PackRequest(
        user_id=user_id, project_id=project_id, book_id=work.book_id,
        node=node.model_dump(mode="python"), bearer=bearer, guide=guide,
        settings=work.settings,
        source_project_id=deriv.source_project_id, branch_point=deriv.branch_point,
        overrides=deriv.overrides,
    )
    try:
        pc = await pack(
            req, book=book, glossary=glossary, knowledge=knowledge,
            canon_repo=canon, outline_repo=outline, scene_links_repo=scene_links,
            structure_repo=structures,  # 23 BA12 — the arc lens
            motif_application_repo=motif_apps,  # X-7 — the motif lens (scene beats)
            motif_repo=motifs,  # X-7 — ditto; BOTH must ride or the lens is dormant
            budget_tokens=settings.pack_token_budget, jobs_repo=jobs,
            grounding_pins_repo=grounding_pins,  # T3.4 — honor per-scene pins
            style_profile_repo=style_profiles,  # T3.5 — density/pace
            voice_profile_repo=voice_profiles,  # T3.5 — present-character voices
            references_repo=references,  # T3.6 — author reference shelf
            embedding_client=embedder,  # T3.6 — provider-registry embed
        )
    except OwnershipError:
        raise HTTPException(status_code=404, detail="book not found")
    except InsufficientGrant:
        # E0-4c: a grantee below VIEW shouldn't reach here (VIEW is the floor),
        # but map defensively for uniformity with the write routers.
        raise HTTPException(status_code=403, detail="insufficient access")
    except BookClientError:
        # book-service unreachable during the SEC2 grant check (or sort-order
        # resolve) → upstream-down, not our bug.
        raise HTTPException(status_code=502, detail={"code": "BOOK_SERVICE_UNAVAILABLE"})

    return {
        "blocks": pc.blocks,
        "prompt": pc.prompt,
        "profile": {
            "source_language": pc.profile.source_language,
            "voice": pc.profile.voice,
            "structure_pref": pc.profile.structure_pref,
            # T3.5 — the resolved prose style + present-character voices steering this scene
            "density_level": pc.profile.density_level,
            "pace_level": pc.profile.pace_level,
            "character_voices": [
                {"name": name, "tags": list(tags)} for name, tags in pc.profile.character_voices
            ],
        },
        "token_count": pc.token_count,
        "dropped_count": pc.dropped_count,
        "l4_dropped_no_position": pc.l4_dropped_no_position,
        "grounding_available": pc.grounding_available,
        "over_budget": pc.over_budget,
        "warnings": pc.warnings,
        # T3.4 — addressable items (present/canon/lore) with pin/exclude state.
        "grounding_items": pc.grounding_items,
    }


@router.put("/works/{project_id}/scenes/{node_id}/grounding-pins")
async def set_grounding_pin(
    project_id: UUID,
    node_id: UUID,
    body: GroundingPinBody,
    user_id: UUID = Depends(get_current_user),
    works: WorksRepo = Depends(get_works_repo),
    outline: OutlineRepo = Depends(get_outline_repo),
    grounding_pins: GroundingPinsRepo = Depends(get_grounding_pins_repo),
    grant: GrantClient = Depends(get_grant_client_dep),
) -> dict[str, Any]:
    """T3.4 — pin / exclude / clear one addressable grounding item for a scene.
    Gated on the E0 book grant (25 PM-8: EDIT — it writes the shared pin set;
    none→404, no existence oracle). Honored on the next pack (preview AND
    generation)."""
    work = await works.get(project_id)
    if work is None:
        raise HTTPException(status_code=404, detail="work not found")
    try:
        await authorize_book(grant, work.book_id, user_id, GrantLevel.EDIT)
    except OwnershipError:
        raise HTTPException(status_code=404, detail="work not found")
    except InsufficientGrant:
        raise HTTPException(status_code=403, detail="insufficient access")
    node = await outline.get_node(node_id)
    if node is None or str(node.project_id) != str(project_id):
        raise HTTPException(status_code=404, detail="scene not found")

    if body.action == "none":
        await grounding_pins.clear(project_id, node_id, body.item_type, body.item_id)
    else:
        await grounding_pins.set_action(
            project_id, node_id, body.item_type, body.item_id, body.action,
            created_by=user_id)
    return {"item_type": body.item_type, "item_id": body.item_id, "action": body.action}
