"""Story 04 — tool/skill catalog routes for the context rack browser."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.client.knowledge_client import get_knowledge_client
from app.deps import get_current_user
from app.models import SkillCatalogResponse, ToolCatalogResponse, ToolCatalogItem, SkillCatalogItem
from app.services.skill_registry import catalog_items as skill_catalog_items
from app.services.tool_discovery import _domain_of, tool_name, tool_tier, tool_visibility, _fn

router = APIRouter(prefix="/v1/chat", tags=["catalog"])


@router.get("/tools/catalog", response_model=ToolCatalogResponse)
async def list_tools_catalog(
    # CAT-4 Part D: default EXCLUDES legacy tools (the curated enabled_tools
    # picker shouldn't surface superseded tools by default — pinning one there
    # would flip the whole session into curated mode, an oversized side effect
    # for what's meant to be a scoped escape hatch). `visibility=legacy` is the
    # dedicated feed for the "Advanced tools" pinned_legacy_tools picker.
    visibility: str | None = Query(None, pattern="^(discoverable|legacy)$"),
    _user_id: str = Depends(get_current_user),
) -> ToolCatalogResponse:
    catalog = await get_knowledge_client().get_tool_definitions()
    want_visibility = visibility or "discoverable"
    items: list[ToolCatalogItem] = []
    for td in catalog:
        name = tool_name(td)
        if not name:
            continue
        tier = tool_tier(td)
        if tier == "S":
            continue  # Tier-S not pinnable from rack (#07a)
        if tool_visibility(td) != want_visibility:
            continue
        desc = _fn(td).get("description", "") or ""
        items.append(ToolCatalogItem(
            name=name,
            # 2026-07-07: resolve through the domain-alias map, not the raw literal
            # prefix — a kg_*/memory_* tool's real GROUP_DIRECTORY domain is
            # "knowledge", not "kg"/"memory" (see tool_discovery._DOMAIN_ALIASES).
            domain=_domain_of(name),
            tier=tier,
            description=desc,
            visibility=tool_visibility(td),
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
