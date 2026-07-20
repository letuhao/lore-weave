"""MCP-fanout S-CONSUMER — find_tools discovery, tier-driven advertising,
H7 cap, H9 budget, C-ACTIVITY, and missing-vs-unavailable phrasing.

Reuses the _FakeClient scripting harness from test_stream_tools. The discovery
path is driven by passing `discovery_catalog`/`discovery_extra_frontend` into
`_stream_with_tools` directly (the same kwargs stream_response wires on the
universal /chat surface)."""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

from app.client.embedding_client import EmbeddingResult
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
    # Track D CD5 — `web_search` is the one ALWAYS-ON CORE tool that is FEDERATED
    # (backend), not a generic frontend tool. It therefore resolves from the catalog;
    # a catalog that lacks it advertises nothing for it (see the degrade test below).
    _tool("web_search", "Search the open web", tier="R", synonyms=["web", "research"]),
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


class TestFindToolsMissingIntent:
    """2026-07-07 (Part E eval, `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE` root cause) —
    a weak local model live-observed calling `find_tools()` with NO `intent` at
    all (schema says `required`, never enforced server-side), 30+ times in one
    turn, because the old generic "No tool matched" note gave it no signal its
    OWN call was malformed. Now a missing/blank intent gets a directive instead
    of a silent zero-token search."""

    def test_missing_intent_returns_directive_not_generic_no_match(self):
        """External audit #5 (2026-07-08 re-verification) — no group + blank intent
        now returns the GROUP_DIRECTORY listing (a concrete next step) alongside
        the directive, not a bare "intent is required" scold with nothing to act on."""
        payload, matched = td.find_tools_result(
            _MIXED_CATALOG, "", 8, exclude=set(), catalog_meta={},
        )
        assert matched == []
        assert payload["tools"] == []
        assert "domains" in payload and payload["domains"]
        assert "group" in payload["note"]
        assert "No tool matched. Reconsider" not in payload["note"]

    def test_whitespace_only_intent_also_rejected(self):
        payload, _ = td.find_tools_result(
            _MIXED_CATALOG, "   ", 8, exclude=set(), catalog_meta={},
        )
        assert "domains" in payload and payload["domains"]

    def test_real_intent_unaffected(self):
        """The fix must not regress the normal case — a real intent still searches."""
        payload, matched = td.find_tools_result(
            _MIXED_CATALOG, "search the glossary", 8, exclude=set(), catalog_meta={},
        )
        assert matched
        assert "required" not in payload.get("note", "")


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


class TestToolListLoadDispatch:
    """WS-1a — tool_list/tool_load are dispatched CONSUMER-LOCAL in the discovery loop."""

    @pytest.mark.asyncio
    async def test_tool_list_dispatched_locally(self):
        kc = _kc(catalog_meta={})
        scripts = [
            [tool_frag(0, id="t", name="tool_list"),
             tool_frag(0, arguments_delta='{"category":"book"}'),
             done("tool_calls")],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))
        result = next(c["tool_call"]["result"] for c in chunks
                      if c.get("tool_call", {}).get("tool") == "tool_list")
        names = [t["name"] for t in result["tools"]]
        assert result["category"] == "book"
        assert "book_create" in names and "book_list" in names

    @pytest.mark.asyncio
    async def test_tool_load_returns_schema_locally(self):
        kc = _kc(catalog_meta={})
        scripts = [
            [tool_frag(0, id="t", name="tool_load"),
             tool_frag(0, arguments_delta='{"name":"translation_start_job"}'),
             done("tool_calls")],
            [tok("loaded"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))
        result = next(c["tool_call"]["result"] for c in chunks
                      if c.get("tool_call", {}).get("tool") == "tool_load")
        assert result["tools"][0]["name"] == "translation_start_job"
        assert "input_schema" in result["tools"][0]

    @pytest.mark.asyncio
    async def test_tool_load_no_args_guides_instead_of_silent_empty(self):
        # review-impl #3 — tool_load with nothing requested returns a guidance note.
        kc = _kc(catalog_meta={})
        scripts = [
            [tool_frag(0, id="t", name="tool_load"),
             tool_frag(0, arguments_delta='{}'),
             done("tool_calls")],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run_discovery(scripts, knowledge_client=kc))
        result = next(c["tool_call"]["result"] for c in chunks
                      if c.get("tool_call", {}).get("tool") == "tool_load")
        assert result["tools"] == []
        assert "note" in result and "tool_list" in result["note"]


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
        generic ui_*/confirm/propose tools, the discovery pair, and the federated
        `web_search` — ≤10 (C-FT; WS-1a bumped 8→10 for tool_list/tool_load, Track D
        CD5 filled the 10th slot with web_search)."""
        from app.services.stream_service import _advertise_discovery_tools, _catalog_index
        adv = _advertise_discovery_tools(
            _catalog_index(_CATALOG), set(),
            frontend_tool_defs(editor=False, book_scoped=False),
        )
        names = [t["function"]["name"] for t in adv]
        # core present
        for n in td.ALWAYS_ON_CORE_NAMES:
            assert n in names
        assert len(td.ALWAYS_ON_CORE_NAMES) <= 10
        # the deterministic discovery pair is core + advertised
        assert "tool_list" in names and "tool_load" in names
        # web_search is core: reachable with NO tool_list/tool_load round-trip
        assert "web_search" in names
        # no discovered domain tools yet (active set empty)
        assert "translation_start_job" not in names

    def test_core_web_search_is_omitted_not_fabricated_when_catalog_lacks_it(self):
        """`web_search` is the only always-on core tool that is FEDERATED, so unlike the
        ui_*/propose/confirm core it has no `generic_frontend_tool_def` fallback. If the
        gateway is degraded and the catalog omits it, it must be silently ABSENT — never
        advertised with a fabricated (paramless) frontend schema, which the model would
        call and get an error from. `_add(None)` is what guarantees this."""
        from app.services.stream_service import _advertise_discovery_tools, _catalog_index
        catalog_without_web = [t for t in _CATALOG if t["function"]["name"] != "web_search"]
        adv = _advertise_discovery_tools(
            _catalog_index(catalog_without_web), set(),
            frontend_tool_defs(editor=False, book_scoped=False),
        )
        names = [t["function"]["name"] for t in adv]
        assert "web_search" not in names
        # the rest of the core still lands — one missing federated tool degrades alone
        assert "tool_list" in names and "confirm_action" in names and "ui_navigate" in names


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
    """Part D (2026-07-07, docs/specs/2026-07-07-skill-authoring-and-mcp-exposure-
    standard.md §8b.9) — `surface_hot_domains` now DERIVES from which skills
    auto-inject by default on a surface (unioning their declared `hot_domains`),
    instead of three hand-authored constants. Sign-off'd behavior change: since
    `knowledge_skill` already auto-injects on EVERY non-admin surface (including
    universal/chat) and already honestly declared `hot_domains={"knowledge"}`
    (2026-07-07, Part A), that declaration is now HONORED — "knowledge" is hot on
    every surface below, including universal, which previously hot-seeded nothing.
    This closes `D-SKILL-HOTDOMAIN-RUNTIME-WIRING`. Every other domain (glossary/
    composition/story/plan) is UNCHANGED from the old hand-authored constants —
    that equivalence is exactly what these tests now assert."""

    def test_universal_is_knowledge_only(self):
        # Previously pure discovery (∅) — "knowledge" is the ONE new addition; no
        # other domain becomes hot on chat (no skill besides knowledge/universal
        # auto-injects there, and universal's own hot_domains is correctly empty).
        assert td.surface_hot_domains(editor=False, book_scoped=False) == {"knowledge"}

    def test_book_scoped_hot_is_glossary_story_and_now_knowledge(self):
        # story_search (the universal manuscript find) is hot on every book-bound
        # surface — a weak model otherwise punts instead of discovering it (measured).
        # F14 — `book` now auto-injects on book-bound surfaces, so book_* tools are hot.
        assert td.surface_hot_domains(editor=False, book_scoped=True) == {
            "glossary", "story", "knowledge", "book",
        }

    def test_editor_matches_book_glossary_skill(self):
        # Both surfaces inject the glossary skill (names glossary_* only) + the story
        # search + the co_write write-mode workflow (close-21-28), whose hot_domains
        # {plan, composition} make plan_compile / composition_package_tree reachable
        # WITHOUT discovery — the deeper P-08 fix. The editor's prose write-back is a
        # FRONTEND tool, so the editor's hot domains still equal the book-scoped surface's.
        editor = td.surface_hot_domains(editor=True, book_scoped=True)
        book = td.surface_hot_domains(editor=False, book_scoped=True)
        # F14 — `book` now auto-injects on book-bound surfaces (a book is open).
        assert editor == book == {"glossary", "story", "knowledge", "book"}

    def test_studio_hot_includes_story_and_knowledge(self):
        studio = td.surface_hot_domains(studio=True)
        assert {"glossary", "composition", "story", "knowledge"} <= studio

    def test_plan_mode_still_adds_plan_domain_on_top(self):
        # The plan-mode carve-out (was PLAN_HOT_DOMAINS, now derived from
        # SYSTEM_SKILLS["plan_forge"].hot_domains) still layers "plan" on, additive
        # to whatever the surface would otherwise be hot for.
        base = td.surface_hot_domains(editor=False, book_scoped=True)
        plan = td.surface_hot_domains(editor=False, book_scoped=True, permission_mode="plan")
        assert plan == base | {"plan"}


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
        while the non-glossary long tail stays out (lazy).

        Part D (2026-07-07): `memory_search` (knowledge domain) is now correctly
        IN this set — see `TestSurfaceHotDomains`'s class docstring for why this
        flipped from the old "stays lazy" expectation (knowledge_skill's declared
        hot_domains is now actually honored, closing D-SKILL-HOTDOMAIN-RUNTIME-
        WIRING)."""
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
        # Part D: knowledge is now hot too (see docstring above) — memory_search
        # rides the seed, it does NOT stay lazy anymore.
        assert "memory_search" in names
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


class TestWorldGroupDiscoverable:
    """W10 remediation (2026-07-11) — group="world" matched NOTHING before this fix:
    world_*/world_map_* carry the literal `world_` prefix, but GROUP_DIRECTORY had no
    "world" key, so `_domain_of` resolved them to the non-group domain "world" and they
    were excluded from every enumerable group AND from "book". Adding the key makes the
    prefix its own group. Mirror of TestDomainAliases."""

    _CATALOG = [
        _tool("world_create", "Create a worldbuilding container", tier="R"),
        _tool("world_map_create", "Create a reference map", tier="R"),
        _tool("book_create", "Create a book", tier="R"),
    ]

    def test_group_world_finds_world_tool(self):
        matches, _ = td.search_catalog(self._CATALOG, "create a world", 8, group="world")
        assert "world_create" in {m["name"] for m in matches}

    def test_group_world_finds_map_tool(self):
        matches, _ = td.search_catalog(self._CATALOG, "create a map", 8, group="world")
        assert "world_map_create" in {m["name"] for m in matches}

    def test_group_world_excludes_book_domain(self):
        matches, _ = td.search_catalog(self._CATALOG, "create", 8, group="world")
        assert "book_create" not in {m["name"] for m in matches}

    def test_hot_tool_names_world_domain_includes_both(self):
        hot = td.hot_tool_names(self._CATALOG, {"world"})
        assert hot == {"world_create", "world_map_create"}


class TestGroupDirectory:
    def test_glossary_entry_exists(self):
        assert "glossary" in td.GROUP_DIRECTORY

    def test_world_entry_exists(self):
        # W10 remediation — world_*/world_map_* now have a group home.
        assert "world" in td.GROUP_DIRECTORY

    def test_text_is_deterministic_and_mentions_group_param(self):
        text = td.group_directory_text()
        assert "glossary" in text
        # WS-6 — the directory now points at the deterministic tool_list primary
        # (find_tools demoted to optional legacy), so it names category=<name>.
        assert "category=" in text

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


# ════════════════════════════════════════════════════════════════════════════
# Design item 1 (2026-07-07 discovery-hardening plan) — true per-domain
# enumeration. Python twin of ai-gateway's `enumerateGroup` (find-tools.ts).
# ════════════════════════════════════════════════════════════════════════════

_ENUM_CATALOG = [
    _tool("book_create", "Create a new book"),
    _tool("book_update_chapter", "Edit a chapter of a book"),
    _tool("book_list", "List books"),
    _tool("translation_start_job", "Start translating a book into another language"),
    _tool("book_legacy_rename", "Old rename endpoint", visibility="legacy"),
]


class TestEnumerateGroup:
    def test_returns_every_non_legacy_tool_in_the_domain(self):
        names = sorted(m["name"] for m in td.enumerate_group(_ENUM_CATALOG, "book"))
        assert names == ["book_create", "book_list", "book_update_chapter"]

    def test_excludes_legacy_tagged_tools(self):
        names = [m["name"] for m in td.enumerate_group(_ENUM_CATALOG, "book")]
        assert "book_legacy_rename" not in names

    def test_is_unranked_and_unfiltered_by_score_floor(self):
        # No INCLUSION_FLOOR/CONFIDENCE_THRESHOLD gate — every non-legacy domain
        # member returned regardless of any notion of "relevance" to anything.
        assert len(td.enumerate_group(_ENUM_CATALOG, "book")) == 3

    def test_respects_exclude_set(self):
        names = {m["name"] for m in td.enumerate_group(_ENUM_CATALOG, "book", exclude={"book_create"})}
        assert names == {"book_list", "book_update_chapter"}

    def test_unknown_domain_returns_empty_not_an_error(self):
        assert td.enumerate_group(_ENUM_CATALOG, "nonexistent_domain") == []


class TestFindToolsResultEnumerationMode:
    """`group` set + `intent` omitted/blank switches to enumeration — the true
    fix for external audit #1/#5 ("find_tools under-returns on generic
    queries" / "no list-all-tools-in-a-domain affordance"). Before this fix,
    `search_catalog("")` always scored 0 (empty intent_tokens), so this
    returned ZERO tools even though the domain plainly has some."""

    def test_group_and_empty_intent_returns_full_unranked_domain_list(self):
        payload, matched = td.find_tools_result(
            _ENUM_CATALOG, "", 8, exclude=set(), catalog_meta={}, group="book",
        )
        assert sorted(matched) == ["book_create", "book_list", "book_update_chapter"]
        assert payload["enumerated"] is True
        assert "note" not in payload

    def test_group_and_whitespace_only_intent_also_enumerates(self):
        payload, matched = td.find_tools_result(
            _ENUM_CATALOG, "   ", 8, exclude=set(), catalog_meta={}, group="book",
        )
        assert sorted(matched) == ["book_create", "book_list", "book_update_chapter"]
        assert payload["enumerated"] is True

    def test_legacy_tools_stay_excluded_from_enumeration(self):
        _, matched = td.find_tools_result(
            _ENUM_CATALOG, "", 8, exclude=set(), catalog_meta={}, group="book",
        )
        assert "book_legacy_rename" not in matched

    def test_group_with_non_empty_intent_uses_ranked_search_not_enumeration(self):
        payload, _ = td.find_tools_result(
            _ENUM_CATALOG, "create a book", 8, exclude=set(), catalog_meta={}, group="book",
        )
        assert "enumerated" not in payload

    def test_group_with_weak_generic_intent_falls_back_to_enumeration(self):
        """External audit #1 (2026-07-08 re-verification) — the ORIGINAL fix above
        only covers a LITERALLY blank intent; a real exploratory agent instead
        phrases a broad ask as non-blank generic text, which token-overlaps
        poorly and used to silently under-return (measured live: `book` → 1/~15
        tools, 7% recall, for this EXACT phrase). A `group`-scoped query that
        scores below CONFIDENCE_THRESHOLD now ALSO falls back to full
        enumeration, same as a literal blank intent would."""
        payload, matched = td.find_tools_result(
            _ENUM_CATALOG, "list everything you can do in this domain", 8,
            exclude=set(), catalog_meta={}, group="book",
        )
        assert sorted(matched) == ["book_create", "book_list", "book_update_chapter"]
        assert payload["enumerated"] is True
        assert "didn't score well" in payload["note"]

    def test_group_with_weak_intent_on_zero_tool_domain_gets_the_honest_empty_note(self):
        """The fallback must not paper over a domain that's genuinely empty —
        it should still get the "genuinely has no tools" note, not the
        "didn't score well" fallback wording (which implies tools exist)."""
        payload, matched = td.find_tools_result(
            _ENUM_CATALOG, "list everything you can do in this domain", 8,
            exclude=set(), catalog_meta={}, group="nonexistent_domain",
        )
        assert matched == []
        assert payload["enumerated"] is True
        assert "genuinely has no tools" in payload["note"]

    def test_no_group_and_empty_intent_is_unaffected_still_the_intent_directive(self):
        """This case is the ALREADY-FIXED `D-SKILL-EVAL-DISCOVERY-LOOP-FLAKE`
        blank-intent directive (commit 1a4983b7b) — enumeration is intentionally
        GROUP-SCOPED only, so a no-group blank intent must not start silently
        enumerating the whole flat catalog. External audit #5 (2026-07-08) adds
        the GROUP_DIRECTORY listing to this same response (a concrete next step),
        it doesn't switch it to full-catalog enumeration."""
        payload, matched = td.find_tools_result(
            _ENUM_CATALOG, "", 8, exclude=set(), catalog_meta={},
        )
        assert matched == []
        assert "enumerated" not in payload
        assert "domains" in payload and payload["domains"]

    def test_a_domain_with_zero_non_legacy_tools_gets_an_honest_not_supported_note(self):
        payload, matched = td.find_tools_result(
            _ENUM_CATALOG, "", 8, exclude=set(), catalog_meta={}, group="nonexistent_domain",
        )
        assert matched == []
        assert "isn't supported" in payload["note"]

    @pytest.mark.asyncio
    async def test_async_twin_falls_back_to_enumeration_on_weak_group_query_too(self):
        """Lockstep check — `find_tools_result_async` shares `_enumeration_result`/
        `_blank_intent_result` with the sync version, but has its own call site
        for the group+weak-intent fallback; must not drift. `_patch_embedding_model(None)`
        degrades the embeddings blend to identical token-overlap-only behavior."""
        with _patch_embedding_model(None):
            payload, matched = await td.find_tools_result_async(
                _ENUM_CATALOG, "list everything you can do in this domain", 8,
                exclude=set(), catalog_meta={}, group="book", user_id=TEST_USER_ID,
            )
        assert sorted(matched) == ["book_create", "book_list", "book_update_chapter"]
        assert payload["enumerated"] is True
        assert "didn't score well" in payload["note"]

    @pytest.mark.asyncio
    async def test_async_twin_no_group_blank_intent_also_returns_domain_directory(self):
        with _patch_embedding_model(None):
            payload, matched = await td.find_tools_result_async(
                _ENUM_CATALOG, "", 8, exclude=set(), catalog_meta={}, user_id=TEST_USER_ID,
            )
        assert matched == []
        assert "domains" in payload and payload["domains"]


class TestEnumerationBudgetsActiveToolNames:
    """HIGH-3 (review-impl) — enumeration mode returns EVERY non-legacy tool in
    a domain, unranked (up to ~56 for composition); `stream_service.py`'s
    `active_tool_names.update(matched)` used to union that UNBOUNDED set
    unconditionally, bypassing the token-budget discipline
    `merge_activated_tools`/`budget_names_by_tokens` already enforce for the
    NEXT-turn persisted `activated_tools` set (curated mode only) — THIS
    turn's `active_tool_names` (which controls whose FULL SCHEMA
    `_advertise_discovery_tools` sends on the next pass, independent of
    curated/non-curated mode) had no budgeting at all. This reopened the
    context-explosion class (docs/eval/context-budget/context-explosion-
    investigation-2026-07-06.md) for the enumeration path. The full unranked
    list must still reach the model in the tool RESULT payload (cheap —
    names+descriptions only); only what gets a full schema advertised next
    pass is capped."""

    @pytest.mark.asyncio
    async def test_enumeration_of_a_large_domain_does_not_blow_past_the_hot_seed_token_budget(self):
        from app.services.tool_surface import HOT_SEED_TOKEN_BUDGET, _tool_tokens

        verbose_desc = "A moderately verbose description of this tool's behavior. " * 12
        big_cat = [_tool(f"book_tool_{i:03d}", verbose_desc) for i in range(50)]
        kc = _kc()
        scripts = [
            [tool_frag(0, id="f1", name="find_tools"),
             tool_frag(0, arguments_delta=json.dumps({"group": "book", "intent": ""})),
             done("tool_calls")],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "hi"}], gen_params={}, tools=[],
                knowledge_client=kc, session_id=str(uuid4()), project_id="proj-1",
                discovery_catalog=big_cat,
                discovery_extra_frontend=frontend_tool_defs(editor=False, book_scoped=False),
            ))

        # Sanity: the RESULT payload fed back to the model still lists every
        # tool in the domain, unranked — enumeration's whole point (cheap,
        # names+descriptions only) is unaffected by this fix.
        find_call = next(c["tool_call"] for c in chunks if c.get("tool_call", {}).get("tool") == "find_tools")
        assert len(find_call["result"]["tools"]) == 50

        client = _FakeClient.instances[0]
        # requests[1] is the pass AFTER the enumeration find_tools call — its
        # `tools` is {core} ∪ {full schemas of active_tool_names}. The full
        # 50-tool domain must NOT all have full schemas advertised there.
        advertised_names = {t["function"]["name"] for t in (client.requests[1].tools or [])}
        book_tool_names = {t["function"]["name"] for t in big_cat}
        advertised_book_tools = advertised_names & book_tool_names
        assert 0 < len(advertised_book_tools) < len(big_cat)
        # Whatever WAS advertised fits the same ceiling the hot-seed uses.
        total_tokens = sum(
            _tool_tokens(td) for td in big_cat
            if td["function"]["name"] in advertised_book_tools
        )
        assert total_tokens <= HOT_SEED_TOKEN_BUDGET


# ════════════════════════════════════════════════════════════════════════════
# Design item 1 — retry-cap (FindToolsAttemptTracker). Python twin of
# ai-gateway's FindToolsAttemptTracker (find-tools.ts).
# ════════════════════════════════════════════════════════════════════════════


class TestFindToolsAttemptTracker:
    def test_first_attempt_for_a_session_is_never_a_repeat(self):
        t = td.FindToolsAttemptTracker()
        assert t.record("session-1", "book", "start a translation") is False

    def test_second_identical_call_same_session_is_a_repeat(self):
        t = td.FindToolsAttemptTracker()
        t.record("session-1", "book", "search the web")
        assert t.record("session-1", "book", "search the web") is True

    def test_near_duplicate_token_set_different_order_casing_is_a_repeat(self):
        t = td.FindToolsAttemptTracker()
        t.record("session-1", "book", "Search The Web")
        assert t.record("session-1", "book", "the web search") is True

    def test_a_genuinely_different_intent_same_session_group_is_not_a_repeat(self):
        t = td.FindToolsAttemptTracker()
        t.record("session-1", "book", "search the web")
        assert t.record("session-1", "book", "translate this chapter") is False

    def test_same_group_intent_different_session_is_not_a_repeat(self):
        t = td.FindToolsAttemptTracker()
        t.record("session-1", "book", "search the web")
        assert t.record("session-2", "book", "search the web") is False

    def test_no_session_id_is_never_tracked_fail_open(self):
        t = td.FindToolsAttemptTracker()
        t.record(None, "book", "search the web")
        assert t.record(None, "book", "search the web") is False

    def test_enumeration_call_blank_intent_never_counts_as_an_attempt(self):
        t = td.FindToolsAttemptTracker()
        assert t.record("session-1", "book", "") is False
        assert t.record("session-1", "book", "") is False

    def test_entry_expires_after_the_ttl_window(self):
        clock = {"t": 0.0}
        t = td.FindToolsAttemptTracker(ttl_s=1000, now=lambda: clock["t"])
        t.record("session-1", "book", "search the web")
        clock["t"] = 5000  # well past the 1000s TTL
        assert t.record("session-1", "book", "search the web") is False

    # ── review-impl fix — the top-level `_sessions` map must actually shrink ─

    def test_top_level_session_map_shrinks_after_a_stale_sessions_entries_expire(self):
        """A session's bucket only ever holds stale entries once its intents
        all pass the TTL — the top-level `session_id` key must be dropped too,
        not just its now-empty inner bucket left behind forever. Proven by
        touching a DIFFERENT, still-active session: that unrelated call must
        still sweep and drop the expired session's now-stale top-level entry."""
        clock = {"t": 0.0}
        t = td.FindToolsAttemptTracker(ttl_s=1000, now=lambda: clock["t"])
        t.record("stale-session", "book", "search the web")
        assert t.session_count == 1
        clock["t"] = 5000  # well past the 1000s TTL for stale-session's entry
        # A record() call for an unrelated session sweeps EVERY tracked
        # session (not just its own) — the stale session's top-level key must
        # be gone after this, not merely its inner bucket emptied.
        t.record("other-session", "book", "translate this chapter")
        assert "stale-session" not in t._sessions  # noqa: SLF001 — internal state check
        assert t.session_count == 1  # only "other-session" remains

    def test_own_session_top_level_key_also_shrinks_once_touched_again_after_expiry(self):
        """The narrower case named in the finding: a session's OWN entries all
        expire and it gets touched again — the sweep drops the stale entry
        before the fresh one is recorded, so the top-level map never grows
        unbounded by re-adding a leaked ghost entry underneath the fresh one."""
        clock = {"t": 0.0}
        t = td.FindToolsAttemptTracker(ttl_s=1000, now=lambda: clock["t"])
        t.record("session-1", "book", "search the web")
        assert t.session_count == 1
        clock["t"] = 5000
        t.record("session-1", "book", "a brand new different intent")
        # Exactly one session tracked (the fresh entry), not a leaked ghost
        # plus the fresh one — the map size never grew past 1.
        assert t.session_count == 1


class TestFindToolsResultRepeatNoteReshaping:
    """`find_tools_result`'s notes reshape on a REPEATED near-duplicate search
    for the SAME session (per the module-level `find_tools_attempts` singleton)
    — a repeat explicitly permits "tell the user not supported" instead of
    another invitation to keep guessing."""

    def test_first_no_match_search_still_invites_one_more_try(self):
        sid = str(uuid4())
        payload, _ = td.find_tools_result(
            _MIXED_CATALOG, "xyzzy quux frobnicate", 8,
            exclude=set(), catalog_meta={}, session_id=sid,
        )
        assert "try once more" in payload["note"].lower()

    def test_repeated_no_match_search_permits_not_supported(self):
        sid = str(uuid4())
        td.find_tools_result(
            _MIXED_CATALOG, "xyzzy quux frobnicate", 8,
            exclude=set(), catalog_meta={}, session_id=sid,
        )
        payload, _ = td.find_tools_result(
            _MIXED_CATALOG, "xyzzy quux frobnicate", 8,
            exclude=set(), catalog_meta={}, session_id=sid,
        )
        assert "not supported" in payload["note"].lower()
        assert "stop searching" in payload["note"].lower()

    def test_near_duplicate_wording_also_counts_as_the_repeat(self):
        sid = str(uuid4())
        td.find_tools_result(
            _MIXED_CATALOG, "xyzzy quux frobnicate", 8,
            exclude=set(), catalog_meta={}, session_id=sid,
        )
        payload, _ = td.find_tools_result(
            _MIXED_CATALOG, "frobnicate quux xyzzy", 8,
            exclude=set(), catalog_meta={}, session_id=sid,
        )
        assert "not supported" in payload["note"].lower()

    def test_no_session_id_never_flags_a_repeat_fail_open(self):
        payload1, _ = td.find_tools_result(
            _MIXED_CATALOG, "xyzzy quux frobnicate zzz", 8, exclude=set(), catalog_meta={},
        )
        payload2, _ = td.find_tools_result(
            _MIXED_CATALOG, "xyzzy quux frobnicate zzz", 8, exclude=set(), catalog_meta={},
        )
        assert "try once more" in payload1["note"].lower()
        assert "try once more" in payload2["note"].lower()

    def test_a_down_provider_note_is_unaffected_by_repeat_status(self):
        sid = str(uuid4())
        cat = [_tool("settings_list_models", "list models", tier="R")]
        meta = {"unavailable_providers": ["book"]}
        td.find_tools_result(cat, "edit a chapter", 8, exclude=set(), catalog_meta=meta, session_id=sid)
        payload, _ = td.find_tools_result(cat, "edit a chapter", 8, exclude=set(), catalog_meta=meta, session_id=sid)
        assert "temporarily unavailable" in payload["note"].lower()


# ════════════════════════════════════════════════════════════════════════════
# Design item 1 (embeddings sub-item, OQ4) — embeddings-backed search_catalog.
# chat-service's FIRST embedding-provider call site. Mandatory fallback
# discipline: on ANY embedding-client failure, behave EXACTLY like
# search_catalog() — never fail, never block, never rank worse than today.
# ════════════════════════════════════════════════════════════════════════════


def _fake_embed_fixed_map(text_vectors: dict[str, list[float]], default: list[float]):
    """Build a fake `.embed()` coroutine mapping known texts to fixed vectors —
    any UNMAPPED text (the fresh per-call `intent` string) gets `default`."""

    async def _embed(*, user_id, model_source, model_ref, texts):
        return EmbeddingResult(
            embeddings=[text_vectors.get(t, default) for t in texts],
            dimension=len(default),
            model="fake-embed-model",
        )

    return _embed


def _patch_embedding_model(ref: tuple[str, str] | None = ("user_model", "embed-m1")):
    """HIGH-2 fix: `search_catalog_semantic` no longer takes the turn's chat
    `model_source`/`model_ref` — it resolves the user's configured
    embedding-capable model via `provider_client.get_provider_client()
    .get_default_model("embedding", user_id)` first. Tests must patch THAT
    resolution (never the real provider-registry) — pass `ref=None` to
    simulate "user has no embedding model configured" (the fast pre-network
    skip path); the default `ref` simulates a configured model so the
    pre-existing embedding-blend tests keep exercising the embed call."""
    mock_provider = AsyncMock()
    mock_provider.get_default_model = AsyncMock(return_value=ref)
    return patch("app.client.provider_client.get_provider_client", return_value=mock_provider)


class TestSearchCatalogSemantic:
    def setup_method(self, _method):
        td._TOOL_VECTOR_CACHE.clear()
        td._EMBEDDING_MODEL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_embedding_similarity_rescues_a_genuine_zero_token_overlap_match(self):
        """The blend's whole point: a tool with NO token overlap with the intent
        (excluded by search_catalog()'s INCLUSION_FLOOR) still surfaces when its
        embedding is semantically close to the intent's embedding."""
        cat = [
            _tool("glossary_search", "Search glossary entities"),
            _tool("book_create", "Create a new book"),
        ]
        # _embedding_text() output for each tool, mapped to orthogonal vectors.
        text_vectors = {
            "glossary search Search glossary entities": [1.0, 0.0],
            "book create Create a new book": [0.0, 1.0],
        }
        fake_embed = _fake_embed_fixed_map(text_vectors, default=[1.0, 0.0])
        mock_client = AsyncMock()
        mock_client.embed.side_effect = fake_embed

        intent = "who is the villain love interest"
        # Sanity: proves this is a genuine zero-overlap case for the token scorer.
        base_matches, _ = td.search_catalog(cat, intent, 8)
        assert base_matches == []

        with _patch_embedding_model(), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            matches, confident = await td.search_catalog_semantic(
                cat, intent, 8, user_id="u1",
            )
        assert "glossary_search" in [m["name"] for m in matches]
        assert confident

    @pytest.mark.asyncio
    async def test_embedding_client_exception_falls_back_to_token_overlap_result(self):
        """MANDATORY fallback: an embedding-client failure must yield the exact
        same result search_catalog() would — never an error, never a worse rank."""
        mock_client = AsyncMock()
        mock_client.embed.side_effect = TimeoutError("provider-registry unreachable")

        intent = "translate my book"
        with _patch_embedding_model(), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            matches, confident = await td.search_catalog_semantic(
                _CATALOG, intent, 8, user_id="u1",
            )
        expected_matches, expected_confident = td.search_catalog(_CATALOG, intent, 8)
        assert matches == expected_matches
        assert confident == expected_confident

    @pytest.mark.asyncio
    async def test_intent_embedding_failure_after_tool_vectors_succeed_still_falls_back(self):
        """The tool-vector batch embed can succeed while the PER-CALL intent
        embed fails (e.g. a transient timeout on the 2nd call) — must still
        degrade to the token-overlap result, not raise."""
        cat = [_tool("glossary_search", "Search glossary entities")]
        calls = {"n": 0}

        async def flaky_embed(*, user_id, model_source, model_ref, texts):
            calls["n"] += 1
            if calls["n"] == 1:
                return EmbeddingResult(embeddings=[[1.0, 0.0]], dimension=2, model="fake")
            raise TimeoutError("intent embed timed out")

        mock_client = AsyncMock()
        mock_client.embed.side_effect = flaky_embed

        intent = "search the glossary"
        with _patch_embedding_model(), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            matches, confident = await td.search_catalog_semantic(
                cat, intent, 8, user_id="u1",
            )
        expected_matches, expected_confident = td.search_catalog(cat, intent, 8)
        assert matches == expected_matches
        assert confident == expected_confident

    @pytest.mark.asyncio
    async def test_tool_vectors_are_cached_only_intent_reembedded_on_a_second_call(self):
        cat = [_tool("glossary_search", "Search glossary entities")]
        embed_calls: list[list[str]] = []

        async def fake_embed(*, user_id, model_source, model_ref, texts):
            embed_calls.append(list(texts))
            return EmbeddingResult(
                embeddings=[[1.0, 0.0] for _ in texts], dimension=2, model="fake",
            )

        mock_client = AsyncMock()
        mock_client.embed.side_effect = fake_embed

        with _patch_embedding_model(), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            await td.search_catalog_semantic(cat, "one", 8, user_id="u1")
            await td.search_catalog_semantic(cat, "two", 8, user_id="u1")
        # Call 1: tool-vector batch embed + intent embed = 2 calls.
        # Call 2: tool-vector cache HIT (same catalog signature + same resolved
        # embedding model) → only the fresh intent embed = 1 more call. Total 3,
        # not 4.
        assert len(embed_calls) == 3

    @pytest.mark.asyncio
    async def test_legacy_and_excluded_tools_never_appear_even_with_a_perfect_embedding_score(self):
        """CAT-4 + the exclude set are enforced BEFORE either score is computed
        — an embeddings-perfect legacy tool must still never surface."""
        cat = [
            _tool("glossary_book_create", "legacy create", visibility="legacy"),
            _tool("glossary_search", "Search glossary entities"),
        ]
        mock_client = AsyncMock()
        mock_client.embed.side_effect = _fake_embed_fixed_map({}, default=[1.0, 0.0])
        with _patch_embedding_model(), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            matches, _ = await td.search_catalog_semantic(
                cat, "add a kind", 8, user_id="u1",
                exclude={"glossary_search"},
            )
        names = [m["name"] for m in matches]
        assert "glossary_book_create" not in names  # CAT-4
        assert "glossary_search" not in names  # exclude set

    # ── HIGH-2 (review-impl) — resolve a REAL embedding-capable model ───────

    @pytest.mark.asyncio
    async def test_uses_the_users_configured_embedding_model_not_the_turn_chat_model(self):
        """`search_catalog_semantic` must resolve the embedding model via
        provider-registry's `embedding`-capability default, not accept/reuse a
        turn's chat model — proven by asserting the embed client actually ran
        (only possible because `_patch_embedding_model()` resolved a model)."""
        cat = [_tool("glossary_search", "Search glossary entities")]
        mock_client = AsyncMock()
        mock_client.embed.side_effect = _fake_embed_fixed_map({}, default=[1.0, 0.0])
        with _patch_embedding_model(("user_model", "bge-m3")), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            await td.search_catalog_semantic(cat, "search the glossary", 8, user_id="u1")
        assert mock_client.embed.await_count > 0
        # The resolved embedding model reached the embed client — never a
        # turn's chat model literal (this function no longer even accepts one).
        for call in mock_client.embed.await_args_list:
            assert call.kwargs["model_source"] == "user_model"
            assert call.kwargs["model_ref"] == "bge-m3"

    @pytest.mark.asyncio
    async def test_no_embedding_model_configured_skips_the_embed_call_entirely(self):
        """HIGH-2 fast pre-network skip: a user with NO `embedding`-capability
        default configured must never reach the embed client at all — straight
        to the token-overlap fallback, no doomed network call."""
        cat = [_tool("glossary_search", "Search glossary entities")]
        mock_client = AsyncMock()
        mock_client.embed.side_effect = AssertionError(
            "embed() must never be called when no embedding model is configured"
        )
        intent = "search the glossary"
        with _patch_embedding_model(None), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            matches, confident = await td.search_catalog_semantic(cat, intent, 8, user_id="u1")
        mock_client.embed.assert_not_awaited()
        expected_matches, expected_confident = td.search_catalog(cat, intent, 8)
        assert matches == expected_matches
        assert confident == expected_confident


class TestToolVectorCacheKeyIncludesModel:
    """HIGH-1 (review-impl) — cross-model cache poisoning fix: the tool-vector
    cache used to key by catalog signature ALONE, so two callers within the
    same 60s TTL window using DIFFERENT embedding models (different
    users/sessions with different BYOK embedding configs) shared the FIRST
    caller's vectors — meaningless since `cosine_similarity` between two
    different embedding models' vector spaces isn't comparable. The cache key
    must now fold in `(model_source, model_ref)` too, so each distinct
    embedding model gets its own independently-computed/cached vector set."""

    def setup_method(self, _method):
        td._TOOL_VECTOR_CACHE.clear()

    @pytest.mark.asyncio
    async def test_two_different_model_refs_against_the_same_catalog_never_share_a_cache_entry(self):
        cat = [_tool("glossary_search", "Search glossary entities")]
        calls: list[tuple[str, str]] = []

        async def fake_embed(*, user_id, model_source, model_ref, texts):
            calls.append((model_source, model_ref))
            # A distinguishable vector per model so a shared/reused vector
            # (the bug) is trivially detectable.
            vec = [1.0, 0.0] if model_ref == "model-a" else [0.0, 1.0]
            return EmbeddingResult(embeddings=[vec for _ in texts], dimension=2, model=model_ref)

        mock_client = AsyncMock()
        mock_client.embed.side_effect = fake_embed

        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            vectors_a = await td._get_tool_vectors(
                cat, user_id="u1", model_source="user_model", model_ref="model-a",
            )
            vectors_b = await td._get_tool_vectors(
                cat, user_id="u2", model_source="user_model", model_ref="model-b",
            )
        # Two DISTINCT embed calls — model-b never hit model-a's cache entry.
        assert len(calls) == 2
        assert vectors_a["glossary_search"] == [1.0, 0.0]
        assert vectors_b["glossary_search"] == [0.0, 1.0]

        # A repeat call for model-a hits its OWN cache entry — no 3rd embed call.
        with patch("app.client.embedding_client.get_embedding_client", return_value=mock_client):
            vectors_a_again = await td._get_tool_vectors(
                cat, user_id="u1", model_source="user_model", model_ref="model-a",
            )
        assert len(calls) == 2
        assert vectors_a_again == vectors_a


class TestToolVectorCacheTTLParity:
    """The tool-vector cache MUST invalidate on the SAME schedule as the tool
    catalog it was computed from (`knowledge_client.py`'s per-user 60s TTL,
    `get_tool_definitions()`) — a drift-lock so a future tune of one constant
    doesn't silently desync the other."""

    def test_ttl_matches_knowledge_client_catalog_ttl(self):
        from app.client.knowledge_client import _TOOL_CATALOG_TTL_S

        assert td.TOOL_VECTOR_CACHE_TTL_S == _TOOL_CATALOG_TTL_S


# ════════════════════════════════════════════════════════════════════════════
# Reconciliation (2026-07-08) — B3 built the retry-cap tracker
# (`FindToolsAttemptTracker`) and the embeddings-backed scorer
# (`search_catalog_semantic`) but, by design (B2 owned `stream_service.py` for
# the tool-call-dedup fix in the same pass), never wired either into the REAL
# `_stream_with_tools()` call path — `session_id` never reached
# `find_tools_result`, and the call site invoked the sync token-overlap
# `find_tools_result` unawaited, so a live `find_tools` call could never
# exercise the embeddings path no matter how well-tested in isolation. This
# class exercises the LIVE call path end-to-end (not `find_tools_result`/
# `search_catalog_semantic` called directly) to prove the wiring, not just the
# underlying units.
# ════════════════════════════════════════════════════════════════════════════


class TestFindToolsLiveWiring:
    def setup_method(self, _method):
        td._TOOL_VECTOR_CACHE.clear()
        td._EMBEDDING_MODEL_CACHE.clear()

    @pytest.mark.asyncio
    async def test_repeated_find_tools_call_in_the_same_live_session_gets_capped(self):
        """A real 3-pass loop: pass 0 and pass 1 each call find_tools with a
        near-duplicate no-match intent in the SAME session — the 2nd must
        carry the retry-cap's "not supported, stop searching" note, proving
        `session_id` now reaches the module-level `find_tools_attempts`
        tracker from the live call path (previously inert in production —
        the old call site never passed it at all).

        `_patch_embedding_model(None)` — this test only cares about the
        retry-cap note wording, not the embeddings blend, so it pins "no
        embedding model configured" (the HIGH-2 fast pre-network skip) to keep
        this deterministic and avoid an unmocked real network call to
        provider-registry."""
        sid = str(uuid4())
        kc = _kc()
        scripts = [
            [tool_frag(0, id="f1", name="find_tools"),
             tool_frag(0, arguments_delta='{"intent":"xyzzy quux frobnicate"}'),
             done("tool_calls")],
            [tool_frag(0, id="f2", name="find_tools"),
             tool_frag(0, arguments_delta='{"intent":"frobnicate quux xyzzy"}'),
             done("tool_calls")],
            [tok("done"), done("stop")],
        ]
        with _patch_embedding_model(None), _patch_client(scripts):
            chunks = await _drain(_stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "hi"}], gen_params={}, tools=[],
                knowledge_client=kc, session_id=sid, project_id="proj-1",
                discovery_catalog=_CATALOG,
                discovery_extra_frontend=frontend_tool_defs(editor=False, book_scoped=False),
            ))

        find_calls = [
            c["tool_call"] for c in chunks if c.get("tool_call", {}).get("tool") == "find_tools"
        ]
        assert len(find_calls) == 2
        assert "try once more" in find_calls[0]["result"]["note"].lower()
        assert "not supported" in find_calls[1]["result"]["note"].lower()
        assert "stop searching" in find_calls[1]["result"]["note"].lower()

    @pytest.mark.asyncio
    async def test_live_find_tools_call_exercises_the_real_embeddings_path(self):
        """Confirms the async wiring genuinely AWAITS the embeddings-backed
        scorer for a real find_tools invocation driven through the loop — not
        just that `find_tools_result_async` can do it when called directly.
        The mocked embedding client proves the async call genuinely fired
        (call count); the fixed embedding vectors (a genuine zero-token-
        overlap case for the token scorer alone, asserted below) prove the
        RESULT the embedding produced is what reaches the model — the
        embeddings path is exercised, not bypassed."""
        cat = [
            _tool("glossary_search", "Search glossary entities"),
            _tool("book_create", "Create a new book"),
        ]
        text_vectors = {
            "glossary search Search glossary entities": [1.0, 0.0],
            "book create Create a new book": [0.0, 1.0],
        }
        fake_embed = _fake_embed_fixed_map(text_vectors, default=[1.0, 0.0])
        mock_client = AsyncMock()
        mock_client.embed.side_effect = fake_embed

        intent = "who is the villain love interest"
        # Sanity: a genuine zero-overlap case for the token scorer alone — the
        # rescue below can ONLY come from the embedding blend actually running.
        base_matches, _ = td.search_catalog(cat, intent, 8)
        assert base_matches == []

        kc = _kc()
        scripts = [
            [tool_frag(0, id="f1", name="find_tools"),
             tool_frag(0, arguments_delta=json.dumps({"intent": intent})),
             done("tool_calls")],
            [tok("done"), done("stop")],
        ]
        with _patch_embedding_model(), \
             patch("app.client.embedding_client.get_embedding_client", return_value=mock_client), \
             _patch_client(scripts):
            chunks = await _drain(_stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "hi"}], gen_params={}, tools=[],
                knowledge_client=kc, session_id=str(uuid4()), project_id="proj-1",
                discovery_catalog=cat,
                discovery_extra_frontend=frontend_tool_defs(editor=False, book_scoped=False),
            ))

        assert mock_client.embed.await_count >= 1  # the async embed path genuinely fired
        find_calls = [
            c["tool_call"] for c in chunks if c.get("tool_call", {}).get("tool") == "find_tools"
        ]
        assert len(find_calls) == 1
        matched_names = [m["name"] for m in find_calls[0]["result"]["tools"]]
        assert "glossary_search" in matched_names
