"""Direct MCP tool calls (NO LLM) — used ONLY by the fixture factory to build
deterministic substrate and to tear it down.

This is the dracula-script pattern (`scripts/run_dracula_mcp_scenario.py`): drive
the ai-gateway MCP surface with the internal-token envelope so setup/teardown is
deterministic. The PROBES, by contrast, drive tools through the model over the SSE
chat edge — that is the thing under test. Keeping the two paths separate is what
lets the harness assert "the MODEL could do it", not "some code could".
"""
from __future__ import annotations

import asyncio
import json

from mcp import ClientSession
from mcp.client.streamable_http import streamablehttp_client

from . import config

_HEADERS = {
    "X-Internal-Token": config.INTERNAL_TOKEN,
    "X-User-Id": config.USER_ID,
    "X-Session-Id": "tle-fixtures",
}


class MCPDirect:
    """Synchronous facade over the async MCP client (one call per invocation)."""

    def call(self, tool: str, args: dict) -> dict:
        return asyncio.run(self._call(tool, args))

    async def _call(self, tool: str, args: dict) -> dict:
        async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=_HEADERS) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                if getattr(res, "isError", False):
                    txt = res.content[0].text if res.content else "?"
                    raise RuntimeError(f"MCP {tool} error: {txt[:300]}")
                sc = getattr(res, "structuredContent", None)
                if isinstance(sc, dict):
                    return sc
                # fall back to parsing the text content
                if res.content:
                    try:
                        return json.loads(res.content[0].text)
                    except Exception:
                        return {"_text": res.content[0].text}
                return {}
