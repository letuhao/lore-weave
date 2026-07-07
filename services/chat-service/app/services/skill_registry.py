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
    # Skill-authoring contract (docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-
    # standard.md Part A) — the GROUP_DIRECTORY domain(s) this skill's prose names tools
    # from DIRECTLY (as opposed to teaching "search for it with find_tools"). Every such
    # domain MUST be hot-seeded whenever this skill is active, or the skill points the
    # model at a tool it can't see yet — the exact bug plan_forge shipped with
    # (2026-07-07: its prose said "call plan_propose_spec" but "plan" was never hot).
    # `test_skill_registry.py::test_every_skills_named_tools_are_in_its_hot_domains`
    # enforces this by scanning the prose for real catalog tool names. Empty = the
    # skill only teaches find_tools-mediated discovery, never assumes direct calling.
    hot_domains: frozenset[str] = frozenset()


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


def _load_composition() -> str:
    from app.services.composition_skill import COMPOSITION_SKILL_PROMPT
    return COMPOSITION_SKILL_PROMPT


def _load_translation() -> str:
    from app.services.translation_skill import TRANSLATION_SKILL_PROMPT
    return TRANSLATION_SKILL_PROMPT


SYSTEM_SKILLS: dict[str, SkillDef] = {
    "glossary": SkillDef(
        code="glossary",
        label="Glossary assistant",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_glossary,
        description="Inspect and curate the book's glossary — characters, places, items, and the kinds/attributes schema.",
        hot_domains=frozenset({"glossary"}),
    ),
    "universal": SkillDef(
        code="universal",
        label="Universal driver",
        surfaces=frozenset({"chat"}),
        prompt_loader=_load_universal,
        description="General multi-step task driver: find and use the right tools to fulfil the request.",
        # Names no domain-specific tool directly (only the always-on core + generic
        # find_tools-mediated discovery) — correctly empty, not an oversight.
        hot_domains=frozenset(),
    ),
    "knowledge": SkillDef(
        code="knowledge",
        label="Knowledge graph",
        surfaces=frozenset({"book", "editor", "chat"}),
        prompt_loader=_load_knowledge,
        description="Query and build the book's knowledge graph and memory (entities, relations, facts).",
        # Found 2026-07-07 building the skill-claims lint: this skill DOES name kg_*/
        # memory_* tools directly ("Use memory_search/... for X. Use kg_graph_query/...
        # for Y.") — the same class of claim plan_forge made. Declaring the domain here
        # states the skill's real intent honestly; it does NOT by itself mean the
        # runtime hot-seeds "knowledge" today (it doesn't — neither
        # `_BOOK_SCOPED_HOT_DOMAINS`/`_STUDIO_HOT_DOMAINS` include it, and unlike the
        # plan-mode fix this can't be a small permission_mode-gated addition: knowledge
        # is auto-injected on EVERY surface including the universal chat surface, which
        # `surface_hot_domains()` hot-seeds nothing on by design). Wiring declared
        # `hot_domains` to the actual runtime seed is Part D of
        # docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md — tracked
        # there, not silently left unfindable.
        hot_domains=frozenset({"knowledge"}),
    ),
    "admin": SkillDef(
        code="admin",
        label="CMS admin",
        surfaces=frozenset({"admin"}),
        prompt_loader=_load_admin,
        description="Edit the platform-wide System-tier glossary defaults (admin only).",
        # The admin surface advertises its OWN small, always-fully-exposed System-tier
        # catalog (a separate /mcp/admin server, INV-T6) — outside the GROUP_DIRECTORY /
        # hot-domain seeding system entirely, so there is no "domain" to declare here.
        hot_domains=frozenset(),
    ),
    "plan_forge": SkillDef(
        code="plan_forge",
        label="PlanForge (novel planner)",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_plan_forge,
        description="Plan the novel's system from a source doc, then hand off to drafting (propose→validate→compile).",
        hot_domains=frozenset({"plan"}),
    ),
    "composition": SkillDef(
        code="composition",
        label="Composition (outline, prose, canon, motifs)",
        # Visible/pinnable on book+editor+studio; AUTO-injected by default only on
        # studio (see resolve_skills_to_inject's legacy branch) — that's the ONE
        # surface where "composition" is already hot (_STUDIO_HOT_DOMAINS), so
        # auto-injecting there adds zero new seeding risk. A curated pin on book/editor
        # is still fully supported (tool_surface.py's generic curated hot-domain union
        # covers it) — it just isn't the silent DEFAULT there, unlike studio.
        surfaces=frozenset({"book", "editor", "studio"}),
        prompt_loader=_load_composition,
        description="Build the outline, write/publish chapter prose, declare canon rules, and use the motif library.",
        hot_domains=frozenset({"composition"}),
    ),
    "translation": SkillDef(
        code="translation",
        label="Translation",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_translation,
        description="Translate chapters, review coverage, publish a version, and apply human corrections.",
        # NEVER auto-injected by default (see resolve_skills_to_inject) — "translation"
        # is not hot-seeded on any surface today, and auto-injecting it broadly would
        # need its own budget-verified rollout (tracked, docs/specs/2026-07-07-skill-
        # authoring-and-mcp-exposure-standard.md Part D). Curated-pin only for now:
        # tool_surface.py's generic curated hot-domain union safely seeds it ONLY for a
        # session that explicitly opted in.
        hot_domains=frozenset({"translation"}),
    ),
}


def skill_metadata_block(
    *, editor: bool, book_scoped: bool, admin: bool, studio: bool = False
) -> str | None:
    """L1 metadata tier (RAID C3): a compact list of the skills AVAILABLE on this
    surface (label + one-line description), so the model knows they exist and can pin
    or request one — at ~tens of tokens, versus loading every full L2 body. Returns
    None when no skill is visible on the surface."""
    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin, studio=studio)
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


def _surface_key(
    *, editor: bool, book_scoped: bool, admin: bool, studio: bool = False
) -> set[str]:
    if admin:
        return {"admin"}
    # ADDITIVE, not exclusive with editor/book below — a studio turn can arrive with NO
    # editor_context/book_context at all (studio_context is its own, independent signal
    # in stream_service.py), so "studio" must be unioned in on its own, not gated behind
    # an editor/book_scoped check that could be false simultaneously. Found 2026-07-07
    # wiring composition_skill: before this fix, a pure-studio turn (studio_context set,
    # editor_context/book_context absent) fell through to the generic "chat" surface —
    # invisible to glossary_skill/plan_forge_skill too, despite their tools being HOT
    # there via `_STUDIO_HOT_DOMAINS` (surface_hot_domains, a separate code path that
    # already treated studio as independent).
    keys: set[str] = {"studio"} if studio else set()
    if editor:
        return keys | {"editor", "book"}
    if book_scoped:
        return keys | {"book"}
    return keys or {"chat"}


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
    studio: bool = False,
) -> list[str]:
    """Return skill codes to inject this turn (ordered, deduped)."""
    if stream_format != "agui" or disable_tools or not tool_calling_enabled:
        return []

    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin, studio=studio)

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
        elif studio:
            # `_STUDIO_HOT_DOMAINS` already hot-seeds glossary+composition+story tools
            # here (surface_hot_domains) — auto-injecting both matching skills adds no
            # new seeding risk, it just teaches tools that were already being advertised
            # silently before this fix.
            out.append("glossary")
            out.append("composition")
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
