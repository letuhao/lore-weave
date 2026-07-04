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
    _parse_tool_args,
    _reassemble_tool_calls,
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
):
    """Build a `_stream_with_tools` async generator with sane defaults."""
    return _stream_with_tools(
        model_source="user_model",
        model_ref=TEST_MODEL_REF,
        user_id=TEST_USER_ID,
        messages=messages if messages is not None else [{"role": "user", "content": "hi"}],
        gen_params=gen_params or {},
        tools=tools if tools is not None else [{"type": "function", "function": {"name": "memory_search"}}],
        knowledge_client=knowledge_client,
        session_id=TEST_SESSION_ID,
        project_id=project_id,
        planner_model_ref=planner_model_ref,
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
        # 2 = the 1 supplied tool + the always-on conversation_search recovery
        # tool (T6/D6), appended whenever the pass already offers tools.
        assert req.tools is not None and len(req.tools) == 2
        assert {t["function"]["name"] for t in req.tools} == {
            "memory_search", "conversation_search",
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
        assert assistant_msg["tool_calls"][0]["function"]["arguments"] == '{"query":"q"}'

        tool_msg = pass1_msgs[2]
        assert tool_msg["role"] == "tool"
        assert tool_msg["tool_call_id"] == "call_x"
        # tool message content is the JSON-encoded result payload.
        assert json.loads(tool_msg["content"]) == {"ok": 1}

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
            # propose_edit is in FRONTEND_TOOL_NAMES → the frontend bucket.
            {"type": "function", "function": {
                "name": "propose_edit",
                "parameters": {"type": "object", "properties": {"replacement": {"type": "string"}}},
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
