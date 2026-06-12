"""A2A phase-2 — compose_prose (in-turn composer-model delegation) tests.

Covers the tool schema and the loop behaviour: when the orchestrator calls
compose_prose, _stream_with_tools streams the SECOND (composer) model inline,
returns its prose as the tool result, sums its usage into the turn, and does NOT
touch knowledge-service. Reuses the _FakeClient scripting harness — note the
SAME client replays scripts in call order, so script[1] is the composer pass.
"""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from app.services.composer import (
    COMPOSE_PROSE_NAME,
    COMPOSE_PROSE_TOOL,
    build_composer_messages,
    compose_prose_defs,
    is_composer_tool,
)
from app.services.stream_events import AgUiEmitter, LegacyEmitter
from app.services.stream_service import _Usage, _stream_with_tools
from tests.conftest import TEST_MODEL_REF, TEST_SESSION_ID, TEST_USER_ID
from tests.test_stream_tools import _drain, _patch_client, done, tok, tool_frag, usage


class TestComposingEvent:
    def test_agui_composing_emits_custom(self):
        import json
        em = AgUiEmitter(thread_id="s", message_id="m")
        on = json.loads(em.composing(True)[0].removeprefix("data: ").strip())
        assert on["type"] == "CUSTOM" and on["name"] == "composing"
        assert on["value"]["active"] is True
        off = json.loads(em.composing(False)[0].removeprefix("data: ").strip())
        assert off["value"]["active"] is False

    def test_legacy_composing_is_noop(self):
        assert LegacyEmitter().composing(True) == []


class TestComposeProseDefs:
    def test_is_composer_tool(self):
        assert is_composer_tool("compose_prose")
        assert not is_composer_tool("memory_search")
        assert not is_composer_tool("propose_edit")

    def test_schema_is_wire_standard(self):
        d = COMPOSE_PROSE_TOOL
        assert d["function"]["name"] == COMPOSE_PROSE_NAME
        assert d["function"]["parameters"]["required"] == ["instructions"]
        assert compose_prose_defs() == [COMPOSE_PROSE_TOOL]

    def test_build_messages_prepends_session_prompt_and_source(self):
        msgs = build_composer_messages(
            {"instructions": "rewrite vividly", "source_text": "It rained."},
            session_system_prompt="You are Lu Xun.",
        )
        assert msgs[0]["role"] == "system"
        assert "Lu Xun" in msgs[0]["content"]
        assert "rewrite vividly" in msgs[1]["content"]
        assert "It rained." in msgs[1]["content"]


class TestComposeProseLoop:
    @pytest.mark.asyncio
    async def test_compose_prose_streams_composer_and_returns_prose(self):
        """Orchestrator calls compose_prose → the composer model is streamed
        inline (script[1]); its prose comes back as the tool result, usage is
        summed across orchestrator + composer + final pass, knowledge-service is
        never called, and the composer request targets the composer model with
        NO tools offered."""
        kc = AsyncMock()
        scripts = [
            # pass 0 — orchestrator calls compose_prose
            [tool_frag(index=0, id="cmp", name="compose_prose"),
             tool_frag(index=0, arguments_delta='{"instructions":"write a rainy opening"}'),
             usage(10, 2), done("tool_calls")],
            # composer stream (the inline 2nd model)
            [tok("The rain fell in silver threads."), usage(50, 8), done("stop")],
            # pass 1 — orchestrator wraps up
            [tok("Drafted it for you."), usage(5, 4), done("stop")],
        ]
        with _patch_client(scripts):
            chunks = await _drain(_stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "write a rainy opening"}],
                gen_params={}, tools=compose_prose_defs(), knowledge_client=kc,
                session_id=TEST_SESSION_ID, project_id=None,
                composer_model=("user_model", "11111111-1111-1111-1111-111111111111"),
                composer_system_prompt="Author voice.",
            ))

        # knowledge-service untouched — compose_prose is fulfilled in-process
        kc.execute_tool.assert_not_awaited()
        kc.mcp_execute_tool.assert_not_awaited()

        # the tool_call chunk carries the composer's prose
        tool_chunks = [c for c in chunks if "tool_call" in c]
        assert len(tool_chunks) == 1
        tcall = tool_chunks[0]["tool_call"]
        assert tcall["tool"] == "compose_prose"
        assert tcall["ok"] is True
        assert tcall["result"]["prose"] == "The rain fell in silver threads."

        # "✍️ Drafting" UI signal: composing on before the writer streams, off after
        composing = [c["composing"]["active"] for c in chunks if "composing" in c]
        assert composing == [True, False]

        # final text + summed usage (10/2 + 50/8 + 5/4 = 65/14)
        assert any(c.get("content") == "Drafted it for you." for c in chunks)
        final_usage = [c["usage"] for c in chunks if c.get("usage")][-1]
        assert final_usage.prompt_tokens == 65
        assert final_usage.completion_tokens == 14

    @pytest.mark.asyncio
    async def test_compose_prose_request_targets_composer_model_without_tools(self):
        from tests.test_stream_tools import _FakeClient
        kc = AsyncMock()
        scripts = [
            [tool_frag(index=0, id="cmp", name="compose_prose"),
             tool_frag(index=0, arguments_delta='{"instructions":"x"}'),
             usage(1, 1), done("tool_calls")],
            [tok("prose"), usage(1, 1), done("stop")],
            [tok("done"), usage(1, 1), done("stop")],
        ]
        with _patch_client(scripts):
            await _drain(_stream_with_tools(
                model_source="user_model", model_ref=TEST_MODEL_REF, user_id=TEST_USER_ID,
                messages=[{"role": "user", "content": "x"}],
                gen_params={}, tools=compose_prose_defs(), knowledge_client=kc,
                session_id=TEST_SESSION_ID, project_id=None,
                composer_model=("user_model", "11111111-1111-1111-1111-111111111111"),
            ))
        # requests: [orchestrator pass0, composer pass, orchestrator pass1]
        reqs = _FakeClient.instances[0].requests
        assert str(reqs[1].model_ref) == "11111111-1111-1111-1111-111111111111"
        assert not getattr(reqs[1], "tools", None)  # composer offered no tools
