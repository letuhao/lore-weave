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

import uuid

from . import config

# 🔴 A FIXED SESSION ID TURNS A PER-SESSION LIMIT INTO A ONE-TIME BUDGET FOR THE WHOLE HARNESS.
# This header was the literal "tle-fixtures" for every seeded call ever made. memory_remember is
# rate-limited per SESSION (knowledge-service executor: _check_remember_rate_limit(ctx.redis,
# ctx.session_id), cap 10), so the harness spent that budget once and every later fixture failed:
# measured 2026-08-23, memory_forget errored 5 of 5 with "the assistant has reached its
# memory_remember limit (10) for this chat session" — a SEED failure that the gate was reporting as
# a transport failure until it was taught to read the error string.
#
# One id per PROCESS, so a fixture behaves like the independent session it is meant to model, and
# two probes running at once do not share a budget. Deliberately not per-CALL: a seed's several
# calls belong to one session, and per-call would defeat any rate limit the platform means to
# enforce — the point is to stop the harness pretending to be one immortal session, not to evade
# the guard.
_SESSION_ID = f"tle-fixtures-{uuid.uuid4().hex[:12]}"

_HEADERS = {
    "X-Internal-Token": config.INTERNAL_TOKEN,
    "X-User-Id": config.USER_ID,
    "X-Session-Id": _SESSION_ID,
}


class MCPToolError(RuntimeError):
    """A tool returned `isError: true`. Carries the server's own message."""


def _flatten(exc: BaseException) -> BaseException:
    """Unwrap an anyio/asyncio ExceptionGroup down to its single real cause.

    `streamablehttp_client` and `ClientSession` are anyio task groups. Any exception
    that escapes their `async with` bodies is re-raised as an ExceptionGroup, so the
    caller sees `unhandled errors in a TaskGroup (1 sub-exception)` and the ACTUAL
    message is buried. That is exactly how F6 presented for a whole eval cycle: the
    server was returning a clear, actionable error ("this project has no embedding
    model configured …") and the harness reported a meaningless wrapper.
    """
    while isinstance(exc, BaseExceptionGroup) and len(exc.exceptions) == 1:
        exc = exc.exceptions[0]
    return exc


class MCPDirect:
    """Synchronous facade over the async MCP client (one call per invocation)."""

    def call(self, tool: str, args: dict) -> dict:
        try:
            return asyncio.run(self._call(tool, args))
        except BaseExceptionGroup as eg:  # transport-level group (not our tool error)
            raise _flatten(eg) from None

    async def _call(self, tool: str, args: dict) -> dict:
        # NEVER raise inside the `async with` bodies — anyio would wrap it in an
        # ExceptionGroup and destroy the message. Capture, exit cleanly, raise after.
        tool_error: str | None = None
        payload: dict = {}
        async with streamablehttp_client(config.AI_GATEWAY_MCP, headers=_HEADERS) as (r, w, _):
            async with ClientSession(r, w) as s:
                await s.initialize()
                res = await s.call_tool(tool, args)
                if getattr(res, "isError", False):
                    tool_error = res.content[0].text if res.content else "?"
                else:
                    sc = getattr(res, "structuredContent", None)
                    if isinstance(sc, dict):
                        payload = sc
                    elif res.content:
                        try:
                            payload = json.loads(res.content[0].text)
                        except Exception:
                            payload = {"_text": res.content[0].text}
        if tool_error is not None:
            raise MCPToolError(f"MCP {tool} error: {tool_error[:500]}")
        return payload
