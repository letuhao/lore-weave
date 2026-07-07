"""MCP-fanout S-CONSUMER — find_tools discovery, tier-driven advertising,
H7 cap, H9 budget, C-ACTIVITY, and missing-vs-unavailable phrasing.

Reuses the _FakeClient scripting harness from test_stream_tools. The discovery
path is driven by passing `discovery_catalog`/`discovery_extra_frontend` into
`_stream_with_tools` directly (the same kwargs stream_response wires on the
universal /chat surface)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services import tool_discovery as td
from app.services.frontend_tools import FRONTEND_TOOL_NAMES, frontend_tool_defs
from app.services.stream_service import (
    TIER_A_AGGREGATE_CAP,
    TIER_A_SAME_OP_CAP,
    _stream_with_tools,
)
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_tools import (
    _FakeClient,
    _drain,
    _envelope,
    _patch_client,
    done,
    tok,
    tool_frag,
    usage,
)


# ── catalog builders ─────────────────────────────────────────────────────────


def _tool(name: str, desc: str = "", *, tier: str = "R", synonyms=None, visibility: str | None = None) -> dict:
    meta: dict = {"tier": tier}
    if synonyms:
        meta["synonyms"] = synonyms
    if visibility:
        meta["visibility"] = visibility
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": desc,
            "parameters": {"type": "object", "properties": {}},
            "_meta": meta,
        },
    }


_CATALOG = [
    _tool("book_create", "Create a new book", tier="A", synonyms=["new book"]),
    _tool("book_list", "List the user's books", tier="R"),
    _tool("chapter_create", "Create a draft chapter", tier="A"),
    _tool("chapter_publish", "Publish a chapter to canon", tier="W"),
    _tool("translation_start_job", "Start translating a book", tier="W",
          synonyms=["translate", "translation"]),
    _tool("settings_list_models", "List the user's models", tier="R"),
]


def _run_discovery(
    scripts,
    *,
    knowledge_client,
    catalog=None,
    extra_frontend=None,
    max_iterations: int = 20,
    messages=None,
):
    if catalog is None:
        catalog = _CATALOG
    return _stream_with_tools(
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=messages if messages is not None else [{"role": "user", "content": "hi"}],
        gen_params={},
        tools=[],  # ignored in discovery mode
        knowledge_client=knowledge_client,
        session_id=TEST_SESSION_ID,
        project_id="proj-1",
        max_iterations=max_iterations,
        discovery_catalog=catalog,
        discovery_extra_frontend=extra_frontend
        if extra_frontend is not None
        else frontend_tool_defs(editor=False, book_scoped=False),
    )


def _kc(catalog_meta: dict | None = None) -> AsyncMock:
    kc = AsyncMock()
    kc.get_catalog_meta = lambda: (catalog_meta or {})
    return kc


# ════════════════════════════════════════════════════════════════════════════
# search_catalog — pure
# ════════════════════════════════════════════════════════════════════════════


class TestSearchCatalog:
    def test_matches_by_name_and_synonym(self):
        matches, confident = td.search_catalog(_CATALOG, "translate my book", 8)
        names = [m["name"] for m in matches]
        assert "translation_start_job" in names
        assert confident

    def test_archive_synonym_recall_h6(self):
        # E1/H6: "archive" should still surface a delete/trash tool via synonyms.
        cat = [_tool("chapter_delete", "Move a chapter to trash",
                     tier="W", synonyms=["archive", "remove"])]
        matches, confident = td.search_catalog(cat, "archive this chapter", 8)
        assert [m["name"] for m in matches] == ["chapter_delete"]
        assert confident

    def test_empty_result_is_not_confident(self):
        matches, confident = td.search_catalog(_CATALOG, "xyzzy quux frobnicate", 8)
        assert matches == [] or not confident

    def test_exclude_skips_core(self):
        matches, _ = td.search_catalog(
            _CATALOG, "create a book", 8, exclude={"book_create"}
        )
        assert "book_create" not in [m["name"] for m in matches]

    def test_one_incidental_shared_word_does_not_outrank_a_real_overlap(self):
        """review-impl live-verification finding (2026-07-06): the fuzzy-rescue
        branch's own docstring says it rescues a tool with NO token overlap, but
        the code never checked that — an EXACT single-token overlap (ratio=1.0
        for identical strings) always qualified as a "strong fuzzy hit," so ANY
        incidental shared word (however generic) overrode the whole score to
        1.0. Live-verified at the real ~190-tool federated catalog: intent "add
        a new kind to the book" scored translation_start_job a perfect 1.0 via
        its synonym "translate a book" sharing only the word "book," outranking
        glossary_ontology_upsert's genuine 3-token overlap (add/a/kind)."""
        cat = [
            _tool("glossary_ontology_upsert",
                  "Create or update book- or user-tier ontology rows (genre, kind, attribute).",
                  tier="A", synonyms=["add a kind", "add a genre", "add an attribute"]),
            # Shares ONLY the word "book" with the intent below — via a synonym,
            # not its name/description — and is otherwise wholly unrelated.
            _tool("translation_start_job", "Start translating a chapter into another language",
                  tier="W", synonyms=["translate a book"]),
        ]
        matches, confident = td.search_catalog(cat, "add a new kind to the book", 8)
        names = [m["name"] for m in matches]
        assert names[0] == "glossary_ontology_upsert"
        assert confident

    def test_fuzzy_rescue_still_works_for_a_genuine_no_overlap_near_spelling(self):
        """The overlap==0 gate must not break the rescue it was designed for —
        a genuine near-miss spelling of the ONLY identifying word, with zero
        exact token overlap otherwise."""
        cat = [_tool("translation_start_job", "Start translating a book",
                      tier="W", synonyms=["translate", "translation"])]
        matches, confident = td.search_catalog(cat, "translit this chapter", 8)
        assert [m["name"] for m in matches] == ["translation_start_job"]
        assert confident


class TestTierReaders:
    def test_tier_defaults_to_R_without_meta(self):
        assert td.tool_tier({"function": {"name": "x"}}) == "R"

    def test_tier_read_from_meta(self):
        assert td.tool_tier(_tool("book_create", tier="A")) == "A"

    def test_strip_meta_removes_meta_only(self):
        stripped = td.strip_tool_meta(_tool("book_create", tier="A"))
        assert "_meta" not in stripped["function"]
        assert stripped["function"]["name"] == "book_create"

    def test_undo_hint_from_result_meta(self):
        hint = td.tool_undo_hint({"undo_hint": {"tool": "chapter_delete", "args": {}}})
        assert hint == {"tool": "chapter_delete", "args": {}}
        assert td.tool_undo_hint(None) is None
        assert td.tool_undo_hint({}) is None


class TestProviderAvailability:
    def test_unavailable_providers_list(self):
        assert td.provider_availability({"unavailable_providers": ["book"]}) == {"book"}

    def test_providers_map(self):
        meta = {"providers": {"book": {"available": False}, "settings": {"available": True}}}
        assert td.provider_availability(meta) == {"book"}

    def test_empty_meta_no_outage(self):
        assert td.provider_availability({}) == set()


# ════════════════════════════════════════════════════════════════════════════
# find_tools in the loop — discovery → call across passes
# ════════════════════════════════════════════════════════════════════════════


class TestFindToolsDiscovery:
    @pytest.mark.asyncio
    async def test_find_tools_then_call_across_passes(self):
        """Pass 0: the model calls find_tools('translate'). Pass 1: now that
        translation_start_job is in the active set, its full schema is advertised
        and the model calls it. Pass 2: text answer."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(
            success=True, result={"confirm_token": "tok"}
        )
        scripts = [
            [tool_frag(0, id="f1", name="find_tools"),
             tool_frag(0, arguments_delta='{"intent":"translate my book"}'),
             done("tool_calls")],
            [tool_frag(0, id="t1", name="translation_start_job"),
             tool_frag(0, arguments_delta='{"book_id":"b"}'),
             done("tool_calls")],
            [tok("Started."), usage(1, 1), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))

        reqs = _FakeClient.instances[0].requests
        # Pass 0 advertised the core (find_tools present) but NOT the domain tool.
        p0_names = [t["function"]["name"] for t in reqs[0].tools]
        assert "find_tools" in p0_names
        assert "translation_start_job" not in p0_names
        # Pass 1 advertised the discovered tool's full schema.
        p1_names = [t["function"]["name"] for t in reqs[1].tools]
        assert "translation_start_job" in p1_names
        # The domain tool actually executed.
        assert kc.mcp_execute_tool.await_count == 1
        assert kc.mcp_execute_tool.await_args.kwargs["tool_name"] == "translation_start_job"
        # find_tools never went to the gateway (consumer-local).
        find_calls = [c for c in chunks if c.get("tool_call", {}).get("tool") == "find_tools"]
        assert len(find_calls) == 1
        assert find_calls[0]["tool_call"]["result"]["tools"]

    @pytest.mark.asyncio
    async def test_advertised_tools_have_no_meta(self):
        """C-TOOL: the `_meta` block is consumer-only and must NOT reach the
        provider in the advertised schema."""
        kc = _kc()
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run_discovery(scripts, knowledge_client=kc))
        # find a core+catalog advertisement; even after a find_tools the schemas
        # are stripped. Pass 0 advertises the core only, but assert globally.
        for req in _FakeClient.instances[0].requests:
            for t in (req.tools or []):
                assert "_meta" not in t["function"]


# ════════════════════════════════════════════════════════════════════════════
# H9 — find_tools + reads uncounted; cap=20 honored
# ════════════════════════════════════════════════════════════════════════════


class TestIterationBudgetH9:
    @pytest.mark.asyncio
    async def test_find_tools_and_reads_do_not_count_against_cap(self):
        """Many find_tools + Tier-R read passes must NOT exhaust the write budget;
        a Tier-A write afterward still executes (would be impossible if discovery
        burned the budget)."""
        kc = _kc()

        def find_pass():
            return [tool_frag(0, id="f", name="find_tools"),
                    tool_frag(0, arguments_delta='{"intent":"books"}'),
                    done("tool_calls")]

        def read_pass():
            return [tool_frag(0, id="r", name="book_list"),
                    tool_frag(0, arguments_delta="{}"),
                    done("tool_calls")]

        # 8 discovery/read passes (> the write cap of 5 if they counted) then a
        # Tier-A write, then a final text answer.
        scripts = [find_pass(), read_pass(), find_pass(), read_pass(),
                   find_pass(), read_pass(), find_pass(), read_pass(),
                   [tool_frag(0, id="w", name="book_create"),
                    tool_frag(0, arguments_delta='{"title":"X"}'),
                    done("tool_calls")],
                   [tok("done"), done("stop")]]
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc, max_iterations=20))

        # The Tier-A write ran (budget was not starved by discovery/reads).
        write_calls = [c for c in chunks
                       if c.get("tool_call", {}).get("tool") == "book_create"]
        assert len(write_calls) == 1
        # And the turn reached a clean text finish.
        assert chunks[-1]["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_write_budget_forces_tool_free_final_pass(self):
        """Write passes decrement the budget (D7): with cap=3, passes 0..1 are
        offered tools and the 3rd (final) pass is forced tool-free, then the loop
        terminates — it never runs unboundedly."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})

        def write_pass(cid):
            return [tool_frag(0, id=cid, name="chapter_create"),
                    tool_frag(0, arguments_delta="{}"),
                    done("tool_calls")]

        # Every pass defiantly emits a write, even the forced-final one.
        scripts = [write_pass("a"), write_pass("b"), write_pass("c")]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc, max_iterations=3))

        reqs = _FakeClient.instances[0].requests
        # Exactly cap passes ran (the loop terminated — no runaway).
        assert len(reqs) == 3
        # Passes 0..1 offered tools; the final pass is forced tool-free (D7).
        assert reqs[0].tools is not None and reqs[1].tools is not None
        assert reqs[-1].tools is None
        # The loop terminated with the defensive limit chunk.
        assert chunks[-1]["finish_reason"] == "stop"


# ════════════════════════════════════════════════════════════════════════════
# H7 — ≤5 same-op Tier-A → batch confirm escalation
# ════════════════════════════════════════════════════════════════════════════


class TestTierAVolumeCapH7:
    @pytest.mark.asyncio
    async def test_sixth_same_op_tier_a_escalates_to_batch_confirm(self):
        """After TIER_A_SAME_OP_CAP auto-writes of the SAME op, the next one
        suspends on a batch confirm_action instead of auto-applying (H7/H2)."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})

        # One pass that calls chapter_create CAP+1 times (indices 0..CAP).
        frags = []
        for i in range(TIER_A_SAME_OP_CAP + 1):
            frags.append(tool_frag(i, id=f"c{i}", name="chapter_create"))
            frags.append(tool_frag(i, arguments_delta=f'{{"n":{i}}}'))
        frags.append(done("tool_calls"))
        scripts = [frags]

        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc, max_iterations=20))

        # Exactly CAP auto-writes executed; the CAP+1-th escalated to a suspend.
        assert kc.mcp_execute_tool.await_count == TIER_A_SAME_OP_CAP
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        pending = suspends[0]["suspend"]["pending_tool_call"]
        assert pending["name"] == "confirm_action"
        assert pending["args"]["items"]  # batch card carries the held op
        assert pending["args"]["domain"] == "chapter"

    @pytest.mark.asyncio
    async def test_aggregate_cap_escalates_on_alternating_ops(self):
        """An ALTERNATING-op turn that exceeds the aggregate ceiling escalates to
        batch confirm even though no single op reaches the per-op cap (H7
        aggregate). Cycle 3 distinct Tier-A ops so each op's count stays below
        TIER_A_SAME_OP_CAP while the turn TOTAL crosses TIER_A_AGGREGATE_CAP."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})

        # Three distinct Tier-A ops, cycled so no single op hits the per-op cap
        # before the aggregate cap. With CAP=12 and 3 ops, each op reaches 4 at
        # 12 writes (<5), so ONLY the aggregate ceiling can trip.
        ops = ["book_create", "chapter_create", "scene_create"]
        catalog = [
            _tool("book_create", "Create a book", tier="A"),
            _tool("chapter_create", "Create a chapter", tier="A"),
            _tool("scene_create", "Create a scene", tier="A"),
        ]
        # Sanity: the construction must exercise the aggregate (not per-op) cap.
        assert TIER_A_AGGREGATE_CAP // len(ops) < TIER_A_SAME_OP_CAP

        # One pass that calls the cycle CAP+1 times (indices 0..CAP).
        frags = []
        for i in range(TIER_A_AGGREGATE_CAP + 1):
            frags.append(tool_frag(i, id=f"c{i}", name=ops[i % len(ops)]))
            frags.append(tool_frag(i, arguments_delta=f'{{"n":{i}}}'))
        frags.append(done("tool_calls"))
        scripts = [frags]

        with _patch_client(scripts):
            chunks = await _drain(
                _run_discovery(
                    scripts, knowledge_client=kc, catalog=catalog, max_iterations=20
                )
            )

        # Auto-writes stop exactly at the aggregate ceiling; the next one suspends.
        assert kc.mcp_execute_tool.await_count == TIER_A_AGGREGATE_CAP
        # No single op reached the per-op cap (proves it was the aggregate cap).
        from collections import Counter

        applied = Counter(
            call.kwargs["tool_name"] for call in kc.mcp_execute_tool.await_args_list
        )
        assert all(n < TIER_A_SAME_OP_CAP for n in applied.values())
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        pending = suspends[0]["suspend"]["pending_tool_call"]
        assert pending["name"] == "confirm_action"
        assert pending["args"]["items"]  # batch card carries the held op


# ════════════════════════════════════════════════════════════════════════════
# C-ACTIVITY (H16) — Tier-A activity + undo
# ════════════════════════════════════════════════════════════════════════════


class TestTierAActivityH16:
    @pytest.mark.asyncio
    async def test_tier_a_emits_activity_with_undo(self):
        """A successful Tier-A write emits an activity block built from the tool
        result's `_meta` (summary + undo_hint)."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(
            success=True,
            result={
                "chapter_id": "ch5",
                "_meta": {
                    "summary": "Created draft chapter 'Chapter 5'",
                    "undo_hint": {"tool": "chapter_delete", "args": {"chapter_id": "ch5"}},
                },
            },
        )
        scripts = [
            [tool_frag(0, id="w", name="chapter_create"),
             tool_frag(0, arguments_delta='{"title":"Chapter 5"}'),
             done("tool_calls")],
            [tok("Done."), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))

        tc = next(c["tool_call"] for c in chunks
                  if c.get("tool_call", {}).get("tool") == "chapter_create")
        assert tc["activity"]["op"] == "chapter_create"
        assert tc["activity"]["summary"] == "Created draft chapter 'Chapter 5'"
        assert tc["activity"]["undo"]["available"] is True
        assert tc["activity"]["undo"]["tool"] == "chapter_delete"

    @pytest.mark.asyncio
    async def test_tier_a_without_undo_hint_marks_unavailable(self):
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"ok": 1})
        scripts = [
            [tool_frag(0, id="w", name="book_create"),
             tool_frag(0, arguments_delta="{}"),
             done("tool_calls")],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))
        tc = next(c["tool_call"] for c in chunks
                  if c.get("tool_call", {}).get("tool") == "book_create")
        assert tc["activity"]["undo"]["available"] is False

    @pytest.mark.asyncio
    async def test_failed_tier_a_reports_failure_no_activity(self):
        """H17: a FAILED Tier-A is reported failed (ok=False), no success activity
        — so a multi-step goal can't claim whole success on a failed step."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(success=False, error="boom")
        scripts = [
            [tool_frag(0, id="w", name="chapter_create"),
             tool_frag(0, arguments_delta="{}"),
             done("tool_calls")],
            [tok("That step failed."), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))
        tc = next(c["tool_call"] for c in chunks
                  if c.get("tool_call", {}).get("tool") == "chapter_create")
        assert tc["ok"] is False
        assert "activity" not in tc


# ════════════════════════════════════════════════════════════════════════════
# H10 — missing vs unavailable phrasing
# ════════════════════════════════════════════════════════════════════════════


class TestMissingVsUnavailableH10:
    @pytest.mark.asyncio
    async def test_no_match_says_no_tool(self):
        kc = _kc(catalog_meta={})
        scripts = [
            [tool_frag(0, id="f", name="find_tools"),
             tool_frag(0, arguments_delta='{"intent":"xyzzy quux frobnicate"}'),
             done("tool_calls")],
            [tok("not supported"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))
        result = next(c["tool_call"]["result"] for c in chunks
                      if c.get("tool_call", {}).get("tool") == "find_tools")
        assert result["tools"] == []
        assert "unavailable_providers" not in result
        assert "no tool matched" in result["note"].lower()

    @pytest.mark.asyncio
    async def test_unavailable_provider_says_try_again(self):
        """H10: when find_tools finds nothing but the gateway reports a provider
        down, the result tells the agent the capability exists — try again."""
        kc = _kc(catalog_meta={"unavailable_providers": ["book"]})
        # A catalog with NO book tools (they dropped out because book is down).
        cat = [_tool("settings_list_models", "list models", tier="R")]
        scripts = [
            [tool_frag(0, id="f", name="find_tools"),
             tool_frag(0, arguments_delta='{"intent":"edit a chapter"}'),
             done("tool_calls")],
            [tok("try again"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc, catalog=cat))
        result = next(c["tool_call"]["result"] for c in chunks
                      if c.get("tool_call", {}).get("tool") == "find_tools")
        assert result["tools"] == []
        assert result["unavailable_providers"] == ["book"]
        assert "try again" in result["note"].lower()


# ════════════════════════════════════════════════════════════════════════════
# F2 — legacy surface advertises no frontend tools / never suspends
# ════════════════════════════════════════════════════════════════════════════


class TestGenericFrontendTools:
    def test_generic_tools_in_frontend_name_set(self):
        for name in ("ui_navigate", "ui_open_book", "ui_open_chapter",
                     "ui_show_panel", "ui_watch_job", "confirm_action",
                     "propose_record_edit"):
            assert name in FRONTEND_TOOL_NAMES

    def test_universal_core_advertises_generic_frontend_tools(self):
        """The always-on core (advertised every universal /chat pass) carries the
        generic ui_*/confirm/propose tools, ≤8 (C-FT)."""
        from app.services.stream_service import _advertise_discovery_tools, _catalog_index
        adv = _advertise_discovery_tools(
            _catalog_index(_CATALOG), set(),
            frontend_tool_defs(editor=False, book_scoped=False),
        )
        names = [t["function"]["name"] for t in adv]
        # core present
        for n in td.ALWAYS_ON_CORE_NAMES:
            assert n in names
        assert len(td.ALWAYS_ON_CORE_NAMES) <= 8
        # no discovered domain tools yet (active set empty)
        assert "translation_start_job" not in names


# ════════════════════════════════════════════════════════════════════════════
# C-FT hot set + lazy tail — per-surface domain scoping (the standard)
# ════════════════════════════════════════════════════════════════════════════


# A mixed-domain catalog spanning several federated services.
_MIXED_CATALOG = [
    _tool("glossary_search", "Search glossary entities", tier="R"),
    _tool("glossary_get_entity", "Read one entity", tier="R"),
    _tool("glossary_propose_batch", "Batch glossary ops", tier="W"),
    _tool("book_create", "Create a book", tier="A"),
    _tool("book_list", "List books", tier="R"),
    _tool("composition_outline_create", "Create an outline", tier="A"),
    _tool("translation_start_job", "Start a translation", tier="W"),
    _tool("settings_list_models", "List models", tier="R"),
    _tool("memory_search", "Search conversation memory", tier="R"),
    _tool("story_search", "Universal manuscript search", tier="R"),
]


class TestSurfaceHotDomains:
    def test_universal_is_pure_discovery(self):
        assert td.surface_hot_domains(editor=False, book_scoped=False) == set()

    def test_book_scoped_hot_is_glossary_and_story(self):
        # story_search (the universal manuscript find) is hot on every book-bound
        # surface — a weak model otherwise punts instead of discovering it (measured).
        assert td.surface_hot_domains(editor=False, book_scoped=True) == {"glossary", "story"}

    def test_editor_matches_book_glossary_skill(self):
        # Both surfaces inject the glossary skill (names glossary_* only) + the story
        # search; the editor's prose write-back is a FRONTEND tool, not a backend
        # domain — so the editor's hot domains equal the book-scoped surface's.
        editor = td.surface_hot_domains(editor=True, book_scoped=True)
        book = td.surface_hot_domains(editor=False, book_scoped=True)
        assert editor == book == {"glossary", "story"}

    def test_studio_hot_includes_story(self):
        studio = td.surface_hot_domains(studio=True)
        assert {"glossary", "composition", "story"} <= studio


class TestHotToolNames:
    def test_empty_domains_yields_empty(self):
        assert td.hot_tool_names(_MIXED_CATALOG, set()) == set()

    def test_picks_only_matching_prefixes(self):
        hot = td.hot_tool_names(_MIXED_CATALOG, {"glossary"})
        assert hot == {"glossary_search", "glossary_get_entity", "glossary_propose_batch"}
        # the long tail is excluded — it stays lazy (find_tools).
        assert "book_create" not in hot
        assert "translation_start_job" not in hot

    def test_multi_domain_union(self):
        hot = td.hot_tool_names(_MIXED_CATALOG, {"glossary", "book"})
        assert "glossary_search" in hot and "book_create" in hot and "book_list" in hot
        assert "composition_outline_create" not in hot
        assert "translation_start_job" not in hot


class TestHotSetAdvertisedOnFirstPass:
    def test_seed_advertises_hot_tools_immediately(self):
        """A book-scoped surface seeds the glossary domain into the active set, so
        its full schemas are advertised on pass 0 WITHOUT a find_tools round-trip —
        while the non-glossary long tail stays out (lazy)."""
        from app.services.stream_service import _advertise_discovery_tools, _catalog_index
        seed = td.hot_tool_names(
            _MIXED_CATALOG, td.surface_hot_domains(editor=False, book_scoped=True)
        )
        adv = _advertise_discovery_tools(
            _catalog_index(_MIXED_CATALOG), seed,
            frontend_tool_defs(editor=False, book_scoped=True),
        )
        names = {t["function"]["name"] for t in adv}
        # glossary hot set present immediately
        assert {"glossary_search", "glossary_get_entity", "glossary_propose_batch"} <= names
        # story_search (universal manuscript find) is hot on a book surface too, so the
        # agent can search/read the manuscript without a find_tools round-trip it never makes
        assert "story_search" in names
        # book-scoped frontend write-back tools present
        assert "glossary_propose_entity_edit" in names
        # the long tail is NOT advertised — it's discovered on demand
        assert "translation_start_job" not in names
        assert "composition_outline_create" not in names
        assert "memory_search" not in names
        # find_tools is still there so the agent can reach the tail
        assert td.FIND_TOOLS_NAME in names

    @pytest.mark.asyncio
    async def test_seeded_loop_advertises_hot_and_still_lazy_for_tail(self):
        """End-to-end through the loop: pass 0 advertises the seeded glossary hot
        set AND find_tools, but not the tail; the agent can act on a hot tool with
        no discovery hop, then find_tools to reach a tail tool."""
        kc = _kc()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"ok": 1})
        seed = td.hot_tool_names(
            _MIXED_CATALOG, td.surface_hot_domains(editor=False, book_scoped=True)
        )
        scripts = [
            # Pass 0: act directly on a hot glossary tool (no find_tools needed).
            [tool_frag(0, id="g", name="glossary_search"),
             tool_frag(0, arguments_delta='{"q":"king"}'),
             done("tool_calls")],
            [tok("Found it."), done("stop")],
        ]
        with _patch_client(scripts):
            stream = _stream_with_tools(
                model_source="user_model",
                model_ref=TEST_MODEL_REF,
                user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "find the king"}],
                gen_params={},
                tools=[],
                knowledge_client=kc,
                session_id=TEST_SESSION_ID,
                project_id="proj-1",
                max_iterations=10,
                discovery_catalog=_MIXED_CATALOG,
                discovery_extra_frontend=frontend_tool_defs(editor=False, book_scoped=True),
                discovery_seed_names=seed,
            )
            chunks = await _drain(stream)

        reqs = _FakeClient.instances[0].requests
        p0 = {t["function"]["name"] for t in reqs[0].tools}
        assert "glossary_search" in p0  # hot — advertised pass 0
        assert "translation_start_job" not in p0  # tail — lazy
        # The hot tool executed directly (no find_tools hop).
        assert kc.mcp_execute_tool.await_count == 1
        assert kc.mcp_execute_tool.await_args.kwargs["tool_name"] == "glossary_search"
        assert chunks[-1]["finish_reason"] == "stop"


# ════════════════════════════════════════════════════════════════════════════
# CAT-4 (mcp-tool-io.md Part 4) — legacy tool visibility
# ════════════════════════════════════════════════════════════════════════════

_LEGACY_CATALOG = [
    _tool("glossary_book_create", "Create a book-native genre, kind, or attribute.",
          tier="A", synonyms=["add a kind", "add a genre", "create attribute"],
          visibility="legacy"),
    _tool("glossary_user_create", "Create a genre, kind, or attribute in your library.",
          tier="A", synonyms=["add a kind"], visibility="legacy"),
    _tool("glossary_ontology_upsert",
          "Create or update book- or user-tier ontology rows (genre, kind, attribute).",
          tier="A", synonyms=["add a kind", "add a genre", "add an attribute"]),
    _tool("glossary_search", "Search glossary entities", tier="R"),
]


class TestVisibilityReaders:
    def test_defaults_to_discoverable_without_meta(self):
        assert td.tool_visibility({"function": {"name": "x"}}) == "discoverable"
        assert td.is_legacy_tool({"function": {"name": "x"}}) is False

    def test_reads_legacy_from_meta(self):
        t = _tool("glossary_book_create", visibility="legacy")
        assert td.tool_visibility(t) == "legacy"
        assert td.is_legacy_tool(t) is True

    def test_unknown_visibility_value_is_not_legacy(self):
        t = {"function": {"name": "x", "_meta": {"visibility": "bogus"}}}
        assert td.tool_visibility(t) == "discoverable"


class TestSearchCatalogCAT4:
    def test_legacy_tool_never_matches_even_on_exact_synonym(self):
        """The regression the eval caught: without CAT-4, the legacy tool's short
        punchy description out-scores the new tool on raw token overlap. CAT-4
        must exclude it categorically, not rely on ranking."""
        matches, confident = td.search_catalog(_LEGACY_CATALOG, "add a new kind to the book", 3)
        names = [m["name"] for m in matches]
        assert "glossary_book_create" not in names
        assert "glossary_user_create" not in names
        assert "glossary_ontology_upsert" in names
        assert confident

    def test_group_scopes_to_one_domain(self):
        matches, _ = td.search_catalog(_MIXED_CATALOG, "list something", 8, group="book")
        names = {m["name"] for m in matches}
        assert names <= {"book_create", "book_list"}

    def test_group_none_searches_everything(self):
        matches, _ = td.search_catalog(_MIXED_CATALOG, "create a book", 8, group=None)
        names = {m["name"] for m in matches}
        assert "book_create" in names


class TestHotToolNamesCAT4:
    def test_legacy_tool_excluded_from_hot_seed_even_in_its_domain(self):
        hot = td.hot_tool_names(_LEGACY_CATALOG, {"glossary"})
        assert "glossary_book_create" not in hot
        assert "glossary_user_create" not in hot
        assert "glossary_search" in hot
        assert "glossary_ontology_upsert" in hot


class TestDomainAliases:
    """2026-07-07 — group="knowledge" matched NOTHING before this fix: the domain's
    tools carry the LITERAL prefixes `kg_`/`memory_`, never `knowledge_`, and the
    group/hot-domain filters compared the literal prefix against the domain name
    directly. Found while auditing GROUP_DIRECTORY for the skill-authoring lint."""

    _CATALOG = [
        _tool("kg_graph_query", "Query the knowledge graph", tier="R"),
        _tool("memory_search", "Search conversation memory", tier="R"),
        _tool("glossary_search", "Search glossary entities", tier="R"),
    ]

    def test_group_knowledge_finds_kg_tool(self):
        matches, _ = td.search_catalog(self._CATALOG, "query the graph", 8, group="knowledge")
        assert "kg_graph_query" in {m["name"] for m in matches}

    def test_group_knowledge_finds_memory_tool(self):
        matches, _ = td.search_catalog(self._CATALOG, "search memory", 8, group="knowledge")
        assert "memory_search" in {m["name"] for m in matches}

    def test_group_knowledge_excludes_other_domains(self):
        matches, _ = td.search_catalog(self._CATALOG, "search", 8, group="knowledge")
        names = {m["name"] for m in matches}
        assert "glossary_search" not in names

    def test_hot_tool_names_knowledge_domain_includes_kg_and_memory(self):
        hot = td.hot_tool_names(self._CATALOG, {"knowledge"})
        assert hot == {"kg_graph_query", "memory_search"}


class TestGroupDirectory:
    def test_glossary_entry_exists(self):
        assert "glossary" in td.GROUP_DIRECTORY

    def test_text_is_deterministic_and_mentions_group_param(self):
        text = td.group_directory_text()
        assert "glossary" in text
        assert "group=" in text

    def test_find_tools_schema_advertises_group_enum(self):
        props = td.FIND_TOOLS_TOOL["function"]["parameters"]["properties"]
        assert props["group"]["enum"] == sorted(td.GROUP_DIRECTORY)


class TestLegacyToolsCatalog:
    """Part D — the server-sourced feed backing the `pinned_legacy_tools`
    manual-injection setting (GET /v1/chat/tools/catalog?visibility=legacy)."""

    def test_returns_only_legacy_tools_sorted_by_name(self):
        items = td.legacy_tools_catalog(_LEGACY_CATALOG)
        names = [i["name"] for i in items]
        assert names == ["glossary_book_create", "glossary_user_create"]
        assert all(i["description"] for i in items)

    def test_empty_when_catalog_has_no_legacy_tools(self):
        assert td.legacy_tools_catalog([_tool("glossary_search", tier="R")]) == []


class TestUnknownPinnedLegacyNames:
    """SET-6 closed-set validation for a PATCH pinned_legacy_tools write."""

    def test_all_valid_returns_empty(self):
        unknown = td.unknown_pinned_legacy_names(_LEGACY_CATALOG, ["glossary_book_create"])
        assert unknown == []

    def test_unknown_name_is_rejected(self):
        unknown = td.unknown_pinned_legacy_names(_LEGACY_CATALOG, ["glossary_book_create", "not_a_real_tool"])
        assert unknown == ["not_a_real_tool"]

    def test_a_discoverable_tool_cannot_be_pinned_as_legacy(self):
        """glossary_ontology_upsert is real but NOT legacy — pinning it through
        this channel is a category error, not a valid escape-hatch use."""
        unknown = td.unknown_pinned_legacy_names(_LEGACY_CATALOG, ["glossary_ontology_upsert"])
        assert unknown == ["glossary_ontology_upsert"]
