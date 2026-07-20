"""F18 (dogfood round-4) — the tool_list loop breaker.

`tool_list` returns the COMPLETE category in one shot (no cursor/paging), so a re-list
of a category the model already listed is provably a loop: the answer is already in the
context window. Yet `tool_list` was dispatched EARLIER in the tool loop than the
repeated-read breaker and returned ok=True UNCONDITIONALLY — nothing bounded it, and a
weak model (gemma) called it 28× in one turn and built nothing.

Two earlier fixes were reverted because they used the repeated-read breaker's lever and
BACKFIRED on the weak model:
  * returning an ERROR on repeat framed it as a failure the model "fixes" by retrying
    HARDER (28 → 311 calls);
  * charging budget to force finalization made the model HALLUCINATE a tool-call as text.

This breaker does neither. On a repeat it AUTO-LOADS the category's tools (the real tools
the model was circling become callable) and STEERS it to use them — forward progress,
never a forced stop. Past a per-turn total it also DE-ADVERTISES tool_list (tool_load
stays, so a specific tool is still reachable by name).

These drive the REAL discovery loop through `_stream_with_tools` (a unit test over the
pure `tool_list_result` cannot prove the model stops looping) — same discipline as
test_repeated_read_breaker.py. Pure in-memory (AsyncMock knowledge client, no DB/port),
so no xdist_group mark.
"""

from __future__ import annotations

import json

import pytest

from app.services.agent_surface import AgentSurfaceTracker
from app.services.stream_service import (
    TOOL_LIST_TOTAL_CAP,
    _stream_with_tools,
)
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_tools import _drain, _patch_client, done, tok, tool_frag
from tests.test_tool_discovery import _CATALOG, _kc


def _list_pass(i: int, category: str) -> list:
    """One LLM pass that calls tool_list(category=…) and stops for tool execution."""
    return _list_pass_args(i, {"category": category})


def _list_pass_args(i: int, args: dict) -> list:
    """One LLM pass that calls tool_list with arbitrary args (to exercise omitted /
    normalized category values)."""
    return [
        tool_frag(0, id=f"L{i}", name="tool_list"),
        tool_frag(0, arguments_delta=json.dumps(args)),
        done("tool_calls"),
    ]


_FINAL = [tok("done"), done("stop")]


def _run(scripts, *, kc, tracker):
    return _stream_with_tools(
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=[{"role": "user", "content": "help me"}],
        gen_params={},
        tools=[],
        discovery_catalog=_CATALOG,
        discovery_extra_frontend=[],
        knowledge_client=kc,
        session_id=TEST_SESSION_ID,
        project_id="proj-1",
        surface_tracker=tracker,
    )


def _tool_list_calls(out: list[dict]) -> list[dict]:
    return [
        c["tool_call"]
        for c in out
        if "tool_call" in c and c["tool_call"]["tool"] == "tool_list"
    ]


def _advertised_surfaces(out: list[dict]) -> list[dict]:
    return [c["agent_surface"] for c in out if c.get("agent_surface", {}).get("advertised")]


def _advertised_names(surface: dict) -> set[str]:
    adv = surface["advertised"]
    return set(adv.get("core", [])) | set(adv.get("frontend", [])) | set(adv.get("activated", []))


async def _drive(scripts):
    tracker = AgentSurfaceTracker()
    kc = _kc()
    with _patch_client(scripts):
        out = await _drain(_run(scripts, kc=kc, tracker=tracker))
    return out


class TestFirstListThenRepeat:
    @pytest.mark.asyncio
    async def test_a_single_list_is_untouched(self):
        """The guard must not tax the common case: one list → the complete list, and
        tool_list stays advertised."""
        out = await _drive([_list_pass(0, "book"), _FINAL])
        calls = _tool_list_calls(out)
        assert len(calls) == 1
        assert calls[0]["ok"] is True
        assert "tools" in calls[0]["result"]
        assert {t["name"] for t in calls[0]["result"]["tools"]} >= {"book_create", "book_list"}
        assert "listed_before" not in calls[0]["result"]
        # tool_list never de-advertised on a single list
        assert all("tool_list" in _advertised_names(s) for s in _advertised_surfaces(out))

    @pytest.mark.asyncio
    async def test_the_repeat_steers_and_auto_loads_instead_of_re_listing(self):
        """THE test. The 2nd list of the SAME category is the loop — it must NOT return
        the list again (that is the loop), but auto-LOAD the category's tools and steer."""
        out = await _drive([_list_pass(0, "book"), _list_pass(1, "book"), _FINAL])
        calls = _tool_list_calls(out)
        assert len(calls) == 2

        # 1st call — the real, complete list.
        assert "tools" in calls[0]["result"]
        assert "listed_before" not in calls[0]["result"]

        # 2nd call — the breaker: a SUCCESS (not an error — erroring backfired), carrying
        # the loaded tools + an explicit steer, NOT the raw list again.
        second = calls[1]["result"]
        assert calls[1]["ok"] is True, "the breaker must NOT error (that provoked harder retry)"
        assert second.get("listed_before") is True
        assert set(second["loaded_tools"]) >= {"book_create", "book_list"}
        assert "tool_list" in second["note"].lower()
        assert "tools" not in second, "must not re-return the enumeration it already gave"

        # the auto-load took effect: the NEXT advertised pass carries the book tools as
        # callable (activated) — the model now has somewhere to go besides tool_list.
        assert "book_create" in _advertised_names(_advertised_surfaces(out)[-1])

    @pytest.mark.asyncio
    async def test_distinct_categories_are_not_a_false_loop(self):
        """Listing two DIFFERENT categories is discovery, not a loop — each is a first
        list and gets its complete enumeration (mirrors polling-is-not-a-loop)."""
        out = await _drive([_list_pass(0, "book"), _list_pass(1, "translation"), _FINAL])
        calls = _tool_list_calls(out)
        assert len(calls) == 2
        for c in calls:
            assert "tools" in c["result"]
            assert "listed_before" not in c["result"]


class TestEdges:
    @pytest.mark.asyncio
    async def test_omitted_and_all_collapse_to_the_same_category(self):
        """category-omitted normalizes to "all" — so an omitted list followed by an
        explicit category="all" is the SAME list re-fetched, i.e. a repeat (guards the
        _norm_cat normalization: two spellings of "everything" must not read as two
        distinct first-lists)."""
        out = await _drive([_list_pass_args(0, {}), _list_pass_args(1, {"category": "all"}), _FINAL])
        calls = _tool_list_calls(out)
        assert len(calls) == 2
        assert "listed_before" not in calls[0]["result"]      # omitted → first list of "all"
        assert calls[1]["result"].get("listed_before") is True  # "all" again → repeat

    @pytest.mark.asyncio
    async def test_empty_category_repeat_steers_gracefully(self):
        """A category with no tools must not crash the breaker: the repeat still returns a
        steer (loaded_tools == []) telling the model there is nothing there — not an error."""
        out = await _drive([_list_pass(0, "jobs"), _list_pass(1, "jobs"), _FINAL])
        calls = _tool_list_calls(out)
        assert len(calls) == 2
        second = calls[1]["result"]
        assert calls[1]["ok"] is True
        assert second.get("listed_before") is True
        assert second["loaded_tools"] == []
        assert "none available" in second["note"].lower()


class TestDeAdvertiseBackstop:
    @pytest.mark.asyncio
    async def test_persistent_spam_de_advertises_tool_list(self):
        """A model that keeps calling tool_list past the per-turn total loses it from the
        advertised set entirely — the backstop. tool_load stays reachable, and everything
        it circled is already loaded, so it is never forced to hallucinate a call."""
        n = TOOL_LIST_TOTAL_CAP + 1
        out = await _drive([_list_pass(i, "book") for i in range(n)] + [_FINAL])
        surfaces = _advertised_surfaces(out)
        # an early pass advertised tool_list; a later pass (after the cap) does not.
        assert "tool_list" in _advertised_names(surfaces[0])
        assert "tool_list" not in _advertised_names(surfaces[-1])
