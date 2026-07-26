"""External MCP discoverability audit #9 — FuncMetadata.convert_result no
longer duplicates a structured tool's full payload into content[0].text."""

from __future__ import annotations

import pytest
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel

from loreweave_mcp import patch_convert_result
from loreweave_mcp.compact_content import _PATCHED_ATTR, _PLACEHOLDER_TEXT


class _EchoOut(BaseModel):
    value: str


@pytest.fixture(autouse=True)
def _ensure_patched():
    # Idempotent — safe even if a prior test/import already applied it.
    assert patch_convert_result() is True


def _make_tool(name: str):
    mcp_server = FastMCP(name)

    @mcp_server.tool()
    def echo() -> _EchoOut:
        return _EchoOut(value="a real payload that would otherwise be duplicated verbatim")

    return mcp_server


class TestPatchConvertResult:
    def test_is_idempotent(self):
        import mcp.server.fastmcp.utilities.func_metadata as fm

        before = fm.FuncMetadata.convert_result
        assert patch_convert_result() is True
        assert fm.FuncMetadata.convert_result is before  # unchanged — no double-wrap

    @pytest.mark.asyncio
    async def test_structured_result_no_longer_duplicates_payload(self):
        mcp_server = _make_tool("test-echo")
        tool = mcp_server._tool_manager.get_tool("echo")
        result = await tool.run({}, convert_result=True)

        unstructured, structured = result
        assert structured == {"value": "a real payload that would otherwise be duplicated verbatim"}
        assert len(unstructured) == 1
        assert isinstance(unstructured[0], TextContent)
        assert unstructured[0].text == _PLACEHOLDER_TEXT
        assert "verbatim" not in unstructured[0].text  # the actual payload text, NOT duplicated

    @pytest.mark.asyncio
    async def test_a_result_the_handler_itself_built_is_untouched(self):
        """A tool that returns a CallToolResult directly (a genuine custom
        shape) must pass through unpatched — this only ever touches the SDK's
        OWN auto-generated duplicate."""
        mcp_server = FastMCP("test-custom")

        @mcp_server.tool()
        def custom() -> _EchoOut:
            res = CallToolResult(content=[TextContent(type="text", text="custom content")])
            res.structuredContent = {"value": "x"}
            return res  # type: ignore[return-value]

        tool = mcp_server._tool_manager.get_tool("custom")
        result = await tool.run({}, convert_result=True)
        assert isinstance(result, CallToolResult)
        assert result.content[0].text == "custom content"

    def test_returns_false_and_does_not_raise_if_target_shape_is_gone(self, monkeypatch):
        """Simulates a future mcp release removing convert_result entirely —
        the patch must degrade to a no-op (False), never raise."""
        import mcp.server.fastmcp.utilities.func_metadata as fm

        monkeypatch.delattr(fm.FuncMetadata, "convert_result")
        monkeypatch.delattr(fm.FuncMetadata, _PATCHED_ATTR, raising=False)
        assert patch_convert_result() is False
