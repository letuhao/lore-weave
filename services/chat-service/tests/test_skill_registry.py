"""Tests for skill_registry (story 04)."""
from __future__ import annotations

import re

from app.services import tool_discovery as td
from app.services.skill_registry import (
    SYSTEM_SKILLS,
    catalog_items,
    resolve_skills_to_inject,
    skill_metadata_block,
    skill_prompts,
)


class TestResolveSkillsToInject:
    def test_empty_skills_universal_chat_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
        )
        assert codes == ["universal", "knowledge"]

    def test_empty_skills_book_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
        )
        assert codes == ["glossary", "knowledge"]

    def test_curated_glossary_only(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["glossary"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
        )
        assert codes == ["glossary"]

    def test_disable_tools_returns_empty(self):
        assert resolve_skills_to_inject(
            enabled_skills=["glossary"],
            stream_format="agui",
            disable_tools=True,
            tool_calling_enabled=True,
            editor=True,
            book_scoped=True,
            admin=False,
        ) == []


class TestStudioSurface:
    """2026-07-07 — a PURE studio turn (studio_context set, editor_context/
    book_context absent) used to fall through to the generic "chat" surface,
    invisible to glossary_skill/composition_skill despite their tools being HOT
    there via `_STUDIO_HOT_DOMAINS` (surface_hot_domains, a separate code path that
    already treated studio as independent) — this is the permanent regression test."""

    def test_pure_studio_turn_auto_injects_glossary_and_composition(self):
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
            studio=True,
        )
        assert codes == ["glossary", "composition", "knowledge"]

    def test_studio_plus_editor_still_works(self):
        """studio is ADDITIVE, not exclusive with editor — a studio panel opened
        within an editor session gets both surfaces' visibility."""
        codes = resolve_skills_to_inject(
            enabled_skills=["composition"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=True,
            book_scoped=True,
            admin=False,
            studio=True,
        )
        assert codes == ["composition"]

    def test_composition_pinned_but_not_visible_without_studio_or_editor(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["composition"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
            studio=False,
        )
        assert codes == []

    def test_admin_still_wins_over_studio(self):
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=True,
            studio=True,
        )
        assert codes == ["admin"]

    def test_skill_metadata_block_lists_composition_on_studio(self):
        block = skill_metadata_block(editor=False, book_scoped=False, admin=False, studio=True)
        assert block is not None
        assert "`composition`" in block


class TestSkillCatalog:
    def test_catalog_has_system_skills(self):
        ids = {row["id"] for row in catalog_items()}
        assert "glossary" in ids
        assert "universal" in ids
        assert "admin" not in ids


class TestPlanForgeSkill:
    def test_plan_forge_in_catalog(self):
        ids = {row["id"] for row in catalog_items()}
        assert "plan_forge" in ids

    def test_plan_forge_resolves_when_pinned_on_book_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["plan_forge"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=True,
            admin=False,
        )
        assert codes == ["plan_forge"]

    def test_plan_forge_hidden_on_plain_chat_surface(self):
        # book/editor only — a non-book chat pin must not inject it.
        codes = resolve_skills_to_inject(
            enabled_skills=["plan_forge"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
        )
        assert codes == []

    def test_plan_forge_prompt_loads(self):
        prompts = skill_prompts(["plan_forge"])
        assert "plan_forge" in prompts
        assert "plan_propose_spec" in prompts["plan_forge"]


class TestSkillMetadataL1:
    def test_book_surface_lists_visible_skills(self):
        block = skill_metadata_block(editor=False, book_scoped=True, admin=False)
        assert block is not None
        assert "Available skills" in block
        # book-surface skills present by their code; chat-only + admin absent
        assert "`glossary`" in block and "`knowledge`" in block and "`plan_forge`" in block
        assert "`admin`" not in block

    def test_admin_surface_only_admin(self):
        block = skill_metadata_block(editor=False, book_scoped=False, admin=True)
        assert block is not None and "`admin`" in block
        assert "`glossary`" not in block

    def test_metadata_is_compact(self):
        # L1 is cheap — the whole book-surface catalog is a handful of lines, one per
        # visible skill. Bound grows deliberately as Part B adds skills (5→8 lines at
        # Phase 2: glossary/knowledge/plan_forge/composition/translation/book/settings/
        # jobs); this asserts "still a short list", not an exact count — bump it when a
        # real new skill lands, don't just raise it to silence a failure.
        block = skill_metadata_block(editor=True, book_scoped=True, admin=False)
        assert block.count("\n- ") <= 9


class TestPhase2Skills:
    """docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md Part B
    Phase 2 (2026-07-07) — book/settings/jobs: all curated-pin-only (never in any
    auto-inject branch), registered + catalog-visible, with the surface split that
    matters: book needs a book in context, settings/jobs are account-level and
    reachable from plain chat too."""

    def test_all_three_registered_with_correct_hot_domains(self):
        for code, domain in (("book", "book"), ("settings", "settings"), ("jobs", "jobs")):
            skill = SYSTEM_SKILLS[code]
            assert skill.hot_domains == frozenset({domain})

    def test_all_three_appear_in_catalog(self):
        ids = {item["id"] for item in catalog_items()}
        assert {"book", "settings", "jobs"} <= ids

    def test_book_not_visible_on_plain_chat_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["book"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
        )
        assert codes == []

    def test_settings_and_jobs_visible_on_plain_chat_surface(self):
        codes = resolve_skills_to_inject(
            enabled_skills=["settings", "jobs"],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=False,
            book_scoped=False,
            admin=False,
        )
        assert set(codes) == {"settings", "jobs"}

    def test_none_of_the_three_auto_inject_by_default(self):
        """Curated-pin only — an empty enabled_skills (surface-default) on a
        book-scoped turn must NOT silently include book/settings/jobs."""
        codes = resolve_skills_to_inject(
            enabled_skills=[],
            stream_format="agui",
            disable_tools=False,
            tool_calling_enabled=True,
            editor=True,
            book_scoped=True,
            admin=False,
        )
        assert not {"book", "settings", "jobs"} & set(codes)


# ════════════════════════════════════════════════════════════════════════════
# Skill-authoring contract (docs/specs/2026-07-07-skill-authoring-and-mcp-
# exposure-standard.md Part A) — a skill's prose must not promise a tool the
# seeding layer never actually delivers. `plan_forge_skill` shipped exactly
# this bug (2026-07-07): its prose named `plan_propose_spec` etc. as directly
# callable, but "plan" was never in any hot-domain set. This is the permanent
# regression test for that bug CLASS, not just that one instance.
# ════════════════════════════════════════════════════════════════════════════

# A domain-prefixed token that is a schema FIELD name, not a tool name — the token's
# own prefix happens to collide with a real GROUP_DIRECTORY domain. Extend this set
# when a new false positive is found (cheaper than a live-catalog fixture — §8b.2 of
# the spec explicitly defers building that infrastructure).
_KNOWN_NON_TOOL_TOKENS: frozenset[str] = frozenset({
    "book_id",
    "book_shared",  # composition_motif_create's `target` enum VALUE, not a tool name
})

# CAT-4 legacy-tagged tools (docs/specs/2026-07-06-tool-catalog-simplification.md) — a
# skill must never point the model at a superseded tool. Source of truth is
# glossary-service's Go registrations (`WithVisibility(..., VisibilityLegacy)` in
# book_tools.go/user_tools.go/mcp_server.go); hand-synced here since chat-service has
# no offline access to the live catalog's `_meta.visibility` (§8b.2, deferred).
_KNOWN_LEGACY_TOOL_NAMES: frozenset[str] = frozenset({
    "glossary_book_create", "glossary_book_patch", "glossary_book_delete",
    "glossary_user_create", "glossary_user_patch", "glossary_user_delete",
    "glossary_propose_new_entity",
})

# Skills exempt from the domain-hot-seed check entirely: `admin` advertises its OWN
# small, always-fully-exposed System-tier catalog on the separate `/mcp/admin` server
# (INV-T6) — a completely different tool space than GROUP_DIRECTORY describes, so
# "which GROUP_DIRECTORY domain must be hot" doesn't apply to it at all.
_EXEMPT_SKILL_CODES: frozenset[str] = frozenset({"admin"})

# A token named only as a NEGATIVE/contrastive reference ("don't use X for this, use Y")
# — not a claim that X is directly callable, so it's exempt from the hot_domains check.
# Keyed by skill code; reviewed case-by-case, not a general escape hatch.
_ALLOWED_CONTRASTIVE_MENTIONS: dict[str, frozenset[str]] = {
    # glossary_skill.py: "Do not use `memory_search` for glossary questions."
    "glossary": frozenset({"memory_search"}),
    # translation_skill.py: "don't call `jobs_get` on a translation job id" — a
    # cross-system warning, not a claim that jobs_get is available/needed here.
    "translation": frozenset({"jobs_get"}),
    # universal_skill.py + workflow_skill.py (concatenated as one prompt body):
    # workflow_skill's cross-domain ORDERING fragment names book_chapter_save_draft/
    # book_chapter_publish as step 2/4 of a multi-step sequence description ("do X,
    # then Y, then Z") — informational sequencing, not a "call this right now" claim
    # the way plan_forge's Act-don't-narrate instruction was. The universal surface is
    # pure find_tools discovery by design (its own description: "find and use the
    # right tool"); the tool becomes reachable as the conversation naturally reaches
    # that step, same as any other domain the universal skill doesn't pre-seed.
    "universal": frozenset({"book_chapter_save_draft", "book_chapter_publish"}),
    # book_skill.py: "(e.g. after `story_search` locates it — this tool lives in the
    # `book` GROUP_DIRECTORY entry ... look for it there, not under `story`)" — a
    # cross-reference explaining WHERE story_search is catalogued, not a "call this
    # directly" claim. Also moot in practice: "story" is already unconditionally hot on
    # every surface book_skill is visible on (_BOOK_SCOPED_HOT_DOMAINS /
    # _STUDIO_HOT_DOMAINS both include it), independent of book_skill's own hot_domains.
    "book": frozenset({"story_search"}),
    # jobs_skill.py: "the domain's own tool ... e.g. `translation_job_control`" — a
    # cross-domain contrastive mention (this generic system vs. a domain's own job
    # tools), the same shape as translation_skill's "jobs_get" entry above, just from
    # the other side of that same boundary.
    "jobs": frozenset({"translation_job_control", "translation_job_status"}),
}

_TOOL_TOKEN_RE = re.compile(r"\b[a-z]+(?:_[a-z0-9]+)+\b")


def _named_tool_domains(prompt_text: str) -> set[tuple[str, str]]:
    """(token, domain) pairs for every domain-prefixed, non-excluded token found in a
    skill's prompt text — reuses chat-service's own domain-alias resolution
    (`td._domain_of`) so "kg_graph_query"/"memory_search" correctly resolve to the
    "knowledge" domain, not literal "kg"/"memory" (2026-07-07 fix)."""
    out: set[tuple[str, str]] = set()
    for token in _TOOL_TOKEN_RE.findall(prompt_text):
        if token in _KNOWN_NON_TOOL_TOKENS:
            continue
        domain = td._domain_of(token)
        if domain in td.GROUP_DIRECTORY:
            out.add((token, domain))
    return out


class TestSkillClaimsLint:
    def test_every_skills_named_tools_are_in_its_hot_domains(self):
        failures = []
        for skill in SYSTEM_SKILLS.values():
            if skill.code in _EXEMPT_SKILL_CODES:
                continue
            allowed_contrastive = _ALLOWED_CONTRASTIVE_MENTIONS.get(skill.code, frozenset())
            prompt = skill.prompt_loader()
            for token, domain in sorted(_named_tool_domains(prompt)):
                if token in allowed_contrastive:
                    continue
                if domain not in skill.hot_domains:
                    failures.append(
                        f"{skill.code}: names '{token}' (domain '{domain}') but "
                        f"hot_domains={sorted(skill.hot_domains)} — either add "
                        f"'{domain}' to hot_domains, or rephrase the prose to say "
                        f"'search for it with find_tools' instead of naming it directly."
                    )
        assert not failures, "\n" + "\n".join(failures)

    def test_no_skill_references_a_legacy_tool(self):
        failures = []
        for skill in SYSTEM_SKILLS.values():
            if skill.code in _EXEMPT_SKILL_CODES:
                continue
            prompt = skill.prompt_loader()
            for token, _domain in sorted(_named_tool_domains(prompt)):
                if token in _KNOWN_LEGACY_TOOL_NAMES:
                    failures.append(
                        f"{skill.code}: references legacy tool '{token}' — point at "
                        f"its replacement instead (see docs/specs/2026-07-06-tool-"
                        f"catalog-simplification.md)."
                    )
        assert not failures, "\n" + "\n".join(failures)

    def test_lint_extraction_sanity(self):
        """The extractor itself: finds real domain tokens, skips field names, resolves
        the kg_/memory_ alias, and ignores tokens with no matching domain at all."""
        text = (
            "Call `glossary_search` first. Pass `book_id` (not a tool). "
            "Then `kg_graph_query` and finally `not_a_domain_thing`."
        )
        pairs = _named_tool_domains(text)
        assert ("glossary_search", "glossary") in pairs
        assert ("kg_graph_query", "knowledge") in pairs
        assert not any(tok == "book_id" for tok, _ in pairs)
        assert not any(tok == "not_a_domain_thing" for tok, _ in pairs)
