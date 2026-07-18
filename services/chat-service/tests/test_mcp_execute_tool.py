"""ARCH-2 C2 — unit tests for the chat-service MCP client path.

Two surfaces are exercised:

1. `KnowledgeClient.mcp_execute_tool()` result formatting + graceful
   degradation — the MCP transport / ClientSession are fully mocked so no
   real network call happens. The method must return the SAME
   {success, result, error} envelope shape as the bespoke
   `execute_tool()` so it is a drop-in replacement, and must NEVER raise
   (a transport failure degrades to success=False, matching the bespoke
   contract).

2. The backend-tool path in `_stream_with_tools()` routes through
   `mcp_execute_tool` — the only tool transport after the ai-gateway hard
   cutover (the bespoke `execute_tool` path was retired).

`mcp_execute_tool` binds `streamablehttp_client` and `ClientSession` at
module level in `app.client.knowledge_client`, so the patch targets are
those module-namespace symbols (patch-where-it-is-used) — this is the
reliable interception point for a function-local `from mcp import ...`.
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.client.knowledge_client import KnowledgeClient  # noqa: E402


# ── helpers ────────────────────────────────────────────────────────────────


def _make_client() -> KnowledgeClient:
    """A KnowledgeClient with no transport — mcp_execute_tool never touches
    the underlying httpx client (it opens its own MCP transport), so the
    default AsyncClient is fine here. We only read self._http.headers."""
    return KnowledgeClient(
        base_url="http://knowledge-service:8092",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=0,
    )


def _text_content(text: str) -> MagicMock:
    item = MagicMock()
    item.text = text
    return item


def _call_tool_result(*, content: list, is_error: bool = False) -> MagicMock:
    result = MagicMock()
    result.isError = is_error
    result.content = content
    return result


def _patch_mcp(call_tool_return=None, call_tool_side_effect=None,
               transport_side_effect=None):
    """Return (transport_patch, session_patch) configured so that

      async with streamablehttp_client(...) as (read, write, _):
          async with ClientSession(read, write) as mcp_session:
              await mcp_session.initialize()
              result = await mcp_session.call_tool(name, args)

    runs against mocks. `call_tool_return` is the CallToolResult to hand
    back; `call_tool_side_effect` raises instead; `transport_side_effect`
    makes the transport __aenter__ raise (simulating connect failure)."""
    transport_cm = MagicMock()
    if transport_side_effect is not None:
        transport_cm.__aenter__ = AsyncMock(side_effect=transport_side_effect)
    else:
        transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), None))
    transport_cm.__aexit__ = AsyncMock(return_value=False)
    transport_factory = MagicMock(return_value=transport_cm)

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    if call_tool_side_effect is not None:
        mock_session.call_tool = AsyncMock(side_effect=call_tool_side_effect)
    else:
        mock_session.call_tool = AsyncMock(return_value=call_tool_return)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_cm)

    return (
        patch("app.client.knowledge_client.streamablehttp_client", transport_factory),
        patch("app.client.knowledge_client.ClientSession", session_factory),
        transport_factory,
        session_factory,
        mock_session,
    )


# ════════════════════════════════════════════════════════════════════════════
# mcp_execute_tool — result formatting + graceful degradation
# ════════════════════════════════════════════════════════════════════════════


class TestMcpExecuteToolResultFormatting:
    @pytest.mark.asyncio
    async def test_success_returns_parsed_result_envelope(self):
        """A non-error CallToolResult whose first content item holds a JSON
        dict → {"success": True, "result": <dict>, "error": None}."""
        client = _make_client()
        fake_payload = {
            "hits": [{"text": "some text", "source_type": "chapter", "score": 0.9}],
            "count": 1,
        }
        result = _call_tool_result(content=[_text_content(json.dumps(fake_payload))])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="user-1",
                session_id="sess-1",
                tool_name="memory_search",
                tool_args={"query": "Elara"},
            )
        assert out["success"] is True
        assert out["result"] == fake_payload
        assert out["error"] is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_prefers_structured_content_over_placeholder(self):
        """#9B — a heavy read returns a PLACEHOLDER in content[0].text + the real
        payload in structuredContent. The parser must use structuredContent, not
        try (and fail) to json.loads the placeholder → 'unparseable content'."""
        client = _make_client()
        real = {"ontology": {"kinds": ["character", "location"]}}
        result = _call_tool_result(content=[_text_content("ok — see structuredContent")])
        result.structuredContent = real
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="user-1",
                session_id="sess-1",
                tool_name="glossary_book_ontology_read",
                tool_args={"book_id": "B1"},
            )
        assert out["success"] is True
        assert out["result"] == real
        assert out["error"] is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_context_headers_set_and_args_carry_no_scope(self):
        """user_id / session_id / project_id ride in the MCP context
        headers (design D3) and are NOT injected into tool_args."""
        client = _make_client()
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, _, mock_session = _patch_mcp(
            call_tool_return=result
        )
        with tpatch, spatch:
            await client.mcp_execute_tool(
                user_id="user-9",
                session_id="sess-9",
                project_id="proj-9",
                tool_name="memory_search",
                tool_args={"query": "Kai"},
            )
        # Transport was constructed with the /mcp URL + the scope headers.
        call = transport_factory.call_args
        assert call.args[0] == "http://knowledge-service:8092/mcp"
        headers = call.kwargs["headers"]
        assert headers["X-Internal-Token"] == "unit-test-token"
        assert headers["X-User-Id"] == "user-9"
        assert headers["X-Session-Id"] == "sess-9"
        assert headers["X-Project-Id"] == "proj-9"
        # call_tool received only the semantic args — no scope leaked in.
        tool_args = mock_session.call_tool.await_args.args[1]
        assert tool_args == {"query": "Kai"}
        assert "user_id" not in tool_args
        assert "project_id" not in tool_args
        assert "session_id" not in tool_args
        await client.aclose()

    @pytest.mark.asyncio
    async def test_project_id_header_omitted_when_none(self):
        """A no-project (Mode 1) chat omits X-Project-Id entirely."""
        client = _make_client()
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={},
                project_id=None,
            )
        headers = transport_factory.call_args.kwargs["headers"]
        assert "X-Project-Id" not in headers
        await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_returns_failure_envelope(self):
        """A transport failure (connect refused) → success=False, never
        raises (graceful degradation, same contract as execute_tool())."""
        import httpx

        client = _make_client()
        tpatch, spatch, *_ = _patch_mcp(
            transport_side_effect=httpx.ConnectError("refused")
        )
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={"query": "test"},
            )
        assert out["success"] is False
        assert out["result"] is None
        assert "mcp tool backend unavailable" in out["error"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_call_tool_raise_returns_failure_envelope(self):
        """A protocol-level exception during call_tool → success=False."""
        client = _make_client()
        tpatch, spatch, *_ = _patch_mcp(
            call_tool_side_effect=RuntimeError("protocol boom")
        )
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={},
            )
        assert out["success"] is False
        assert "mcp tool backend unavailable" in out["error"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_is_error_result_maps_to_failure_envelope(self):
        """An MCP isError=True result (e.g. server-side auth ValueError) →
        success=False with the error text surfaced."""
        client = _make_client()
        result = _call_tool_result(
            content=[_text_content("invalid internal token")], is_error=True
        )
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={},
            )
        assert out["success"] is False
        assert out["result"] is None
        assert "token" in out["error"].lower()
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_content_returns_failure_envelope(self):
        """A result with no content items → success=False."""
        client = _make_client()
        result = _call_tool_result(content=[])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={},
            )
        assert out["success"] is False
        assert "empty content" in out["error"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_unparseable_text_returns_failure_envelope(self):
        """A first content item whose text is not JSON → success=False."""
        client = _make_client()
        result = _call_tool_result(content=[_text_content("<<<not json>>>")])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={},
            )
        assert out["success"] is False
        assert "unparseable" in out["error"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_overlay_tool_plain_text_is_wrapped_as_success(self):
        """REG-P2-03 — an EXTERNAL federated (overlay) tool (u_/b_/s_<hash>_…) may
        return PLAIN TEXT (prose/markdown), a VALID result. It must be wrapped as
        {"text": ...} success, NOT rejected like an internal tool's non-JSON. This is
        the bug that broke every external-MCP tool result (e.g. DeepWiki)."""
        client = _make_client()
        text = "Available pages for x/y:\n- 1 Intro\n- 2 Architecture"
        result = _call_tool_result(content=[_text_content(text)])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u", session_id="s",
                tool_name="u_a2bbc662_read_wiki_structure",
                tool_args={"repoName": "x/y"},
            )
        assert out["success"] is True
        assert out["result"] == {"text": text}
        assert out["error"] is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_overlay_tool_json_still_parsed_as_dict(self):
        """An overlay tool that DOES return JSON is parsed normally (the text
        pass-through only triggers on a JSON decode failure — no double-wrap)."""
        client = _make_client()
        result = _call_tool_result(content=[_text_content(json.dumps({"answer": "42"}))])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u", session_id="s",
                tool_name="u_a2bbc662_ask_question", tool_args={"q": "?"},
            )
        assert out["success"] is True
        assert out["result"] == {"answer": "42"}
        await client.aclose()

    @pytest.mark.asyncio
    async def test_structured_tool_error_dict_maps_to_failure(self):
        """The server dispatcher returns {"success": False, "error": ...}
        for tool-level failures — the client must map that to a
        success=False envelope (not report it as a successful result)."""
        client = _make_client()
        payload = {"success": False, "error": "entity not found"}
        result = _call_tool_result(content=[_text_content(json.dumps(payload))])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_recall_entity",
                tool_args={"entity_name": "Ghost"},
            )
        assert out["success"] is False
        assert out["result"] is None
        assert out["error"] == "entity not found"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_mcp_empty_success_payload_normalized_to_empty_dict(self):
        """A wire payload of "null" (JSON for None) is an EMPTY SUCCESS — the
        parser must coerce result to {} so an empty success is byte-identical
        to execute_tool's success path on BOTH transports (the MCP server's
        _dispatch already does `result.result or {}`). Without the coercion
        this would leak result=None into a success=True envelope."""
        client = _make_client()
        # isError=False, first content text is the literal JSON null.
        result = _call_tool_result(content=[_text_content("null")])
        tpatch, spatch, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_remember",
                tool_args={"text": "Kai is a swordsman"},
            )
        assert out == {"success": True, "result": {}, "error": None}
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# mcp_execute_tool — transport timeout + trace_id forwarding (D-K21B-06 / K7e)
# ════════════════════════════════════════════════════════════════════════════
#
# These guard the just-applied fixes to mcp_execute_tool:
#   1. timeout=sse_read_timeout=self._tool_timeout_s is passed to
#      streamablehttp_client — the ONLY guard against silent re-drift to the
#      SDK's 300s sse_read_timeout default (a stalled backend would hang ~10x
#      the bespoke tool ceiling).
#   2. X-Trace-Id rides the MCP context headers when current_trace_id() is set,
#      and is OMITTED when the contextvar is empty — same K7e contract as the
#      bespoke execute_tool / build_context paths.
#
# The transport_factory captured by _patch_mcp records the exact kwargs the
# production code passed to streamablehttp_client, so we assert on them
# directly (no real network call happens).


class TestMcpTransportTimeoutAndTraceId:
    @pytest.mark.asyncio
    async def test_mcp_timeout_kwargs_bound_to_tool_budget(self):
        """Both `timeout` (connect) and `sse_read_timeout` passed to
        streamablehttp_client MUST equal the client's _tool_timeout_s. The
        tool RESULT rides the SSE read channel, so leaving sse_read_timeout at
        the SDK default (300s) would let a stalled backend hang ~10x the 30s
        ceiling. This assertion is the only regression guard against that drift."""
        client = KnowledgeClient(
            base_url="http://knowledge-service:8092",
            internal_token="unit-test-token",
            timeout_s=0.5,
            retries=0,
            tool_timeout_s=17.0,  # distinct, non-default value to prove the bind
        )
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, *_ = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            await client.mcp_execute_tool(
                user_id="u",
                session_id="s",
                tool_name="memory_search",
                tool_args={"query": "Kai"},
            )
        call_kwargs = transport_factory.call_args.kwargs
        assert call_kwargs["timeout"] == 17.0
        assert call_kwargs["sse_read_timeout"] == 17.0
        assert call_kwargs["timeout"] == call_kwargs["sse_read_timeout"] == client._tool_timeout_s
        await client.aclose()

    @pytest.mark.asyncio
    async def test_mcp_forwards_trace_id_when_set(self):
        """With a trace id set in the contextvar, the MCP context headers must
        carry X-Trace-Id == that id so knowledge-service stitches its logs to
        the originating chat turn (K7e)."""
        from app.middleware.trace_id import trace_id_var

        client = _make_client()
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, *_ = _patch_mcp(call_tool_return=result)
        token = trace_id_var.set("trace-abc123")
        try:
            with tpatch, spatch:
                await client.mcp_execute_tool(
                    user_id="u",
                    session_id="s",
                    tool_name="memory_search",
                    tool_args={"query": "Kai"},
                )
        finally:
            trace_id_var.reset(token)
        headers = transport_factory.call_args.kwargs["headers"]
        assert headers["X-Trace-Id"] == "trace-abc123"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_mcp_omits_trace_id_when_unset(self):
        """With an empty contextvar, X-Trace-Id must be omitted entirely so
        knowledge-service mints its own — same contract as execute_tool."""
        from app.middleware.trace_id import trace_id_var

        client = _make_client()
        result = _call_tool_result(content=[_text_content("{}")])
        tpatch, spatch, transport_factory, *_ = _patch_mcp(call_tool_return=result)
        # Explicitly clear so no prior test leaked a value into this task.
        token = trace_id_var.set("")
        try:
            with tpatch, spatch:
                await client.mcp_execute_tool(
                    user_id="u",
                    session_id="s",
                    tool_name="memory_search",
                    tool_args={"query": "Kai"},
                )
        finally:
            trace_id_var.reset(token)
        headers = transport_factory.call_args.kwargs["headers"]
        assert "X-Trace-Id" not in headers
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# Backend-tool path in _stream_with_tools
# ════════════════════════════════════════════════════════════════════════════
#
# Re-uses the _FakeClient + event-builder scaffolding from test_stream_tools
# to drive one tool-call pass followed by a text pass, then asserts the call
# routed through mcp_execute_tool (the only tool transport).


from tests.test_stream_tools import (  # noqa: E402
    _FakeClient,
    _envelope,
    _patch_client,
    _run,
    _drain,
    done,
    tok,
    tool_frag,
)


def _one_tool_then_text_scripts() -> list:
    return [
        [
            tool_frag(index=0, id="c1", name="memory_search"),
            tool_frag(index=0, arguments_delta='{"query":"Kai"}'),
            done("tool_calls"),
        ],
        [tok("answer"), done("stop")],
    ]


class TestMcpToolPath:
    @pytest.mark.asyncio
    async def test_backend_tool_routes_through_mcp(self):
        """A backend (memory) tool call routes through mcp_execute_tool — the
        only tool transport after the ai-gateway hard cutover."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(success=True, result={"hit": 1})

        scripts = _one_tool_then_text_scripts()
        with _patch_client(scripts):
            await _drain(_run(scripts, knowledge_client=kc))

        kc.mcp_execute_tool.assert_awaited_once()
        # Scope rides in kwargs; semantic args carry no scope.
        assert kc.mcp_execute_tool.await_args.kwargs["tool_name"] == "memory_search"
        assert kc.mcp_execute_tool.await_args.kwargs["tool_args"] == {"query": "Kai"}
        assert kc.mcp_execute_tool.await_args.kwargs["session_id"] is not None

    @pytest.mark.asyncio
    async def test_mcp_path_envelope_drives_tool_call_chunk(self):
        """The MCP envelope feeds the tool_call chunk."""
        kc = AsyncMock()
        kc.mcp_execute_tool.return_value = _envelope(
            success=True, result={"entities": ["Kai"]}
        )

        scripts = _one_tool_then_text_scripts()
        with _patch_client(scripts):
            chunks = await _drain(_run(scripts, knowledge_client=kc))

        tool_chunks = [c["tool_call"] for c in chunks if "tool_call" in c]
        assert len(tool_chunks) == 1
        tc = tool_chunks[0]
        assert tc["tool"] == "memory_search"
        assert tc["ok"] is True
        assert tc["result"] == {"entities": ["Kai"]}
