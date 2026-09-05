"""Tests for the K21-B tool-calling loop in stream_service.

Phase K21 Cycle B (KNOWLEDGE_SERVICE_K21B_DESIGN §5) — `_stream_with_tools`
is the new async generator that wraps `client.stream()` in an
iteration so the LLM can call knowledge-service memory tools
mid-response. These tests script `loreweave_llm.Client.stream()` pass
by pass to exercise the loop's branches.

Mocking strategy
----------------
`_stream_with_tools` constructs `Client(...)` directly (the symbol
imported into `app.services.stream_service`). We patch that symbol with
a `_FakeClient` class whose `.stream(request)` pops the next scripted
event list off a queue and yields it as an async generator, and whose
`.aclose()` is an async no-op. Each `_FakeClient` records every
`StreamRequest` it was handed so tests can assert on `tools` /
`tool_choice` per pass.

The SDK event objects (`TokenEvent`, `ToolCallEvent`, ...) are the real
pydantic models — `_stream_with_tools` dispatches on `isinstance`, so
the events must be genuine instances.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from loreweave_llm import (
    DoneEvent,
    LLMError,
    ReasoningEvent,
    TokenEvent,
    ToolCallEvent,
    UsageEvent,
)

from app.config import settings
from app.services.stream_service import (
    MAX_TOOL_ITERATIONS,
    _Usage,
    _collapse_identical_tool_calls,
    _drop_duplicate_empty_tool_calls,
    _extract_leaked_tool_calls,
    _flush_activated_tools,
    _narrated_uncalled_writes,
    _parse_tool_args,
    _rail_is_in_flight,
    _reassemble_tool_calls,
    _split_interior_leaked_tool_calls,
    _split_safe_emit,
    _stream_via_gateway,
    _stream_with_tools,
)
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID


# ── event-builder shorthands ────────────────────────────────────────────────


def tok(delta: str) -> TokenEvent:
    return TokenEvent(delta=delta)


def reasoning(delta: str) -> ReasoningEvent:
    return ReasoningEvent(delta=delta)


def usage(inp: int, out: int) -> UsageEvent:
    return UsageEvent(input_tokens=inp, output_tokens=out)


def done(reason: str = "stop") -> DoneEvent:
    return DoneEvent(finish_reason=reason)


def tool_frag(
    index: int = 0,
    id: str | None = None,
    name: str | None = None,
    arguments_delta: str = "",
) -> ToolCallEvent:
    """One incremental ToolCallEvent fragment. The gateway sends `id` +
    `name` on the first fragment for an index, `arguments_delta` on the
    rest (design D4)."""
    return ToolCallEvent(
        index=index, id=id, name=name, arguments_delta=arguments_delta
    )


# ── fake loreweave_llm.Client ───────────────────────────────────────────────


class _FakeClient:
    """Stand-in for `loreweave_llm.Client`.

    `scripts` is a list of pass-scripts; each script is a list of SDK
    events OR an Exception instance. The Nth `client.stream()` call
    replays `scripts[N]` — yielding the events, or raising the exception
    if the script *is* an exception.

    `requests` records every `StreamRequest` handed to `.stream()` so a
    test can assert tools / tool_choice per pass.
    """

    # class-level — set by the test before patching Client in
    _scripts: list = []
    instances: list["_FakeClient"] = []

    def __init__(self, **kwargs):
        self.init_kwargs = kwargs
        self.requests: list = []
        self._call_index = 0
        self.closed = False
        self.cancelled: list = []  # M3 — stream_job_ids cancelled on disconnect
        _FakeClient.instances.append(self)

    async def cancel_job(self, job_id):
        self.cancelled.append(str(job_id))

    def stream(self, request):
        self.requests.append(request)
        script = self._scripts[self._call_index]
        self._call_index += 1

        async def _gen():
            if isinstance(script, BaseException):
                raise script
            for ev in script:
                yield ev

        return _gen()

    async def aclose(self):
        self.closed = True


def _patch_client(scripts: list):
    """Context-manager: patch `Client` in stream_service with a
    `_FakeClient` whose `.stream()` replays `scripts` pass by pass."""
    _FakeClient._scripts = scripts
    _FakeClient.instances = []
    return patch("app.services.stream_service.Client", _FakeClient)


def _envelope(success: bool = True, result: dict | None = None, error: str | None = None) -> dict:
    """The {success, result, error} envelope knowledge_client.execute_tool
    returns (mirrors knowledge-service ToolExecuteResponse)."""
    return {"success": success, "result": result, "error": error}


async def _drain(gen) -> list[dict]:
    """Collect every chunk an async generator yields."""
    out: list[dict] = []
    async for c in gen:
        out.append(c)
    return out


# ── M3 (chat disconnect-cancel) ──────────────────────────────────────────────


async def test_via_gateway_mints_job_id_and_disconnect_uses_cascade():
    """A stream aborted mid-flight (consumer aclose → GeneratorExit) unwinds to the
    helper's aclose() — the SILENT cascade frees the slot + finalizes the row. Chat
    must NOT issue an explicit DELETE (that path notifies → 'Chat cancelled' spam)."""
    scripts = [[tok("hel"), tok("lo"), usage(1, 2), done()]]
    with _patch_client(scripts):
        gen = _stream_via_gateway(
            "user_model", str(TEST_MODEL_REF), str(TEST_USER_ID),
            [{"role": "user", "content": "hi"}], {},
        )
        first = await gen.__anext__()
        assert first["content"] == "hel"
        await gen.aclose()  # client disconnected mid-stream
    client = _FakeClient.instances[0]
    assert client.requests[0].stream_job_id, "stream_job_id must be minted + sent"
    assert client.closed, "aclose must run (the cascade that finalizes the row)"
    assert client.cancelled == [], "no explicit DELETE on disconnect (no notify spam)"


async def test_via_gateway_mints_job_id_on_natural_completion():
    """A completed stream mints + sends the id (so the observability row exists)
    and issues no explicit cancel."""
    scripts = [[tok("hi"), usage(1, 1), done()]]
    with _patch_client(scripts):
        out = await _drain(_stream_via_gateway(
            "user_model", str(TEST_MODEL_REF), str(TEST_USER_ID),
            [{"role": "user", "content": "hi"}], {},
        ))
    client = _FakeClient.instances[0]
    assert client.requests[0].stream_job_id  # minted (row exists)
    assert client.cancelled == []
    assert client.closed
    assert out[-1]["finish_reason"] == "stop"


def _run(
    scripts: list,
    *,
    knowledge_client,
    messages: list[dict] | None = None,
    tools: list[dict] | None = None,
    gen_params: dict | None = None,
    project_id: str | None = "proj-1",
    planner_model_ref: str | None = None,
    max_iterations: int = MAX_TOOL_ITERATIONS,
    discovery_catalog: list[dict] | None = None,
):
    """Build a `_stream_with_tools` async generator with sane defaults.

    🔴 **THE DEFAULT ADVERTISED SET NOW COVERS WHAT THE SCRIPT CALLS, AND THAT IS A CONSEQUENCE OF
    CP-5.10 RATHER THAN A CONVENIENCE.** Before that row, `tools` was *"something to put in front of
    the model"* and the dispatch path never consulted it; the check landed 2026-08-10 and coupled
    **advertised** to **dispatchable**, so twelve tests that dispatch a tool they never advertised
    (`composition_list_outline`, `glossary_plan`, `plan_propose_spec`, …) began receiving
    `unknown_tool` instead of exercising the loop behaviour they are about. **They were red at
    `HEAD` and nobody noticed, because the CP-5 rows were verified with `-k cp…` and the full suite
    was never run.**

    The default is widened rather than the check weakened: a test that passes `tools=` explicitly
    still controls its own surface, so a future test CAN assert the refusal. And nothing is blinded
    here — 5.10's guard is `test_cp5_namesource.py`, which reads the dispatch source directly, plus
    the live measurement of 353 real calls with zero false refusals.
    """
    if tools is None:
        # A pass-script may be a bare exception (the capability-fallback tests raise mid-stream),
        # so only list-shaped passes are scanned.
        _called = sorted({
            ev.name for s in scripts if isinstance(s, list) for ev in s
            if isinstance(ev, ToolCallEvent) and ev.name
        })
        tools = [{"type": "function", "function": {"name": n}}
                 for n in (_called or ["memory_search"])]
    return _stream_with_tools(
        discovery_catalog=discovery_catalog,
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=messages if messages is not None else [{"role": "user", "content": "hi"}],
        gen_params=gen_params or {},
        tools=tools,
        knowledge_client=knowledge_client,
        session_id=TEST_SESSION_ID,
        project_id=project_id,
        planner_model_ref=planner_model_ref,
        max_iterations=max_iterations,
    )


# ════════════════════════════════════════════════════════════════════════════
# _parse_tool_args — pure unit
# ════════════════════════════════════════════════════════════════════════════


class TestParseToolArgs:
    def test_valid_json_object(self):
        assert _parse_tool_args('{"q": "Kai", "limit": 3}') == {"q": "Kai", "limit": 3}

    def test_empty_string_yields_empty_dict(self):
        assert _parse_tool_args("") == {}

    def test_malformed_json_yields_empty_dict(self):
        # A half-streamed / truncated arguments string must not raise.
        assert _parse_tool_args('{"q": "Ka') == {}

    def test_non_dict_json_yields_empty_dict(self):
        # A bare JSON array / scalar is valid JSON but not a tool-args
        # object — the loop still needs a dict for execute_tool.
        assert _parse_tool_args('["a", "b"]') == {}
        assert _parse_tool_args("42") == {}
        assert _parse_tool_args('"just a string"') == {}

    def test_whitespace_only_is_not_empty_but_unparseable(self):
        # "   " is truthy so it skips the empty-string short-circuit,
        # then json.loads raises → {}.
        assert _parse_tool_args("   ") == {}

    def test_json_null_yields_empty_dict(self):
        assert _parse_tool_args("null") == {}

    def test_gemma4_native_tokens_are_repaired(self):
        # D-TOOLCALL-GEMMA-TOKEN-LEAK — real string captured live from
        # google/gemma-4-26b-a4b-qat via LM Studio (llama.cpp#21316/#21680):
        # `<|"|>` stands in for a literal quote, object keys are unquoted.
        raw = '{query:<|"|>tình hình thời sự hôm nay<|"|>}'
        assert _parse_tool_args(raw) == {"query": "tình hình thời sự hôm nay"}

    def test_gemma4_leaked_wrapper_is_stripped_and_repaired(self):
        # The same malformation, but with the outer <|tool_call>call:NAME…
        # <tool_call|> wrapper still attached (observed when the provider
        # leaks the whole native token sequence instead of separating out
        # a clean `name` + `arguments` pair).
        raw = (
            '<|tool_call>call:glossary_web_search{query:<|"|>tình hình '
            'thời sự hôm nay<|"|>}<tool_call|>'
        )
        assert _parse_tool_args(raw) == {"query": "tình hình thời sự hôm nay"}

    def test_truncated_stream_is_not_guess_repaired(self):
        # A genuinely truncated (unbalanced-braces) string must NOT be
        # handed to json_repair — it would happily invent a plausible-but-
        # unverifiable closing value. Unbalanced braces stays a hard {}.
        assert _parse_tool_args('{query:<|"|>tình hình') == {}

    def test_minor_syntax_slip_still_repaired_generically(self):
        # Not Gemma-specific — json_repair's general net catches a plain
        # trailing-comma slip from any provider.
        assert _parse_tool_args('{"q": "Kai", "limit": 3,}') == {"q": "Kai", "limit": 3}

    def test_surviving_control_token_is_refused_not_disguised(self):
        # D-TOOLCALL-GEMMA-INTERIOR-LEAK post-condition. `repair_json` will absorb a
        # surviving control token into the nearest string value and hand back JSON that
        # PARSES — which is worse than failing, because every caller downstream then
        # treats a corrupted payload as clean. Live shape (session 019faf5b seq 16): the
        # model's SECOND call was swallowed into the first call's `type` value, and the
        # tool reported `enum: create_kinds"},{params:{description: does not equal any
        # of [...]` — an enum the model never wrote. Must degrade to {}, not to a lie.
        raw = (
            '{ops:[{type:<|"|>create_kinds<|"|>}]}<tool_call|><|channel>thought'
            '<channel|><|tool_call>call:glossary_propose_entities{items:[]}'
        )
        assert _parse_tool_args(raw) == {}

    def test_clean_args_after_the_split_still_parse(self):
        # The head segment `_split_interior_leaked_tool_calls` hands back carries no
        # marker, so the post-condition above must not fire on it.
        assert _parse_tool_args('{ops:[{type:<|"|>create_kinds<|"|>}]}') == {
            "ops": [{"type": "create_kinds"}]
        }


# ════════════════════════════════════════════════════════════════════════════
# _split_interior_leaked_tool_calls — D-TOOLCALL-GEMMA-INTERIOR-LEAK
# ════════════════════════════════════════════════════════════════════════════


class TestSplitInteriorLeakedToolCalls:
    """The model packs several tool calls into ONE args payload, separated by its own
    native control tokens. Recover them as separate calls instead of letting json
    repair swallow them into a value (live: session 019faf5b seq 16 → 10,882 chars of
    repeated prose, author hit Stop)."""

    def test_a_wellformed_provider_is_untouched(self):
        calls = [{"id": "a", "name": "book_read", "arguments": '{"book_id": "b1"}'}]
        assert _split_interior_leaked_tool_calls(list(calls)) == calls

    def test_the_swallowed_second_call_is_recovered(self):
        # The live payload: propose_batch's args carry a whole second call to
        # glossary_propose_entities — the tool the model was CORRECTLY told to use.
        raw = (
            '{ops:[{type:<|"|>create_kinds<|"|>}]}<tool_call|><|channel>thought'
            '<channel|><|tool_call>call:glossary_propose_entities{items:[{name:<|"|>Lâm Uyên<|"|>}]}'
        )
        out = _split_interior_leaked_tool_calls(
            [{"id": "c1", "name": "glossary_propose_batch", "arguments": raw}]
        )
        assert [c["name"] for c in out] == [
            "glossary_propose_batch", "glossary_propose_entities",
        ]
        # Head keeps only its own args, with the marker gone — so it parses honestly.
        assert _parse_tool_args(out[0]["arguments"]) == {"ops": [{"type": "create_kinds"}]}
        # …and the recovered call carries the model's real intent.
        assert _parse_tool_args(out[1]["arguments"]) == {"items": [{"name": "Lâm Uyên"}]}

    def test_a_truncated_trailing_call_is_still_recovered(self):
        # The live capture was cut off mid-call (no closing `<tool_call|>`); the body
        # must run to end-of-string rather than being dropped.
        raw = '{a:1}<|tool_call>call:glossary_propose_entities{items:[{name:<|"|>Kai<|"|>}]}'
        out = _split_interior_leaked_tool_calls(
            [{"id": "c1", "name": "x", "arguments": raw}]
        )
        assert len(out) == 2
        assert out[1]["name"] == "glossary_propose_entities"
        assert _parse_tool_args(out[1]["arguments"]) == {"items": [{"name": "Kai"}]}

    def test_marker_with_no_call_behind_it_leaves_a_clean_head(self):
        # Reasoning-channel tokens with no second call: nothing to recover, but the
        # head must still be stripped so the surviving call parses.
        out = _split_interior_leaked_tool_calls(
            [{"id": "c1", "name": "x", "arguments": '{a:1}<|channel>thought<channel|>'}]
        )
        assert len(out) == 1
        assert _parse_tool_args(out[0]["arguments"]) == {"a": 1}

    def test_a_leading_marker_with_a_real_call_behind_it_drops_the_empty_shell(self):
        # Marker at position 0 → the entry never had args of its own. A real call WAS
        # recovered, so the model's intent is fully carried by it; the shell is dropped
        # rather than dispatched as `{}` (same contract as the sibling dedupe helpers —
        # a dropped call never reaches `working`, so no result is owed for it).
        out = _split_interior_leaked_tool_calls(
            [{"id": "c1", "name": "x",
              "arguments": '<|tool_call>call:book_read{book_id:<|"|>b1<|"|>}'}]
        )
        assert [c["name"] for c in out] == ["book_read"]
        assert _parse_tool_args(out[0]["arguments"]) == {"book_id": "b1"}

    def test_a_marker_only_payload_keeps_its_marker_for_the_dispatch_guard(self):
        # Nothing recoverable and no head → there is no intent to act on. The args must
        # be left EXACTLY as they arrived so the dispatch guard can report an honest
        # "your args were corrupted", instead of the marker being stripped into blank
        # args that dispatch and draw a misleading "missing required field".
        out = _split_interior_leaked_tool_calls(
            [{"id": "c1", "name": "x", "arguments": '<|channel>thought<channel|>'}]
        )
        assert len(out) == 1
        assert out[0]["arguments"] == '<|channel>thought<channel|>'

    def test_ids_are_unique_so_the_provider_never_sees_a_collision(self):
        raw = '{a:1}<|tool_call>call:t1{x:1}<tool_call|><|tool_call>call:t2{y:2}'
        out = _split_interior_leaked_tool_calls(
            [{"id": "c1", "name": "head", "arguments": raw}]
        )
        assert [c["name"] for c in out] == ["head", "t1", "t2"]
        assert len({c["id"] for c in out}) == 3


# ════════════════════════════════════════════════════════════════════════════
# _narrated_uncalled_writes — D-NARRATED-WRITE
# ════════════════════════════════════════════════════════════════════════════


def _tool(name: str, tier: str) -> dict:
    return {"type": "function", "function": {"name": name, "_meta": {"tier": tier}}}


CATALOG = {
    "composition_outline_node_edit": _tool("composition_outline_node_edit", "A"),
    "composition_outline_node_create": _tool("composition_outline_node_create", "A"),
    "composition_get_outline_node": _tool("composition_get_outline_node", "R"),
    "glossary_propose_entities": _tool("glossary_propose_entities", "W"),
}


class TestNarratedUncalledWrites:
    """The 'claimed a write it never made' detector. For an author this is the worst
    failure the turn loop has — they are told the work is done and sent to go look at
    it. Live (Mị Đế 019faf5b seq 32): the model wrote *'5 cảnh hiện đang ở trạng thái
    Draft trong Outline, bạn hãy mở tab Outline để kiểm tra'* after six tool calls, all
    of them reads, with zero outline nodes in the database."""

    def test_names_a_write_it_never_called(self):
        text = ("`composition_outline_node_create`: Tôi đã tạo một Chương 1. "
                "`composition_outline_node_edit`: Tôi đã tạo và điền chi tiết 5 cảnh.")
        assert _narrated_uncalled_writes(
            text, catalog_index=CATALOG, attempted={"composition_get_outline_node"},
        ) == ["composition_outline_node_create", "composition_outline_node_edit"]

    def test_a_write_it_actually_called_is_not_flagged(self):
        # The whole point: only a NARRATED-but-uncalled write counts.
        assert _narrated_uncalled_writes(
            "Tôi đã gọi composition_outline_node_edit và nó trả về node id.",
            catalog_index=CATALOG, attempted={"composition_outline_node_edit"},
        ) == []

    def test_a_write_it_TRIED_and_failed_is_not_flagged(self):
        # A failed attempt already gives the model honest feedback to report; nudging
        # there would be noise on top of a real error.
        assert _narrated_uncalled_writes(
            "composition_outline_node_edit báo lỗi.",
            catalog_index=CATALOG, attempted={"composition_outline_node_edit"},
        ) == []

    def test_a_named_READ_tool_is_never_flagged(self):
        # Nothing was claimed to have changed, so there is nothing for the author to go
        # and not find. Flagging reads would fire on ordinary explanation.
        assert _narrated_uncalled_writes(
            "Mình dùng composition_get_outline_node để xem dàn ý.",
            catalog_index=CATALOG, attempted=set(),
        ) == []

    def test_an_invented_name_is_not_flagged_here(self):
        # An invented tool is a DIFFERENT bug with its own honest message at the dispatch
        # chokepoint ("you invented it"). Conflating the two would tell a model that
        # hallucinated a name to go and call it.
        assert _narrated_uncalled_writes(
            "Tôi sẽ dùng glossary_propose_elements để tạo.",
            catalog_index=CATALOG, attempted=set(),
        ) == []

    def test_ordinary_prose_with_snake_case_words_is_ignored(self):
        # The loose identifier regex is filtered by the CATALOG, so prose that merely
        # contains underscores never trips it.
        assert _narrated_uncalled_writes(
            "value_shift của cảnh này đi từ chaos sang tension, xem mục story_seed.",
            catalog_index=CATALOG, attempted=set(),
        ) == []

    def test_empty_text_is_safe(self):
        assert _narrated_uncalled_writes("", catalog_index=CATALOG, attempted=set()) == []


# ════════════════════════════════════════════════════════════════════════════
# _flush_activated_tools — D-TOOLLOAD-LOST-ON-SUSPEND
# ════════════════════════════════════════════════════════════════════════════


class TestFlushActivatedTools:
    """`tool_load` only survives into the next turn if EVERY way a turn can end writes
    the hot set back. The flush used to live on the normal-completion path alone, and
    the suspend path returns before reaching it — so the one turn that loads a WRITE
    tool (tier A/W ⇒ it suspends for approval) was the one that discarded it."""

    @pytest.mark.asyncio
    async def test_a_dirty_state_is_written_and_marked_clean(self):
        pool = AsyncMock()
        state = {"activated_tools": ["a", "b"], "dirty": True}
        await _flush_activated_tools(pool, "s1", state)
        assert pool.execute.await_count == 1
        assert pool.execute.await_args.args[1:] == ("s1", ["a", "b"])
        # Marked clean so a later exit on the same turn cannot write it twice.
        assert state["dirty"] is False

    @pytest.mark.asyncio
    async def test_a_clean_state_writes_nothing(self):
        pool = AsyncMock()
        await _flush_activated_tools(pool, "s1", {"activated_tools": ["a"], "dirty": False})
        pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_no_state_at_all_is_safe(self):
        pool = AsyncMock()
        await _flush_activated_tools(pool, "s1", None)
        pool.execute.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_db_failure_never_takes_down_the_turn(self):
        # Best-effort by design: losing this costs one re-load next turn, and must not
        # fail a turn that otherwise succeeded.
        pool = AsyncMock()
        pool.execute.side_effect = RuntimeError("db down")
        await _flush_activated_tools(pool, "s1", {"activated_tools": ["a"], "dirty": True})


# ════════════════════════════════════════════════════════════════════════════
# _rail_is_in_flight — D-RAIL-INFLIGHT-ON-ATTEMPT
# ════════════════════════════════════════════════════════════════════════════


class TestRailIsInFlight:
    def test_a_succeeded_step_tool_is_in_flight(self):
        assert _rail_is_in_flight(
            resumed_mid_rail=False,
            step_tools_succeeded=["glossary_adopt_standards"],
            step_tools_attempted=[],
        )

    def test_a_resume_mid_rail_is_in_flight(self):
        # The confirm executes off the backend chokepoint, so it never reaches
        # turn_succeeded — but the rail is unambiguously live.
        assert _rail_is_in_flight(
            resumed_mid_rail=True, step_tools_succeeded=[], step_tools_attempted=[],
        )

    def test_an_ATTEMPTED_but_FAILED_step_tool_is_in_flight(self):
        # THE FIX. Two live incidents, unrelated triggers, identical shape: every tool
        # call in the iteration failed (capability floor withheld the tool / the decoder
        # corrupted its args), so turn_succeeded stayed empty, the step-runner read the
        # rail as "not started", injected nothing, and the model fell into repeated prose
        # (40,597 and 10,882 chars) until the author hit Stop. Intent is what makes a rail
        # live — the model reached for the step; the platform is what stopped it.
        assert _rail_is_in_flight(
            resumed_mid_rail=False,
            step_tools_succeeded=[],
            step_tools_attempted=["glossary_propose_entities"],
        )

    def test_a_turn_that_never_touched_the_rail_is_not_in_flight(self):
        # The rail must NOT be driven on a turn where the author asked something
        # unrelated and the model never reached for a step tool — that is the
        # "governance serves the author" boundary, not something to widen.
        assert not _rail_is_in_flight(
            resumed_mid_rail=False, step_tools_succeeded=[], step_tools_attempted=[],
        )


# ════════════════════════════════════════════════════════════════════════════
# _reassemble_tool_calls — pure unit
# ════════════════════════════════════════════════════════════════════════════


class TestReassembleToolCalls:
    def test_single_call(self):
        frags = {0: {"id": "call_1", "name": "memory_search", "arguments": '{"q":"Kai"}'}}
        calls = _reassemble_tool_calls(frags)
        assert calls == [{"id": "call_1", "name": "memory_search", "arguments": '{"q":"Kai"}'}]

    def test_multiple_calls_ordered_by_index(self):
        # Insert out of index order — output must still be index-sorted.
        frags = {
            2: {"id": "c2", "name": "tool_b", "arguments": "{}"},
            0: {"id": "c0", "name": "tool_a", "arguments": "{}"},
            1: {"id": "c1", "name": "tool_c", "arguments": "{}"},
        }
        calls = _reassemble_tool_calls(frags)
        assert [c["id"] for c in calls] == ["c0", "c1", "c2"]
        assert [c["name"] for c in calls] == ["tool_a", "tool_c", "tool_b"]

    def test_missing_id_and_name_default_to_empty_string(self):
        # A fragment dict that never received an id/name (slot default
        # is None) must collapse to "" not None.
        frags = {0: {"id": None, "name": None, "arguments": ""}}
        calls = _reassemble_tool_calls(frags)
        assert calls == [{"id": "", "name": "", "arguments": ""}]

    def test_missing_arguments_key_defaults_to_empty_string(self):
        frags = {0: {"id": "c0", "name": "t"}}
        calls = _reassemble_tool_calls(frags)
        assert calls[0]["arguments"] == ""

    def test_empty_frags_yields_empty_list(self):
        assert _reassemble_tool_calls({}) == []


# ════════════════════════════════════════════════════════════════════════════
# _stream_with_tools — the loop
# ════════════════════════════════════════════════════════════════════════════


class TestStreamWithToolsNoToolCalls:
    @pytest.mark.asyncio
    async def test_single_pass_text_only(self):
        """A pass that emits only TokenEvents + DoneEvent → the loop
        yields the text chunks then one trailing usage/finish_reason
        chunk and stops after a SINGLE pass (design §4 'no tool calls
        → this pass IS the final response')."""
        kc = AsyncMock()
        scripts = [[tok("Hello"), tok(" world"), usage(10, 5), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # Two text chunks + one trailing chunk.
        text = [c for c in chunks if c.get("content")]
        assert [c["content"] for c in text] == ["Hello", " world"]

        final = chunks[-1]
        assert final["content"] == ""
        assert final["finish_reason"] == "stop"
        assert isinstance(final["usage"], _Usage)
        assert final["usage"].prompt_tokens == 10
        assert final["usage"].completion_tokens == 5

        # Only one client.stream() pass happened.
        assert len(_FakeClient.instances) == 1
        assert len(_FakeClient.instances[0].requests) == 1
        # No tool was executed.
        kc.mcp_execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_reasoning_events_yielded(self):
        """ReasoningEvents surface as reasoning_content chunks (design §4)."""
        kc = AsyncMock()
        scripts = [[reasoning("thinking..."), tok("answer"), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        reasoning_chunks = [c for c in chunks if c.get("reasoning_content")]
        assert [c["reasoning_content"] for c in reasoning_chunks] == ["thinking..."]

    @pytest.mark.asyncio
    async def test_first_pass_offers_tools_with_tool_choice_auto(self):
        """A non-final pass must carry the tools array and
        tool_choice='auto' (design D7)."""
        kc = AsyncMock()
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        req = _FakeClient.instances[0].requests[0]
        # The always-on recovery set appended whenever a pass already offers tools:
        #   the 1 supplied tool (memory_search)
        # + conversation_search       (T6/D6 — recall EARLIER messages in THIS session)
        # + chat_search_sessions      (B1/WS-1.9 — CROSS-session recall; added later, updated here
        #                              by M4/P-2: a concurrent session wired it in and left this
        #                              assertion at the old count of 2. Assert the NAME SET so the
        #                              next addition fails with a meaningful diff, not a magic number.)
        assert req.tools is not None
        assert {t["function"]["name"] for t in req.tools} == {
            "memory_search", "conversation_search", "chat_search_sessions",
        }
        assert req.tool_choice == "auto"

    @pytest.mark.asyncio
    async def test_missing_done_event_falls_back_to_stop(self):
        """If the stream ends without a DoneEvent, finish_reason
        defaults to 'stop' (design §4 `finish or "stop"`)."""
        kc = AsyncMock()
        scripts = [[tok("hi"), usage(1, 1)]]  # no DoneEvent
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))
        assert chunks[-1]["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_client_closed_after_run(self):
        """The SDK client is closed in the finally block."""
        kc = AsyncMock()
        scripts = [[tok("hi"), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))
        assert _FakeClient.instances[0].closed is True


class TestStreamWithToolsOneToolCall:
    @pytest.mark.asyncio
    async def test_one_tool_pass_then_text_pass(self):
        """A pass that emits ToolCallEvent fragments + DoneEvent → the
        loop reassembles them, calls execute_tool, appends the
        assistant+tool messages, and re-streams; a following no-tool
        pass ends it."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(
            success=True, result={"entities": ["Kai"]}
        )
        scripts = [
            # Pass 0 — model calls memory_search.
            [
                tok("Let me check. "),
                tool_frag(index=0, id="call_1", name="memory_search"),
                tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
                usage(10, 4),
                done("tool_calls"),
            ],
            # Pass 1 — model answers in text.
            [tok("Kai is a knight."), usage(8, 6), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # execute_tool was called once with the parsed args.
        kc.mcp_execute_tool.assert_awaited_once()
        call_kwargs = kc.mcp_execute_tool.await_args.kwargs
        assert call_kwargs["tool_name"] == "memory_search"
        assert call_kwargs["tool_args"] == {"query": "Kai"}
        assert call_kwargs["user_id"] == TEST_USER_ID
        assert call_kwargs["session_id"] == TEST_SESSION_ID
        assert call_kwargs["project_id"] == "proj-1"

        # A tool_call chunk was yielded.
        tool_chunks = [c for c in chunks if "tool_call" in c]
        assert len(tool_chunks) == 1
        tc = tool_chunks[0]["tool_call"]
        assert tc["tool"] == "memory_search"
        assert tc["ok"] is True
        assert tc["iteration"] == 0
        assert tc["args"] == {"query": "Kai"}
        assert tc["result"] == {"entities": ["Kai"]}
        assert tc["error"] is None
        # ARCH-1 C3: the provider tool-call id is propagated so the AG-UI
        # TOOL_CALL_* events key on the same id persisted in the message.
        assert tc["id"] == "call_1"

        # Text from BOTH passes was streamed.
        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert text == "Let me check. Kai is a knight."

        # Two passes total.
        assert len(_FakeClient.instances[0].requests) == 2

    @pytest.mark.asyncio
    async def test_assistant_and_tool_messages_appended_to_working(self):
        """After a tool pass, the loop appends one assistant message
        (with tool_calls) and one tool message per call to the working
        list — visible on pass 1's request (design D5)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"ok": 1})
        scripts = [
            [
                tok("preamble"),
                tool_frag(index=0, id="call_x", name="memory_search"),
                tool_frag(index=0, arguments_delta='{"query":"q"}'),
                done("tool_calls"),
            ],
            [tok("final"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        # Pass 1's request carries the appended messages.
        pass1_msgs = _FakeClient.instances[0].requests[1].messages
        # original user + assistant + tool == 3
        assert len(pass1_msgs) == 3

        assistant_msg = pass1_msgs[1]
        assert assistant_msg["role"] == "assistant"
        assert assistant_msg["content"] == "preamble"
        assert assistant_msg["tool_calls"][0]["id"] == "call_x"
        assert assistant_msg["tool_calls"][0]["type"] == "function"
        assert assistant_msg["tool_calls"][0]["function"]["name"] == "memory_search"
        # D-TOOLCALL-HISTORY-ARGS-NOT-JSON: arguments is now re-serialized via
        # _parse_tool_args + json.dumps (always valid JSON, whitespace-normalized)
        # rather than the raw streamed string verbatim — compare semantically.
        assert json.loads(assistant_msg["tool_calls"][0]["function"]["arguments"]) == {"query": "q"}

        tool_msg = pass1_msgs[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_x"
        # tool message content is the JSON-encoded result payload.
        assert json.loads(tool_msg["content"]) == {"ok": 1}

    @pytest.mark.asyncio
    async def test_blank_tool_call_arguments_persisted_as_valid_json_not_empty_string(self):
        """D-TOOLCALL-HISTORY-ARGS-NOT-JSON — live-found via LM Studio's own
        console warning ("Failed to parse function call arguments JSON string
        ''") reproducing identically across two UNRELATED models (gemma AND
        qwen), which ruled out a per-model decoding defect and pointed at a
        shared request-payload bug: this repo was persisting a tool call's raw,
        possibly-EMPTY `arguments` string verbatim into `working`, which then
        gets re-sent to the provider as conversation history on the NEXT pass.
        Per the OpenAI tool-calling wire contract, `function.arguments` must
        always be a JSON-parseable string (minimum `"{}"`) — a literal `""` is
        invalid and made the provider's own history-reconstruction throw on
        every subsequent pass, plausibly corrupting its context and
        perpetuating the very "blank args" pattern this was mistaken for a
        pure model defect. This test proves a call with NO arguments_delta at
        all is persisted as valid, parseable JSON, never the empty string."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"ok": 1})
        scripts = [
            [
                tool_frag(index=0, id="call_blank", name="find_tools"),
                # deliberately no arguments_delta — the model streamed nothing.
                done("tool_calls"),
            ],
            [tok("final"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        pass1_msgs = _FakeClient.instances[0].requests[1].messages
        assistant_msg = pass1_msgs[1]
        raw_args = assistant_msg["tool_calls"][0]["function"]["arguments"]
        assert raw_args != "", "arguments must never be persisted as a literal empty string"
        assert json.loads(raw_args) == {}, "a blank tool call must be re-serialized as valid JSON ({})"

    @pytest.mark.asyncio
    async def test_d7_oversized_success_result_is_withheld_with_notice(self, monkeypatch):
        """D7: a single successful tool result over the per-contributor cap is replaced
        at the dispatch site by a self-correcting overflow notice — the giant dump never
        reaches the model. The tool_call_id pairing is preserved (no orphan)."""
        from app.config import settings
        monkeypatch.setattr(settings, "tool_result_token_cap", 30, raising=False)
        kc = AsyncMock()
        big = {"nodes": [{"i": i, "text": "word " * 40} for i in range(400)]}
        kc.mcp_execute_tool.return_value = _envelope(success=True, result=big)
        scripts = [
            [
                tool_frag(index=0, id="call_big", name="composition_list_outline"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))
        tool_msg = _FakeClient.instances[0].requests[1].messages[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_big"  # pairing intact (no orphan)
        body = json.loads(tool_msg["content"])
        assert body["error"] == "tool_result_overflow"
        assert body["tool"] == "composition_list_outline"
        assert "word word" not in tool_msg["content"]  # the dump is gone

    @pytest.mark.asyncio
    async def test_d7_oversized_error_result_is_not_capped(self, monkeypatch):
        """D7 applies to re-requestable data dumps, not error payloads — a failed tool
        keeps its (already small) error content even with a tiny cap set."""
        from app.config import settings
        monkeypatch.setattr(settings, "tool_result_token_cap", 1, raising=False)
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=False, error="boom")
        scripts = [
            [
                tool_frag(index=0, id="call_e", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))
        tool_msg = _FakeClient.instances[0].requests[1].messages[2]
        assert json.loads(tool_msg["content"]) == {"error": "boom"}

    @pytest.mark.asyncio
    async def test_d13a_collapse_flag_forwarded_to_in_loop_compaction(self, monkeypatch):
        """D13a wiring: the `compact_collapse_duplicates_enabled` config flag reaches the
        in-loop compaction call's `collapse_duplicates` param (a typo'd flag name would
        break this even though the feature ships default-off)."""
        from app.config import settings
        from app.services.compaction import CompactionReport
        monkeypatch.setattr(settings, "compact_collapse_duplicates_enabled", True, raising=False)
        seen: dict = {}

        async def fake_compact(msgs, **kwargs):
            seen.update(kwargs)
            return msgs, CompactionReport()

        monkeypatch.setattr("app.services.stream_service.compact_messages", fake_compact)
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"ok": 1})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        gen = _stream_with_tools(
            model_source="user_model", model_ref=TEST_MODEL_REF, user_id=TEST_USER_ID,
            messages=[{"role": "user", "content": "hi"}], gen_params={},
            tools=[{"type": "function", "function": {"name": "memory_search"}}],
            knowledge_client=kc, session_id=TEST_SESSION_ID, project_id="proj-1",
            effective_limit=8000,  # enables the in-loop compaction guard
        )
        with _patch_client(scripts):
            await _drain(gen)
        assert seen.get("collapse_duplicates") is True

    @pytest.mark.asyncio
    async def test_caller_messages_not_mutated(self):
        """The loop works on a copy — the caller's `messages` list is
        not mutated (design §4 `working = list(messages)`)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        original = [{"role": "user", "content": "hi"}]
        scripts = [
            [
                tool_frag(index=0, id="c1", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, messages=original))
        assert original == [{"role": "user", "content": "hi"}]

    @pytest.mark.asyncio
    async def test_multiple_tool_calls_in_one_pass_by_index(self):
        """A pass emitting two tool calls at index 0 and 1 → both are
        reassembled and executed, one tool_call chunk each (design D4)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            [
                tool_frag(index=0, id="c0", name="memory_search"),
                tool_frag(index=1, id="c1", name="memory_get_entity"),
                tool_frag(index=0, arguments_delta='{"query":"a"}'),
                tool_frag(index=1, arguments_delta='{"name":"b"}'),
                done("tool_calls"),
            ],
            [tok("answer"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        assert kc.mcp_execute_tool.await_count == 2
        names = [c.kwargs["tool_name"] for c in kc.mcp_execute_tool.await_args_list]
        assert names == ["memory_search", "memory_get_entity"]
        args = [c.kwargs["tool_args"] for c in kc.mcp_execute_tool.await_args_list]
        assert args == [{"query": "a"}, {"name": "b"}]

        tool_chunks = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert [t["tool"] for t in tool_chunks] == ["memory_search", "memory_get_entity"]


class TestInteriorLeakThroughTheLoop:
    """D-TOOLCALL-GEMMA-INTERIOR-LEAK end-to-end through `_stream_with_tools`.

    The pure-function tests above prove the split; these prove the LOOP acts on it.
    Reconstructed from the live incident (session 019faf5b seq 16): the model packed a
    second, CORRECT call into the first call's arguments, json repair swallowed it into an
    enum value, the tool blamed the model for a value it never wrote, and the turn ended
    in 10,882 characters of repeated prose."""

    @pytest.mark.asyncio
    async def test_the_swallowed_call_actually_executes(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        # ONE provider tool-call fragment carrying TWO calls.
        leaked = (
            '{query:<|"|>a<|"|>}<tool_call|><|channel>thought<channel|>'
            '<|tool_call>call:memory_get_entity{name:<|"|>b<|"|>}'
        )
        scripts = [
            [
                tool_frag(index=0, id="c0", name="memory_search"),
                tool_frag(index=0, arguments_delta=leaked),
                done("tool_calls"),
            ],
            [tok("answer"), done("stop")],
        ]
        # 🔴 **BOTH NAMES MUST BE ADVERTISED EXPLICITLY, AND THAT IS A FINDING ABOUT CP-5.10.**
        # The second call is not in the script at all — the interior-leak splitter MANUFACTURES it
        # at runtime from the corrupted argument blob. 5.10's name check refuses a dispatch whose
        # tool is in neither of the turn's indexes, so a call this repair reconstructs is refused
        # whenever the extracted tool was not advertised, even though the tool is real and the
        # repair is doing exactly what it exists to do. The default here cannot see the name (it
        # scans `ToolCallEvent.name`), so it is named — and the interaction is recorded rather than
        # papered over. See the RUNSTATE row: *replacing a surface does not carry its guarantees.*
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": n}}
                       for n in ("memory_search", "memory_get_entity")],
            ))

        # BOTH calls dispatch, with their own un-corrupted args — before the fix the
        # second one existed only as text glued inside the first one's `query`.
        assert kc.mcp_execute_tool.await_count == 2
        assert [c.kwargs["tool_name"] for c in kc.mcp_execute_tool.await_args_list] == [
            "memory_search", "memory_get_entity",
        ]
        assert [c.kwargs["tool_args"] for c in kc.mcp_execute_tool.await_args_list] == [
            {"query": "a"}, {"name": "b"},
        ]
        # …and nothing marker-shaped survives into what the UI records.
        for t in (c["tool_call"] for c in chunks if "tool_call" in c):
            assert "<|" not in json.dumps(t["args"], ensure_ascii=False)

    @pytest.mark.asyncio
    async def test_an_unsplittable_leak_is_refused_with_an_honest_error(self):
        """A marker the split cannot resolve into a real call must NOT dispatch, and the
        model must be told the DECODER corrupted its args — not that it sent a bad value.
        Misattributing this is what made the incident unrecoverable."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            [
                tool_frag(index=0, id="c0", name="memory_search"),
                # A bare control token with no `call:NAME{…}` behind it, and the marker
                # first — so the head is empty and there is nothing to recover.
                tool_frag(index=0, arguments_delta='<|channel>{query:<|"|>a<|"|>}'),
                done("tool_calls"),
            ],
            [tok("answer"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        kc.mcp_execute_tool.assert_not_awaited()
        errs = [c["tool_call"]["error"] for c in chunks if "tool_call" in c]
        assert len(errs) == 1
        assert "arrived corrupted" in errs[0]
        # The blame must land on the decoder, and the model must be told to KEEP its
        # tool choice — the opposite of the schema-error message it used to get.
        assert "decoding fault" in errs[0]
        assert "do not change which tool you chose" in errs[0]


class TestNarratedWriteThroughTheLoop:
    """D-NARRATED-WRITE end-to-end. The pure-function tests prove the DETECTOR; this
    proves the LOOP wires it to the whole turn's prose.

    That wiring is the part that was wrong first time and shipped a guard which never
    fired: `text_parts` is re-created every pass, so scanning it caught only the final
    pass. The real shape has the claim and the silence in DIFFERENT passes — the model
    announces "I will now create the scenes", reads a couple of tools, then closes with
    prose that no longer repeats the tool name."""

    @pytest.mark.asyncio
    async def test_a_claim_made_in_an_EARLIER_pass_still_nudges(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        catalog = [
            _tool("composition_outline_node_edit", "A"),
            _tool("composition_get_outline_node", "R"),
        ]
        scripts = [
            # pass 1: names the WRITE tool, then calls only a READ
            [
                tok("Tôi sẽ dùng composition_outline_node_edit để tạo 5 cảnh."),
                tool_frag(index=0, id="c0", name="composition_get_outline_node"),
                tool_frag(index=0, arguments_delta='{"node_id":"n1"}'),
                done("tool_calls"),
            ],
            # pass 2: closes the turn, prose no longer mentions the tool
            [tok("Xong rồi, bạn mở tab Outline để kiểm tra nhé."), done("stop")],
            # pass 3: exists only if the guard nudged
            [tok("Xin lỗi, tôi chưa thực sự tạo cảnh nào."), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, discovery_catalog=catalog))

        client = _FakeClient.instances[0]
        assert len(client.requests) == 3, "the guard must force one more pass"
        # The directive is injected as a synthetic user message on the final request.
        sent = client.requests[-1].messages
        directive = [m for m in sent if str(m.get("content", "")).startswith("[SYSTEM DIRECTIVE]")]
        assert len(directive) == 1
        assert "composition_outline_node_edit" in directive[0]["content"]
        assert "you did not call" in directive[0]["content"]

    @pytest.mark.asyncio
    async def test_the_named_write_tool_is_ARMED_so_the_directive_is_actionable(self):
        """A directive to "call it now" is empty if the tool is not on the wire — and
        off-surface is the usual reason the model narrated instead of calling. Measured
        live: told to `tool_load` first, the model kept reading and re-claiming instead.
        So the guard arms the tool itself, and says so."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        catalog = [_tool("composition_outline_node_edit", "A"), _tool("book_read", "R")]
        scripts = [
            # The write tool is in the CATALOG but never seeded onto this turn's surface.
            [tok("Tôi sẽ dùng composition_outline_node_edit."), done("stop")],
            [tok("Rồi, tôi gọi thật đây."), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, discovery_catalog=catalog))

        client = _FakeClient.instances[0]
        assert len(client.requests) == 2
        # The tool is now actually offered on the nudged pass — not merely talked about.
        offered = {
            t["function"]["name"] for t in (client.requests[-1].tools or [])
            if isinstance(t, dict) and isinstance(t.get("function"), dict)
        }
        assert "composition_outline_node_edit" in offered
        directive = next(
            m for m in client.requests[-1].messages
            if str(m.get("content", "")).startswith("[SYSTEM DIRECTIVE]")
        )
        assert "no tool_load needed" in directive["content"]

    @pytest.mark.asyncio
    async def test_it_nudges_at_most_once_per_turn(self):
        """The cap is load-bearing: a guard against a model talking instead of acting
        must never itself become the loop it prevents."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        catalog = [_tool("composition_outline_node_edit", "A")]
        keeps_claiming = [tok("Tôi dùng composition_outline_node_edit rồi."), done("stop")]
        scripts = [list(keeps_claiming) for _ in range(6)]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, discovery_catalog=catalog))

        client = _FakeClient.instances[0]
        assert len(client.requests) == 2, "one nudge, then the turn ends"

    @pytest.mark.asyncio
    async def test_a_write_actually_called_never_nudges(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        catalog = [_tool("composition_outline_node_edit", "A")]
        scripts = [
            [
                tok("Tôi gọi composition_outline_node_edit đây."),
                tool_frag(index=0, id="c0", name="composition_outline_node_edit"),
                tool_frag(index=0, arguments_delta='{"op":"create"}'),
                done("tool_calls"),
            ],
            [tok("Đã tạo xong."), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, discovery_catalog=catalog))

        client = _FakeClient.instances[0]
        assert len(client.requests) == 2, "no extra pass — the write really happened"


class TestSplitSafeEmit:
    """D-TOOLCALL-GEMMA-TOKEN-LEAK cosmetic fix — the streaming hold-back
    splitter, pure-function."""

    def test_no_marker_flushes_everything(self):
        assert _split_safe_emit("Kai is a knight.") == ("Kai is a knight.", "")

    def test_full_marker_holds_from_its_start(self):
        buf = 'Let me try. <|tool_call>call:x{y:1}<tool_call|>'
        flush, hold = _split_safe_emit(buf)
        assert flush == "Let me try. "
        assert hold == '<|tool_call>call:x{y:1}<tool_call|>'

    def test_partial_marker_at_tail_is_held(self):
        # The marker is arriving one delta at a time; only "<|tool_c" has
        # streamed so far — must NOT flush any of it (could still become the
        # marker OR just be a coincidental "<").
        flush, hold = _split_safe_emit("Let me try. <|tool_c")
        assert flush == "Let me try. "
        assert hold == "<|tool_c"

    def test_bare_angle_bracket_at_buffer_end_is_held_until_disambiguated(self):
        # A trailing "<" (the buffer's LAST char) is indistinguishable from
        # the marker's start yet — held back, not lost; the caller flushes it
        # at pass-end if no leak is ever confirmed (see TestGemmaTokenLeakSalvage).
        # A "<" NOT at the tail (more text already followed it) is unambiguous
        # and flushes immediately — real prose is not held hostage forever.
        assert _split_safe_emit("value is <") == ("value is ", "<")
        assert _split_safe_emit("3 < 5") == ("3 < 5", "")

    def test_accumulating_across_calls_matches_live_streaming(self):
        # Mirrors the main loop: each delta appends to the held buffer, which
        # is re-split every time — a marker delivered in tiny fragments is
        # never partially flushed.
        buf = ""
        for delta in ["Ok. ", "<", "|", "tool_call>", "call:x{y:1}", "<tool_call|>"]:
            buf += delta
            flush, buf = _split_safe_emit(buf)
            assert "<" not in flush  # nothing marker-shaped ever leaks through flush
        assert buf == '<|tool_call>call:x{y:1}<tool_call|>'


class TestExtractLeakedToolCalls:
    """D-TOOLCALL-GEMMA-TOKEN-LEAK — pure-function extraction, live-captured shape."""

    def test_extracts_name_and_raw_body(self):
        text = (
            'Let\'s try again.\n<|tool_call>call:memory_search{query:<|"|>Kai'
            '<|"|>}<tool_call|>'
        )
        assert _extract_leaked_tool_calls(text) == [
            ("memory_search", '{query:<|"|>Kai<|"|>}')
        ]

    def test_no_match_on_clean_text(self):
        assert _extract_leaked_tool_calls("Kai is a knight.") == []

    def test_multiple_leaked_calls_all_extracted(self):
        text = (
            '<|tool_call>call:a{x:<|"|>1<|"|>}<tool_call|> and '
            '<|tool_call>call:b{y:<|"|>2<|"|>}<tool_call|>'
        )
        assert _extract_leaked_tool_calls(text) == [
            ("a", '{x:<|"|>1<|"|>}'),
            ("b", '{y:<|"|>2<|"|>}'),
        ]


class TestGemmaTokenLeakSalvage:
    """D-TOOLCALL-GEMMA-TOKEN-LEAK — the cross-channel recovery in the main
    loop, live-reproduced against google/gemma-4-26b-a4b-qat via LM Studio:
    the model correctly names the intended tool but abandons the structured
    tool_calls channel and dumps its native tokens into plain text/reasoning
    instead. The salvage must still execute the tool the model intended."""

    @pytest.mark.asyncio
    async def test_leaked_call_with_no_structured_tool_frags_is_recovered(self):
        """A pass with ZERO ToolCallEvent fragments — only a leaked pattern in
        the reasoning stream — must still execute the tool and continue the
        loop, not end the turn as if no tool was called."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [
            [
                reasoning("Let me search.\n"),
                reasoning('<|tool_call>call:memory_search{query:<|"|>Kai<|"|>}<tool_call|>'),
                usage(10, 4),
                done("stop"),  # note: NOT "tool_calls" — LM Studio never framed one
            ],
            [tok("Kai is a knight."), usage(8, 6), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        kc.mcp_execute_tool.assert_awaited_once()
        call_kwargs = kc.mcp_execute_tool.await_args.kwargs
        assert call_kwargs["tool_name"] == "memory_search"
        assert call_kwargs["tool_args"] == {"query": "Kai"}

        # The loop continued to a second pass instead of ending on pass 0.
        assert len(_FakeClient.instances[0].requests) == 2
        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert text == "Kai is a knight."
        # D-TOOLCALL-GEMMA-TOKEN-LEAK cosmetic fix — the raw leak marker must
        # never reach the visible content OR reasoning_content stream.
        reasoning_text = "".join(c["reasoning_content"] for c in chunks if c.get("reasoning_content"))
        assert "<|tool_call>" not in text
        assert "<|tool_call>" not in reasoning_text
        assert reasoning_text == "Let me search.\n"

    @pytest.mark.asyncio
    async def test_salvaged_call_on_the_forced_final_pass_still_gets_a_followup(self):
        """D-TOOLCALL-GEMMA-TOKEN-LEAK follow-up (live-repro'd 2026-07-07): the
        leak is most likely on the D7 forced tool-free FINAL pass (tools were
        withheld this pass specifically) — a broken-template model dumps its
        native tokens as plain text once it can't get a real tool_calls slot.
        The pre-existing D7 termination guard ("no tools offered yet the model
        emitted calls → do not loop again") must NOT swallow a genuinely
        salvaged+executed call — the turn needs one more pass so the model can
        use the result, or the tool call succeeding is pointless (nothing ever
        reads the answer)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hits": ["Kai"]})
        scripts = [
            # max_iterations=1 forces last_iter=True (offered_tools=False) on
            # THIS very first pass — reproducing the real scenario exactly.
            [
                reasoning('<|tool_call>call:memory_search{query:<|"|>Kai<|"|>}<tool_call|>'),
                usage(10, 4),
                done("stop"),
            ],
            [tok("Kai is a knight, per the search."), usage(8, 6), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc, max_iterations=1))

        kc.mcp_execute_tool.assert_awaited_once()
        # The loop reached pass 1 — the fix. Before it, the turn ended empty
        # right after the tool call, and this second request never happened.
        assert len(_FakeClient.instances[0].requests) == 2
        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert text == "Kai is a knight, per the search."
        # Cosmetic fix: the leak never reached the visible content stream —
        # the model's real answer is the ONLY thing the user ever sees.
        assert "<|tool_call>" not in text

    @pytest.mark.asyncio
    async def test_leaked_call_for_an_unoffered_tool_is_dropped_not_executed(self):
        """/review-impl MED — a leaked name is free-form regex output, not a
        provider-attested id. Text that happens to match the marker shape (a
        hallucination, or untrusted content the model echoed back from an
        earlier tool RESULT) naming a tool NEVER offered this turn must be
        dropped, not executed — the salvage only recovers calls for tools
        genuinely reachable this turn, closing off an injection-adjacent
        surface without weakening the legitimate-leak case."""
        kc = AsyncMock()
        scripts = [[
            reasoning('<|tool_call>call:evil_tool{query:<|"|>x<|"|>}<tool_call|>'),
            usage(10, 4),
            done("stop"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # Not offered this turn (default tools=[memory_search]) → dropped, so
        # the pass correctly ends as "no tool calls" — a single provider pass,
        # nothing executed.
        kc.mcp_execute_tool.assert_not_called()
        assert len(_FakeClient.instances[0].requests) == 1
        final = chunks[-1]
        assert final["finish_reason"] == "stop"

    @pytest.mark.asyncio
    async def test_bare_angle_bracket_in_real_prose_is_not_lost(self):
        """Real prose whose LAST delta this pass is a bare '<' (ambiguous —
        could be the start of the leak marker, held back live) but no leak
        ever forms must still reach the user, flushed at pass-end once the
        leak scan comes back empty."""
        kc = AsyncMock()
        scripts = [[tok("value is "), tok("<"), usage(5, 3), done("stop")]]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # The "<" was held (not in the first content chunk) yet still
        # reaches the user overall — nothing genuine silently dropped.
        assert [c["content"] for c in chunks if c.get("content")] == ["value is ", "<"]
        kc.mcp_execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_leaked_call_repairs_a_structured_calls_empty_args(self):
        """A pass DOES emit a ToolCallEvent (name known) but its arguments
        never arrive (empty) — the same tool name leaking into plain content
        this pass is the only place the real query survived; use it."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            [
                tool_frag(index=0, id="call_1", name="memory_search"),
                tok('<|tool_call>call:memory_search{query:<|"|>Kai<|"|>}<tool_call|>'),
                usage(10, 4),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        call_kwargs = kc.mcp_execute_tool.await_args.kwargs
        assert call_kwargs["tool_args"] == {"query": "Kai"}


class TestDuplicateEmptyToolCallDedup:
    """D-TOOLCALL-DUP-EMPTY-CALL — a sibling of D-TOOLCALL-GEMMA-TOKEN-LEAK
    (same defective-decoding local-model family), different manifestation:
    the model emits a genuinely well-formed STRUCTURED tool call, then, in
    the SAME pass, a second structured call to the IDENTICAL tool name with
    empty/missing arguments — two distinct entries in the provider's own
    `tool_calls` array (confirmed via real Postgres transcripts: the model's
    own reasoning narrates "calling glossary_web_search twice, the second one
    without a query" but cannot self-correct). Left unhandled, the malformed
    duplicate reaches `execute_tool` and trips a `missing properties`
    validation error — one real session hit this 13+ times before giving up
    or hallucinating an answer. The fix must drop ONLY this narrow pattern,
    never a legitimate second call with its own distinct, valid arguments."""

    # ── pure function ────────────────────────────────────────────────────

    def test_drops_the_malformed_duplicate(self):
        calls = [
            {"id": "c0", "name": "glossary_web_search",
             "arguments": '{"query":"chiến tranh Mỹ và Iran"}'},
            {"id": "c1", "name": "glossary_web_search", "arguments": ""},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == [calls[0]]

    def test_drops_a_duplicate_with_unparseable_arguments_too(self):
        # Not just empty-string — anything _parse_tool_args can't repair
        # into a non-empty dict counts as "empty" for dedup purposes.
        calls = [
            {"id": "c0", "name": "glossary_web_search", "arguments": '{"query":"a"}'},
            {"id": "c1", "name": "glossary_web_search", "arguments": "{"},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == [calls[0]]

    def test_keeps_a_legitimate_second_call_with_distinct_valid_args(self):
        calls = [
            {"id": "c0", "name": "glossary_web_search", "arguments": '{"query":"a"}'},
            {"id": "c1", "name": "glossary_web_search", "arguments": '{"query":"b"}'},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == calls

    def test_keeps_both_when_neither_is_well_formed(self):
        # No well-formed predecessor to be "a duplicate of" — the pre-existing
        # empty-args → validation-error path still applies normally here.
        calls = [
            {"id": "c0", "name": "glossary_web_search", "arguments": ""},
            {"id": "c1", "name": "glossary_web_search", "arguments": ""},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == calls

    def test_ignores_different_tool_names(self):
        calls = [
            {"id": "c0", "name": "glossary_web_search", "arguments": '{"query":"a"}'},
            {"id": "c1", "name": "memory_search", "arguments": ""},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == calls

    def test_single_call_is_untouched(self):
        calls = [{"id": "c0", "name": "glossary_web_search", "arguments": ""}]
        assert _drop_duplicate_empty_tool_calls(calls) == calls

    def test_drops_multiple_consecutive_empty_duplicates(self):
        calls = [
            {"id": "c0", "name": "glossary_web_search", "arguments": '{"query":"a"}'},
            {"id": "c1", "name": "glossary_web_search", "arguments": ""},
            {"id": "c2", "name": "glossary_web_search", "arguments": ""},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == [calls[0]]

    def test_drops_a_non_adjacent_duplicate_interleaved_with_another_tool(self):
        """review-impl MED fix: the old dedup only compared a call to the
        IMMEDIATELY PRECEDING kept call regardless of tool name — for
        [A(good), B(good), A(empty)], the trailing empty A wasn't recognized
        as a duplicate of the earlier A because B sat between them. Now tracks
        the last well-formed call PER TOOL NAME, so this non-adjacent
        duplicate is still caught; B(good) is untouched (a distinct tool)."""
        calls = [
            {"id": "c0", "name": "glossary_web_search", "arguments": '{"query":"a"}'},
            {"id": "c1", "name": "memory_search", "arguments": '{"query":"b"}'},
            {"id": "c2", "name": "glossary_web_search", "arguments": ""},
        ]
        assert _drop_duplicate_empty_tool_calls(calls) == [calls[0], calls[1]]

    # ── integration: the full _stream_with_tools loop ──────────────────────

    @pytest.mark.asyncio
    async def test_malformed_duplicate_dropped_no_validation_error_surfaced(self):
        """A pass with two ToolCallEvent fragments for the SAME tool — index 0
        well-formed, index 1 empty — must execute ONLY the first: the empty
        duplicate never reaches `execute_tool`, so the `missing properties`
        validation error a real backend would return for it is never
        surfaced back to the model at all."""
        kc = AsyncMock()

        async def _execute(*, tool_name, tool_args, **_kw):
            if not tool_args:
                # Mirrors the real backend's behavior on the actual bug —
                # if dedup fails, this is what derails the model 13+ times.
                return _envelope(success=False, error='missing properties: ["query"]')
            return _envelope(success=True, result={"hits": ["ok"]})

        kc.mcp_execute_tool.side_effect = _execute
        scripts = [
            [
                tool_frag(index=0, id="c0", name="glossary_web_search"),
                tool_frag(index=1, id="c1", name="glossary_web_search"),
                tool_frag(index=0, arguments_delta='{"query":"chiến tranh Mỹ và Iran"}'),
                tool_frag(index=1, arguments_delta=""),
                done("tool_calls"),
            ],
            [tok("here are the results"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "glossary_web_search"}}],
            ))

        # Only the well-formed call executed.
        assert kc.mcp_execute_tool.await_count == 1
        call_kwargs = kc.mcp_execute_tool.await_args_list[0].kwargs
        assert call_kwargs["tool_name"] == "glossary_web_search"
        assert call_kwargs["tool_args"] == {"query": "chiến tranh Mỹ và Iran"}

        # Exactly one tool_call chunk, and it succeeded — no validation-error
        # chunk for a dropped second call ever reached the model/UI.
        tool_chunks = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert len(tool_chunks) == 1
        assert tool_chunks[0]["ok"] is True
        assert tool_chunks[0]["error"] is None
        assert not any(
            c.get("tool_call", {}).get("error") for c in chunks if "tool_call" in c
        )

    @pytest.mark.asyncio
    async def test_legitimate_second_call_with_distinct_valid_args_still_executes(self):
        """Two genuinely distinct calls to the SAME tool in one pass (e.g. two
        different searches) must both execute — dedup must never fire when the
        second call carries its own real, non-empty arguments."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [
            [
                tool_frag(index=0, id="c0", name="glossary_web_search"),
                tool_frag(index=1, id="c1", name="glossary_web_search"),
                tool_frag(index=0, arguments_delta='{"query":"a"}'),
                tool_frag(index=1, arguments_delta='{"query":"b"}'),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "glossary_web_search"}}],
            ))

        assert kc.mcp_execute_tool.await_count == 2
        args = [c.kwargs["tool_args"] for c in kc.mcp_execute_tool.await_args_list]
        assert args == [{"query": "a"}, {"query": "b"}]
        tool_chunks = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert len(tool_chunks) == 2
        assert all(t["ok"] for t in tool_chunks)


class TestToolCallFragmentReassembly:
    @pytest.mark.asyncio
    async def test_arguments_delta_concatenated_across_fragments(self):
        """First fragment carries id+name, later fragments carry
        arguments_delta only — the concatenated arguments parse
        correctly (design D4)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            [
                tool_frag(index=0, id="c1", name="memory_search"),
                tool_frag(index=0, arguments_delta='{"que'),
                tool_frag(index=0, arguments_delta='ry":"Ka'),
                tool_frag(index=0, arguments_delta='i Stormblade"}'),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        # The four fragments reassembled into a single valid JSON arg dict.
        assert kc.mcp_execute_tool.await_args.kwargs["tool_args"] == {
            "query": "Kai Stormblade"
        }

    @pytest.mark.asyncio
    async def test_id_and_name_from_first_fragment_only(self):
        """Only the first fragment for an index carries id+name; the
        loop must keep them even though later fragments leave them
        None."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            [
                # First fragment: id + name, no args.
                tool_frag(index=0, id="call_abc", name="memory_search"),
                # Later fragments: args only, id/name are None.
                tool_frag(index=0, id=None, name=None, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # The assistant message's tool_call kept the id from fragment 1.
        pass1_msgs = _FakeClient.instances[0].requests[1].messages
        assert pass1_msgs[1]["tool_calls"][0]["id"] == "call_abc"
        assert pass1_msgs[1]["tool_calls"][0]["function"]["name"] == "memory_search"
        # The tool message echoes that id.
        assert pass1_msgs[2]["tool_call_id"] == "call_abc"


class TestMaxIterationCap:
    @pytest.mark.asyncio
    async def test_five_iteration_cap_forces_tool_free_final_pass(self):
        """A client.stream mock that returns tool calls on every pass —
        the loop must run exactly MAX_TOOL_ITERATIONS passes, the FINAL
        pass must be invoked tool-free (no tools, tool_choice unset —
        design D7), and the loop terminates."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})

        def _tool_pass():
            return [
                tool_frag(index=0, id="c", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ]

        # Every pass emits tool calls. Even the forced-tool-free final
        # pass is scripted to (defiantly) emit tool calls — the loop
        # must still terminate via the post-loop guard, NOT loop forever.
        scripts = [_tool_pass() for _ in range(MAX_TOOL_ITERATIONS)]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        reqs = _FakeClient.instances[0].requests
        # Exactly MAX_TOOL_ITERATIONS passes, no more.
        assert len(reqs) == MAX_TOOL_ITERATIONS

        # Passes 0..N-2 offered tools.
        for r in reqs[:-1]:
            assert r.tools is not None
            assert r.tool_choice == "auto"

        # The FINAL pass is forced tool-free: no tools array, no
        # tool_choice (design D7 — tool_choice="none" style).
        final_req = reqs[-1]
        assert final_req.tools is None
        assert final_req.tool_choice is None

        # The loop terminated and emitted the defensive limit chunk.
        assert chunks[-1]["finish_reason"] == "stop"
        assert isinstance(chunks[-1]["usage"], _Usage)

    @pytest.mark.asyncio
    async def test_final_pass_no_tool_calls_ends_cleanly(self):
        """Realistic D7 path: the forced-tool-free final pass cannot
        emit tool calls, so it falls through to the text-answer return
        (not the post-loop defensive chunk)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})

        def _tool_pass():
            return [
                tool_frag(index=0, id="c", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ]

        # Passes 0..N-2 call tools; the final pass answers in text.
        scripts = [_tool_pass() for _ in range(MAX_TOOL_ITERATIONS - 1)]
        scripts.append([tok("Final answer."), usage(3, 7), done("stop")])
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        assert len(_FakeClient.instances[0].requests) == MAX_TOOL_ITERATIONS
        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert "Final answer." in text
        assert chunks[-1]["finish_reason"] == "stop"


class TestCapabilityFallback:
    @pytest.mark.asyncio
    async def test_tools_not_supported_retries_tool_free(self):
        """An LLMError carrying LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER on
        the first pass → the loop retries tool-free (design D8) and
        completes."""
        kc = AsyncMock()
        exc = LLMError(
            "provider does not support tools",
            code="LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER",
        )
        scripts = [
            exc,  # pass 0 — raises mid-stream.
            [tok("tool-free answer"), usage(5, 5), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        reqs = _FakeClient.instances[0].requests
        # Pass 0 offered tools; pass 1 (the retry) did not.
        assert reqs[0].tools is not None
        assert reqs[1].tools is None
        assert reqs[1].tool_choice is None

        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert text == "tool-free answer"
        assert chunks[-1]["finish_reason"] == "stop"
        kc.mcp_execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_tools_unsupported_via_message_not_code(self):
        """_is_tools_unsupported also matches when the substring is in
        the message, not the .code attr — robustness check."""
        kc = AsyncMock()
        # No code kwarg → .code stays the default "LLM_ERROR"; the
        # TOOLS_NOT_SUPPORTED token lives only in the message.
        exc = LLMError("gateway said TOOLS_NOT_SUPPORTED for this provider")
        scripts = [
            exc,
            [tok("answer"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))
        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert text == "answer"

    @pytest.mark.asyncio
    async def test_non_tools_llm_error_propagates(self):
        """A non-tools LLMError is real — it must propagate, not be
        swallowed by the D8 retry path."""
        kc = AsyncMock()
        exc = LLMError("rate limited", code="LLM_RATE_LIMITED")
        scripts = [exc]
        with _patch_client(scripts):
            with pytest.raises(LLMError, match="rate limited"):
                await _drain(_run(scripts, knowledge_client=kc))

    @pytest.mark.asyncio
    async def test_tools_unsupported_on_non_tool_pass_propagates(self):
        """If the loop already dropped tools and a later pass still
        raises a tools-unsupported error, it must propagate — the D8
        retry only fires when the failing pass actually offered tools
        (`offered_tools` guard)."""
        kc = AsyncMock()
        # Pass 0: tools-unsupported → drop tools, retry.
        # Pass 1 (tool-free retry): another tools-unsupported error.
        #   offered_tools is False here → must propagate, not infinite-loop.
        exc0 = LLMError("a", code="LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER")
        exc1 = LLMError("b TOOLS_NOT_SUPPORTED", code="LLM_TOOLS_NOT_SUPPORTED_FOR_PROVIDER")
        scripts = [exc0, exc1]
        with _patch_client(scripts):
            with pytest.raises(LLMError, match="^b "):
                await _drain(_run(scripts, knowledge_client=kc))


class TestUsageSumming:
    @pytest.mark.asyncio
    async def test_usage_sums_across_passes(self):
        """Each pass is a separate billed gateway job — the trailing
        usage chunk carries the SUM across all passes (design D10)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            # Pass 0 — tool call, usage 10/4.
            [
                tool_frag(index=0, id="c", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                usage(10, 4),
                done("tool_calls"),
            ],
            # Pass 1 — tool call, usage 20/8.
            [
                tool_frag(index=0, id="c2", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                usage(20, 8),
                done("tool_calls"),
            ],
            # Pass 2 — final text answer, usage 5/30.
            [tok("answer"), usage(5, 30), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        final_usage = chunks[-1]["usage"]
        assert final_usage.prompt_tokens == 10 + 20 + 5
        assert final_usage.completion_tokens == 4 + 8 + 30

    @pytest.mark.asyncio
    async def test_usage_summed_even_when_a_pass_omits_usage_event(self):
        """A pass with no UsageEvent contributes 0 — the sum still
        reflects the passes that did report."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            # Pass 0 — tool call, NO usage event.
            [
                tool_frag(index=0, id="c", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            # Pass 1 — final, usage 7/9.
            [tok("answer"), usage(7, 9), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))
        assert chunks[-1]["usage"].prompt_tokens == 7
        assert chunks[-1]["usage"].completion_tokens == 9


class TestToolExecutionFailure:
    @pytest.mark.asyncio
    async def test_tool_failure_does_not_crash_loop(self):
        """A tool execution failure (execute_tool returns success=False)
        does not crash the loop — the error is fed back as the tool
        message and the loop continues to a final text answer."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(
            success=False, result=None, error="entity not found"
        )
        scripts = [
            [
                tool_frag(index=0, id="c1", name="memory_get_entity"),
                tool_frag(index=0, arguments_delta='{"name":"Ghost"}'),
                done("tool_calls"),
            ],
            [tok("I could not find that."), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # The loop completed with a text answer.
        text = "".join(c["content"] for c in chunks if c.get("content"))
        assert text == "I could not find that."
        assert chunks[-1]["finish_reason"] == "stop"

        # The tool_call chunk reflects the failure.
        tc = [c["tool_call"] for c in chunks if "tool_call" in c][0]
        assert tc["ok"] is False
        assert tc["error"] == "entity not found"
        assert tc["result"] is None

        # The tool message fed back to the model carries the error,
        # not a result (design §4 `{"error": envelope.get("error")}`).
        pass1_msgs = _FakeClient.instances[0].requests[1].messages
        tool_msg = pass1_msgs[2]
        assert json.loads(tool_msg["content"]) == {"error": "entity not found"}

    @pytest.mark.asyncio
    async def test_partial_tool_failure_in_multi_call_pass(self):
        """When one of several tool calls fails, the loop still feeds
        every result back and continues."""
        kc = AsyncMock()
        kc.mcp_execute_tool.side_effect = [
            _envelope(success=True, result={"hit": 1}),
            _envelope(success=False, error="boom"),
        ]
        scripts = [
            [
                tool_frag(index=0, id="c0", name="memory_search"),
                tool_frag(index=1, id="c1", name="memory_get_entity"),
                tool_frag(index=0, arguments_delta="{}"),
                tool_frag(index=1, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("ok"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        tool_chunks = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert [t["ok"] for t in tool_chunks] == [True, False]
        # The loop still reached a clean text finish.
        assert chunks[-1]["finish_reason"] == "stop"


class TestProjectIdPassthrough:
    @pytest.mark.asyncio
    async def test_none_project_id_forwarded_to_execute_tool(self):
        """A no-project (Mode 1) chat passes project_id=None straight
        through to execute_tool (design D9 — the executor handles a
        null project)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = [
            [
                tool_frag(index=0, id="c", name="memory_search"),
                tool_frag(index=0, arguments_delta="{}"),
                done("tool_calls"),
            ],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, project_id=None))
        assert kc.mcp_execute_tool.await_args.kwargs["project_id"] is None


class TestPlannerModelRefAuthority:
    """#19 — choosing the planner model is a USER/config decision, never the agent's.
    chat-service is authoritative over the glossary_plan model_ref: a session pin wins,
    and an absent pin STRIPS any model-supplied ref so the per-user Settings default
    (resolved downstream in glossary) applies. Without this a weak model that fills the
    exposed model_ref arg silently overrides the user's selection."""

    def _glossary_plan_script(self, args_json: str):
        return [
            [
                tool_frag(index=0, id="p1", name="glossary_plan"),
                tool_frag(index=0, arguments_delta=args_json),
                done("tool_calls"),
            ],
            [tok("planned"), done("stop")],
        ]

    @pytest.mark.asyncio
    async def test_session_pin_injected_when_model_omits_ref(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = self._glossary_plan_script('{"book_id":"b1","goal":"design ontology"}')
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, planner_model_ref="session-model"))
        assert kc.mcp_execute_tool.await_args.kwargs["tool_args"]["model_ref"] == "session-model"

    @pytest.mark.asyncio
    async def test_session_pin_overrides_model_supplied_ref(self):
        """The fix: a model that fills model_ref does NOT bypass the user's session pin."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = self._glossary_plan_script(
            '{"book_id":"b1","goal":"x","model_ref":"model-hallucinated"}'
        )
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, planner_model_ref="session-model"))
        assert kc.mcp_execute_tool.await_args.kwargs["tool_args"]["model_ref"] == "session-model"

    @pytest.mark.asyncio
    async def test_model_supplied_ref_stripped_when_no_session_pin(self):
        """No session pin → the model's guess is removed so glossary resolves the
        per-user Settings 'planner' default (not whatever the model invented)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = self._glossary_plan_script(
            '{"book_id":"b1","goal":"x","model_ref":"model-hallucinated"}'
        )
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, planner_model_ref=None))
        assert "model_ref" not in kc.mcp_execute_tool.await_args.kwargs["tool_args"]

    # D-PLANFORGE-DEFAULT-MODEL — plan_propose_spec now gets the SAME authority
    # treatment as glossary_plan (composition-service resolves a fallback when
    # model_ref is absent instead of hard-erroring "model_ref required").
    def _plan_propose_script(self, args_json: str):
        return [
            [
                tool_frag(index=0, id="p1", name="plan_propose_spec"),
                tool_frag(index=0, arguments_delta=args_json),
                done("tool_calls"),
            ],
            [tok("proposed"), done("stop")],
        ]

    @pytest.mark.asyncio
    async def test_plan_propose_spec_session_pin_injected_when_model_omits_ref(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = self._plan_propose_script(
            '{"book_id":"b1","source_markdown":"x","mode":"llm"}'
        )
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, planner_model_ref="session-model"))
        assert kc.mcp_execute_tool.await_args.kwargs["tool_args"]["model_ref"] == "session-model"

    @pytest.mark.asyncio
    async def test_plan_propose_spec_session_pin_overrides_model_supplied_ref(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = self._plan_propose_script(
            '{"book_id":"b1","source_markdown":"x","mode":"llm","model_ref":"model-hallucinated"}'
        )
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, planner_model_ref="session-model"))
        assert kc.mcp_execute_tool.await_args.kwargs["tool_args"]["model_ref"] == "session-model"

    @pytest.mark.asyncio
    async def test_plan_propose_spec_model_supplied_ref_stripped_when_no_session_pin(self):
        """No session pin -> the model's guess is removed so composition-service's
        resolve_planner_model fallback applies (not whatever the model invented)."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={})
        scripts = self._plan_propose_script(
            '{"book_id":"b1","source_markdown":"x","mode":"llm","model_ref":"model-hallucinated"}'
        )
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc, planner_model_ref=None))
        assert "model_ref" not in kc.mcp_execute_tool.await_args.kwargs["tool_args"]


class TestPlannerHardStop:
    """#18 — the planner has no ReAct loop in CODE; the "loops forever" is the chat
    agent re-calling the heavy (~39s) glossary_plan in a self-recheck cycle, gated only
    by a SOFT skill rule. Logic — not the prompt — must bound it: the FIRST glossary_plan
    a turn runs; a 2nd+ call in the SAME tool loop is short-circuited WITHOUT executing,
    with a tool result steering the model to present/confirm the plan it already has."""

    @pytest.mark.asyncio
    async def test_second_glossary_plan_in_a_turn_is_short_circuited(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"plan": "p"})
        scripts = [
            # Pass 0 — first glossary_plan: runs for real.
            [
                tool_frag(index=0, id="p1", name="glossary_plan"),
                tool_frag(index=0, arguments_delta='{"book_id":"b1","goal":"design"}'),
                done("tool_calls"),
            ],
            # Pass 1 — the self-recheck: a SECOND glossary_plan. Must NOT execute.
            [
                tool_frag(index=0, id="p2", name="glossary_plan"),
                tool_frag(index=0, arguments_delta='{"book_id":"b1","goal":"recheck"}'),
                done("tool_calls"),
            ],
            # Pass 2 — model gives up re-planning and answers.
            [tok("here is the plan"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # The planner ran EXACTLY once — the 2nd call never reached the MCP transport.
        assert kc.mcp_execute_tool.await_count == 1
        assert kc.mcp_execute_tool.await_args.kwargs["tool_name"] == "glossary_plan"

        # The short-circuited 2nd call still surfaces a failed tool_call so the FE/model
        # sees it, carrying guidance (not a silent drop).
        plan_chunks = [
            c["tool_call"] for c in chunks
            if "tool_call" in c and c["tool_call"]["tool"] == "glossary_plan"
        ]
        assert len(plan_chunks) == 2
        assert plan_chunks[0]["ok"] is True
        assert plan_chunks[1]["ok"] is False
        assert plan_chunks[1]["id"] == "p2"
        assert "again" in (plan_chunks[1]["error"] or "").lower()

    @pytest.mark.asyncio
    async def test_single_glossary_plan_is_unaffected(self):
        """The common, correct case — ONE plan per turn — runs normally."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"plan": "p"})
        scripts = [
            [
                tool_frag(index=0, id="p1", name="glossary_plan"),
                tool_frag(index=0, arguments_delta='{"book_id":"b1","goal":"design"}'),
                done("tool_calls"),
            ],
            [tok("planned"), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))
        kc.mcp_execute_tool.assert_awaited_once()


# ════════════════════════════════════════════════════════════════════════════
# W1 — tool-schema token measurement at the advertise chokepoint
# ════════════════════════════════════════════════════════════════════════════


class TestW1SchemaTokens:
    """The first pass that OFFERS tools yields exactly one
    {"schema_tokens": {frontend_tool_schemas, mcp_tool_schemas}} chunk —
    the previously-unmeasured hidden bucket of the context breakdown."""

    @pytest.mark.asyncio
    async def test_first_pass_reports_split_schema_tokens(self):
        kc = AsyncMock()
        tools = [
            {"type": "function", "function": {
                "name": "memory_search",
                "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
            }},
            # confirm_action is in FRONTEND_TOOL_NAMES → the frontend bucket. (propose_edit
            # moved to ai-gateway in Phase 2, so a still-frontend tool fills the bucket here.)
            {"type": "function", "function": {
                "name": "confirm_action",
                "parameters": {"type": "object", "properties": {"confirm_token": {"type": "string"}}},
            }},
        ]
        scripts = [[tok("hi"), usage(1, 1), done()]]
        with _patch_client(scripts):
            out = await _drain(_run(scripts, knowledge_client=kc, tools=tools))
        st = [c for c in out if "schema_tokens" in c]
        assert len(st) == 1, "measured once per turn, at the first advertise"
        split = st[0]["schema_tokens"]
        assert set(split) == {"frontend_tool_schemas", "mcp_tool_schemas"}
        assert split["frontend_tool_schemas"] > 0
        assert split["mcp_tool_schemas"] > 0
        # It is the FIRST chunk (before any token), so a consumer can fold it
        # into the finish-time frame regardless of how the turn ends.
        assert "schema_tokens" in out[0]

    @pytest.mark.asyncio
    async def test_no_tools_no_schema_chunk(self):
        kc = AsyncMock()
        scripts = [[tok("hi"), usage(1, 1), done()]]
        with _patch_client(scripts):
            out = await _drain(_run(scripts, knowledge_client=kc, tools=[]))
        assert [c for c in out if "schema_tokens" in c] == []


class TestConversationSearchDispatch:
    """T6/D6 — a model call to conversation_search is CONSUMER-LOCAL: it runs the
    session-scoped recovery read in-process (never mcp_execute_tool) and feeds the
    shaped result back. Proves the WIRING effect, not just the advertise."""

    @pytest.mark.asyncio
    async def test_call_dispatches_locally_with_session_scope(self, monkeypatch):
        kc = AsyncMock()
        captured: dict = {}

        async def _fake_run(pool, *, session_id, owner_user_id, args):
            captured["session_id"] = session_id
            captured["owner"] = owner_user_id
            captured["args"] = args
            return {"query": "Kai", "count": 1,
                    "hits": [{"turn": 2, "role": "user", "snippet": "Kai is a knight"}]}

        # No DB in a unit test — stub the pool getter + the shaper (both imported
        # into stream_service's namespace).
        monkeypatch.setattr("app.services.stream_service.get_pool", lambda: object())
        monkeypatch.setattr(
            "app.services.stream_service.run_conversation_search", _fake_run)

        scripts = [
            [tok("let me check. "),
             tool_frag(index=0, id="cs1", name="conversation_search"),
             tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
             usage(5, 2), done("tool_calls")],
            [tok("Kai is a knight."), usage(3, 2), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        # Consumer-local: the generic MCP executor is NEVER touched.
        kc.mcp_execute_tool.assert_not_awaited()
        # The engine got the tenancy scoping the recovery read requires.
        assert captured["args"] == {"query": "Kai"}
        assert captured["owner"] == TEST_USER_ID
        assert captured["session_id"] == TEST_SESSION_ID

        tool_chunks = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert len(tool_chunks) == 1
        tc = tool_chunks[0]
        assert tc["tool"] == "conversation_search"
        assert tc["ok"] is True
        assert tc["result"]["count"] == 1
        assert tc["error"] is None
        assert tc["id"] == "cs1"
        # The final text pass ran after the recovered fact was fed back.
        assert any(c.get("content") == "Kai is a knight." for c in chunks)

    @pytest.mark.asyncio
    async def test_engine_error_maps_to_not_ok(self, monkeypatch):
        kc = AsyncMock()

        async def _err_run(pool, *, session_id, owner_user_id, args):
            return {"error": "conversation_search could not read the history: boom"}

        monkeypatch.setattr("app.services.stream_service.get_pool", lambda: object())
        monkeypatch.setattr(
            "app.services.stream_service.run_conversation_search", _err_run)

        scripts = [
            [tool_frag(index=0, id="cs2", name="conversation_search"),
             tool_frag(index=0, arguments_delta='{"query":"x"}'),
             done("tool_calls")],
            [tok("done"), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        tc = next(c["tool_call"] for c in chunks if "tool_call" in c)
        # A DB blip surfaces as a not-ok tool call the model can self-correct from.
        assert tc["ok"] is False
        assert tc["result"] is None
        assert "boom" in tc["error"]


# ════════════════════════════════════════════════════════════════════════════
# Phase 0 (frontend-tools → MCP migration) — the wired MCP-native validation seam
# ════════════════════════════════════════════════════════════════════════════


class TestFrontendToolValidationSeam:
    """A frontend tool whose args fail its OWN canonical JSON-Schema is rejected
    with the standard `required: missing properties` signal and the run
    CONTINUES — it must never suspend an un-appliable card (the reported bug,
    session 019f771a: propose_edit called with propose_record_edit's args). A
    well-formed call still suspends exactly as before."""

    @pytest.mark.asyncio
    async def test_bad_frontend_args_rejected_and_not_suspended(self):
        # The Phase 0 seam still guards the REMAINING frontend tools (confirm_action,
        # glossary_*, propose_record_edit). propose_edit's own incident-shape rejection
        # moved to ai-gateway (propose-edit-tool.spec.ts) in Phase 2. Here confirm_action
        # (requires confirm_token+descriptor+title) is called with the record-edit shape
        # → the seam rejects it BEFORE suspending, feeding the model the repair signal.
        from tests._v1_tool_fixtures import CONFIRM_ACTION_TOOL

        kc = AsyncMock()
        incident_args = {
            "domain": "book",
            "resource_ref": {"book_id": "b", "chapter_id": "c"},
            "changes": [{"field_label": "Body", "old_value": "a", "new_value": "b", "target": "body"}],
        }
        scripts = [
            [
                tool_frag(index=0, id="call_x", name="confirm_action"),
                tool_frag(index=0, arguments_delta=json.dumps(incident_args)),
                done("tool_calls"),
            ],
            [tok("Let me correct that."), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc, tools=[CONFIRM_ACTION_TOOL]))

        # NEVER suspended — no un-appliable card was rendered.
        assert not any("suspend" in c for c in chunks)
        tcs = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert len(tcs) == 1
        assert tcs[0]["tool"] == "confirm_action"
        assert tcs[0]["ok"] is False
        # 🔴 THE ASSERTION IS THE PROPERTY, NOT THE PHRASE. This pinned the literal string
        # "required: missing properties" — the Phase-0 frontend validator's wording. V7 moved
        # confirm_action to ai-gateway, so the refusal now comes from the standard arg-validation
        # path and reads "is missing required argument(s): [...] Do NOT guess a value and do NOT
        # substitute a placeholder". The safety property never changed; only the sentence did, and
        # a test that pins a sentence reds on an improvement to it.
        #
        # What must hold (IN-6, self-correcting one-liner): the refusal NAMES the missing argument
        # and tells the model what to do. A bare "invalid arguments" would pass neither clause.
        err = tcs[0]["error"]
        assert "confirm_token" in err, f"the refusal does not name the missing arg: {err}"
        assert "missing" in err.lower(), f"the refusal does not say what is wrong: {err}"
        assert chunks[-1]["finish_reason"] == "stop"
        # Rejected BEFORE dispatch — the bad call never reached a backend, frontend tool or not.
        kc.mcp_execute_tool.assert_not_called()

    @pytest.mark.asyncio
    async def test_valid_frontend_args_still_suspend(self):
        from tests._v1_tool_fixtures import CONFIRM_ACTION_TOOL

        kc = AsyncMock()
        good = {"confirm_token": "tok", "descriptor": "book.publish", "title": "Publish?", "domain": "book"}
        scripts = [
            [
                tool_frag(index=0, id="call_ok", name="confirm_action"),
                tool_frag(index=0, arguments_delta=json.dumps(good)),
                done("tool_calls"),
            ],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc, tools=[CONFIRM_ACTION_TOOL]))

        susp = [c["suspend"] for c in chunks if "suspend" in c]
        assert len(susp) == 1
        assert susp[0]["pending_tool_call"]["name"] == "confirm_action"
        assert susp[0]["pending_tool_call"]["args"] == good


class TestTaskGateSuspend:
    """ext-tasks (T1c(3)) — a backend tool returning a task envelope (a capability-
    gated domain gate: composition_create_derivative) suspends the run with the task
    MARKED, so resume drives the domain's provide-input tool instead of a client
    execution. Dormant on the current stack (nothing declares tasks caps)."""

    @pytest.mark.asyncio
    async def test_backend_task_envelope_suspends_with_task_marker(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = {
            "success": True, "result": None, "error": None,
            "task": {"taskId": "task_z", "status": "input_required",
                     "inputRequests": {"title": "Spawn dị bản?"}},
        }
        scripts = [
            [
                tool_frag(index=0, id="call_g", name="composition_create_derivative"),
                tool_frag(index=0, arguments_delta='{"project_id":"p","name":"AU"}'),
                done("tool_calls"),
            ],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "composition_create_derivative"}}],
            ))

        susp = [c["suspend"] for c in chunks if "suspend" in c]
        assert len(susp) == 1
        pend = susp[0]["pending_tool_call"]
        assert pend["name"] == "composition_create_derivative"
        assert pend["task"] == {"taskId": "task_z", "status": "input_required",
                                "inputRequests": {"title": "Spawn dị bản?"}}


class TestCollapseIdenticalToolCalls:
    """D-TOOLCALL-DUP-IDENTICAL — byte-identical calls in ONE pass collapse to one.

    Measured live over 24h of transcripts (2026-07-23): affected sessions had
    `count(DISTINCT args) = 1` across 3-4 calls of the same tool, all at `iteration: 0`
    — parallel duplicates in a single emission, not sequential retries. A CORRECTNESS
    fix: a write tool without its own idempotency would run N times for one user intent.
    """

    def test_collapses_byte_identical_repeats(self):
        args = '{"book_id":"b1","items":[{"name":"Lâm Uyên","kind":"character"}]}'
        calls = [
            {"id": "c0", "name": "glossary_propose_entities", "arguments": args},
            {"id": "c1", "name": "glossary_propose_entities", "arguments": args},
            {"id": "c2", "name": "glossary_propose_entities", "arguments": args},
        ]
        assert _collapse_identical_tool_calls(calls) == [calls[0]]

    def test_collapses_args_differing_only_in_key_order_or_whitespace(self):
        calls = [
            {"id": "c0", "name": "tool_list", "arguments": '{"category":"glossary"}'},
            {"id": "c1", "name": "tool_list", "arguments": '{ "category" : "glossary" }'},
        ]
        assert _collapse_identical_tool_calls(calls) == [calls[0]]

    def test_keeps_distinct_args_for_the_same_tool(self):
        # A genuine parallel batch (two different searches) must survive intact.
        calls = [
            {"id": "c0", "name": "glossary_search", "arguments": '{"query":"a"}'},
            {"id": "c1", "name": "glossary_search", "arguments": '{"query":"b"}'},
        ]
        assert _collapse_identical_tool_calls(calls) == calls

    def test_keeps_same_args_for_different_tools(self):
        calls = [
            {"id": "c0", "name": "tool_list", "arguments": '{"category":"glossary"}'},
            {"id": "c1", "name": "tool_load", "arguments": '{"category":"glossary"}'},
        ]
        assert _collapse_identical_tool_calls(calls) == calls

    def test_single_call_and_empty_list_are_untouched(self):
        one = [{"id": "c0", "name": "t", "arguments": "{}"}]
        assert _collapse_identical_tool_calls(one) == one
        assert _collapse_identical_tool_calls([]) == []

    def test_composes_with_the_empty_duplicate_dropper(self):
        # Real shape: one well-formed call, an identical repeat, and a malformed empty.
        # Run in the same order production does — empties dropped FIRST, so a `{}` call
        # is never the survivor a later well-formed call would collapse into.
        args = '{"query":"a"}'
        calls = [
            {"id": "c0", "name": "glossary_search", "arguments": args},
            {"id": "c1", "name": "glossary_search", "arguments": args},
            {"id": "c2", "name": "glossary_search", "arguments": ""},
        ]
        assert _collapse_identical_tool_calls(
            _drop_duplicate_empty_tool_calls(calls)
        ) == [calls[0]]


class TestCollapseIsWiredIntoTheLoop:
    """K9 — every test above calls the helper DIRECTLY. None of them proves the loop
    reaches it, and a correct helper nobody calls is this repo's recurring silent-no-op
    shape. Two post-fix live runs failed to reproduce the duplicate emission (the model
    simply did not misbehave those times), so waiting for it to fire in the wild is not a
    verification strategy — the duplicate has to be INJECTED at the seam it arrives from.

    These drive the real `_stream_with_tools` with a gateway script that emits the exact
    measured shape (3 byte-identical calls at iteration 0) and assert on the EFFECT that
    matters: how many times the tool actually EXECUTES.
    """

    _ARGS = '{"query":"Lâm Uyên"}'

    def _dup_pass(self, n: int, args_list: list[str] | None = None):
        """One gateway pass emitting `n` complete tool calls, streamed as the gateway
        really streams them: id+name on the first fragment per index, args after."""
        args_list = args_list or [self._ARGS] * n
        evs = []
        for i in range(n):
            evs.append(tool_frag(index=i, id=f"c{i}", name="memory_search"))
            evs.append(tool_frag(index=i, arguments_delta=args_list[i]))
        evs.append(done("tool_calls"))
        return evs

    @pytest.mark.asyncio
    async def test_three_identical_calls_execute_the_tool_ONCE(self):
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(result={"hits": []})
        scripts = [self._dup_pass(3), [tok("done"), usage(1, 1), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        assert kc.mcp_execute_tool.await_count == 1, (
            "the loop executed the duplicate emission more than once — a write tool "
            "without its own idempotency would have made N rows from one user intent"
        )

    @pytest.mark.asyncio
    async def test_the_collapsed_ids_never_reach_the_provider(self):
        """The other half of correctness: the assistant message the NEXT pass sends back
        must not advertise tool_call ids that were never answered, or the provider waits
        on a response that will never come.
        """
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(result={"hits": []})
        scripts = [self._dup_pass(3), [tok("done"), usage(1, 1), done("stop")]]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        second = _FakeClient.instances[0].requests[1]
        assistant = [m for m in second.messages if m.get("role") == "assistant"
                     and m.get("tool_calls")]
        assert assistant, "the second pass must carry the assistant tool_calls message"
        ids = [c["id"] for c in assistant[-1]["tool_calls"]]
        answered = [m["tool_call_id"] for m in second.messages if m.get("role") == "tool"]
        assert len(ids) == 1, f"collapsed ids leaked into the wire: {ids}"
        assert sorted(ids) == sorted(answered), (
            "every advertised tool_call id must have a matching tool result"
        )

    @pytest.mark.asyncio
    async def test_a_genuine_parallel_batch_still_runs_BOTH(self):
        """The guard against over-collapsing. Without this the test above passes just as
        well for a loop that dropped every call but the first.
        """
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(result={"hits": []})
        scripts = [
            self._dup_pass(2, ['{"query":"a"}', '{"query":"b"}']),
            [tok("done"), usage(1, 1), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        assert kc.mcp_execute_tool.await_count == 2, (
            "two DIFFERENT searches in one emission are a legitimate parallel batch"
        )
