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


SYSTEM_SKILLS: dict[str, SkillDef] = {
    "glossary": SkillDef(
        code="glossary",
        label="Glossary assistant",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_glossary,
    ),
    "universal": SkillDef(
        code="universal",
        label="Universal driver",
        surfaces=frozenset({"chat"}),
        prompt_loader=_load_universal,
    ),
    "knowledge": SkillDef(
        code="knowledge",
        label="Knowledge graph",
        surfaces=frozenset({"book", "editor", "chat"}),
        prompt_loader=_load_knowledge,
    ),
    "admin": SkillDef(
        code="admin",
        label="CMS admin",
        surfaces=frozenset({"admin"}),
        prompt_loader=_load_admin,
    ),
}


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
) -> list[str]:
    """Return skill codes to inject this turn (ordered, deduped)."""
    if stream_format != "agui" or disable_tools or not tool_calling_enabled:
        return []

    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin)

    if enabled_skills:
        out: list[str] = []
        for code in enabled_skills:
            skill = SYSTEM_SKILLS.get(code)
            if skill and _skill_visible(skill, active):
                out.append(code)
        return out

    # Legacy auto-inject (empty enabled_skills = surface-default).
    out: list[str] = []
    if admin:
        out.append("admin")
    elif editor or book_scoped:
        out.append("glossary")
    else:
        out.append("universal")
    if not admin:
        out.append("knowledge")
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
