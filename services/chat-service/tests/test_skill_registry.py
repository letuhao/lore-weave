"""Tests for skill_registry (story 04)."""
from __future__ import annotations

import re
from unittest.mock import AsyncMock, patch

import pytest

from app.services import tool_discovery as td
from app.services.skill_registry import (
    SYSTEM_SKILLS,
    catalog_items,
    resolve_skills_to_inject,
    resolve_skills_to_inject_async,
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
        # + co_write: the write-mode workflow auto-injects on book/editor surfaces (close-21-28)
        assert codes == ["glossary", "knowledge", "co_write"]

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
        # close-21-28: co_write auto-injects on every WRITE-mode book/editor surface
        # (the write-mode workflow sibling of plan mode's plan_forge). Curation adds to it.
        assert codes == ["glossary", "co_write"]

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
        assert codes == ["composition", "co_write"]  # + the write-mode workflow (close-21-28)

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
        assert codes == ["plan_forge", "co_write"]  # write mode adds co_write (close-21-28)

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


class TestF0OrphanedWebResearchCoverage:
    """F0 (docs/plans/2026-07-07-intent-skill-router.md) — before this fix, the
    universal/chat surface (no book open) had NO skill teaching that general web
    research is possible at all: `glossary_web_search`/`glossary_deep_research`
    lived only inside `glossary_skill`, whose `surfaces` excludes `chat`. Traced
    root cause of 4 real failed production sessions (docs/specs/2026-07-07-mcp-
    discovery-and-reliability-hardening.md §1). This is the permanent regression
    coverage for the fix: universal_skill now names the tools directly."""

    def test_universal_l1_metadata_mentions_web_research_on_chat_surface(self):
        # The chat surface (no editor/book/admin/studio) is exactly the universal
        # surface the 4 failed sessions hit — confirm the L1 (cheap, always-injected)
        # tier now surfaces web-research guidance there, not just the L2 body.
        block = skill_metadata_block(editor=False, book_scoped=False, admin=False)
        assert block is not None
        assert "`universal`" in block
        assert "web research" in block.lower()

    def test_universal_prompt_names_web_search_tool_with_call_shape(self):
        prompt = skill_prompts(["universal"])["universal"]
        # Track D CD5 — the universal tool, not the glossary-prefixed one.
        assert "web_search" in prompt
        # The exact call shape (verified against services/provider-registry-service/
        # internal/api/mcp_web_search_tool.go): a `query` string, optional `max_results`
        # (1-10, default 5), no book/entity required.
        assert "`query`" in prompt
        assert "max_results" in prompt

    def test_universal_prompt_does_not_name_the_superseded_glossary_alias(self):
        # `glossary_web_search` is `visibility: legacy` + `superseded_by: web_search`.
        # The model must never be pointed at it — not even to explain it's deprecated
        # (that only teaches it a name it should never emit).
        prompt = skill_prompts(["universal"])["universal"]
        assert "glossary_web_search" not in prompt

    def test_universal_prompt_says_web_search_needs_no_discovery_roundtrip(self):
        # web_search is ALWAYS-ON CORE. If the prompt still told the model to tool_load it
        # from a category, every research turn would burn a needless discovery round-trip
        # (and `research` isn't even the category it used to name).
        prompt = skill_prompts(["universal"])["universal"]
        assert 'tool_load` `glossary_web_search' not in prompt
        assert 'tool_list(category="glossary")' not in prompt

    def test_universal_prompt_distinguishes_deep_research_as_book_scoped(self):
        # glossary_deep_research needs book_id + entity_id + human confirm — it is
        # NOT reachable from the bookless universal surface. The prompt must say so,
        # not imply it is directly callable here (that would be a fresh instance of
        # the exact claims-drift bug this spec's lint exists to catch).
        prompt = skill_prompts(["universal"])["universal"]
        assert "glossary_deep_research" in prompt
        assert "book_id" in prompt and "entity_id" in prompt

    def test_universal_hot_domains_stay_empty_no_47_tool_domain_hot_seed(self):
        # Real constraint (investigated 2026-07-08): hot_tool_names()/
        # surface_hot_domains() (app/services/tool_discovery.py) only support
        # DOMAIN-level hot-seeding, not a per-tool hot-seed — there is no mechanism
        # to hot-seed just glossary_web_search/glossary_deep_research without pulling
        # in glossary-service's entire ~47-tool "glossary" domain on every chat
        # surface turn. The fix deliberately does NOT add "glossary" to universal's
        # hot_domains (that would blow the token budget); it relies on the SAME
        # find_tools-mediated reachability the universal skill already uses for every
        # other domain it doesn't pre-seed.
        assert SYSTEM_SKILLS["universal"].hot_domains == frozenset()


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
# book_tools.go/user_tools.go/mcp_server.go/web_search_tool.go); hand-synced here since
# chat-service has no offline access to the live catalog's `_meta.visibility` (§8b.2,
# deferred).
_KNOWN_LEGACY_TOOL_NAMES: frozenset[str] = frozenset({
    "glossary_book_create", "glossary_book_patch", "glossary_book_delete",
    "glossary_user_create", "glossary_user_patch", "glossary_user_delete",
    "glossary_propose_new_entity",
    # Track D CD5 — superseded by the universal `web_search` (provider-registry). Demoted
    # in place, not renamed: the C-GW prefix gate binds a name to its provider.
    "glossary_web_search",
})

# Skills exempt from the domain-hot-seed check entirely: `admin` advertises its OWN
# small, always-fully-exposed System-tier catalog on the separate `/mcp/admin` server
# (INV-T6) — a completely different tool space than GROUP_DIRECTORY describes, so
# "which GROUP_DIRECTORY domain must be hot" doesn't apply to it at all.
_EXEMPT_SKILL_CODES: frozenset[str] = frozenset({"admin", "co_write"})  # co_write keeps its tools LAZY (find_tools-reachable), not hot — close-21-28

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
    # universal_skill.py names `glossary_deep_research` as a CONTRAST to `web_search`
    # ("don't confuse the two — deep_research needs a book_id AND entity_id and a human
    # confirm"). That is a boundary warning, not a "call this now" claim, so it needs no
    # hot-seed: the "glossary" domain is ~47 tools and seeding it wholesale to cover one
    # contrastive mention would blow the chat surface's token budget (hot_tool_names()/
    # surface_hot_domains() are domain-level only, not per-tool — see skill_registry.py's
    # "universal" hot_domains comment).
    #
    # Track D CD5: `web_search` itself is NOT listed here — it is ALWAYS-ON CORE, so
    # `_named_tool_domains` exempts it outright. And `glossary_web_search` is gone from
    # the prompt entirely: it is now `visibility: legacy`, and a skill must never point
    # the model at a superseded name (test_no_skill_references_a_legacy_tool).
    "universal": frozenset({
        "book_chapter_save_draft", "book_chapter_publish",
        "glossary_deep_research",
    }),
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
        # An ALWAYS-ON CORE tool is advertised on every surface, every turn, so naming it
        # can never be an unreachable claim — the thing this lint exists to catch. Exempt
        # it regardless of hot_domains. (Before Track D CD5 the core tools escaped only by
        # accident: `tool_list`/`tool_load`/`find_tools` have prefixes that aren't
        # GROUP_DIRECTORY domains. `web_search` resolves to the real `research` domain, so
        # the accident stopped covering the set and the exemption had to become explicit.)
        if token in td.ALWAYS_ON_CORE_NAMES:
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


# ════════════════════════════════════════════════════════════════════════════
# Part F / F2 — Intent→Skill Router wiring (docs/plans/2026-07-07-intent-skill-
# router.md). `resolve_skills_to_inject_async` layers the embedding-similarity
# router (app/services/skill_router.py, unit-tested directly in
# test_skill_router.py) on top of the exact same static/structural result
# `resolve_skills_to_inject` already returns. These tests cover the WIRING —
# additive-union, never-remove, mandatory fallback, and the same hard gate the
# sync function applies — by mocking `route_additional_skills` rather than a
# real embedding client (see test_skill_router.py for the router's own
# embedding-level behaviour).
# ════════════════════════════════════════════════════════════════════════════


class TestResolveSkillsToInjectAsyncRouter:
    def setup_method(self, _method):
        from app.services import skill_router
        skill_router.reset_skill_vector_cache()

    @pytest.mark.asyncio
    async def test_blank_intent_returns_static_result_without_calling_router(self):
        with patch("app.services.skill_router.route_additional_skills", new=AsyncMock()) as mock_route:
            codes = await resolve_skills_to_inject_async(
                enabled_skills=[],
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=False,
                admin=False,
                intent_text="",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert codes == resolve_skills_to_inject(
            enabled_skills=[], stream_format="agui", disable_tools=False,
            tool_calling_enabled=True, editor=False, book_scoped=False, admin=False,
        )
        mock_route.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_disable_tools_bypasses_router_entirely(self):
        """Same hard gate the sync function applies (stream_format/disable_tools/
        tool_calling_enabled) — the router must never fire when the turn has no
        tool-calling in play at all."""
        with patch("app.services.skill_router.route_additional_skills", new=AsyncMock()) as mock_route:
            codes = await resolve_skills_to_inject_async(
                enabled_skills=["glossary"],
                stream_format="agui",
                disable_tools=True,
                tool_calling_enabled=True,
                editor=True,
                book_scoped=True,
                admin=False,
                intent_text="translate this chapter please",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert codes == []
        mock_route.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_additive_union_adds_router_skill_without_removing_static_defaults(self):
        """The router may ADD a skill the static path wouldn't have picked
        (e.g. `settings` on the plain chat surface), but the static defaults
        (`universal`, `knowledge`) must still be present, unchanged order."""
        with patch(
            "app.services.skill_router.route_additional_skills",
            new=AsyncMock(return_value=["settings"]),
        ):
            codes = await resolve_skills_to_inject_async(
                enabled_skills=[],
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=False,
                admin=False,
                intent_text="please switch my default chat model",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert codes == ["universal", "knowledge", "settings"]

    @pytest.mark.asyncio
    async def test_router_addition_never_duplicates_a_static_default(self):
        with patch(
            "app.services.skill_router.route_additional_skills",
            new=AsyncMock(return_value=["knowledge", "settings"]),
        ):
            codes = await resolve_skills_to_inject_async(
                enabled_skills=[],
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=False,
                admin=False,
                intent_text="what do you know about the villain",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        # "knowledge" is already a static default — must not appear twice.
        assert codes == ["universal", "knowledge", "settings"]
        assert codes.count("knowledge") == 1

    @pytest.mark.asyncio
    async def test_router_exception_falls_back_to_exactly_the_static_result(self):
        """MANDATORY fallback (spec §14): a router-level exception (e.g. a bug
        in route_additional_skills itself, not just an embed failure — that
        case is covered inside skill_router.py's own try/except) must still
        degrade to EXACTLY resolve_skills_to_inject()'s static result."""
        with patch(
            "app.services.skill_router.route_additional_skills",
            new=AsyncMock(side_effect=RuntimeError("boom")),
        ):
            codes = await resolve_skills_to_inject_async(
                enabled_skills=[],
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=True,
                admin=False,
                intent_text="translate this chapter please",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert codes == resolve_skills_to_inject(
            enabled_skills=[], stream_format="agui", disable_tools=False,
            tool_calling_enabled=True, editor=False, book_scoped=True, admin=False,
        )

    @pytest.mark.asyncio
    async def test_embedding_client_outage_end_to_end_falls_back_to_static_result(self):
        """End-to-end (no router-level mock — only the embedding client is
        faked to fail, exactly like a real provider-registry outage) — proves
        the WHOLE chain (skill_registry → skill_router → embedding_client)
        degrades to the static result, not just the router's own unit tests."""
        mock_client = AsyncMock()
        mock_client.embed.side_effect = TimeoutError("provider-registry unreachable")
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            codes = await resolve_skills_to_inject_async(
                enabled_skills=[],
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=False,
                admin=False,
                intent_text="search the web for the latest news",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert codes == ["universal", "knowledge"]

    @pytest.mark.asyncio
    async def test_curated_pins_matching_nothing_on_surface_still_lets_router_help(self):
        """A curated session whose pins are invisible on THIS surface yields an
        empty static `base` — the router must still be allowed to add
        something in exactly that case (not short-circuited by `not base`)."""
        with patch(
            "app.services.skill_router.route_additional_skills",
            new=AsyncMock(return_value=["settings"]),
        ) as mock_route:
            codes = await resolve_skills_to_inject_async(
                enabled_skills=["book"],  # book_skill isn't visible on plain chat
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=False,
                admin=False,
                intent_text="manage my account settings",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        mock_route.assert_awaited_once()
        assert codes == ["settings"]


class TestF2TracedWebResearchBugRemainsFixed:
    """Part F's own root-cause trace (docs/plans/2026-07-07-intent-skill-
    router.md, docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-
    standard.md §12): a general web-research ask on the universal/chat surface
    (no book open) used to have NO skill teaching that capability exists.
    F0 (TestF0OrphanedWebResearchCoverage above) already closed this by
    extending `universal_skill`'s own prompt — `universal` is a STATIC
    default on the chat surface, injected regardless of the router. This is
    the proof that F2 (the router) does not need to add anything extra for
    this specific traced case: the effective result set already carries the
    fix through the static path alone, and the router is correctly a no-op
    here (both because there's nothing more to add, AND because `glossary`
    — where the actual tools live — stays surfaces-filtered OFF the chat
    surface even if it scored high, per test_skill_router.py's surfaces test)."""

    @pytest.mark.asyncio
    async def test_general_web_search_intent_on_chat_surface_still_resolves_via_static_universal(self):
        mock_client = AsyncMock()
        mock_client.embed.side_effect = TimeoutError("provider-registry unreachable")
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            codes = await resolve_skills_to_inject_async(
                enabled_skills=[],
                stream_format="agui",
                disable_tools=False,
                tool_calling_enabled=True,
                editor=False,
                book_scoped=False,
                admin=False,
                intent_text="search the web for current news about the war",
                user_id="u1", model_source="user_model", model_ref="m1",
            )
        assert codes == ["universal", "knowledge"]
        prompt = skill_prompts(codes)["universal"]
        # Track D CD5 — the capability is now taught as the universal `web_search`
        # (always-on core), not the superseded glossary alias.
        assert "web_search" in prompt
        assert "glossary_web_search" not in prompt
        assert "find_tools" in prompt
