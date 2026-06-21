"""Stateless FastMCP wiring + per-call envelope extraction (extracted from
knowledge-service `app/mcp/server.py`).

Identity/scope ids come ONLY from request headers (the per-call envelope) —
NEVER from LLM-supplied tool args (SEC-1). The internal token is checked with a
constant-time compare before anything else runs (no timing side-channel), so the
MCP path is byte-for-byte as strict as the bespoke `/internal/*` paths.

`ToolContext` is intentionally minimal — just the envelope identity + the raw
internal token. Each consuming service composes its own repos/clients on top; the
kit does not know about any domain's data layer.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

from mcp.server.fastmcp import Context as MCPContext
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

__all__ = ["ToolContext", "build_tool_context", "make_stateless_fastmcp"]


@dataclass(frozen=True)
class ToolContext:
    """The per-call envelope identity, lifted from request headers.

    All fields originate from the MCP request headers set by the caller
    (chat-service → gateway → provider). They are NEVER taken from tool args.
    """

    user_id: UUID
    session_id: str
    project_id: UUID | None = None
    trace_id: str | None = None
    internal_token: str = ""


def make_stateless_fastmcp(name: str) -> FastMCP:
    """Build a stateless FastMCP server wired exactly like the proven
    knowledge-service MCP facade:

    - ``stateless_http=True`` — each tool call is independent; the per-call
      scope arrives in headers, so there is no MCP session state to retain.
    - ``streamable_http_path="/"`` — so mounting the ASGI app at ``/mcp`` in the
      host FastAPI app yields the endpoint at exactly ``/mcp`` (not ``/mcp/mcp``).
    - DNS-rebinding protection DISABLED — this is an INTERNAL service-to-service
      endpoint authed by ``X-Internal-Token`` over the private network; the SDK's
      default localhost-only Host allowlist would 421 a cross-process call with a
      ``Host: <svc>:<port>`` header. The trust boundary here is the network +
      internal token, not the Host header.
    """
    return FastMCP(
        name,
        stateless_http=True,
        streamable_http_path="/",
        transport_security=TransportSecuritySettings(
            enable_dns_rebinding_protection=False
        ),
    )


def _require_header(ctx: MCPContext, header: str) -> str:
    val = ctx.request_context.request.headers.get(header)
    if not val:
        raise ValueError(f"missing required context header: {header!r}")
    return val


def _optional_header(ctx: MCPContext, header: str) -> str | None:
    return ctx.request_context.request.headers.get(header) or None


def build_tool_context(ctx: MCPContext, internal_token: str) -> ToolContext:
    """Validate ``X-Internal-Token`` (constant-time, SEC-1) and lift the per-call
    identity envelope from headers into a ``ToolContext``.

    Raises ``ValueError`` when the token is missing/wrong or a required header is
    absent/malformed — FastMCP surfaces this as a tool-level error (success=False),
    not a 5xx, so the chat-service loop can tell "tool refused" from "backend down".

    ``internal_token`` is the service's configured shared secret (from env, never
    hardcoded — CLAUDE.md "no hardcoded secrets"); the caller passes it in so the
    kit holds no global config.
    """
    raw_token = _require_header(ctx, "x-internal-token")
    # Constant-time comparison — no timing side-channel on the shared token.
    # _require_header already guarantees a non-empty str, so compare_digest never
    # receives None.
    if not internal_token or not secrets.compare_digest(raw_token, internal_token):
        raise ValueError("invalid internal token")

    raw_user_id = _require_header(ctx, "x-user-id")
    try:
        user_id = UUID(raw_user_id)
    except ValueError:
        raise ValueError(f"x-user-id is not a valid UUID: {raw_user_id!r}")

    raw_project_id = _optional_header(ctx, "x-project-id")
    project_id: UUID | None = None
    if raw_project_id:
        try:
            project_id = UUID(raw_project_id)
        except ValueError:
            raise ValueError(f"x-project-id is not a valid UUID: {raw_project_id!r}")

    session_id = _require_header(ctx, "x-session-id")
    trace_id = _optional_header(ctx, "x-trace-id")

    return ToolContext(
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
        trace_id=trace_id,
        internal_token=raw_token,
    )
