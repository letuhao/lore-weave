"""System-tier skill registry (story 04 / #07a).

v1 skills are static prompt modules — no user-defined skills table.
``resolve_skills_to_inject`` filters by session pins + surface flags;
empty ``enabled_skills`` preserves legacy auto-inject behaviour.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class SkillDef:
    code: str
    label: str
    surfaces: frozenset[str]
    prompt_loader: Callable[[], str]
    # L1 (metadata tier, RAID C3): a one-line description injected ALWAYS for every
    # surface-visible skill (cheap), so the model knows the skill EXISTS and can ask to
    # use it, even when the full L2 body is only loaded for a resolved/pinned skill.
    description: str = ""


def _load_glossary() -> str:
    from app.services.glossary_skill import GLOSSARY_SKILL_PROMPT
    return GLOSSARY_SKILL_PROMPT


def _load_admin() -> str:
    from app.services.glossary_skill import GLOSSARY_ADMIN_SKILL_PROMPT
    return GLOSSARY_ADMIN_SKILL_PROMPT


def _load_universal() -> str:
    from app.services.universal_skill import UNIVERSAL_SKILL_PROMPT
    from app.services.workflow_skill import WORKFLOW_SKILL_PROMPT
    return UNIVERSAL_SKILL_PROMPT + "\n\n" + WORKFLOW_SKILL_PROMPT


def _load_knowledge() -> str:
    from app.services.knowledge_skill import KNOWLEDGE_SKILL_PROMPT
    return KNOWLEDGE_SKILL_PROMPT


def _load_plan_forge() -> str:
    from app.services.plan_forge_skill import PLAN_FORGE_SKILL_PROMPT
    return PLAN_FORGE_SKILL_PROMPT


SYSTEM_SKILLS: dict[str, SkillDef] = {
    "glossary": SkillDef(
        code="glossary",
        label="Glossary assistant",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_glossary,
        description="Inspect and curate the book's glossary — characters, places, items, and the kinds/attributes schema.",
    ),
    "universal": SkillDef(
        code="universal",
        label="Universal driver",
        surfaces=frozenset({"chat"}),
        prompt_loader=_load_universal,
        description="General multi-step task driver: find and use the right tools to fulfil the request.",
    ),
    "knowledge": SkillDef(
        code="knowledge",
        label="Knowledge graph",
        surfaces=frozenset({"book", "editor", "chat"}),
        prompt_loader=_load_knowledge,
        description="Query and build the book's knowledge graph and memory (entities, relations, facts).",
    ),
    "admin": SkillDef(
        code="admin",
        label="CMS admin",
        surfaces=frozenset({"admin"}),
        prompt_loader=_load_admin,
        description="Edit the platform-wide System-tier glossary defaults (admin only).",
    ),
    "plan_forge": SkillDef(
        code="plan_forge",
        label="PlanForge (novel planner)",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_plan_forge,
        description="Plan the novel's system from a source doc, then hand off to drafting (propose→validate→compile).",
    ),
}


def skill_metadata_block(*, editor: bool, book_scoped: bool, admin: bool) -> str | None:
    """L1 metadata tier (RAID C3): a compact list of the skills AVAILABLE on this
    surface (label + one-line description), so the model knows they exist and can pin
    or request one — at ~tens of tokens, versus loading every full L2 body. Returns
    None when no skill is visible on the surface."""
    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin)
    lines = [
        f"- **{s.label}** (`{s.code}`): {s.description}"
        for s in SYSTEM_SKILLS.values()
        if s.description and _skill_visible(s, active)
    ]
    if not lines:
        return None
    return (
        "## Available skills\n"
        "These skills are available on this surface. The relevant one is loaded in full; "
        "if the user's request fits another, say so or pin it.\n" + "\n".join(lines)
    )


def _surface_key(*, editor: bool, book_scoped: bool, admin: bool) -> set[str]:
    if admin:
        return {"admin"}
    if editor:
        return {"editor", "book"}
    if book_scoped:
        return {"book"}
    return {"chat"}


def _skill_visible(skill: SkillDef, active: set[str]) -> bool:
    return bool(skill.surfaces & active)


def resolve_skills_to_inject(
    *,
    enabled_skills: list[str],
    stream_format: str,
    disable_tools: bool,
    tool_calling_enabled: bool,
    editor: bool,
    book_scoped: bool,
    admin: bool,
    permission_mode: str = "write",
) -> list[str]:
    """Return skill codes to inject this turn (ordered, deduped)."""
    if stream_format != "agui" or disable_tools or not tool_calling_enabled:
        return []

    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin)

    if enabled_skills:
        out = [
            code for code in enabled_skills
            if (skill := SYSTEM_SKILLS.get(code)) and _skill_visible(skill, active)
        ]
    else:
        # Legacy auto-inject (empty enabled_skills = surface-default).
        out = []
        if admin:
            out.append("admin")
        elif editor or book_scoped:
            out.append("glossary")
        else:
            out.append("universal")
        if not admin:
            out.append("knowledge")

    # RAID Wave B2 (07S §5b) — PLAN mode auto-injects the plan_forge skill on the
    # surfaces that allow it (book/editor), even when not pinned, so the model
    # knows the propose→validate→compile flow. Write/ask modes are unchanged.
    if permission_mode == "plan" and "plan_forge" not in out:
        pf = SYSTEM_SKILLS.get("plan_forge")
        if pf and _skill_visible(pf, active):
            out.append("plan_forge")
    return out


def skill_prompts(codes: list[str]) -> dict[str, str]:
    """Map skill code → system prompt text."""
    prompts: dict[str, str] = {}
    for code in codes:
        skill = SYSTEM_SKILLS.get(code)
        if skill:
            prompts[code] = skill.prompt_loader()
    return prompts


def catalog_items() -> list[dict]:
    """System skills for GET /v1/chat/skills/catalog."""
    return [
        {
            "id": s.code,
            "label": s.label,
            "surfaces": sorted(s.surfaces),
        }
        for s in SYSTEM_SKILLS.values()
        if s.code != "admin"  # admin surface is cms-only; omit from rack browser
    ]
