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

import json
import logging
import secrets
from typing import Annotated, Any, Literal
from uuid import UUID

from mcp.server.fastmcp import Context as MCPContext
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from loreweave_mcp import patch_convert_result, require_meta
from pydantic import Field, ValidationError

from app.clients.book_client import get_book_client
from app.clients.embedding_client import get_embedding_client
from app.clients.reranker_client import get_reranker_client
from app.clients.grant_client import get_grant_client
from app.config import settings
from app.db.neo4j import neo4j_session
from app.db.neo4j_repos.entities import list_entities_filtered
from app.db.neo4j_repos.facts import FactType
from app.db.pool import get_knowledge_pool
from app.db.repositories.graph_schemas import GraphSchemasRepo
from app.db.repositories.graph_views import GraphViewsRepo
from app.db.repositories.ontology_mutations import OntologyMutationsRepo
from app.db.repositories.pending_facts import PendingFactsRepo
from app.db.repositories.projects import ProjectsRepo
from app.db.repositories.summaries import SummariesRepo
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

# P4/Wave-C slice D — public MCP-key spend carrier. knowledge-service builds its
# OWN ToolContext (richer than the loreweave_mcp kit's), so the kit's universal
# carrier hook never runs here — we must set the loreweave_llm attribution
# contextvar ourselves in _build_tool_context, or kg_build_graph/build_wiki/
# run_benchmark (priced) would carry NO per-key cap + NO attribution. Soft import
# so a knowledge build without loreweave_llm still loads.
try:
    from loreweave_llm.attribution import set_public_key_attribution as _set_llm_attribution
except Exception:  # pragma: no cover
    _set_llm_attribution = None
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

# External MCP discoverability audit #9 — every structured tool result used
# to duplicate its full payload into content[0].text (already-JSON-parsed
# structuredContent sitting right next to a JSON-STRINGIFIED copy of the same
# data). knowledge-service builds its own FastMCP instance directly (unlike
# composition/jobs/translation/lore-enrichment-service, which go through the
# shared `loreweave_mcp.make_stateless_fastmcp` chokepoint and get this for
# free) — this service already ships `loreweave_mcp` as a dependency (it's
# installed via `pip install /sdk` in the Dockerfile) even though it doesn't
# use the rest of the kit, so this is a plain function import, not a new
# dependency. See sdks/python/loreweave_mcp/compact_content.py for the fix
# itself (a defensive FastMCP monkeypatch — never raises even if a future mcp
# release changes the shape it targets).
patch_convert_result()

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


# ── W0 #4b — model-directed validation errors ─────────────────────────
# FastMCP surfaces a pydantic arg-validation failure as the RAW multi-line
# dump (with the errors.pydantic.dev URL) — noise a model cannot act on.
# Intercept at the per-server tool-dispatch chokepoint and rewrite to a
# ONE-LINE directive (arg name + what pydantic expected + what was sent).
# Mirrors jobs-service/translation-service; the loreweave_mcp kit will
# absorb the shared copy later (kit is outside the W0 change surface).


def _validation_directive(tool_name: str, exc: ValidationError) -> str:
    """One line: every failing arg with pydantic's expectation + the sent shape."""
    parts = []
    errs = exc.errors(include_url=False)
    for err in errs[:3]:
        loc = ".".join(str(p) for p in err.get("loc", ())) or "arguments"
        msg = err.get("msg", "invalid value")
        sent = err.get("input")
        parts.append(f"`{loc}`: {msg} (you sent a {type(sent).__name__})")
    if len(errs) > 3:
        parts.append(f"(+{len(errs) - 3} more)")
    return (
        f"invalid arguments for {tool_name} — "
        + "; ".join(parts)
        + ". Fix the argument and call the tool again."
    )


def _install_validation_error_rewriter(server: FastMCP) -> None:
    """Wrap the FastMCP tool manager's dispatch so a ToolError caused by a
    pydantic ValidationError re-raises with the one-line directive instead of
    the raw dump. Non-validation errors pass through untouched."""
    manager = server._tool_manager
    original = manager.call_tool

    async def call_tool(name, arguments, *args, **kwargs):
        try:
            return await original(name, arguments, *args, **kwargs)
        except ToolError as e:
            cause = e.__cause__
            if isinstance(cause, ValidationError):
                raise ToolError(_validation_directive(name, cause)) from cause
            raise

    manager.call_tool = call_tool


_install_validation_error_rewriter(mcp_server)

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

# L1/L2 reference-first `detail` arg (Context Budget Law §6b). Enum-locked Literal
# so a weak local model can't send a free-string value; versioned default "full"
# (legacy callers unchanged). Advertised on the SET-returning tools; the FastMCP
# signature MUST carry it or FastMCP strips it from the forwarded args (the
# three-schema-source lockstep — definitions/graph_schema_tools + this signature +
# the executor handler). Mirrored into the bespoke OpenAI schema (_DETAIL_PROP).
_DETAIL_ARG = Annotated[
    Literal["summary", "full"],
    "Response granularity. 'full' (default) = every field; 'summary' = a compact "
    "reference projection (ids/title/snippet/score; heavy bodies dropped) for "
    "cheap scanning — re-read specifics at full detail or via a get-by-id sibling. "
    "Result `meta` reports total/returned/truncated.",
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


def _parse_spend_cap(raw: str | None) -> float | None:
    """Parse X-Mcp-Spend-Cap-Usd to a non-negative float, else None (fails OPEN to
    no per-key cap on a malformed value — the owner guardrail still bounds spend).
    Mirrors loreweave_mcp.context._parse_spend_cap (P4/Wave-C slice D)."""
    if not raw:
        return None
    try:
        v = float(raw)
    except (TypeError, ValueError):
        return None
    return v if v >= 0 else None


def _require_envelope_user(ctx: MCPContext) -> UUID:
    """Authenticate the MCP envelope: internal-token check + caller identity.

    Shared by the tool dispatch path (_build_tool_context) and the Wave C5
    resource read path, so both surfaces apply byte-identical auth BEFORE any
    repo access. Raises ValueError (FastMCP surfaces it as an MCP-level error,
    not a 500) on a missing/wrong token or a malformed user id.
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
        return UUID(raw_user_id)
    except ValueError:
        raise ValueError(f"x-user-id is not a valid UUID: {raw_user_id!r}")


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
    user_id = _require_envelope_user(ctx)

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

    # P4/Wave-C slice D — set (or CLEAR) the public-key spend carrier on the
    # loreweave_llm contextvar for THIS task, so a priced kg_* tool's provider job
    # carries mcp_key_id + cap into job_meta (header is gone by the time we submit
    # to provider-registry). Mirrors loreweave_mcp.build_tool_context's universal
    # hook, which this custom builder bypasses. A first-party call clears it (None).
    if _set_llm_attribution is not None:
        _set_llm_attribution(mcp_key_id, _parse_spend_cap(_optional_header(ctx, "x-mcp-spend-cap-usd")))

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
        # #12 story_search (universal manuscript search) deps — the raw-search
        # hybrid engine's lexical leg (book-service) + BYOK reranker.
        book_client=get_book_client(),
        reranker_client=get_reranker_client(),
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
    """Build a ToolContext, call execute_tool(), return the result dict.

    A tool-level failure (ToolResult.success=False) RAISES ``ToolError`` so the
    MCP result carries ``isError: true`` (D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR).
    It used to return ``{"success": False, "error": ...}`` on an otherwise
    *successful* tool result, which meant:
      * ai-gateway's C4 normalizer (which triggers on isError / a throw) never
        saw a knowledge tool failure, so it was never normalized; and
      * any consumer branching on ``isError`` read a failed call as a success —
        the silent-success bug class.

    The error body is JSON — ``{"code"?, "message", "detail"?}`` — matching the
    exact shape ai-gateway itself puts in ``content[0].text``
    (``JSON.stringify({code, message})``), so a stable ``code`` (e.g.
    ``KG_ENDPOINT_NOT_NODE``) and ``detail`` (``{"missing": [...]}``) survive to
    the caller and a workflow can branch on them instead of parsing prose
    (contract C4/C5). chat-service's ``knowledge_client.mcp_execute_tool``
    decodes it back out of the isError branch.

    An infrastructure exception (Neo4j down, etc.) still propagates as itself.
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

    err: dict[str, Any] = {"message": result.error or "tool error"}
    if result.code is not None:
        err["code"] = result.code
    if result.detail is not None:
        err["detail"] = result.detail
    raise ToolError(json.dumps(err, default=str))


# ── Tool registrations ────────────────────────────────────────────────
# Descriptions mirror app/tools/definitions.py verbatim (the OpenAI
# function-calling schemas) so the LLM gets the same call guidance on
# both the bespoke and MCP paths.


@mcp_server.tool(
    name="story_search",
    description=(
        "Search the book's manuscript for text or ideas — the universal find "
        "tool. Use it to LOCATE where something appears before reading or "
        "editing: an exact phrase/name (mode=exact), a concept described in "
        "your own words (mode=semantic), or both fused (mode=hybrid, default, "
        "best for most queries). granularity=chapter tells you WHICH chapters "
        "match; granularity=block drills into the matching passages with "
        "snippets. Follow up with book_get_chapter to read."
    ),
    meta=require_meta(
        "R", "project",
        tool_name="story_search",
    ),
)
async def story_search(
    ctx: MCPContext,
    query: Annotated[str, "The text or idea to find — an exact phrase, a character/place name, or a natural-language description."],
    mode: Annotated[
        Literal["hybrid", "exact", "semantic"],
        "hybrid (default) = exact + semantic fused and reranked; exact = literal text match only; semantic = meaning match only.",
    ] = "hybrid",
    granularity: Annotated[
        Literal["chapter", "block"],
        "chapter (default) = which chapters match; block = the matching passages with snippets.",
    ] = "chapter",
    limit: Annotated[
        int,
        Field(ge=1, le=SEARCH_LIMIT_MAX),
        f"Max hits to return (default {SEARCH_LIMIT_DEFAULT}, max {SEARCH_LIMIT_MAX}).",
    ] = SEARCH_LIMIT_DEFAULT,
    detail: _DETAIL_ARG = "full",
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {
        "query": query, "mode": mode, "granularity": granularity, "limit": limit,
        "detail": detail,
    }
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "story_search", args)


@mcp_server.tool(
    name="memory_search",
    description=(
        "Search the project's stored knowledge for what is already known about a "
        "topic, character, place, or event before answering — the book's chapter "
        "text (lexical + semantic, so it finds an exact phrase even with nothing "
        "indexed yet), past chat turns, and glossary entries. Returns the most "
        "relevant snippets. (For locating/reading manuscript prose specifically, "
        "`story_search` is the primary find tool.)"
    ),
    meta=require_meta(
        "R", "project",
        tool_name="memory_search",
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
    detail: _DETAIL_ARG = "full",
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"query": query, "limit": limit, "detail": detail}
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
    meta=require_meta(
        "R", "project",
        tool_name="memory_recall_entity",
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
    meta=require_meta(
        "R", "project",
        tool_name="memory_timeline",
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
    detail: _DETAIL_ARG = "full",
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"limit": limit, "detail": detail}
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
    meta=require_meta(
        "A", "project",
        tool_name="memory_remember",
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
    meta=require_meta(
        "A", "project",
        tool_name="memory_forget",
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
    meta=require_meta(
        "A", "user",
        tool_name="kg_project_create",
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


@mcp_server.tool(
    name="kg_project_list",
    description=(
        "List YOUR OWN knowledge projects (id, name, type, linked book). Use this "
        "to find the `project_id` to pass to a project-scoped kg_* tool when no "
        "project is in scope. Owner-scoped: only the caller's projects are returned."
    ),
    meta=require_meta(
        "R", "user",
        tool_name="kg_project_list",
    ),
)
async def kg_project_list(
    ctx: MCPContext,
    include_archived: Annotated[
        bool, "Also include archived projects (default false)."
    ] = False,
    limit: Annotated[
        int, Field(ge=1, le=50), "Max projects to return (default 20)."
    ] = 20,
) -> dict:
    return await _dispatch(
        ctx, "kg_project_list", {"include_archived": include_archived, "limit": limit}
    )


@mcp_server.tool(
    name="kg_project_set_embedding_model",
    description=(
        "Configure the project's EMBEDDING MODEL — the one-time setup that "
        "kg_run_benchmark and kg_build_graph both require. Call this when a build "
        "reports the project has no embedding model configured, instead of sending "
        "the user to the UI. Pass a provider-registry user_model UUID for one of your "
        "own embedding models (find one with settings_list_models). The vector "
        "dimension is probed automatically. Free, reversible, owner-only. Then call "
        "kg_run_benchmark, then kg_build_graph."
    ),
    meta=require_meta(
        "A", "project",
        tool_name="kg_project_set_embedding_model",
    ),
)
async def kg_project_set_embedding_model(
    ctx: MCPContext,
    embedding_model: Annotated[
        str, "provider-registry user_model UUID of an embedding model you own."
    ],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"embedding_model": embedding_model}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_project_set_embedding_model", args)


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
    meta=require_meta(
        "R", "project",
        tool_name="kg_graph_query",
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
    detail: _DETAIL_ARG = "full",
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"limit": limit, "detail": detail}
    if view is not None:
        args["view"] = view
    if as_of_chapter is not None:
        args["as_of_chapter"] = as_of_chapter
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_graph_query", args)


@mcp_server.tool(
    name="kg_world_query",
    description=(
        "Read the rolled-up knowledge graph of an entire WORLD as nodes + edges — the "
        "union of every member book's canon KG plus the world-level lore. Use this to "
        "synthesize ACROSS all books in a world (recurring entities, cross-book "
        "relationships), not one project at a time. Owner-only: partitions owned by "
        "others are skipped and reported in partitions_unreadable."
    ),
    meta=require_meta(
        "R", "project",
        tool_name="kg_world_query",
    ),
)
async def kg_world_query(
    ctx: MCPContext,
    world_id: Annotated[
        str,
        "The id of the world to roll up (you must own it). Pass it explicitly — a world "
        "spans many projects, so the session's single-project scope doesn't apply.",
    ],
    limit: Annotated[
        int,
        Field(ge=1, le=GRAPH_LIMIT_MAX),
        "Max nodes in the union (default 200).",
    ] = 200,
    unify: Annotated[
        Literal["off", "by_name", "semantic"],
        "Cross-book entity unification. 'off' (default) = the raw per-book forest. "
        "'by_name' matches the same entity across books by name/alias; 'semantic' also "
        "matches by meaning (embeddings, catching renames). Both add "
        "unification_clusters + inferred SAME_AS bridge_edges (one connected graph).",
    ] = "off",
    detail: _DETAIL_ARG = "full",
) -> dict:
    return await _dispatch(
        ctx, "kg_world_query",
        {"world_id": world_id, "limit": limit, "unify": unify, "detail": detail},
    )


@mcp_server.tool(
    name="kg_multi_query",
    description=(
        "Read the UNION knowledge graph across an ARBITRARY SET of your knowledge "
        "projects as nodes + edges — e.g. compare a canon KG against a fan-theory KG, "
        "or load two unrelated books at once. Unlike kg_world_query (a whole world), "
        "you name the exact project_ids. Owner-only: ids you don't own are skipped and "
        "reported in partitions_unreadable (the result also carries partitions_read)."
    ),
    meta=require_meta(
        "R", "user",
        tool_name="kg_multi_query",
    ),
)
async def kg_multi_query(
    ctx: MCPContext,
    project_ids: Annotated[
        list[str],
        Field(min_length=1, max_length=16),
        "The project ids to union (1–16; you must own each). Pass them explicitly — this "
        "loads an arbitrary set of your KGs, not the session's single project.",
    ],
    limit: Annotated[
        int,
        Field(ge=1, le=GRAPH_LIMIT_MAX),
        "Max nodes in the union (default 200).",
    ] = 200,
    unify: Annotated[
        Literal["off", "by_name", "semantic"],
        "Cross-book entity unification. 'off' (default) = the raw per-book forest. "
        "'by_name' matches the same entity across books by name/alias; 'semantic' also "
        "matches by meaning (embeddings, catching renames). Both add "
        "unification_clusters + inferred SAME_AS bridge_edges (one connected graph).",
    ] = "off",
    detail: _DETAIL_ARG = "full",
) -> dict:
    return await _dispatch(
        ctx, "kg_multi_query",
        {"project_ids": project_ids, "limit": limit, "unify": unify, "detail": detail},
    )


@mcp_server.tool(
    name="kg_entity_edge_timeline",
    description=(
        "Retrieve the ordered temporal chain of one relationship type for a "
        "single entity (e.g. a character's drive arc). Use an entity id and an "
        "edge-type code seen in an earlier graph result. Returns the full arc, "
        "including closed (superseded) instances."
    ),
    meta=require_meta(
        "R", "project",
        tool_name="kg_entity_edge_timeline",
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
    detail: _DETAIL_ARG = "full",
) -> dict:
    # No project_id arg: this tool scopes by the ENTITY (resolved to its owner +
    # OD-8-gated in the handler), so a project_id here would be a no-op.
    return await _dispatch(
        ctx,
        "kg_entity_edge_timeline",
        {"entity_id": entity_id, "edge_type": edge_type, "limit": limit, "detail": detail},
    )


@mcp_server.tool(
    name="kg_schema_read",
    description=(
        "Read the resolved (effective) graph schema for the current project — "
        "the edge types, fact types, controlled vocab, and expected node "
        "kinds. Use this to learn what relationship and fact codes are valid "
        "before proposing an edge or fact."
    ),
    meta=require_meta(
        "R", "project",
        tool_name="kg_schema_read",
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
    meta=require_meta(
        "R", "user",
        tool_name="kg_list_templates",
    ),
)
async def kg_list_templates(
    ctx: MCPContext,
    scope: Annotated[
        Literal["system", "user"] | list[Literal["system", "user"]] | None,
        "Optional — restrict to 'system' or 'user' templates. Pass ONE value as a "
        "plain string (a one-element list is tolerated and unwrapped). Omit for both.",
    ] = None,
) -> dict:
    # W0 #3 — models routinely send ["system"] for this filter arg. Unwrap a
    # one-element list; reject a multi-element list with a directive (omitting
    # scope already returns both, so a 2-element list means "omit").
    if isinstance(scope, list):
        if len(scope) == 1:
            scope = scope[0]
        else:
            raise ValueError(
                "`scope` must be a single value ('system' or 'user'), not a list — "
                "omit it entirely to get both"
            )
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
    meta=require_meta(
        "R", "project",
        tool_name="kg_sync_available",
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
    meta=require_meta(
        "R", "user",
        tool_name="kg_view_read",
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
    meta=require_meta(
        "R", "project",
        tool_name="kg_triage_list",
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
    detail: _DETAIL_ARG = "full",
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"status": status, "limit": limit, "detail": detail}
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
    meta=require_meta(
        "A", "project",
        tool_name="kg_propose_fact",
    ),
)
async def kg_propose_fact(
    ctx: MCPContext,
    fact_text: Annotated[str, "The fact to propose, as a clear statement."],
    fact_type: Annotated[
        Literal["decision", "preference", "milestone", "negation", "statement", "commitment"],
        "decision = a choice made; preference = a standing like/dislike; "
        "milestone = a notable achievement; negation = something NOT true.",
    ],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"fact_text": fact_text, "fact_type": fact_type}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_propose_fact", args)


@mcp_server.tool(
    name="kg_propose_edge",
    description=(
        "Propose a relationship edge between two entities for human review. "
        "The edge is validated against the project schema and parked in the "
        "triage inbox — it is NEVER written to the graph directly. If the edge "
        "type is temporal you MUST supply valid_from (the chapter ordinal it "
        "began); otherwise the proposal is rejected."
    ),
    meta=require_meta(
        "A", "project",
        tool_name="kg_propose_edge",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {
        "source_entity_id": source_entity_id,
        "target_entity_id": target_entity_id,
        "edge_type": edge_type,
    }
    if project_id is not None:
        args["project_id"] = project_id
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
    name="kg_project_entities_to_nodes",
    description=(
        "Project this book's recorded glossary entities into the knowledge "
        "graph as nodes — the structured way to seed the graph from lore you "
        "already entered, WITHOUT needing any chapter prose written. "
        "Deterministic and idempotent: re-running adds no duplicates. Returns "
        "how many nodes were newly created vs. already existed. Do this before "
        "proposing edges between entities (an edge needs both endpoints to be "
        "nodes first)."
    ),
    meta=require_meta(
        "A", "project",
        tool_name="kg_project_entities_to_nodes",
    ),
)
async def kg_project_entities_to_nodes(
    ctx: MCPContext,
    entity_ids: Annotated[
        list[str] | None,
        "Optional — the specific glossary entity ids to project. Omit to "
        "project the book's whole active glossary.",
    ] = None,
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {}
    if entity_ids is not None:
        args["entity_ids"] = entity_ids
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_project_entities_to_nodes", args)


@mcp_server.tool(
    name="kg_create_node",
    description=(
        "Manually create ONE knowledge-graph entity node (a character, place, "
        "faction, item, …). Use this BEFORE kg_propose_edge when a relationship's "
        "endpoint isn't in the graph yet — an edge whose endpoints aren't nodes is "
        "parked and later fails. Idempotent: the same name+kind returns the existing "
        "node. Returns the entity_id to use as an edge endpoint."
    ),
    meta=require_meta("A", "project", tool_name="kg_create_node"),
)
async def kg_create_node(
    ctx: MCPContext,
    name: Annotated[str, "the entity's name"],
    kind: Annotated[
        str, "the entity kind, e.g. 'character', 'location', 'faction', 'item'"
    ],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"name": name, "kind": kind}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_create_node", args)


@mcp_server.tool(
    name="kg_view_upsert",
    description=(
        "Create or replace one of the caller's saved views (a named lens of "
        "edge-type + node-kind codes) for the current project. Owner-scoped: "
        "only ever touches your own view."
    ),
    meta=require_meta(
        "A", "user",
        tool_name="kg_view_upsert",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {
        "code": code,
        "name": name,
        "description": description,
        "edge_type_codes": edge_type_codes or [],
        "node_kind_codes": node_kind_codes or [],
    }
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_view_upsert", args)


@mcp_server.tool(
    name="kg_view_delete",
    description=(
        "Delete one of the caller's saved views by code for the current "
        "project. Owner-scoped and reversible (recreate with kg_view_upsert)."
    ),
    meta=require_meta(
        "A", "user",
        tool_name="kg_view_delete",
    ),
)
async def kg_view_delete(
    ctx: MCPContext,
    code: Annotated[str, "The code of the view to delete."],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"code": code}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_view_delete", args)


@mcp_server.tool(
    name="kg_triage_resolve",
    description=(
        "Resolve a triage signature group with a low-impact, reversible "
        "action: map, re_target, drop_edge, close_previous, or dismiss. "
        "Schema-changing actions (add to vocab/schema, widen, promote to "
        "glossary) are NOT available here — those need explicit human "
        "confirmation via the review surface."
    ),
    meta=require_meta(
        "A", "project",
        tool_name="kg_triage_resolve",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"signature": signature, "action": action, "params": params or {}}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_triage_resolve", args)


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
    meta=require_meta(
        "W", "project",
        tool_name="kg_schema_edit",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"verb": verb, "level": level, "code": code, "label": label}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_schema_edit", args)


@mcp_server.tool(
    name="kg_adopt_template",
    description=(
        "Propose adopting (copying down) a system or user ontology template "
        "into THIS project, scaffolding its edge types / node kinds / fact "
        "types. High-impact — it does NOT apply immediately; it returns a "
        "confirm_token and a summary, and a human confirms on the review "
        "surface. Pick a source_schema_id from kg_list_templates."
    ),
    meta=require_meta(
        "W", "project",
        tool_name="kg_adopt_template",
    ),
)
async def kg_adopt_template(
    ctx: MCPContext,
    source_schema_id: Annotated[
        str, "The template id to adopt (from kg_list_templates)."
    ],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"source_schema_id": source_schema_id}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_adopt_template", args)


@mcp_server.tool(
    name="kg_sync_apply",
    description=(
        "Propose syncing THIS project's ontology with its upstream template — "
        "applying per-change keep_mine / take_theirs decisions (read the diff "
        "with kg_sync_available first). High-impact (overwrites/deprecates rows "
        "+ bumps the schema version), so it returns a confirm_token and summary; "
        "a human confirms on the review surface."
    ),
    meta=require_meta(
        "W", "project",
        tool_name="kg_sync_apply",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    # Typed item model (not bare list[dict]) so the MCP inputSchema carries the
    # SAME per-decision shape the bespoke OpenAI schema advertises (parity).
    # model_dump() back to plain dicts — execute_tool re-validates via the arg model.
    args: dict[str, Any] = {
        "base_source_hash": base_source_hash,
        "decisions": [d.model_dump() for d in (decisions or [])],
    }
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_sync_apply", args)


@mcp_server.tool(
    name="kg_triage_place_edge",
    description=(
        "Place an agent-drafted proposed edge (from kg_triage_list, item_type "
        "'proposed_edge') into the knowledge graph. High-impact (it writes a "
        "real edge), so it does NOT apply immediately — it returns a "
        "confirm_token and a summary; a human confirms on the review surface."
    ),
    meta=require_meta(
        "W", "project",
        tool_name="kg_triage_place_edge",
    ),
)
async def kg_triage_place_edge(
    ctx: MCPContext,
    triage_id: Annotated[
        str, "The proposed_edge triage item id to place (from kg_triage_list)."
    ],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"triage_id": triage_id}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_triage_place_edge", args)


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
    meta=require_meta(
        "W", "project",
        tool_name="kg_triage_schema_write",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {
        "signature": signature,
        "action": action,
        "code": code,
        "label": label,
        "set_code": set_code,
        "add_kinds": add_kinds or [],
    }
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_triage_schema_write", args)


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
        "an embedding model configured — if it does not, call kg_project_set_embedding_model "
        "then kg_run_benchmark first, rather than sending the user to the UI. Pick "
        "the extraction llm_model from settings_list_models."
    ),
    meta=require_meta(
        "W", "project",
        async_job=True,
        tool_name="kg_build_graph",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {
        "llm_model": llm_model, "scope": scope, "reasoning_effort": reasoning_effort,
    }
    if chapter_from is not None:
        args["chapter_from"] = chapter_from
    if chapter_to is not None:
        args["chapter_to"] = chapter_to
    if project_id is not None:
        args["project_id"] = project_id
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
    meta=require_meta(
        "W", "project",
        async_job=True,
        tool_name="kg_build_wiki",
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
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {
        "model_ref": model_ref, "model_source": model_source,
        "reasoning_effort": reasoning_effort,
    }
    if entity_ids is not None:
        args["entity_ids"] = entity_ids
    if project_id is not None:
        args["project_id"] = project_id
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
    meta=require_meta(
        "A", "project",
        tool_name="kg_run_benchmark",
    ),
)
async def kg_run_benchmark(
    ctx: MCPContext, project_id: _PROJECT_ID_ARG = None
) -> dict:
    args: dict[str, Any] = {}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "kg_run_benchmark", args)


# ── W11-M2 reader "ask the lore" tools ────────────────────────────────
# Spoiler-windowed reads for a reader's chat agent. The cutoff is SERVER-enforced
# from the reader's OWN furthest-read chapter — there is deliberately no
# before_chapter arg, so an agent cannot widen its own spoiler window. All Tier-R,
# scope=project; a non-grantee gets a uniform "project not found" (anti-oracle).
@mcp_server.tool(
    name="lore_ask",
    description=(
        "Ask about a book's lore SPOILER-SAFELY on the reader's behalf. Returns a "
        "spoiler-windowed evidence bundle — canon entities the reader has met + "
        "manuscript passages — bounded to the reader's OWN furthest-read chapter (you "
        "cannot widen it). Compose the answer from this evidence on your own model; if "
        "window_available is false the reader's position couldn't be pinned so nothing "
        "is shown."
    ),
    meta=require_meta("R", "project", tool_name="lore_ask"),
)
async def lore_ask(
    ctx: MCPContext,
    query: Annotated[
        str,
        "What the reader is asking — a name, a relationship, or 'what has happened so "
        "far', in natural language.",
    ],
    limit: Annotated[
        int, Field(ge=1, le=50), "Max passages + canon entities each (default 25)."
    ] = 25,
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"query": query, "limit": limit}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "lore_ask", args)


@mcp_server.tool(
    name="lore_browse_entities",
    description=(
        "List the CANON cast (characters, places, factions) the reader has met so far "
        "— spoiler-windowed to their furthest-read chapter. A reader whose position "
        "can't be pinned gets an empty list, never the whole cast."
    ),
    meta=require_meta("R", "project", tool_name="lore_browse_entities"),
)
async def lore_browse_entities(
    ctx: MCPContext,
    kind: Annotated[
        str | None,
        "Optional — restrict to one entity kind (e.g. 'character', 'location'). Omit "
        "for the whole windowed cast.",
    ] = None,
    limit: Annotated[int, Field(ge=1, le=50), "Max entities (default/max 50)."] = 50,
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"limit": limit}
    if kind is not None:
        args["kind"] = kind
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "lore_browse_entities", args)


@mcp_server.tool(
    name="lore_entity",
    description=(
        "One entity's spoiler-windowed status + known facts, bounded to the reader's "
        "furthest-read chapter (facts established later are hidden)."
    ),
    meta=require_meta("R", "project", tool_name="lore_entity"),
)
async def lore_entity(
    ctx: MCPContext,
    entity_id: Annotated[
        str, "The entity id returned by lore_browse_entities / lore_ask."
    ],
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"entity_id": entity_id}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "lore_entity", args)


@mcp_server.tool(
    name="lore_timeline",
    description=(
        "The sequence of events up to the reader's position — spoiler-windowed so "
        "later events are hidden. Empty when the reader's position can't be pinned."
    ),
    meta=require_meta("R", "project", tool_name="lore_timeline"),
)
async def lore_timeline(
    ctx: MCPContext,
    limit: Annotated[int, Field(ge=1, le=50), "Max events (default/max 50)."] = 50,
    project_id: _PROJECT_ID_ARG = None,
) -> dict:
    args: dict[str, Any] = {"limit": limit}
    if project_id is not None:
        args["project_id"] = project_id
    return await _dispatch(ctx, "lore_timeline", args)


# ── MCP resources (RAID Wave C5) ──────────────────────────────────────
# Read-only, project-scoped resources federated by ai-gateway (resources/read).
# Both are URI TEMPLATES ({project_id}), so they are advertised via
# resources/templates/list rather than resources/list — a project's ids are
# per-user, so there is no global concrete list to enumerate.
#
# Tenancy: identity is envelope-only (design D3) — _require_envelope_user runs
# the SAME internal-token + X-User-Id gate as the tool path BEFORE any repo
# access, and project ownership is verified with the owner-keyed lookup the
# memory tools use (ProjectsRepo.get is (user_id, project_id)-keyed, so a
# non-owned project reads as "project not found" — anti-oracle, H13). The
# {project_id} URI parameter is the resource-path analog of the H-I project_id
# tool arg: the caller names a project, the owner gate confines it to its own.

_ENTITIES_RESOURCE_CAP = 100


async def _require_owned_project(ctx: MCPContext, project_id: str) -> tuple[UUID, UUID]:
    """Envelope auth + project-ownership gate for the resource read path.

    Mirrors _require_project_owner_memory (app/tools/executor.py): the project
    named in the URI must be OWNED by the envelope user. Raises ValueError —
    FastMCP surfaces it as a resource-read error, never a 500. Anti-oracle: a
    non-owned and a missing project raise the SAME "project not found" (H13).
    """
    user_id = _require_envelope_user(ctx)
    try:
        pid = UUID(project_id)
    except ValueError:
        raise ValueError(f"project_id is not a valid UUID: {project_id!r}")
    project = await ProjectsRepo(get_knowledge_pool()).get(user_id, pid)
    if project is None:
        raise ValueError("project not found")
    return user_id, pid


@mcp_server.resource(
    "knowledge://project/{project_id}/summary",
    name="project_summary",
    title="Project summary (story so far)",
    description=(
        "The L1 project summary — the rolling story-so-far text knowledge-service "
        "maintains for one knowledge project. Plain text; a project with no "
        "summary yet returns a short note saying so."
    ),
    mime_type="text/plain",
)
async def project_summary_resource(project_id: str, ctx: MCPContext) -> str:
    user_id, pid = await _require_owned_project(ctx, project_id)
    summary = await SummariesRepo(get_knowledge_pool()).get(user_id, "project", pid)
    if summary is None or not summary.content:
        return (
            "(no project summary yet — build the knowledge graph or edit the "
            "Memory page to create one)"
        )
    return summary.content


@mcp_server.resource(
    "knowledge://project/{project_id}/entities",
    name="project_entities",
    title="Project entities (canonical cast)",
    description=(
        "Compact JSON list of the project's glossary-anchored (canonical) "
        "entities from the knowledge graph — name, kind, and aliases per entry, "
        f"capped at {_ENTITIES_RESOURCE_CAP} by anchor score. Use "
        "memory_recall_entity for full details on any one of them."
    ),
    mime_type="application/json",
)
async def project_entities_resource(project_id: str, ctx: MCPContext) -> str:
    user_id, pid = await _require_owned_project(ctx, project_id)
    # status='canonical' = glossary-anchored (glossary_entity_id set, active);
    # anchor_score ordering surfaces the strongest anchors first. Repo params
    # are str ids (the Neo4j property space), unlike the UUID-typed Postgres
    # repos above.
    async with neo4j_session() as session:
        rows, total = await list_entities_filtered(
            session,
            user_id=str(user_id),
            project_id=str(pid),
            kind=None,
            search=None,
            limit=_ENTITIES_RESOURCE_CAP,
            offset=0,
            status="canonical",
            sort_by="anchor_score",
        )
    payload = {
        "project_id": str(pid),
        "count": len(rows),
        "total": total,
        "entities": [
            # NOTE: :Entity nodes carry no description property (name / kind /
            # aliases only — see app/db/neo4j_repos/entities.py Entity); the
            # aliases stand in as the compact per-entity context.
            {"name": e.name, "kind": e.kind, "aliases": e.aliases[:5]}
            for e in rows
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


# ── MCP prompts (RAID Wave C5) ────────────────────────────────────────
# Canned prompt templates for a novel-writing agent, federated by ai-gateway
# (prompts/list + prompts/get). They render INSTRUCTIONS ONLY — no stored data
# is embedded at render time (the model fetches everything through the
# tenancy-gated tools above), so rendering needs no envelope identity. Prompt
# arguments are strings per the MCP spec; FastMCP strips an (unused here) ctx
# param from the advertised argument list the same way tools do.


@mcp_server.prompt(
    name="recap_story_so_far",
    title="Recap the story so far",
    description=(
        "Build a grounded recap of a knowledge project's story so far using the "
        "memory tools. Argument: project_id — the knowledge project to recap."
    ),
)
def recap_story_so_far(
    project_id: Annotated[str, "The knowledge project id to recap."],
) -> str:
    return (
        f"Recap the story so far for knowledge project {project_id}.\n\n"
        "Ground every statement in stored knowledge — never invent events:\n"
        f"1. Call memory_timeline (project_id={project_id}) for the ordered "
        "narrative events.\n"
        f"2. Call memory_search (project_id={project_id}) on any arc that needs "
        "more detail, and kg_graph_query to see how the cast relates as of the "
        "latest chapter.\n"
        "3. Write the recap: 2-3 paragraphs, chronological, naming the key "
        "characters, places, and unresolved threads.\n"
        "If a tool returns nothing, say what is missing instead of guessing."
    )


@mcp_server.prompt(
    name="entity_dossier",
    title="Entity deep-dive dossier",
    description=(
        "Compile a deep-dive dossier on one story entity via memory_recall_entity "
        "and kg_graph_query. Argument: entity_name — the entity's name as it "
        "appears in the story."
    ),
)
def entity_dossier(
    entity_name: Annotated[str, "The entity's name as it appears in the story."],
) -> str:
    return (
        f"Compile a deep-dive dossier on the entity {entity_name!r}.\n\n"
        "Ground every claim in stored knowledge — never invent details:\n"
        f"1. Call memory_recall_entity (entity_name={entity_name!r}) for the "
        "stored details and direct relationships.\n"
        "2. Call kg_graph_query to place the entity in the wider graph, and "
        "kg_entity_edge_timeline (with an entity id + edge-type code from the "
        "graph result) to trace how a key relationship evolved.\n"
        f"3. Call memory_search (query={entity_name!r}) for supporting text "
        "snippets.\n"
        "4. Write the dossier: identity, role in the story, relationships, "
        "timeline of significant changes, and open questions.\n"
        "If the entity is unknown, say so and list the closest matches the "
        "tools returned instead of inventing one."
    )


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
