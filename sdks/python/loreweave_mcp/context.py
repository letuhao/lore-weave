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

from .compact_content import patch_convert_result, patch_tool_run_size_gate

# Soft dependency on the LLM SDK (P4/Wave-C slice D). The kit lives in services
# that DON'T submit LLM jobs (e.g. a pure read facade) and so may not depend on
# loreweave_llm — skip the carrier hook there. Where it IS installed, every tool
# call routes public-key attribution into the job_meta carrier (see
# build_tool_context).
try:
    from loreweave_llm.attribution import set_public_key_attribution as _set_llm_attribution
except Exception:  # pragma: no cover - exercised by services without loreweave_llm
    _set_llm_attribution = None

__all__ = [
    "ToolContext",
    "build_tool_context",
    "make_stateless_fastmcp",
    "is_owner_only",
    "apply_public_key_attribution_headers",
]


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
    # The public MCP API key id (X-Mcp-Key-Id) when the call originated at the
    # public edge (mcp-public-gateway); None for first-party traffic. Carrier for
    # per-key spend attribution (H-C) and the owned-resources-only default (OD-8).
    mcp_key_id: str | None = None
    # The public key's per-key USD spend sub-cap (X-Mcp-Spend-Cap-Usd), forwarded
    # by the edge from the resolved key; None when the key has no cap or for
    # first-party traffic. P4/Wave-C slice D (H-K) — rides job_meta to the
    # provider-registry reserve so two concurrent calls can't exceed the cap.
    spend_cap_usd: float | None = None
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

    Also applies `patch_convert_result()` (external MCP discoverability audit
    #9 — payload duplication) once per process: every service that builds its
    FastMCP server through this one shared chokepoint gets the fix for free,
    with no separate wiring of its own.
    """
    patch_convert_result()
    patch_tool_run_size_gate()
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
    mcp_key_id = _optional_header(ctx, "x-mcp-key-id")
    spend_cap_usd = _parse_spend_cap(_optional_header(ctx, "x-mcp-spend-cap-usd"))

    # P4/Wave-C slice D — universal carrier hook. Set (or CLEAR) the public-key
    # attribution on the loreweave_llm contextvar for THIS task, so any provider
    # job this tool submits via loreweave_llm.submit_job carries mcp_key_id + cap
    # in job_meta (the header is gone by the time we call provider-registry). Done
    # here, once per tool call, so no priced provider needs per-tool wiring. A
    # first-party call clears it to None (no leak across pooled tasks). Soft dep:
    # services without loreweave_llm installed simply skip it.
    if _set_llm_attribution is not None:
        _set_llm_attribution(mcp_key_id, spend_cap_usd)

    return ToolContext(
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
        trace_id=trace_id,
        mcp_key_id=mcp_key_id,
        spend_cap_usd=spend_cap_usd,
        internal_token=raw_token,
    )


def _parse_spend_cap(raw: str | None) -> float | None:
    """Parse the X-Mcp-Spend-Cap-Usd header to a non-negative float, or None when
    absent/malformed/negative. A malformed cap fails OPEN to None (no per-key cap)
    rather than rejecting the call — the owner-level guardrail still bounds spend,
    and the edge is the trusted source of this value (a bad value here is a bug,
    not an attack vector)."""
    if not raw:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def apply_public_key_attribution_headers(
    mcp_key_id: str | None, spend_cap_raw: str | None
) -> None:
    """Lift the public-key spend-attribution headers (X-Mcp-Key-Id /
    X-Mcp-Spend-Cap-Usd) into the loreweave_llm contextvar for THIS async task.

    ``build_tool_context`` already does this for MCP *tool calls*. This helper is for
    a NON-tool-call effect the kit's hook doesn't cover — e.g. a REST
    ``/v1/<domain>/actions/confirm`` route that, on an approved public action, runs
    an IN-PROCESS LLM submit and must tag its ``job_meta`` with the agent's key + cap
    (P4/Wave-C slice A, the confirm-route carrier-lift). Set it before the in-process
    submit and CLEAR it in a ``finally`` by calling with ``(None, None)`` so the
    attribution never leaks into the next request on a pooled worker.

    No-op when ``loreweave_llm`` isn't installed (first-party services). An empty
    header value is treated as absent; a malformed cap fails open to None.
    """
    if _set_llm_attribution is None:
        return
    key = mcp_key_id or None
    _set_llm_attribution(key, _parse_spend_cap(spend_cap_raw))


def is_owner_only(ctx: object) -> bool:
    """Whether ownership must resolve to OWNED resources only — dropping
    grant-derived (shared-with-me) access (OD-8).

    True exactly for public MCP-key traffic (``mcp_key_id`` set): a third-party
    agent acting as user U must not reach books merely shared with U, whose true
    owner never consented to a third-party agent. First-party calls return False
    (grant-aware resolution unchanged).

    Duck-typed on a ``mcp_key_id`` attribute so it works for both this kit's
    ``ToolContext`` and a consuming service's richer context (e.g.
    knowledge-service composes its own).
    """
    return getattr(ctx, "mcp_key_id", None) is not None
