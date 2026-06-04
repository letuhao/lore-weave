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
    _stream_with_tools,
)
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID


@pytest.fixture(autouse=True)
def _bespoke_tool_path(monkeypatch):
    """These tests exercise the tool-LOOP mechanics via the bespoke
    knowledge_client.execute_tool path they assert on (assert_awaited_once, etc.).
    The transport choice (USE_MCP_TOOLS, default flipped to True) is orthogonal
    and covered by test_mcp_execute_tool — pin it False here so the loop tests
    stay deterministic regardless of the default."""
    monkeypatch.setattr(settings, "use_mcp_tools", False)


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
        _FakeClient.instances.append(self)

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


def _run(
    scripts: list,
    *,
    knowledge_client,
    messages: list[dict] | None = None,
    tools: list[dict] | None = None,
    gen_params: dict | None = None,
    project_id: str | None = "proj-1",
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
        kc.execute_tool.assert_not_called()

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
        assert req.tools is not None and len(req.tools) == 1
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
        kc.execute_tool.return_value = _envelope(
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
        kc.execute_tool.assert_awaited_once()
        call_kwargs = kc.execute_tool.await_args.kwargs
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
        kc.execute_tool.return_value = _envelope(success=True, result={"ok": 1})
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
        kc.execute_tool.return_value = _envelope(success=True, result={})
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
        kc.execute_tool.return_value = _envelope(success=True, result={})
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

        assert kc.execute_tool.await_count == 2
        names = [c.kwargs["tool_name"] for c in kc.execute_tool.await_args_list]
        assert names == ["memory_search", "memory_get_entity"]
        args = [c.kwargs["tool_args"] for c in kc.execute_tool.await_args_list]
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
        kc.execute_tool.return_value = _envelope(success=True, result={})
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
        assert kc.execute_tool.await_args.kwargs["tool_args"] == {
            "query": "Kai Stormblade"
        }

    @pytest.mark.asyncio
    async def test_id_and_name_from_first_fragment_only(self):
        """Only the first fragment for an index carries id+name; the
        loop must keep them even though later fragments leave them
        None."""
        kc = AsyncMock()
        kc.execute_tool.return_value = _envelope(success=True, result={})
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
        kc.execute_tool.return_value = _envelope(success=True, result={})

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
        kc.execute_tool.return_value = _envelope(success=True, result={})

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
        kc.execute_tool.assert_not_called()

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
        kc.execute_tool.return_value = _envelope(success=True, result={})
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
        kc.execute_tool.return_value = _envelope(success=True, result={})
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
        kc.execute_tool.return_value = _envelope(
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
        kc.execute_tool.side_effect = [
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
        kc.execute_tool.return_value = _envelope(success=True, result={})
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
        assert kc.execute_tool.await_args.kwargs["project_id"] is None
