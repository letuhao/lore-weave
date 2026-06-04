"""ARCH-2 C2 — independent client-side pin of the MCP envelope contract.

WHY THIS FILE EXISTS (review finding #3):
The existing dual-run gate test (test_mcp_execute_tool.py
::TestUseMcpToolsGate) asserts that the bespoke `execute_tool` path and the
`mcp_execute_tool` path return the same envelope — but it does so by handing
BOTH paths the SAME pre-built mock envelope. Equality between two pre-matched
mocks proves nothing about whether the REAL transports actually agree on the
wire; it only proves the test author wrote the same literal twice.

This file removes the shared-mock shortcut. It guards the C2 "identical
envelope" contract from the CLIENT side by pinning the real
`KnowledgeClient.mcp_execute_tool()` parser against the SAME documented
server-side `_dispatch` output shapes that the knowledge-service contract
tests (test_mcp_contract.py) pin from the SERVER side. The agreement between
the two ends is therefore asserted through an independently-documented
INTERMEDIATE wire shape — not through a single mock object reused on both
sides.

The documented `_dispatch` output shapes (knowledge-service
app/mcp/server.py) — these are the exact bytes the chat client sees as
`result.content[0].text` with `isError=False`:
  - on success: the BARE executor payload, a dict with NO top-level
    'success' key, e.g. {"hits": [], "count": 0}
  - on tool failure: {"success": False, "error": "<msg>"}
An MCP-protocol/handler error instead surfaces as `isError=True`.

Real cross-process wire equality (the actual bytes flowing between the two
live services) remains covered by D-ARCH2-MCP-LIVE-SMOKE.

Patch targets mirror test_mcp_execute_tool.py: `mcp_execute_tool` binds
`streamablehttp_client` and `ClientSession` at module level in
`app.client.knowledge_client`, so we patch those module-namespace symbols
(patch-where-it-is-used).
"""
from __future__ import annotations

import json
import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.client.knowledge_client import KnowledgeClient  # noqa: E402


# ── helpers (same scaffolding/patch targets as test_mcp_execute_tool.py) ─────


def _make_client() -> KnowledgeClient:
    """A KnowledgeClient with no real transport — mcp_execute_tool opens its
    own (mocked) MCP transport, so the default AsyncClient is fine here."""
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
    """A CallToolResult-like object: isError flag + a content list."""
    result = MagicMock()
    result.isError = is_error
    result.content = content
    return result


def _patch_mcp(call_tool_return):
    """Wire the async-with transport + ClientSession chain to mocks so that

      async with streamablehttp_client(...) as (read, write, _):
          async with ClientSession(read, write) as mcp_session:
              await mcp_session.initialize()
              result = await mcp_session.call_tool(name, args)

    runs entirely against mocks, with `call_tool` returning the supplied
    CallToolResult-like object. Returns (transport_patch, session_patch)."""
    transport_cm = MagicMock()
    transport_cm.__aenter__ = AsyncMock(
        return_value=(MagicMock(), MagicMock(), None)
    )
    transport_cm.__aexit__ = AsyncMock(return_value=False)
    transport_factory = MagicMock(return_value=transport_cm)

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=call_tool_return)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_cm)

    return (
        patch("app.client.knowledge_client.streamablehttp_client", transport_factory),
        patch("app.client.knowledge_client.ClientSession", session_factory),
    )


# ════════════════════════════════════════════════════════════════════════════
# Documented _dispatch shapes → real parser → asserted envelope
# ════════════════════════════════════════════════════════════════════════════


class TestMcpEnvelopeParity:
    @pytest.mark.asyncio
    async def test_bare_success_payload_maps_to_success_envelope(self):
        """Server _dispatch success → BARE executor payload (no top-level
        'success' key). Fed verbatim through the real parser, it must wrap to
        {"success": True, "result": <payload>, "error": None}."""
        client = _make_client()
        # Exact documented bytes on the wire: bare payload, isError=False.
        bare_payload = {"hits": [{"id": "1"}], "count": 1}
        result = _call_tool_result(
            content=[_text_content(json.dumps(bare_payload))],
            is_error=False,
        )
        tpatch, spatch = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="user-1",
                session_id="sess-1",
                tool_name="memory_search",
                tool_args={"query": "Elara"},
            )
        assert out == {
            "success": True,
            "result": {"hits": [{"id": "1"}], "count": 1},
            "error": None,
        }
        await client.aclose()

    @pytest.mark.asyncio
    async def test_server_success_false_payload_maps_to_failure_envelope(self):
        """Server _dispatch tool failure → {"success": False, "error": msg}
        carried as isError=False JSON text. The real parser must recognise
        the structured failure and surface it as a success=False envelope
        (NOT report it as a successful result)."""
        client = _make_client()
        # Exact documented bytes on the wire: structured failure, isError=False.
        failure_payload = {"success": False, "error": "tool refused"}
        result = _call_tool_result(
            content=[_text_content(json.dumps(failure_payload))],
            is_error=False,
        )
        tpatch, spatch = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="user-2",
                session_id="sess-2",
                tool_name="memory_recall_entity",
                tool_args={"entity_name": "Ghost"},
            )
        assert out["success"] is False
        assert out["result"] is None
        assert out["error"] == "tool refused"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_isError_true_maps_to_failure_envelope(self):
        """An MCP-protocol/handler error surfaces as isError=True. The real
        parser must map it to a success=False envelope and surface the error
        text from the first content item."""
        client = _make_client()
        result = _call_tool_result(
            content=[_text_content("invalid internal token")],
            is_error=True,
        )
        tpatch, spatch = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            out = await client.mcp_execute_tool(
                user_id="user-3",
                session_id="sess-3",
                tool_name="memory_search",
                tool_args={"query": "x"},
            )
        assert out["success"] is False
        assert out["result"] is None
        assert out["error"] == "invalid internal token"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_success_carries_empty_dict_on_both_transports(self):
        """Empty-success parity: a memory tool that succeeds with no payload
        must surface `result == {}` (never None) on BOTH transports.

          - MCP wire: isError=False, content text == "null" (JSON for None).
            The server's _dispatch already does `result.result or {}`, but a
            bare "null" can still reach the parser, which coerces None → {}.
          - Bespoke HTTP: a 200 body {"success": True, "result": None,
            "error": None} (an older knowledge-service that hasn't coerced
            server-side) is coerced client-side to result == {}.

        Asserting both here pins the contract that an empty success is the
        SAME {} on each path — so the LLM never sees a None where the other
        transport would have shown {}."""
        # ── MCP path: "null" content → {} ──────────────────────────────────
        mcp_client = _make_client()
        result = _call_tool_result(
            content=[_text_content("null")], is_error=False
        )
        tpatch, spatch = _patch_mcp(call_tool_return=result)
        with tpatch, spatch:
            mcp_out = await mcp_client.mcp_execute_tool(
                user_id="user-4",
                session_id="sess-4",
                tool_name="memory_remember",
                tool_args={"text": "Kai is a swordsman"},
            )
        await mcp_client.aclose()

        # ── Bespoke path: 200 {success:True, result:None} → {} ─────────────
        def _handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"success": True, "result": None, "error": None},
            )

        bespoke_client = KnowledgeClient(
            base_url="http://knowledge-service:8092",
            internal_token="unit-test-token",
            timeout_s=0.5,
            retries=0,
            transport=httpx.MockTransport(_handler),
        )
        bespoke_out = await bespoke_client.execute_tool(
            user_id="user-4",
            session_id="sess-4",
            tool_name="memory_remember",
            tool_args={"text": "Kai is a swordsman"},
        )
        await bespoke_client.aclose()

        # Both transports now carry {} for an empty success — byte-identical.
        assert mcp_out == {"success": True, "result": {}, "error": None}
        assert bespoke_out["success"] is True
        assert bespoke_out["result"] == {}
        assert bespoke_out["error"] is None
        assert mcp_out["result"] == bespoke_out["result"]
