"""Tests for tool_surface (story 04)."""
from __future__ import annotations

from app.services.tool_surface import (
    assemble_initial_active_names,
    effective_enabled_tools,
    is_curated,
    merge_activated_tools,
)


def _tool(name: str) -> dict:
    return {"type": "function", "function": {"name": name, "description": name}}


def _tool_padded(i: int) -> dict:
    return {"type": "function", "function": {"name": f"t{i}", "description": "x" * 200}}


class TestToolSurface:
    def test_is_curated(self):
        assert not is_curated([])
        assert is_curated(["book_get_chapter"])

    def test_is_curated_skill_only_pin(self):
        """2026-07-07 (Part E live-eval root cause) — a skill-only pin (the REAL
        frontend's `useContextRack.ts` pin-skill path, which never sets
        `enabled_tools`) must also enter curated mode, or the skill's own
        hot_domains never get seeded (the skill's PROMPT still tells the model
        to call its tools directly — a live-observed "falsely claims a
        documented tool doesn't exist" failure class)."""
        assert not is_curated([], [])
        assert is_curated([], ["translation"])
        assert is_curated(["book_get_chapter"], [])

    def test_assemble_auto_mode_uses_hot_seed(self):
        hot = {"glossary_search", "glossary_list"}
        out = assemble_initial_active_names(
            curated=False,
            enabled_tools=[],
            activated_tools=[],
            hot_seed_names=hot,
        )
        assert out == hot

    def test_assemble_auto_mode_readvertises_only_current_workflow_tools(self):
        # A multi-turn workflow's step tools persist in activated_tools; assemble MUST
        # re-advertise them in auto mode (the S03 cross-turn drop) — BUT ONLY those that
        # belong to a currently-visible workflow. A stale find_tools accumulation left in
        # activated_tools by a prior curated phase MUST be dropped (review-impl leak fix).
        hot = {"glossary_search", "glossary_list"}
        out = assemble_initial_active_names(
            curated=False,
            enabled_tools=[],
            activated_tools=[
                "glossary_propose_status_change",  # current workflow step tool
                "glossary_propose_merge",          # current workflow step tool
                "translation_start_job",           # STALE find_tools accumulation
                "kg_build_graph",                  # STALE find_tools accumulation
            ],
            hot_seed_names=hot,
            workflow_step_tools={"glossary_propose_status_change", "glossary_propose_merge"},
        )
        assert out == hot | {"glossary_propose_status_change", "glossary_propose_merge"}
        assert "translation_start_job" not in out
        assert "kg_build_graph" not in out

    def test_assemble_auto_mode_no_workflow_filter_stays_hot_seed_only(self):
        # No workflow_step_tools supplied → strict original auto behavior: hot-seed only,
        # activated_tools (whatever they are) NEVER leak. Defends the resume path, which
        # does not pass the filter.
        hot = {"glossary_search"}
        out = assemble_initial_active_names(
            curated=False,
            enabled_tools=[],
            activated_tools=["translation_start_job", "kg_build_graph"],
            hot_seed_names=hot,
        )
        assert out == hot

    def test_assemble_curated_uses_pins_and_activated(self):
        out = assemble_initial_active_names(
            curated=True,
            enabled_tools=["book_get_chapter"],
            activated_tools=["translation_start"],
            hot_seed_names={"glossary_search"},
        )
        assert out == {"book_get_chapter", "translation_start"}

    def test_glossary_skill_unions_hot_glossary_tools(self):
        catalog = [_tool("glossary_search"), _tool("book_get_chapter")]
        pins = effective_enabled_tools(
            ["book_get_chapter"],
            glossary_skill=True,
            catalog=catalog,
            hot_domains={"glossary"},
        )
        assert "glossary_search" in pins
        assert "book_get_chapter" in pins

    def test_merge_activated_tools_caps(self):
        from app.services.tool_surface import ACTIVATED_TOOLS_CAP
        base = [f"t{i}" for i in range(ACTIVATED_TOOLS_CAP)]
        merged = merge_activated_tools(base, {"new_tool"})
        assert len(merged) == ACTIVATED_TOOLS_CAP
        assert merged[-1] == "new_tool"

    def test_merge_activated_tools_scales_budget_with_context_length(self):
        # A 1M-context session must NOT get the same token-budget cap a 200K
        # session would — the exact bug class a flat/unscaled budget reintroduces.
        catalog = [_tool_padded(i) for i in range(200)]
        current = [f"t{i}" for i in range(200)]
        flat = merge_activated_tools(current, set(), catalog=catalog)
        scaled = merge_activated_tools(current, set(), catalog=catalog, context_length=1_000_000)
        assert len(scaled) > len(flat)

    def test_discovery_seed_curated_ignores_hot_tail(self):
        from app.services.tool_surface import (
            SessionToolPins,
            discovery_seed_for_surface,
        )
        catalog = [
            _tool("book_get_chapter"),
            _tool("glossary_search"),
            _tool("translation_start_job"),
        ]
        pins = SessionToolPins(
            effective_enabled=["book_get_chapter"],
            effective_skills=[],
            curated_mode=True,
            activation_state={"activated_tools": [], "dirty": False},
        )
        seed = discovery_seed_for_surface(
            catalog, pins=pins, editor=False, book_scoped=False,
        )
        assert seed == {"book_get_chapter"}

    def test_pinned_legacy_rides_every_mode(self):
        """CAT-4 Part D — a manually-pinned legacy tool is unioned into the
        advertised set in BOTH curated and auto mode; it's a per-session
        override, not part of the discovery heuristic."""
        from app.services.tool_surface import SessionToolPins, discovery_seed_for_surface

        catalog = [_tool("book_get_chapter")]

        auto_pins = SessionToolPins(
            effective_enabled=[], effective_skills=[], curated_mode=False,
            activation_state={"activated_tools": [], "dirty": False},
            pinned_legacy=["glossary_book_create"],
        )
        auto_seed = discovery_seed_for_surface(catalog, pins=auto_pins, editor=False, book_scoped=False)
        assert "glossary_book_create" in auto_seed

        curated_pins = SessionToolPins(
            effective_enabled=["book_get_chapter"], effective_skills=[], curated_mode=True,
            activation_state={"activated_tools": [], "dirty": False},
            pinned_legacy=["glossary_book_create"],
        )
        curated_seed = discovery_seed_for_surface(catalog, pins=curated_pins, editor=False, book_scoped=False)
        assert "glossary_book_create" in curated_seed

    def test_resolve_session_tool_pins_reads_pinned_legacy_from_row(self):
        pins = resolve_session_tool_pins({"pinned_legacy_tools": ["glossary_user_delete"]})
        assert pins.pinned_legacy == ["glossary_user_delete"]
        # A row with no column at all (pre-migration / test fixture gap)
        # degrades to an empty list, never a KeyError/AttributeError.
        assert resolve_session_tool_pins({}).pinned_legacy == []


# ── context-explosion fix: token-budgeted hot-seed + activation cap ───────────

from app.services.tool_surface import (  # noqa: E402
    HOT_SEED_TOKEN_BUDGET,
    budget_names_by_tokens,
    discovery_seed_for_surface,
    resolve_session_tool_pins,
)


def _tool_big(name: str, desc_len: int) -> dict:
    return {"type": "function",
            "function": {"name": name, "description": "x" * desc_len,
                         "parameters": {"type": "object", "properties": {}}}}


class TestTokenBudgetedSeed:
    def test_huge_budget_keeps_all(self):
        cat = [_tool_big(f"glossary_w{i}", 200) for i in range(10)]
        names = {t["function"]["name"] for t in cat}
        out = budget_names_by_tokens(cat, names, token_budget=1_000_000)
        assert out == names

    def test_tiny_budget_trims_but_keeps_at_least_one(self):
        cat = [_tool_big(f"glossary_w{i}", 4000) for i in range(10)]  # ~1K tok each
        names = {t["function"]["name"] for t in cat}
        out = budget_names_by_tokens(cat, names, token_budget=2500)
        assert 0 < len(out) < len(names)

    def test_read_tools_prioritized_over_writes(self):
        # equal-size read + write tools; a budget that fits only some → reads win
        cat = ([_tool_big(f"glossary_search_{i}", 3000) for i in range(3)]
               + [_tool_big(f"glossary_propose_{i}", 3000) for i in range(3)])
        names = {t["function"]["name"] for t in cat}
        out = budget_names_by_tokens(cat, names, token_budget=2200)  # ~ fits ~3
        # every kept catalog tool should be a read tool (writes deprioritized)
        assert out and all("search" in n for n in out)

    def test_non_catalog_names_pass_through_free(self):
        cat = [_tool_big("glossary_search", 200)]
        out = budget_names_by_tokens(cat, {"glossary_search", "find_tools", "ui_navigate"},
                                     token_budget=1_000_000)
        assert {"find_tools", "ui_navigate"} <= out

    def test_allowlisted_write_stays_hot_despite_read_pressure(self):
        # WS-1b — many big reads would fill the budget; the allowlisted canon-write
        # (glossary_propose_entities) must still survive the read-first trim.
        cat = ([_tool_big(f"glossary_search_{i}", 4000) for i in range(6)]  # ~1K tok each
               + [_tool_big("glossary_propose_entities", 400)])            # small, allowlisted
        names = {t["function"]["name"] for t in cat}
        out = budget_names_by_tokens(cat, names, token_budget=2000)
        assert "glossary_propose_entities" in out

    def test_book_update_details_survives_read_pressure_with_large_schema(self):
        # REGRESSION (dogfood 2026-07-21, D-BOOK-UPDATE-DETAILS-STARVED): book_update_details
        # is a Tier-W write with a LARGE 5-field schema. The read-first + ascending-size trim
        # starved it OUT of the advertised set entirely, so every model (weak local Gemma AND
        # gpt-4o-mini) mis-routed "update the description" to book_chapter_create — the tool it
        # could actually see. It was never advertised despite being federated. This is a HARDER
        # case than the small glossary write above: a big schema is the FIRST thing the size
        # ordering drops. Lock it so the tool stays hot regardless of schema size.
        cat = ([_tool_big(f"book_get_{i}", 4000) for i in range(6)]      # ~1K tok each read
               + [_tool_big("book_chapter_save_draft", 3000)]           # allowlisted sibling
               + [_tool_big("book_update_details", 6000)])              # LARGE write, allowlisted
        names = {t["function"]["name"] for t in cat}
        out = budget_names_by_tokens(cat, names, token_budget=2000)
        assert "book_update_details" in out, (
            "book_update_details must stay advertised despite its large schema — this is the "
            "starvation bug that made every model mis-route 'update the description'"
        )
        assert "book_chapter_save_draft" in out  # the sibling draft-capture write, same guarantee

    def test_book_update_details_is_in_the_allowlist(self):
        # The literal fix: membership in ALWAYS_HOT_WRITES. Guards a future edit that drops it.
        from app.services.tool_surface import ALWAYS_HOT_WRITES
        assert "book_update_details" in ALWAYS_HOT_WRITES

    def test_recall_and_timeline_classified_as_reads(self):
        from app.services.tool_surface import _is_read_tool
        assert _is_read_tool("memory_recall_entity")
        assert _is_read_tool("memory_timeline")
        assert not _is_read_tool("glossary_propose_entities")

    def test_sticky_domain_reseeds_book_when_not_book_scoped(self):
        # D-DOMAIN-HOTSET-NOT-STICKY — a universal chat (book_scoped=False) that
        # engaged the book domain two turns ago must STILL hot-seed book tools, so
        # the model can act on a low-signal follow-up ("Option 3, go with that")
        # instead of wandering / hallucinating. book_update_details is the tool that
        # went missing live.
        cat = [_tool("book_update_details"), _tool("book_get"), _tool("book_list"),
               _tool("glossary_search")]
        pins = resolve_session_tool_pins({"enabled_tools": [], "activated_tools": []})
        # WITHOUT stickiness: universal chat has no book domain → book tools absent
        cold = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=False)
        assert "book_update_details" not in cold
        # WITH stickiness (book engaged recently): book tools are re-seeded
        warm = discovery_seed_for_surface(
            cat, pins=pins, editor=False, book_scoped=False, sticky_domains={"book"},
        )
        assert "book_update_details" in warm
        assert "book_get" in warm

    def test_sticky_domain_rides_the_same_token_budget(self):
        # Stickiness unions into hot_domains BEFORE the single budget — it must not
        # blow the ceiling even if the sticky domain is huge (same additive-per-domain
        # discipline as binding_categories; no second independently-budgeted call).
        cat = [_tool_big(f"book_t{i}", 4000) for i in range(60)]
        pins = resolve_session_tool_pins({"enabled_tools": [], "activated_tools": []})
        seed = discovery_seed_for_surface(
            cat, pins=pins, editor=False, book_scoped=False, sticky_domains={"book"},
        )
        assert 0 < len(seed) < 20  # bounded, not the whole 60-tool domain

    def test_book_scoped_seed_is_bounded(self):
        # 60 glossary tools, each ~1K tokens = 60K → must be bounded to the budget.
        cat = [_tool_big(f"glossary_t{i}", 4000) for i in range(60)]
        pins = resolve_session_tool_pins({"enabled_tools": [], "activated_tools": []})
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=True)
        seed_tokens = sum(
            len(str(t["function"])) for t in cat if t["function"]["name"] in seed
        )
        # far smaller than the whole domain; count is a small hot core, not 60
        assert len(seed) < 20
        # and the token budget is respected (chars ≈ 4× tokens, generous ceiling)
        assert seed_tokens <= HOT_SEED_TOKEN_BUDGET * 6

    def test_studio_seed_stays_bounded_with_knowledge_added(self):
        """Part D (2026-07-07) — surface_hot_domains now derives "knowledge" as a
        4th hot domain on studio (glossary+composition+story+knowledge, was 3
        before). This is the SAME shared `budget_names_by_tokens` call as always
        (no new call site, no new ceiling) — proves it gracefully truncates a
        wider candidate set rather than growing the cap itself."""
        cat = (
            [_tool_big(f"glossary_t{i}", 4000) for i in range(20)]
            + [_tool_big(f"composition_t{i}", 4000) for i in range(20)]
            + [_tool_big(f"kg_t{i}", 4000) for i in range(20)]
            + [_tool_big(f"memory_t{i}", 4000) for i in range(20)]
        )
        pins = resolve_session_tool_pins({"enabled_tools": [], "activated_tools": []})
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=False, studio=True)
        seed_tokens = sum(
            len(str(t["function"])) for t in cat if t["function"]["name"] in seed
        )
        assert seed_tokens <= HOT_SEED_TOKEN_BUDGET * 6


class TestCuratedSkillHotDomainUnion:
    """docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-standard.md Part B — a
    curated session that pins a skill whose domain isn't otherwise hot (translation,
    composition on a non-studio surface) must still get that domain's tools seeded,
    generalizing the plan-mode carve-out beyond just "plan"."""

    def test_curated_pin_of_translation_skill_seeds_translation_domain(self):
        cat = [_tool_big(f"translation_t{i}", 200) for i in range(5)] + [
            _tool_big("glossary_search", 200)
        ]
        pins = resolve_session_tool_pins({
            "enabled_tools": ["glossary_search"],
            "enabled_skills": ["translation"],
            "activated_tools": [],
        })
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=True)
        names = {t["function"]["name"] for t in cat}
        translation_names = {n for n in names if n.startswith("translation_")}
        assert translation_names <= seed
        assert "glossary_search" in seed  # the explicit pin still rides along

    def test_skill_only_pin_with_NO_enabled_tools_still_seeds_the_domain(self):
        """THE real-world case (2026-07-07 live-eval root cause): the actual
        frontend pin-skill UI (`useContextRack.ts`) sends `enabled_skills` alone
        — `enabled_tools` is always `[]`. Every OTHER test in this class
        co-pins a dummy `enabled_tools` entry, which accidentally exercised
        curated_mode through that param and masked this exact path — this is
        the one that must never regress. Covers book/settings/jobs (all
        curated-pin-only) via translation as the representative case; the
        mechanism is domain-agnostic (SYSTEM_SKILLS-driven), not per-skill."""
        cat = [_tool_big(f"translation_t{i}", 200) for i in range(5)]
        pins = resolve_session_tool_pins({
            "enabled_tools": [],
            "enabled_skills": ["translation"],
            "activated_tools": [],
        })
        assert pins.curated_mode  # the actual bug: this used to be False here
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=True)
        names = {t["function"]["name"] for t in cat}
        assert names <= seed

    def test_pinned_skill_invisible_on_current_surface_does_NOT_hot_seed(self):
        """review-impl finding (2026-07-08, MED) — a stale/cross-surface pin
        must not hot-seed a skill's tools with no matching prompt to guide
        them. `book_skill.surfaces = {book, editor, studio}` — NOT `chat`. A
        session that pinned "book" earlier (e.g. on a book page) but is now on
        the plain chat surface must not silently advertise all 21 book_* tool
        schemas with zero explanation of how/why to use them."""
        cat = [_tool_big(f"book_t{i}", 200) for i in range(5)]
        pins = resolve_session_tool_pins({
            "enabled_tools": [],
            "enabled_skills": ["book"],
            "activated_tools": [],
        })
        assert pins.curated_mode
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=False, studio=False)
        names = {t["function"]["name"] for t in cat}
        assert not (names & seed)

    def test_skill_only_pin_of_glossary_also_seeds_via_the_glossary_gate(self):
        """The glossary-specific gate (`effective_enabled_tools`) had the SAME
        `or not enabled_tools` short-circuit bug — a pure glossary-only curated
        pin (no enabled_tools) must still hot-seed glossary, not just the
        generic per-skill union path exercised above."""
        cat = [_tool_big(f"glossary_t{i}", 200) for i in range(5)]
        pins = resolve_session_tool_pins({
            "enabled_tools": [],
            "enabled_skills": ["glossary"],
            "activated_tools": [],
        })
        assert pins.curated_mode
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=True)
        names = {t["function"]["name"] for t in cat}
        assert names <= seed

    def test_curated_pin_of_composition_skill_on_non_studio_surface_seeds_it(self):
        """Composition is already hot on studio via _STUDIO_HOT_DOMAINS — this proves
        the union ALSO works on a plain book-scoped surface (studio=False) where
        composition is NOT otherwise hot, via an explicit curated pin."""
        cat = [_tool_big(f"composition_t{i}", 200) for i in range(5)]
        pins = resolve_session_tool_pins({
            "enabled_tools": ["composition_t0"],
            "enabled_skills": ["composition"],
            "activated_tools": [],
        })
        seed = discovery_seed_for_surface(
            cat, pins=pins, editor=False, book_scoped=True, studio=False,
        )
        names = {t["function"]["name"] for t in cat}
        assert names <= seed

    def test_two_pinned_skills_share_ONE_budget_not_two(self):
        """review-impl fix — pinning composition AND translation together must NOT
        seed ~2x HOT_SEED_TOKEN_BUDGET (one full ceiling per skill); both domains'
        candidate tools compete for ONE shared ceiling, same as the auto-mode path
        already shares one budget across a whole surface's hot_domains set."""
        # Each tool ~1K tokens (200 chars name+desc * ~4 chars/tok ≈ 200 raw, padded
        # big below); 10 composition + 10 translation tools far exceeds one budget.
        cat = (
            [_tool_big(f"composition_t{i}", 4000) for i in range(10)]
            + [_tool_big(f"translation_t{i}", 4000) for i in range(10)]
        )
        pins = resolve_session_tool_pins({
            "enabled_tools": ["composition_t0"],
            "enabled_skills": ["composition", "translation"],
            "activated_tools": [],
        })
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=True)
        seed_tokens = sum(
            len(str(t["function"])) for t in cat if t["function"]["name"] in seed
        )
        # Bounded to roughly ONE budget's worth (generous chars-per-token ceiling),
        # not two full budgets' worth of tools from two separately-budgeted calls.
        assert seed_tokens <= HOT_SEED_TOKEN_BUDGET * 6

    def test_no_double_budget_when_skill_domain_already_covered(self):
        """A curated session with empty effective_skills (default) already unions
        glossary+story via the existing gate — pinning "glossary" explicitly too must
        not trigger a SECOND, independently-budgeted call for the same domain (the
        exact review-impl HIGH bug class from 2026-07-07, generalized-loop edition)."""
        cat = [_tool_big(f"glossary_t{i}", 200) for i in range(5)]
        pins = resolve_session_tool_pins({
            "enabled_tools": ["glossary_t0"],
            "enabled_skills": ["glossary"],
            "activated_tools": [],
        })
        seed_with_pin = discovery_seed_for_surface(
            cat, pins=pins, editor=False, book_scoped=True,
        )
        pins_no_skill = resolve_session_tool_pins({
            "enabled_tools": ["glossary_t0"],
            "enabled_skills": [],
            "activated_tools": [],
        })
        seed_without_pin = discovery_seed_for_surface(
            cat, pins=pins_no_skill, editor=False, book_scoped=True,
        )
        # Same result whether "glossary" is explicitly pinned or left to the default
        # empty-skills gate — the generic loop found nothing NEW to add (already covered).
        assert seed_with_pin == seed_without_pin

    def test_curated_pin_of_phase2_skills_seeds_book_settings_jobs_domains(self):
        """Part B Phase 2 (2026-07-07) — book/settings/jobs are ALL curated-pin-only
        (never auto-injected, none in _BOOK_SCOPED_HOT_DOMAINS/_STUDIO_HOT_DOMAINS) —
        proves the same generic union that already covers translation/composition also
        covers these three, with no per-skill wiring needed."""
        cat = (
            [_tool_big(f"book_t{i}", 200) for i in range(3)]
            + [_tool_big(f"settings_t{i}", 200) for i in range(3)]
            + [_tool_big(f"jobs_t{i}", 200) for i in range(3)]
        )
        pins = resolve_session_tool_pins({
            "enabled_tools": ["book_t0"],
            "enabled_skills": ["book", "settings", "jobs"],
            "activated_tools": [],
        })
        seed = discovery_seed_for_surface(cat, pins=pins, editor=False, book_scoped=True)
        names = {t["function"]["name"] for t in cat}
        assert names <= seed


class TestActivatedTokenCap:
    def test_catalog_caps_by_tokens_not_count(self):
        from app.services.tool_surface import merge_activated_tools
        cat = [_tool_big(f"t{i}", 4000) for i in range(80)]  # ~1K tok each
        names = [t["function"]["name"] for t in cat]
        merged = merge_activated_tools([], set(names), catalog=cat)
        # token budget (6K) ⇒ far fewer than the count cap of 64
        assert 0 < len(merged) < 20

    def test_no_catalog_falls_back_to_count_cap(self):
        from app.services.tool_surface import merge_activated_tools, ACTIVATED_TOOLS_CAP
        names = {f"t{i}" for i in range(100)}
        merged = merge_activated_tools([], names)  # no catalog → legacy count cap
        assert len(merged) == ACTIVATED_TOOLS_CAP
