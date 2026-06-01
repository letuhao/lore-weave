"""ARCH-1 C1 — MCP server facade for knowledge-service memory tools.

Mounts at /mcp on the existing FastAPI app (app/main.py).
Transport: Streamable HTTP (JSON-RPC over HTTP).

Design constraints (single-sourced from app/tools/definitions.py + the
2026-06-01 ARCH-1/2 build plan):

- Calls app.tools.executor.execute_tool() — NO logic duplication. Each
  tool handler is a thin shim that builds a ToolContext from request
  headers and delegates to the existing executor.
- user_id / project_id / session_id come from MCP context headers,
  never from LLM-supplied tool arguments (design D3). The inputSchema
  the LLM sees exposes only the semantic args (the ``ctx`` parameter is
  injected by FastMCP and does not appear in the schema).
- Auth: X-Internal-Token header checked before dispatch. A missing or
  wrong token raises ValueError, which FastMCP surfaces as a tool-level
  error (success=False) — not a 5xx — so the chat-service loop can tell
  "tool refused" apart from "backend down".
- Dual-run: the existing /internal/tools/* endpoints are NOT removed.

Implementation notes (verified against the installed mcp SDK, 1.27.2):
- ``FastMCP.streamable_http_app()`` is a *synchronous* method here — it
  returns the Starlette ASGI app directly (build_mcp_app() wraps it so
  the call site does not have to know the SDK detail).
- ``streamable_http_path`` is set to ``"/"`` so the mount point in
  main.py (``app.mount("/mcp", ...)``) yields the endpoint at ``/mcp``
  rather than ``/mcp/mcp``.
- ``stateless_http=True`` — each tool call is independent; the per-call
  scope arrives in headers, so there is no MCP session state to retain
  between calls.
- A ``-> dict`` tool return is JSON-serialised into the call result's
  text content, so the varying success/error dict shapes the executor
  returns all pass through cleanly to the MCP client.
"""

from __future__ import annotations

import logging
import secrets
from typing import Annotated, Any, Literal
from uuid import UUID

from mcp.server.fastmcp import Context as MCPContext
from mcp.server.fastmcp import FastMCP
from pydantic import Field

from app.clients.embedding_client import get_embedding_client
from app.config import settings
from app.db.neo4j_repos.facts import FactType
from app.db.pool import get_knowledge_pool
from app.db.repositories.pending_facts import PendingFactsRepo
from app.db.repositories.projects import ProjectsRepo
from app.tools.definitions import (
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    TIMELINE_LIMIT_DEFAULT,
    TIMELINE_LIMIT_MAX,
)
from app.tools.executor import ToolContext, execute_tool, get_tools_redis

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

# Module-level FastMCP instance. build_mcp_app() converts it to an ASGI
# app for mounting in main.py. stateless_http=True + path="/" so the
# mount at "/mcp" exposes the endpoint at exactly "/mcp".
mcp_server = FastMCP(
    "knowledge-memory",
    stateless_http=True,
    streamable_http_path="/",
)


# ── Context extraction helpers ────────────────────────────────────────


def _require_header(ctx: MCPContext, header: str) -> str:
    """Extract a required header from the MCP request context.

    Raises ValueError (surfaces as an MCP tool error) when absent."""
    val = ctx.request_context.request.headers.get(header)
    if not val:
        raise ValueError(f"missing required context header: {header!r}")
    return val


def _optional_header(ctx: MCPContext, header: str) -> str | None:
    return ctx.request_context.request.headers.get(header) or None


def _build_tool_context(ctx: MCPContext) -> ToolContext:
    """Build a ToolContext from MCP request headers.

    Raises ValueError when required headers are missing or the internal
    token is wrong — FastMCP converts this to a tool-level error
    (success=False), not a 500.

    Repos/clients are resolved via the same process-singleton getters
    that back app/deps.py's Depends() factories — they are already
    initialised by main.py's lifespan, so this does not re-initialise
    anything. The deps.py factories are ``async def`` only for FastAPI
    Depends() integration; here we construct the repos directly from the
    synchronous pool getter (verified: ProjectsRepo/PendingFactsRepo
    take a pool positional, get_knowledge_pool() is a sync getter) to
    avoid a throwaway coroutine.
    """
    raw_token = _require_header(ctx, "x-internal-token")
    # Constant-time comparison — mirrors app/middleware/internal_auth.py so the
    # MCP path is byte-for-byte as strict as the bespoke /internal/tools/execute
    # path on the shared service token (no timing side-channel). _require_header
    # already guarantees raw_token is a non-empty str, so compare_digest never
    # receives None.
    if not secrets.compare_digest(raw_token, settings.internal_service_token):
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
            raise ValueError(
                f"x-project-id is not a valid UUID: {raw_project_id!r}"
            )

    session_id = _require_header(ctx, "x-session-id")

    pool = get_knowledge_pool()
    return ToolContext(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        projects_repo=ProjectsRepo(pool),
        pending_facts_repo=PendingFactsRepo(pool),
        embedding_client=get_embedding_client(),
        redis=get_tools_redis(),
    )


async def _dispatch(ctx: MCPContext, tool_name: str, tool_args: dict) -> dict:
    """Build a ToolContext, call execute_tool(), return a result dict.

    A tool-level failure (ToolResult.success=False) returns
    ``{"success": False, "error": str}`` — FastMCP surfaces this as a
    normal tool result, not an exception. An infrastructure exception
    (Neo4j down, etc.) propagates so FastMCP reports it as a tool error
    the client sees as a backend failure, mirroring the bespoke
    /internal/tools/execute 503 contract.
    """
    tool_ctx = _build_tool_context(ctx)
    result = await execute_tool(tool_ctx, tool_name, tool_args)
    if result.success:
        # None is contract-forbidden by ToolResult (handlers always return a
        # dict); the {} coercion is defensive, and {} is the canonical
        # empty-success sentinel agreed with the chat-service client (see
        # knowledge_client.mcp_execute_tool). Coercing only on `is None`
        # (not `or`) stops silently swallowing a falsy-but-not-None payload.
        return result.result if result.result is not None else {}
    # Structured tool error so the MCP client can inspect it without
    # parsing free text.
    return {"success": False, "error": result.error}


# ── Tool registrations ────────────────────────────────────────────────
# Descriptions mirror app/tools/definitions.py verbatim (the OpenAI
# function-calling schemas) so the LLM gets the same call guidance on
# both the bespoke and MCP paths.


@mcp_server.tool(
    name="memory_search",
    description=(
        "Semantic search over the user's stored memory for the current "
        "project — chapter text, past chat turns, and glossary entries. "
        "Call this to find what is already known about a topic, character, "
        "place, or event before answering. Returns the most relevant text "
        "snippets."
    ),
)
async def memory_search(
    ctx: MCPContext,
    query: Annotated[str, "What to search for, in natural language."],
    limit: Annotated[
        int,
        Field(ge=1, le=SEARCH_LIMIT_MAX),
        f"Max snippets to return (default {SEARCH_LIMIT_DEFAULT}, "
        f"max {SEARCH_LIMIT_MAX}).",
    ] = SEARCH_LIMIT_DEFAULT,
    source_type: Annotated[
        Literal["chapter", "chat", "glossary"] | None,
        "Optional — restrict to one source: 'chapter', 'chat', or "
        "'glossary'. Omit to search all.",
    ] = None,
) -> dict:
    args: dict[str, Any] = {"query": query, "limit": limit}
    if source_type is not None:
        args["source_type"] = source_type
    return await _dispatch(ctx, "memory_search", args)


@mcp_server.tool(
    name="memory_recall_entity",
    description=(
        "Look up a specific entity (character, place, organization, item, "
        "etc.) by name and return its stored details plus its relationships "
        "to other entities. Use this when the user asks about a named thing "
        "and you need what memory holds on it."
    ),
)
async def memory_recall_entity(
    ctx: MCPContext,
    entity_name: Annotated[str, "The entity's name as it appears in the story."],
) -> dict:
    return await _dispatch(ctx, "memory_recall_entity", {"entity_name": entity_name})


@mcp_server.tool(
    name="memory_timeline",
    description=(
        "Retrieve narrative events in order for the current project, "
        "optionally filtered by a date range or by an entity that took part. "
        "Use this to answer 'what happened' or 'when did' questions."
    ),
)
async def memory_timeline(
    ctx: MCPContext,
    from_date: Annotated[
        str | None,
        "Optional inclusive lower bound, ISO date (YYYY, YYYY-MM, or "
        "YYYY-MM-DD).",
    ] = None,
    to_date: Annotated[
        str | None,
        "Optional inclusive upper bound, same ISO form.",
    ] = None,
    entity_name: Annotated[
        str | None,
        "Optional — only events this named entity took part in.",
    ] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=TIMELINE_LIMIT_MAX),
        f"Max events to return (default {TIMELINE_LIMIT_DEFAULT}, "
        f"max {TIMELINE_LIMIT_MAX}).",
    ] = TIMELINE_LIMIT_DEFAULT,
) -> dict:
    args: dict[str, Any] = {"limit": limit}
    if from_date is not None:
        args["from_date"] = from_date
    if to_date is not None:
        args["to_date"] = to_date
    if entity_name is not None:
        args["entity_name"] = entity_name
    return await _dispatch(ctx, "memory_timeline", args)


@mcp_server.tool(
    name="memory_remember",
    description=(
        "Store a new fact into long-term memory. Use sparingly — only for "
        "durable, important information the user explicitly stated or "
        "confirmed. Stored facts are recorded at low confidence and tagged "
        "as assistant-created so the user can review them."
    ),
)
async def memory_remember(
    ctx: MCPContext,
    fact_text: Annotated[str, "The fact to store, as a clear statement."],
    fact_type: Annotated[
        FactType,
        "decision = a choice made; preference = a standing like/dislike or "
        "habit; milestone = a notable achievement; negation = something "
        "explicitly NOT true.",
    ],
) -> dict:
    return await _dispatch(
        ctx,
        "memory_remember",
        {"fact_text": fact_text, "fact_type": fact_type},
    )


@mcp_server.tool(
    name="memory_forget",
    description=(
        "Invalidate a previously stored fact by its id so it no longer "
        "appears in memory. Only use a fact_id you have seen in an earlier "
        "tool result."
    ),
)
async def memory_forget(
    ctx: MCPContext,
    fact_id: Annotated[str, "The id of the fact to invalidate."],
) -> dict:
    return await _dispatch(ctx, "memory_forget", {"fact_id": fact_id})


# ── ASGI factory ──────────────────────────────────────────────────────


def build_mcp_app():
    """Return the ASGI app to mount at /mcp in main.py.

    ``FastMCP.streamable_http_app()`` returns a Starlette app whose own
    lifespan runs the StreamableHTTP session manager. Under FastAPI a
    *mounted* sub-app's lifespan is NOT auto-run, so main.py runs the
    session manager directly inside its own lifespan (see
    ``mcp_server.session_manager.run()`` there).
    """
    return mcp_server.streamable_http_app()
