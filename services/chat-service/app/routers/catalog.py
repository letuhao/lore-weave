"""Story 04 — tool/skill catalog routes for the context rack browser."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.client.knowledge_client import get_knowledge_client
from app.deps import get_current_user
from app.models import SkillCatalogResponse, ToolCatalogResponse, ToolCatalogItem, SkillCatalogItem
from app.services.skill_registry import catalog_items as skill_catalog_items
from app.services.tool_discovery import _provider_prefix, tool_name, tool_tier, _fn

router = APIRouter(prefix="/v1/chat", tags=["catalog"])


@router.get("/tools/catalog", response_model=ToolCatalogResponse)
async def list_tools_catalog(
    _user_id: str = Depends(get_current_user),
) -> ToolCatalogResponse:
    catalog = await get_knowledge_client().get_tool_definitions()
    items: list[ToolCatalogItem] = []
    for td in catalog:
        name = tool_name(td)
        if not name:
            continue
        tier = tool_tier(td)
        if tier == "S":
            continue  # Tier-S not pinnable from rack (#07a)
        desc = _fn(td).get("description", "") or ""
        items.append(ToolCatalogItem(
            name=name,
            domain=_provider_prefix(name),
            tier=tier,
            description=desc,
        ))
    items.sort(key=lambda x: x.name)
    return ToolCatalogResponse(items=items)


@router.get("/skills/catalog", response_model=SkillCatalogResponse)
async def list_skills_catalog(
    _user_id: str = Depends(get_current_user),
) -> SkillCatalogResponse:
    return SkillCatalogResponse(
        items=[SkillCatalogItem(**row) for row in skill_catalog_items()],
    )
