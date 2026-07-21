"""System-tier skill registry (story 04 / #07a).

v1 skills are static prompt modules — no user-defined skills table.
``resolve_skills_to_inject`` filters by session pins + surface flags;
empty ``enabled_skills`` preserves legacy auto-inject behaviour.

``resolve_skills_to_inject_async`` (Part F / F2, docs/plans/2026-07-07-intent-
skill-router.md) is an ADDITIVE async twin that layers the Intent→Skill Router
on top of this exact same structural result — see its own docstring.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

logger = logging.getLogger(__name__)


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


def _load_glossary_shaping() -> str:
    from app.services.glossary_skill import GLOSSARY_SHAPING_PROMPT
    return GLOSSARY_SHAPING_PROMPT


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


def _load_co_write() -> str:
    from app.services.co_write_skill import CO_WRITE_SKILL_PROMPT
    return CO_WRITE_SKILL_PROMPT


def _load_composition() -> str:
    from app.services.composition_skill import COMPOSITION_SKILL_PROMPT
    return COMPOSITION_SKILL_PROMPT


def _load_translation() -> str:
    from app.services.translation_skill import TRANSLATION_SKILL_PROMPT
    return TRANSLATION_SKILL_PROMPT


def _load_book() -> str:
    from app.services.book_skill import BOOK_SKILL_PROMPT
    return BOOK_SKILL_PROMPT


def _load_settings() -> str:
    from app.services.settings_skill import SETTINGS_SKILL_PROMPT
    return SETTINGS_SKILL_PROMPT


def _load_jobs() -> str:
    from app.services.jobs_skill import JOBS_SKILL_PROMPT
    return JOBS_SKILL_PROMPT


SYSTEM_SKILLS: dict[str, SkillDef] = {
    "glossary": SkillDef(
        code="glossary",
        label="Glossary assistant",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_glossary,
        description="Inspect and curate the book's glossary — characters, places, items, and the kinds/attributes schema.",
        hot_domains=frozenset({"glossary"}),
    ),
    "glossary_shaping": SkillDef(
        code="glossary_shaping",
        label="Glossary ontology-shaping",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_glossary_shaping,
        # N5a (dogfood 2026-07-18 F3): the PROACTIVE ontology-building half of the glossary
        # skill. Split OUT of the always-injected `glossary` core because its imperative
        # "adopt standards / do not skip it" framing made the co-writer rebuild a newcomer's
        # ontology on a plain "write a chapter" turn (a live Gemma QC proved a guard-line
        # alone did not hold). Injected ONLY when the author is actually doing glossary/world
        # work — pinned in the rack, or added by the intent router / find_tools — never on the
        # legacy auto-inject path. Hidden from the catalog (it's an internal companion to
        # `glossary`, not a separately-browsable capability).
        description=(
            "Set up, build, or expand the book's world ontology — kinds, attributes, adopt "
            "standards, batch ontology proposals. Companion to the glossary skill; loads only "
            "when the author explicitly does world/lore setup."
        ),
        hot_domains=frozenset({"glossary"}),
    ),
    "universal": SkillDef(
        code="universal",
        label="Universal driver",
        surfaces=frozenset({"chat"}),
        prompt_loader=_load_universal,
        description=(
            "General multi-step task driver: find and use the right tools to fulfil "
            "the request — including general web research on any topic via web_search, "
            "no book required."
        ),
        # hot_domains stays EMPTY, and after Track D CD5 that is no longer a compromise.
        # The prompt's one actionable tool, `web_search`, is ALWAYS-ON CORE (advertised
        # every turn, on every surface), so it needs no hot-seed at all — which is exactly
        # why it was promoted: general web research is this surface's core capability, yet
        # it used to cost a tool_list+tool_load round-trip through the `glossary` domain it
        # never belonged to.
        # `glossary_deep_research` is named only as a CONTRAST (don't confuse it with
        # web_search — it needs a book_id AND entity_id and a human confirm); it stays
        # find_tools-mediated, as do the book_chapter_save_draft/book_chapter_publish
        # sequencing mentions. Hot-seeding glossary's ~47-tool domain to cover one
        # contrastive mention would blow the chat surface's token budget (hot_tool_names()/
        # surface_hot_domains() are DOMAIN-level only, not per-tool — a real constraint,
        # not an oversight; see test_skill_registry.py's
        # `_ALLOWED_CONTRASTIVE_MENTIONS["universal"]`).
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
    "co_write": SkillDef(
        code="co_write",
        label="Co-writing (draft + materialise the plan)",
        surfaces=frozenset({"book", "editor"}),
        prompt_loader=_load_co_write,
        # The write-mode workflow (close-21-28): co-write prose AND materialise the story —
        # when the author lays out their story, propose AND compile it into linked structure,
        # never stop at a proposal. Orient/verify with composition_package_tree. Closes the
        # S06 gap where the agent proposed but never compiled (structure_node=0).
        description="Co-write prose AND make the plan real — when the author lays out their story, propose then COMPILE it into the linked chapter/scene structure the drafts hang on; orient with composition_package_tree.",
        # DELIBERATELY EMPTY (close-21-28): unlike plan_forge (which forces `plan` hot in
        # plan mode), the WRITE-mode workflow keeps the surface LEAN — it does NOT drag the
        # plan/composition long tail hot onto every co-writing turn (the "long-tail stays
        # lazy" design, test_seed_advertises_hot_tools_immediately). The tools it names are
        # reachable via find_tools (the skill instructs it) + the agent's federation; the
        # value here is the INSTRUCTION (propose→compile), not forcing tools hot. Exempt from
        # the named-tools-in-hot-domains lint for that reason.
        hot_domains=frozenset(),
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
    "book": SkillDef(
        code="book",
        label="Book (chapters, revisions, publish)",
        # Same authoring surfaces as composition — book_* tools are meaningful
        # wherever a book is open, including the studio workbench.
        surfaces=frozenset({"book", "editor", "studio"}),
        prompt_loader=_load_book,
        description="Browse/edit books and chapters, save and restore draft revisions, publish/unpublish, and propose cover/media/audio generation.",
        # F14 (round-4 dogfood, 2026-07-20): AUTO-injected on the book-bound surfaces
        # (studio/editor/book_scoped) — a book is OPEN, so book_* tools (list/get/delete/
        # publish chapters) must be hot-seeded. Was previously curated-pin-only, which meant
        # a book workbench advertised ZERO book tools; the agent asked to manage chapters
        # couldn't, and grabbed a wrong tool. (Still pinnable elsewhere.)
        hot_domains=frozenset({"book"}),
    ),
    "settings": SkillDef(
        code="settings",
        label="Settings (profile, AI providers/models)",
        # Account-level, not book-scoped — visible from the plain chat surface too,
        # unlike book/composition/translation which need a book in context.
        surfaces=frozenset({"book", "editor", "studio", "chat"}),
        prompt_loader=_load_settings,
        description="Manage the user's profile and BYOK AI provider/model registry — list, register, favorite, activate, default, delete.",
        hot_domains=frozenset({"settings"}),
    ),
    "jobs": SkillDef(
        code="jobs",
        label="Jobs (background job monitor/control)",
        # Account-level, cross-service — same reasoning as settings.
        surfaces=frozenset({"book", "editor", "studio", "chat"}),
        prompt_loader=_load_jobs,
        description="List, inspect, cancel, or pause the user's own background jobs across every service.",
        hot_domains=frozenset({"jobs"}),
    ),
}


# ── F7c (2026-07-19) — the `load_skill` control tool (twin of tool_load) ──────
# Consumer-local meta-tool (like tool_list/tool_load/workflow_load): reads
# SYSTEM_SKILLS, executes nothing, returns a skill's full L2 body so the model can
# follow its workflow. Advertised only when `lazy_skill_bodies` is on (the L1 index
# tells the model a skill EXISTS; this pulls its instructions on demand). The
# returned body lands as a tool result → persists in message history like any tool
# result, so no per-session `activated_skills` column is needed.
LOAD_SKILL_NAME = "load_skill"

# Closed set (Frontend-Tool-Contract discipline) — every separately-loadable skill
# code. `admin` (its own CMS surface) and `glossary_shaping` (internal companion of
# `glossary`, auto-added on world-setup intent, never separately loadable) are excluded,
# matching skill_metadata_block / catalog_items.
LOADABLE_SKILL_CODES: list[str] = sorted(
    c for c in SYSTEM_SKILLS if c not in ("admin", "glossary_shaping")
)

LOAD_SKILL_TOOL: dict = {
    "type": "function",
    "function": {
        "name": LOAD_SKILL_NAME,
        "description": (
            "Load the full instructions for a skill from the 'Available skills' list so you "
            "can follow its workflow. Loading returns the skill's guidance; it runs nothing. "
            "Use it when the user's request fits a skill whose body isn't already in context "
            "(the skill list shows what each one does)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "skill": {
                    "type": "string",
                    "enum": LOADABLE_SKILL_CODES,
                    "description": "A single skill code from the Available skills list.",
                },
                "skills": {
                    "type": "array",
                    "items": {"type": "string", "enum": LOADABLE_SKILL_CODES},
                    "description": "Several skill codes to load at once.",
                },
            },
            "additionalProperties": False,
        },
        # C-TOOL — pure disclosure, executes nothing, no scope key. Explicit tier so it
        # never relies on the silent "R" default the wire gates exist to close.
        "_meta": {"tier": "R", "scope": "none"},
    },
}


def load_skill_result(codes: list[str]) -> dict:
    """Build the ``load_skill`` payload: full L2 body per requested skill code.

    Pure disclosure — returns bodies, activates/executes nothing. Unknown codes come
    back under ``not_found`` (never a silent drop — a resolver that drops a request
    without saying so is how a model hallucinates the call succeeded). No surface
    filter: the L1 index only lists surface-visible skills, and handing over a body
    for an off-surface skill is harmless (the model still reaches its tools via
    find_tools), so a strict filter would only add a needless error path."""
    want: list[str] = []
    for c in codes:
        if c and c not in want:
            want.append(c)
    loaded: list[dict] = []
    not_found: list[str] = []
    for code in want:
        skill = SYSTEM_SKILLS.get(code)
        if skill is None:
            not_found.append(code)
            continue
        loaded.append({"skill": code, "label": skill.label, "body": skill.prompt_loader()})
    payload: dict = {"skills": loaded}
    if not_found:
        payload["not_found"] = sorted(not_found)
    if not loaded and not not_found:
        payload["note"] = (
            "No skill requested — pass `skill` or `skills` (a code from the Available skills list)."
        )
    return payload


def skill_metadata_block(
    *, editor: bool, book_scoped: bool, admin: bool, studio: bool = False, lazy: bool = False
) -> str | None:
    """L1 metadata tier (RAID C3): a compact list of the skills AVAILABLE on this
    surface (label + one-line description), so the model knows they exist and can pin
    or request one — at ~tens of tokens, versus loading every full L2 body. Returns
    None when no skill is visible on the surface.

    ``lazy`` (F7c) — when the surface auto-defaults are NOT force-injected as full L2
    bodies, this index is the model's only signal a skill exists, so the closing line
    tells it to `load_skill('<code>')` the body on demand (the twin of tool_load)."""
    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin, studio=studio)
    lines = [
        f"- **{s.label}** (`{s.code}`): {s.description}"
        for s in SYSTEM_SKILLS.values()
        # glossary_shaping (N5a) is an INTERNAL companion of `glossary`, auto-added when the
        # user does glossary work — not a separately-pinnable capability, so keep it out of the
        # L1 "available skills" list too (consistent with catalog_items).
        if s.description and _skill_visible(s, active) and s.code != "glossary_shaping"
    ]
    if not lines:
        return None
    guidance = (
        "These skills are available on this surface. When the user's request fits one, "
        "call `load_skill('<code>')` to load its full instructions, then follow them. "
        "Their tools are already reachable (via tool_list/tool_load, or already hot); load a skill for its workflow."
        if lazy
        else "These skills are available on this surface. The relevant one is loaded in full; "
        "if the user's request fits another, say so or pin it."
    )
    return "## Available skills\n" + guidance + "\n" + "\n".join(lines)


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
    binding_skills: list[str] | None = None,
    lazy_bodies: bool = False,
) -> list[str]:
    """Return skill codes to inject this turn (ordered, deduped).

    ``binding_skills`` (WS-3/C6 ``inject_skills``) is the mode→capability binding's
    contribution. STRICTLY ADDITIVE and surface-filtered, exactly like the router's
    additions: it can only GROW the result, never remove a skill the static path
    selected. Default ``None`` ⇒ byte-identical behavior to before WS-3, which is what
    keeps every existing caller (and the degrade path, when the registry is down)
    unchanged.

    ``lazy_bodies`` (F7c) — when True, the NON-curated SURFACE-DEFAULT auto-inject
    (the ``else`` branch: glossary/knowledge/composition/universal) is suppressed:
    the model knows those skills exist via the L1 index and pulls a body with
    `load_skill` on demand, or the intent router preloads the matching one. Only the
    BLANKET surface defaults go lazy — explicit PINS (``enabled_skills``), the mode
    bindings (plan_forge in plan mode, co_write in write mode), glossary_shaping on a
    glossary pin, and ``binding_skills`` are DELIBERATE selections and still inject
    their full L2. Default False ⇒ byte-identical to the pre-F7c behavior.
    """
    if stream_format != "agui" or disable_tools or not tool_calling_enabled:
        return []

    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin, studio=studio)

    if enabled_skills:
        out = [
            code for code in enabled_skills
            if (skill := SYSTEM_SKILLS.get(code)) and _skill_visible(skill, active)
        ]
    elif lazy_bodies:
        # F7c lazy: skip the blanket surface auto-inject. `admin` is the ONE exception —
        # it is not a lazy-loadable capability (its own CMS surface + catalog), and the
        # admin turn genuinely needs its body, so it is never deferred. Everything else
        # (glossary/knowledge/composition/universal) is reached via the L1 index +
        # load_skill / the intent router.
        out = ["admin"] if admin else []
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
            # F14 (round-4 dogfood, 2026-07-20) — a book is OPEN in the studio, yet `book`
            # was curated-pin-only, so book_* tools (list/get/delete/publish chapters) were
            # NEVER hot-seeded. The agent asked to "manage chapters" saw ZERO book tools and
            # grabbed composition_get_mine_job instead (proven by the advertised-surface
            # monitor). A book workbench must offer its own book tools by default.
            out.append("book")
        elif editor or book_scoped:
            out.append("glossary")
            # F14 — book_* tools are meaningful wherever a book is open (the book skill's own
            # surfaces include editor); seed them on the chapter-editor / book-scoped surface too.
            out.append("book")
        else:
            out.append("universal")
        if not admin:
            out.append("knowledge")

    # RAID Wave B2 (07S §5b) — PLAN mode auto-injects the plan_forge skill on the
    # surfaces that allow it (book/editor), even when not pinned, so the model
    # knows the propose→validate→compile flow. Write/ask modes are unchanged.
    #
    # WS-3 note: the System-tier `plan` binding now expresses this same rule as DATA
    # (mode_bindings: plan → inject_skills[plan_forge]). This hardcode STAYS as the
    # degrade-safe fallback — the binding arrives over HTTP from agent-registry, and a
    # registry outage must not silently strip plan mode of PlanForge. The two agree; the
    # union below is idempotent.
    if permission_mode == "plan" and "plan_forge" not in out:
        pf = SYSTEM_SKILLS.get("plan_forge")
        if pf and _skill_visible(pf, active):
            out.append("plan_forge")

    # close-21-28 — WRITE mode is co-writing, and a co-writing author DOES lay out their
    # story. Auto-inject the LIGHT `co_write` workflow (parallel to plan mode's plan_forge)
    # so the agent MATERIALISES the plan (propose AND compile → linked structure) instead of
    # proposing and stopping. The S06 flagship replay proved the gap: without this the book
    # ends at structure_node=0 — a planning feature that never worked end-to-end. plan_forge
    # (the heavy HIL loop) stays PLAN-mode only; this is the lighter write-mode sibling.
    if permission_mode == "write" and "co_write" not in out:
        cw = SYSTEM_SKILLS.get("co_write")
        if cw and _skill_visible(cw, active):
            out.append("co_write")

    # N5a (dogfood 2026-07-18 F3) — the ontology-SHAPING companion is injected ONLY when the
    # author has explicitly PINNED the glossary skill (real glossary/world work), never on the
    # legacy auto-inject path where its "adopt standards / do not skip it" push made the
    # co-writer rebuild a newcomer's ontology on a plain "write a chapter" turn. The lean
    # `glossary` core (auto-injected) still teaches lookup/edit + points at tool_list/tool_load for
    # setup; the intent router adds glossary_shaping too when a turn's meaning matches world
    # setup (the skill carries a description). Additive + surface-filtered like the rest.
    if "glossary" in enabled_skills and "glossary_shaping" not in out:
        gs = SYSTEM_SKILLS.get("glossary_shaping")
        if gs and _skill_visible(gs, active):
            out.append("glossary_shaping")

    # WS-3 (C6) — the mode→capability binding's skills. Additive + surface-filtered.
    for code in binding_skills or []:
        if code in out:
            continue
        sk = SYSTEM_SKILLS.get(code)
        if sk is None:
            # A stored setting that can never take effect. The registry now rejects an
            # unknown code at the write, so reaching here means the two sides have DRIFTED
            # (a skill renamed/removed in chat-service while a binding still names it) —
            # which is exactly the kind of thing that otherwise stays invisible forever.
            logger.warning(
                "mode binding injects skill %r, which does not exist here — ignored", code,
            )
            continue
        if _skill_visible(sk, active):
            out.append(code)
    return out


async def resolve_skills_to_inject_async(
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
    intent_text: str = "",
    user_id: str = "",
    model_source: str = "",
    model_ref: str = "",
    binding_skills: list[str] | None = None,
    lazy_bodies: bool = False,
) -> list[str]:
    """Async twin of ``resolve_skills_to_inject`` — the Intent→Skill Router
    (Part F / F2, docs/plans/2026-07-07-intent-skill-router.md; docs/specs/
    2026-07-07-skill-authoring-and-mcp-exposure-standard.md §13-14).

    Computes the EXACT same static/structural result first (unchanged, same
    code path, same tests) — then, when ``intent_text`` is non-blank, embeds it
    ONCE and cosine-ranks it (``skill_router.route_additional_skills``) against
    a small process-cached set of skill-description vectors, UNIONING in any
    skill that clears the confidence threshold and is visible on the active
    surface. This is strictly ADDITIVE (§13.2): it can only grow the static
    result, never remove a skill the static path already selected (e.g.
    ``knowledge`` auto-injecting everywhere per Part D) — mirrors the "one
    shared ceiling, add-only" discipline the hot-domain budgeting system already
    enforces elsewhere in this codebase.

    Mirrors the ``find_tools_result`` / ``find_tools_result_async`` pattern
    (tool_discovery.py) B3 already established: the SYNC function stays exactly
    as-is for callers that don't need routing (``surface_hot_domains()``'s own
    internal call with ``enabled_skills=[]`` — a deliberately static/structural
    default derivation, unaffected by any one turn's intent — is the reason the
    sync version must never be removed or changed here); this async twin is what
    the live per-turn call sites (``stream_service.py``) actually await.

    MANDATORY fallback discipline (§14): any embedding-call failure, timeout,
    or router exception falls back to EXACTLY the static result — this
    function can only make skill selection better or identical to
    ``resolve_skills_to_inject``, never worse or blocking. A blank
    ``intent_text`` (the default) short-circuits before any embedding work,
    so an existing caller that doesn't pass it behaves identically to calling
    the sync function.
    """
    base = resolve_skills_to_inject(
        enabled_skills=enabled_skills,
        stream_format=stream_format,
        disable_tools=disable_tools,
        tool_calling_enabled=tool_calling_enabled,
        editor=editor,
        book_scoped=book_scoped,
        admin=admin,
        permission_mode=permission_mode,
        studio=studio,
        binding_skills=binding_skills,
        lazy_bodies=lazy_bodies,
    )
    # Same hard gate the sync function itself applies (stream_format/disable_tools/
    # tool_calling_enabled) — `base` is already [] in that case; short-circuiting
    # here too just avoids the pointless embed-attempt. Deliberately NOT gated on
    # `not base`: a curated session whose pins matched nothing on this surface
    # also yields an empty `base`, and the router should still be allowed to help
    # in exactly that case.
    if stream_format != "agui" or disable_tools or not tool_calling_enabled:
        return base
    if not intent_text or not intent_text.strip():
        return base

    active = _surface_key(editor=editor, book_scoped=book_scoped, admin=admin, studio=studio)
    try:
        from app.services.skill_router import route_additional_skills  # noqa: PLC0415

        additions = await route_additional_skills(
            intent_text=intent_text,
            active_surface=active,
            already_selected=base,
            user_id=user_id,
            model_source=model_source,
            model_ref=model_ref,
        )
    except Exception:  # noqa: BLE001 — mandatory fallback, never raise into the turn
        logger.warning(
            "skill router failed; falling back to static skill selection", exc_info=True,
        )
        return base
    if not additions:
        return base
    return base + [code for code in additions if code not in base]


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
        # admin surface is cms-only; glossary_shaping is an internal companion to `glossary`
        # (N5a) — neither is a separately-browsable capability, so omit from the rack browser.
        if s.code not in ("admin", "glossary_shaping")
    ]
