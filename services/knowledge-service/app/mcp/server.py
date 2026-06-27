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
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field

from app.clients.embedding_client import get_embedding_client
from app.clients.grant_client import get_grant_client
from app.config import settings
from app.db.neo4j_repos.facts import FactType
from app.db.pool import get_knowledge_pool
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.graph_views import GraphViewsRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.repositories.pending_facts import PendingFactsRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.triage import TriageRepo
from app.ontology.resolver import OntologyResolver
from app.routers.public.ontology import get_glossary_ontology_client
from app.tools.definitions import (
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    TIMELINE_LIMIT_DEFAULT,
    TIMELINE_LIMIT_MAX,
)
from app.tools.executor import ToolContext, execute_tool, get_tools_redis
from app.tools.graph_schema_tools import (
    GRAPH_LIMIT_DEFAULT,
    GRAPH_LIMIT_MAX,
    TRIAGE_LIMIT_DEFAULT,
    TRIAGE_LIMIT_MAX,
    KgSyncDecision,
)
from app.tools.graph_schema_tools import (
    TIMELINE_LIMIT_DEFAULT as KG_TIMELINE_LIMIT_DEFAULT,
)
from app.tools.graph_schema_tools import (
    TIMELINE_LIMIT_MAX as KG_TIMELINE_LIMIT_MAX,
)

logger = logging.getLogger(__name__)

__all__ = ["mcp_server", "build_mcp_app"]

# Module-level FastMCP instance. build_mcp_app() converts it to an ASGI
# app for mounting in main.py. stateless_http=True + path="/" so the
# mount at "/mcp" exposes the endpoint at exactly "/mcp".
mcp_server = FastMCP(
    "knowledge-memory",
    stateless_http=True,
    streamable_http_path="/",
    # ARCH-2 D-ARCH2-MCP-LIVE-SMOKE: this is an INTERNAL service-to-service MCP
    # endpoint (chat-service → knowledge-service over the docker/private network,
    # authed by X-Internal-Token). The MCP SDK's DNS-rebinding protection only
    # allows localhost Host headers by default, so a cross-process call with
    # Host "knowledge-service:8092" gets 421 Misdirected Request. Disable it —
    # the trust boundary here is the private network + internal token, not the
    # Host header (which matters for browser-facing servers, not this one).
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)

# H-I: the optional project_id parameter shared by project-scoped tools. The
# public edge mints no X-Project-Id, so a public agent supplies the project here;
# the trusted envelope still wins when present, and the owner gate confines it to
# the caller's own projects (executor._resolve_project_scope + the per-tool gate).
# Mirrors ProjectScopedArgs.project_id (drift-locked by test_mcp_server's
# inputSchema-mirrors-bespoke check).
_PROJECT_ID_ARG = Annotated[
    str | None,
    "Knowledge project id to scope this call to. Omit to use the project linked "
    "to the current session; on the public API set it to one of your own projects.",
]


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
    mcp_key_id = _optional_header(ctx, "x-mcp-key-id")

    pool = get_knowledge_pool()
    projects_repo = ProjectsRepo(pool)
    return ToolContext(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        mcp_key_id=mcp_key_id,
        projects_repo=projects_repo,
        pending_facts_repo=PendingFactsRepo(pool),
        embedding_client=get_embedding_client(),
        redis=get_tools_redis(),
        # Lane LF (KG ontology MCP tools) deps — same process-singleton pool +
        # grant-client getter the HTTP routers/deps.py use, constructed directly
        # (the repos take a sync pool positional; the grant client is a process
        # singleton). Populated for the unified /mcp surface.
        grant_client=get_grant_client(),
        graph_views_repo=GraphViewsRepo(pool),
        graph_schemas_repo=GraphSchemasRepo(pool),
        triage_repo=TriageRepo(pool),
        ontology_resolver=OntologyResolver(
            schemas=GraphSchemasRepo(pool),
            projects=projects_repo,
            glossary=get_glossary_ontology_client(),
        ),
        ontology_mutations_repo=OntologyMutationsRepo(pool),
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"query": query, "limit": limit}
    if source_type is not None:
        args["source_type"] = source_type
    if project_id is not None:
        args["project_id"] = project_id
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"entity_name": entity_name}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "memory_recall_entity", args)


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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"limit": limit}
    if from_date is not None:
        args["from_date"] = from_date
    if to_date is not None:
        args["to_date"] = to_date
    if entity_name is not None:
        args["entity_name"] = entity_name
    if project_id is not None:
        args["project_id"] = project_id
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"fact_text": fact_text, "fact_type": fact_type}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "memory_remember", args)


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


# ── Knowledge-project lifecycle ───────────────────────────────────────
# kg_project_create is the book↔KG bootstrap: the KG schema, extraction, and
# wiki tools all operate on "the current project", so an agent needs to be able
# to stand one up. Class-W (additive, reversible); book-bound create is
# book-owner-only (D-KG-LF-PROJECT-CREATE-MCP).


@mcp_server.tool(
    name="kg_project_create",
    description=(
        "Create (or get) the knowledge PROJECT that anchors a book's knowledge "
        "graph + memory — the prerequisite for the KG schema, extraction, and "
        "wiki tools (which all act on 'the current project'). A book-bound "
        "project (book_id set) can only be created by the book's owner; omit "
        "book_id for a personal project. Idempotent per book. Returns the "
        "project_id — use it as the active project for subsequent KG tools."
    ),
)
async def kg_project_create(
    ctx: MCPContext,
    name: Annotated[str, "A human-readable project name."],
    project_type: Annotated[
        Literal["book", "translation", "code", "general"],
        "Project kind (default 'book' for a book's KG).",
    ] = "book",
    book_id: Annotated[
        str | None,
        "Link to this book (book-owner only). Omit for a personal project.",
    ] = None,
    description: Annotated[str, "Optional project description."] = "",
    genre: Annotated[
        str | None, "Optional genre hint (e.g. 'gothic horror')."
    ] = None,
) -> dict:
    args: dict[str, Any] = {"name": name, "project_type": project_type, "description": description}
    if book_id is not None:
        args["book_id"] = book_id
    if genre is not None:
        args["genre"] = genre
    return await _dispatch(ctx, "kg_project_create", args)


# ── KG ontology tools (lane LF; KM1/KM2 + R-class KM3/KM4) ─────────────
# Descriptions mirror app/tools/graph_schema_tools.py verbatim. R (read) +
# reversible W tiers below; the class-C ontology tools (adopt / schema-edit /
# sync-apply / schema-mutating-triage) follow at the end of the file. The
# class-C tools NEVER write — each MINTS a confirm-token + summary that a human
# redeems on the review surface (POST /v1/kg/actions/confirm, browser-JWT), so
# the agent only proposes and the INV-T3 human-confirm backstop holds (mirrors
# glossary's adopt/propose tools). System-tier ADMIN tools stay off this
# catalog — they live behind the separate RS256-gated /mcp/admin endpoint
# (D-KG-LF-KM6 cleared 2026-06-21).


@mcp_server.tool(
    name="kg_graph_query",
    description=(
        "Read the current project's knowledge graph as nodes + edges, "
        "optionally narrowed to a named view (lens) and to a point in the "
        "story via a chapter ordinal. Use this to see who relates to whom as "
        "of a given chapter. Returns nodes, edges, and any warnings."
    ),
)
async def kg_graph_query(
    ctx: MCPContext,
    view: Annotated[
        str | None,
        "Optional view code (a saved lens). Omit to read the whole graph.",
    ] = None,
    as_of_chapter: Annotated[
        int | None,
        Field(ge=0),
        "Optional chapter ordinal — the graph as it stood at that chapter. "
        "Omit for the latest state.",
    ] = None,
    limit: Annotated[
        int,
        Field(ge=1, le=GRAPH_LIMIT_MAX),
        f"Max edges to scan (default {GRAPH_LIMIT_DEFAULT}).",
    ] = GRAPH_LIMIT_DEFAULT,
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"limit": limit}
    if view is not None:
        args["view"] = view
    if as_of_chapter is not None:
        args["as_of_chapter"] = as_of_chapter
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_graph_query", args)


@mcp_server.tool(
    name="kg_entity_edge_timeline",
    description=(
        "Retrieve the ordered temporal chain of one relationship type for a "
        "single entity (e.g. a character's drive arc). Use an entity id and an "
        "edge-type code seen in an earlier graph result. Returns the full arc, "
        "including closed (superseded) instances."
    ),
)
async def kg_entity_edge_timeline(
    ctx: MCPContext,
    entity_id: Annotated[str, "The entity id (as seen in a graph result)."],
    edge_type: Annotated[str, "The relationship edge-type code to trace."],
    limit: Annotated[
        int,
        Field(ge=1, le=KG_TIMELINE_LIMIT_MAX),
        f"Max instances (default {KG_TIMELINE_LIMIT_DEFAULT}).",
    ] = KG_TIMELINE_LIMIT_DEFAULT,
) -> dict:
    # No project_id arg: this tool scopes by the ENTITY (resolved to its owner +
    # OD-8-gated in the handler), so a project_id here would be a no-op.
    return await _dispatch(
        ctx,
        "kg_entity_edge_timeline",
        {"entity_id": entity_id, "edge_type": edge_type, "limit": limit},
    )


@mcp_server.tool(
    name="kg_schema_read",
    description=(
        "Read the resolved (effective) graph schema for the current project — "
        "the edge types, fact types, controlled vocab, and expected node "
        "kinds. Use this to learn what relationship and fact codes are valid "
        "before proposing an edge or fact."
    ),
)
async def kg_schema_read(
    ctx: MCPContext, project_id: _PROJECT_ID_ARG = None
) -> dict:
    args: dict[str, Any] = {}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_schema_read", args)


@mcp_server.tool(
    name="kg_list_templates",
    description=(
        "List the graph-schema templates available to adopt — the system "
        "(built-in) templates and the caller's own user templates. Use this to "
        "discover what ontologies a project could be based on."
    ),
)
async def kg_list_templates(
    ctx: MCPContext,
    scope: Annotated[
        Literal["system", "user"] | None,
        "Optional — restrict to 'system' or 'user' templates. Omit for both.",
    ] = None,
) -> dict:
    args: dict[str, Any] = {}
    if scope is not None:
        args["scope"] = scope
    return await _dispatch(ctx, "kg_list_templates", args)


@mcp_server.tool(
    name="kg_sync_available",
    description=(
        "Check whether the current project's graph schema has upstream "
        "template updates available to pull (a tree-granular diff). Read-only: "
        "reports what changed; it does NOT apply anything."
    ),
)
async def kg_sync_available(
    ctx: MCPContext, project_id: _PROJECT_ID_ARG = None
) -> dict:
    args: dict[str, Any] = {}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_sync_available", args)


@mcp_server.tool(
    name="kg_view_read",
    description=(
        "List the caller's saved views (named lenses of edge/node kinds) for "
        "the current project. Views are per-user — you only ever see your own."
    ),
)
async def kg_view_read(
    ctx: MCPContext, project_id: _PROJECT_ID_ARG = None
) -> dict:
    args: dict[str, Any] = {}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_view_read", args)


@mcp_server.tool(
    name="kg_triage_list",
    description=(
        "List the project's triage queue — extracted graph elements that did "
        "not match the schema and are parked for human review — grouped by "
        "signature with a count and a suggested-action list."
    ),
)
async def kg_triage_list(
    ctx: MCPContext,
    status: Annotated[
        Literal["pending", "pending_glossary", "resolved", "dismissed"],
        "Which queue to list (default 'pending').",
    ] = "pending",
    limit: Annotated[
        int,
        Field(ge=1, le=TRIAGE_LIMIT_MAX),
        f"Max signature groups (default {TRIAGE_LIMIT_DEFAULT}).",
    ] = TRIAGE_LIMIT_DEFAULT,
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"status": status, "limit": limit}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_triage_list", args)


@mcp_server.tool(
    name="kg_propose_fact",
    description=(
        "Propose a narrative fact for the current project into the review "
        "inbox (a draft awaiting the user's confirmation — it does NOT enter "
        "the graph immediately). Use for durable, important facts the user "
        "stated or confirmed."
    ),
)
async def kg_propose_fact(
    ctx: MCPContext,
    fact_text: Annotated[str, "The fact to propose, as a clear statement."],
    fact_type: Annotated[
        Literal["decision", "preference", "milestone", "negation"],
        "decision = a choice made; preference = a standing like/dislike; "
        "milestone = a notable achievement; negation = something NOT true.",
    ],
) -> dict:
    return await _dispatch(
        ctx,
        "kg_propose_fact",
        {"fact_text": fact_text, "fact_type": fact_type},
    )


@mcp_server.tool(
    name="kg_propose_edge",
    description=(
        "Propose a relationship edge between two entities for human review. "
        "The edge is validated against the project schema and parked in the "
        "triage inbox — it is NEVER written to the graph directly. If the edge "
        "type is temporal you MUST supply valid_from (the chapter ordinal it "
        "began); otherwise the proposal is rejected."
    ),
)
async def kg_propose_edge(
    ctx: MCPContext,
    source_entity_id: Annotated[str, "The id of the relationship's source entity."],
    target_entity_id: Annotated[str, "The id of the relationship's target entity."],
    edge_type: Annotated[str, "The relationship edge-type code (see kg_schema_read)."],
    source_kind: Annotated[
        str | None, "Optional — the source entity's node kind, for validation."
    ] = None,
    target_kind: Annotated[
        str | None, "Optional — the target entity's node kind, for validation."
    ] = None,
    valid_from: Annotated[
        int | None,
        Field(ge=0),
        "The chapter ordinal the relationship began. REQUIRED for a temporal "
        "edge type.",
    ] = None,
    valid_to: Annotated[
        int | None,
        Field(ge=0),
        "Optional — the chapter ordinal the relationship ended.",
    ] = None,
) -> dict:
    args: dict[str, Any] = {
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "edge_type": edge_type,
    }
    if source_kind is not None:
        args["source_kind"] = source_kind
    if target_kind is not None:
        args["target_kind"] = target_kind
    if valid_from is not None:
        args["valid_from"] = valid_from
    if valid_to is not None:
        args["valid_to"] = valid_to
    return await _dispatch(ctx, "kg_propose_edge", args)


@mcp_server.tool(
    name="kg_view_upsert",
    description=(
        "Create or replace one of the caller's saved views (a named lens of "
        "edge-type + node-kind codes) for the current project. Owner-scoped: "
        "only ever touches your own view."
    ),
)
async def kg_view_upsert(
    ctx: MCPContext,
    code: Annotated[str, "The view's stable code (slug)."],
    name: Annotated[str, "A human-readable view name."],
    description: Annotated[str, "Optional description."] = "",
    edge_type_codes: Annotated[
        list[str] | None, "Edge-type codes the view includes (empty = all)."
    ] = None,
    node_kind_codes: Annotated[
        list[str] | None, "Node-kind codes the view includes (empty = all)."
    ] = None,
) -> dict:
    return await _dispatch(
        ctx,
        "kg_view_upsert",
        {
            "code": code,
            "name": name,
            "description": description,
            "edge_type_codes": edge_type_codes or [],
            "node_kind_codes": node_kind_codes or [],
        },
    )


@mcp_server.tool(
    name="kg_view_delete",
    description=(
        "Delete one of the caller's saved views by code for the current "
        "project. Owner-scoped and reversible (recreate with kg_view_upsert)."
    ),
)
async def kg_view_delete(
    ctx: MCPContext,
    code: Annotated[str, "The code of the view to delete."],
) -> dict:
    return await _dispatch(ctx, "kg_view_delete", {"code": code})


@mcp_server.tool(
    name="kg_triage_resolve",
    description=(
        "Resolve a triage signature group with a low-impact, reversible "
        "action: map, re_target, drop_edge, close_previous, or dismiss. "
        "Schema-changing actions (add to vocab/schema, widen, promote to "
        "glossary) are NOT available here — those need explicit human "
        "confirmation via the review surface."
    ),
)
async def kg_triage_resolve(
    ctx: MCPContext,
    signature: Annotated[str, "The triage signature to resolve (from kg_triage_list)."],
    action: Annotated[
        Literal["map", "re_target", "drop_edge", "close_previous", "dismiss"],
        "The KG-local resolution action to apply.",
    ],
    params: Annotated[
        dict | None, "Optional action parameters (e.g. the map target code)."
    ] = None,
) -> dict:
    return await _dispatch(
        ctx,
        "kg_triage_resolve",
        {"signature": signature, "action": action, "params": params or {}},
    )


# ── KG ontology class-C tools (KM6) — PROPOSE only ─────────────────────
# Each mints a confirm-token + summary (no write); a human redeems it via
# POST /v1/kg/actions/confirm (browser-JWT). See the catalog note above.


@mcp_server.tool(
    name="kg_schema_edit",
    description=(
        "Propose a change to THIS project's ontology: add or deprecate an edge "
        "type or fact type. High-impact (it changes the graph's shape and bumps "
        "the schema version), so it does NOT apply immediately — it returns a "
        "confirm_token and a summary; a human must confirm it on the review "
        "surface. Requires the project to have adopted its own ontology first."
    ),
)
async def kg_schema_edit(
    ctx: MCPContext,
    verb: Annotated[
        Literal["add", "deprecate"],
        "add a new type, or deprecate (soft-remove) an existing one.",
    ],
    level: Annotated[
        Literal["edge_type", "fact_type"],
        "Which kind of ontology element to change.",
    ],
    code: Annotated[str, "The type's code (e.g. WORSHIPS, prophecy)."],
    label: Annotated[
        str, "Human-readable label (for add; defaults to the code)."
    ] = "",
) -> dict:
    return await _dispatch(
        ctx,
        "kg_schema_edit",
        {"verb": verb, "level": level, "code": code, "label": label},
    )


@mcp_server.tool(
    name="kg_adopt_template",
    description=(
        "Propose adopting (copying down) a system or user ontology template "
        "into THIS project, scaffolding its edge types / node kinds / fact "
        "types. High-impact — it does NOT apply immediately; it returns a "
        "confirm_token and a summary, and a human confirms on the review "
        "surface. Pick a source_schema_id from kg_list_templates."
    ),
)
async def kg_adopt_template(
    ctx: MCPContext,
    source_schema_id: Annotated[
        str, "The template id to adopt (from kg_list_templates)."
    ],
) -> dict:
    return await _dispatch(
        ctx, "kg_adopt_template", {"source_schema_id": source_schema_id}
    )


@mcp_server.tool(
    name="kg_sync_apply",
    description=(
        "Propose syncing THIS project's ontology with its upstream template — "
        "applying per-change keep_mine / take_theirs decisions (read the diff "
        "with kg_sync_available first). High-impact (overwrites/deprecates rows "
        "+ bumps the schema version), so it returns a confirm_token and summary; "
        "a human confirms on the review surface."
    ),
)
async def kg_sync_apply(
    ctx: MCPContext,
    base_source_hash: Annotated[
        str, "The upstream hash returned by kg_sync_available (drift guard)."
    ],
    decisions: Annotated[
        list[KgSyncDecision] | None,
        "Per-change decisions to apply (omit for none).",
    ] = None,
) -> dict:
    # Typed item model (not bare list[dict]) so the MCP inputSchema carries the
    # SAME per-decision shape the bespoke OpenAI schema advertises (parity).
    # model_dump() back to plain dicts — execute_tool re-validates via the arg model.
    return await _dispatch(
        ctx,
        "kg_sync_apply",
        {
            "base_source_hash": base_source_hash,
            "decisions": [d.model_dump() for d in (decisions or [])],
        },
    )


@mcp_server.tool(
    name="kg_triage_place_edge",
    description=(
        "Place an agent-drafted proposed edge (from kg_triage_list, item_type "
        "'proposed_edge') into the knowledge graph. High-impact (it writes a "
        "real edge), so it does NOT apply immediately — it returns a "
        "confirm_token and a summary; a human confirms on the review surface."
    ),
)
async def kg_triage_place_edge(
    ctx: MCPContext,
    triage_id: Annotated[
        str, "The proposed_edge triage item id to place (from kg_triage_list)."
    ],
) -> dict:
    return await _dispatch(ctx, "kg_triage_place_edge", {"triage_id": triage_id})


@mcp_server.tool(
    name="kg_triage_schema_write",
    description=(
        "Resolve a schema-mutating triage signature group: add_to_vocab (add a "
        "controlled-vocab value), add_to_schema (add an edge type), "
        "widen_target_kinds (allow more target node kinds on an edge type), or "
        "set_multi_active (let an edge type hold multiple open instances). This "
        "changes the project ontology and bumps the schema version, so it does "
        "NOT apply immediately — it returns a confirm_token and a summary; a "
        "human confirms on the review surface."
    ),
)
async def kg_triage_schema_write(
    ctx: MCPContext,
    signature: Annotated[
        str, "The triage signature to resolve (from kg_triage_list)."
    ],
    action: Annotated[
        Literal[
            "add_to_vocab", "add_to_schema", "widen_target_kinds", "set_multi_active"
        ],
        "The schema-mutating resolution action to apply.",
    ],
    code: Annotated[
        str, "The new/affected element code (add_to_vocab / add_to_schema)."
    ] = "",
    label: Annotated[str, "Human-readable label (for add actions)."] = "",
    set_code: Annotated[str, "The vocab-set code (add_to_vocab only)."] = "",
    add_kinds: Annotated[
        list[str] | None,
        "Target node-kind codes to allow (widen_target_kinds only).",
    ] = None,
) -> dict:
    return await _dispatch(
        ctx,
        "kg_triage_schema_write",
        {
            "signature": signature,
            "action": action,
            "code": code,
            "label": label,
            "set_code": set_code,
            "add_kinds": add_kinds or [],
        },
    )


# ── Cost-gated job triggers (KM6) — PROPOSE only ──────────────────────
# kg_build_graph mints a confirm-token carrying a cost estimate; the human
# confirms via /v1/kg/actions/confirm and the extraction job starts there
# (D-KG-LF-BUILDKG-MCP). Nothing is spent at mint time.


@mcp_server.tool(
    name="kg_build_graph",
    description=(
        "Build the current project's knowledge graph by starting an extraction job over "
        "the book's chapters. EXPENSIVE (LLM cost) so it does NOT run immediately — it "
        "returns a confirm_token + summary; a human confirms on the review surface (which "
        "shows the estimated cost) and the job starts then. Requires the project to have "
        "an embedding model configured (run extraction setup once in the UI first). Pick "
        "the extraction llm_model from settings_list_models."
    ),
)
async def kg_build_graph(
    ctx: MCPContext,
    llm_model: Annotated[
        str, "The extraction LLM model ref (from settings_list_models)."
    ],
    scope: Annotated[
        Literal["all", "chapters", "chat", "glossary_sync"],
        "What to extract (default 'all').",
    ] = "all",
    chapter_from: Annotated[
        int | None,
        Field(ge=0),
        "Optional inclusive lower chapter ordinal (with chapter_to).",
    ] = None,
    chapter_to: Annotated[
        int | None,
        Field(ge=0),
        "Optional inclusive upper chapter ordinal (with chapter_from).",
    ] = None,
    reasoning_effort: Annotated[
        Literal["none", "low", "medium", "high"],
        "Model reasoning effort (default 'none'; clamped to your grant — Edit "
        "caps at medium, Manage/owner at high).",
    ] = "none",
) -> dict:
    args: dict[str, Any] = {
        "llm_model": llm_model, "scope": scope, "reasoning_effort": reasoning_effort,
    }
    if chapter_from is not None:
        args["chapter_from"] = chapter_from
    if chapter_to is not None:
        args["chapter_to"] = chapter_to
    return await _dispatch(ctx, "kg_build_graph", args)


@mcp_server.tool(
    name="kg_build_wiki",
    description=(
        "Generate wiki articles for the current project's book entities. EXPENSIVE (LLM "
        "cost per entity) so it does NOT run immediately — it returns a confirm_token + "
        "summary; a human confirms on the review surface (which shows the entity count + "
        "estimated cost) and the job starts then. Omit entity_ids to generate for ALL the "
        "book's glossary entities (extract the glossary first); pick the model_ref from "
        "settings_list_models."
    ),
)
async def kg_build_wiki(
    ctx: MCPContext,
    model_ref: Annotated[
        str, "The wiki-generation LLM model ref (from settings_list_models)."
    ],
    model_source: Annotated[
        str, "Model source (default 'user_model' for BYOK)."
    ] = "user_model",
    entity_ids: Annotated[
        list[str] | None,
        "Optional explicit entity ids; omit to generate for ALL book entities.",
    ] = None,
    reasoning_effort: Annotated[
        Literal["none", "low", "medium", "high"],
        "Model reasoning effort (default 'none'; clamped to your grant — Edit "
        "caps at medium, Manage/owner at high).",
    ] = "none",
) -> dict:
    args: dict[str, Any] = {
        "model_ref": model_ref, "model_source": model_source,
        "reasoning_effort": reasoning_effort,
    }
    if entity_ids is not None:
        args["entity_ids"] = entity_ids
    return await _dispatch(ctx, "kg_build_wiki", args)


@mcp_server.tool(
    name="kg_run_benchmark",
    description=(
        "Run the required embedding-quality benchmark for the current project's embedding "
        "model. Build-KG (kg_build_graph) is BLOCKED until this passes — call this when a "
        "build preview warns the benchmark is not passing, instead of sending the user to "
        "the UI. Cheap (embeddings only, no LLM cost) and runs immediately on a hidden "
        "sandbox. Returns passed + gate_failures; a pass enables Build-KG for this model."
    ),
)
async def kg_run_benchmark(ctx: MCPContext) -> dict:
    return await _dispatch(ctx, "kg_run_benchmark", {})


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
