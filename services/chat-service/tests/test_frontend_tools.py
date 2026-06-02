"""ARCH-1 C6 — frontend-tool (editor write-back) suspend/resume tests.

Reuses the _FakeClient scripting harness from test_stream_tools. Covers:
 - the propose_edit schema + name set,
 - the tool loop SUSPENDING on a frontend tool (no server execution, a `suspend`
   chunk with the rehydrate state),
 - a backend tool in the SAME pass still executing before the suspend,
 - tool-def gating (advertised only for agui + editor_context),
 - the emitter's tool_call_pending + suspended finish.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from app.services.frontend_tools import (
    FRONTEND_TOOL_NAMES,
    PROPOSE_EDIT_TOOL,
    frontend_tool_defs,
    is_frontend_tool,
)
from app.services.stream_events import AgUiEmitter, LegacyEmitter
from tests.test_stream_tools import (
    _FakeClient,
    _drain,
    _envelope,
    _patch_client,
    _run,
    done,
    tok,
    tool_frag,
    usage,
)


# ── schema / name set ────────────────────────────────────────────────────────


class TestFrontendToolDefs:
    def test_propose_edit_is_a_frontend_tool(self):
        assert is_frontend_tool("propose_edit")
        assert "propose_edit" in FRONTEND_TOOL_NAMES

    def test_memory_tools_are_not_frontend(self):
        assert not is_frontend_tool("memory_search")
        assert not is_frontend_tool("memory_remember")

    def test_schema_is_wire_standard_openai_function(self):
        d = PROPOSE_EDIT_TOOL
        assert d["type"] == "function"
        assert d["function"]["name"] == "propose_edit"
        params = d["function"]["parameters"]
        assert set(params["required"]) == {"operation", "text"}
        assert params["properties"]["operation"]["enum"] == ["insert_at_cursor", "replace_selection"]
        # no non-standard keys leak to the provider
        assert "execution_location" not in d and "execution_location" not in d["function"]

    def test_frontend_tool_defs_returns_propose_edit(self):
        assert frontend_tool_defs() == [PROPOSE_EDIT_TOOL]


# ── the suspend in the tool loop ─────────────────────────────────────────────


class TestSuspendLoop:
    @pytest.mark.asyncio
    async def test_frontend_tool_suspends_without_executing(self):
        """A propose_edit call yields a `suspend` chunk carrying the rehydrate
        state and does NOT call knowledge_client.execute_tool."""
        kc = AsyncMock()
        scripts = [[
            tool_frag(index=0, id="call_fe", name="propose_edit"),
            tool_frag(index=0, arguments_delta='{"operation":"insert_at_cursor","text":"Hi"}'),
            usage(10, 4),
            done("tool_calls"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "propose_edit"}}],
            ))
        # never executed server-side
        kc.execute_tool.assert_not_awaited()
        kc.mcp_execute_tool.assert_not_awaited()
        # a single suspend chunk with the pending call + working history
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        s = suspends[0]["suspend"]
        assert s["pending_tool_call"]["name"] == "propose_edit"
        assert s["pending_tool_call"]["id"] == "call_fe"
        assert s["pending_tool_call"]["args"] == {"operation": "insert_at_cursor", "text": "Hi"}
        assert s["input_tokens"] == 10 and s["output_tokens"] == 4
        # the dangling assistant tool-call message is in `working`
        assert any(m.get("role") == "assistant" and m.get("tool_calls") for m in s["working"])

    @pytest.mark.asyncio
    async def test_backend_tool_executes_then_suspends_on_frontend_tool(self):
        """A pass with a memory_* tool AND propose_edit: the memory tool runs
        inline (result in working), then the loop suspends on propose_edit."""
        kc = AsyncMock()
        kc.execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [[
            tool_frag(index=0, id="call_mem", name="memory_search"),
            tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
            tool_frag(index=1, id="call_fe", name="propose_edit"),
            tool_frag(index=1, arguments_delta='{"operation":"insert_at_cursor","text":"x"}'),
            usage(5, 2),
            done("tool_calls"),
        ]]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "memory_search"}},
                       {"type": "function", "function": {"name": "propose_edit"}}],
            ))
        # memory tool executed once
        kc.execute_tool.assert_awaited_once()
        # a tool_call chunk for the memory tool + a suspend for propose_edit
        tool_chunks = [c for c in chunks if "tool_call" in c]
        assert [c["tool_call"]["tool"] for c in tool_chunks] == ["memory_search"]
        suspends = [c for c in chunks if "suspend" in c]
        assert len(suspends) == 1
        # working has the memory tool result before the suspend
        working = suspends[0]["suspend"]["working"]
        assert any(m.get("role") == "tool" and m.get("tool_call_id") == "call_mem" for m in working)

    @pytest.mark.asyncio
    async def test_memory_only_pass_is_unchanged(self):
        """Regression: a pass with only a memory tool still executes inline and
        loops to a normal text answer (no suspend)."""
        kc = AsyncMock()
        kc.execute_tool.return_value = _envelope(success=True, result={"hits": []})
        scripts = [
            [tool_frag(index=0, id="c1", name="memory_search"),
             tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
             usage(3, 1), done("tool_calls")],
            [tok("Kai is a knight."), usage(2, 5), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_run(
                scripts, knowledge_client=kc,
                tools=[{"type": "function", "function": {"name": "memory_search"}}],
            ))
        kc.execute_tool.assert_awaited_once()
        assert not [c for c in chunks if "suspend" in c]
        # final text chunk present
        assert any(c.get("content") == "Kai is a knight." for c in chunks)


# ── emitter pending + suspended finish ───────────────────────────────────────


def _parse(line: str) -> dict:
    return json.loads(line.removeprefix("data: ").strip())


class TestPendingEmitter:
    def test_agui_tool_call_pending_omits_result(self):
        em = AgUiEmitter(thread_id="s", message_id="m")
        lines = em.tool_call_pending({"id": "c1", "tool": "propose_edit",
                                      "args": {"operation": "insert_at_cursor", "text": "Hi"}})
        types = [_parse(x)["type"] for x in lines]
        assert types == ["TOOL_CALL_START", "TOOL_CALL_ARGS", "TOOL_CALL_END"]
        assert "TOOL_CALL_RESULT" not in types  # result comes on resume
        args = _parse(lines[1])
        assert json.loads(args["delta"]) == {"operation": "insert_at_cursor", "text": "Hi"}

    def test_agui_finish_suspended_carries_pending(self):
        em = AgUiEmitter(thread_id="s", message_id="m")
        lines = em.finish(
            {"type": "finish-message", "finishReason": "tool_calls", "usage": {}, "timing": {}},
            status="suspended",
            pending={"runId": "r1", "toolCallId": "c1", "toolName": "propose_edit"},
        )
        run_finished = _parse(lines[-1])
        assert run_finished["type"] == "RUN_FINISHED"
        assert run_finished["result"]["status"] == "suspended"
        assert run_finished["result"]["pendingToolCall"]["runId"] == "r1"

    def test_legacy_pending_is_noop(self):
        assert LegacyEmitter().tool_call_pending({"id": "c", "tool": "propose_edit", "args": {}}) == []
