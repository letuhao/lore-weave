# BUILD Plan: ARCH-1/ARCH-2 C1+C2 — MCP Server Facade (knowledge-service) + MCP Client (chat-service)

**Date:** 2026-06-01
**Branch:** arch-unify-chat-rag
**Design doc:** `docs/plans/2026-06-01-arch-1-2-design-agui-mcp.md`
**Architect:** letuhao / Claude

---

## 1. Task Classification

**XL** — 12+ files touched across 2 services with 3 distinct side effects.

| Dimension | Count | Detail |
|---|---|---|
| Services touched | 2 | knowledge-service, chat-service |
| Files created | 2 | `knowledge-service/app/mcp/__init__.py`, `knowledge-service/app/mcp/server.py` |
| Files modified | 6 | `knowledge-service/app/main.py`, `knowledge-service/requirements.txt`, `chat-service/app/client/knowledge_client.py`, `chat-service/app/services/stream_service.py`, `chat-service/app/config.py`, `chat-service/requirements.txt` |
| Side effects | 3 | New `/mcp` HTTP endpoint (MCP server mount), `USE_MCP_TOOLS` env var gate, new `mcp` PyPI dep in both services |
| Test files | 2+ | One per service (C1 MCP tool list+call, C2 dual-run gate) |

Plan file required per XL rule. Spec already exists in the design doc above. Sub-agent review recommended at REVIEW phase.

---

## 2. MCP Tool Contracts

These are the canonical five tools the MCP server (C1) must expose. They are single-sourced from `app/tools/definitions.py` in knowledge-service. The MCP server reads them at build time — no duplication of the schema text.

### 2.1 `memory_search`

**Description:** Semantic search over the user's stored memory for the current project — chapter text, past chat turns, and glossary entries. Call this to find what is already known about a topic, character, place, or event before answering. Returns the most relevant text snippets.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "query": {
      "type": "string",
      "description": "What to search for, in natural language."
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20,
      "description": "Max snippets to return (default 10)."
    },
    "source_type": {
      "type": "string",
      "enum": ["chapter", "chat", "glossary"],
      "description": "Optional — restrict to one source. Omit to search all."
    }
  },
  "required": ["query"],
  "additionalProperties": false
}
```

**Return type:** `{"hits": [{"text": str, "source_type": str, "score": float}], "count": int}` on success; `{"error": str}` on tool failure.

---

### 2.2 `memory_recall_entity`

**Description:** Look up a specific entity (character, place, organization, item, etc.) by name and return its stored details plus its relationships to other entities. Use this when the user asks about a named thing and you need what memory holds on it.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "entity_name": {
      "type": "string",
      "description": "The entity's name as it appears in the story."
    }
  },
  "required": ["entity_name"],
  "additionalProperties": false
}
```

**Return type:** `{"found": bool, "entity": {name, kind, aliases, confidence}, "relations": [{subject, predicate, object}], "relations_truncated": bool, "other_matches": [str]}` when found; `{"found": false, "entity_name": str}` when not found.

---

### 2.3 `memory_timeline`

**Description:** Retrieve narrative events in order for the current project, optionally filtered by a date range or by an entity that took part. Use this to answer 'what happened' or 'when did' questions.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "from_date": {
      "type": "string",
      "description": "Optional inclusive lower bound, ISO date (YYYY, YYYY-MM, or YYYY-MM-DD)."
    },
    "to_date": {
      "type": "string",
      "description": "Optional inclusive upper bound, same ISO form."
    },
    "entity_name": {
      "type": "string",
      "description": "Optional — only events this named entity took part in."
    },
    "limit": {
      "type": "integer",
      "minimum": 1,
      "maximum": 50,
      "description": "Max events to return (default 20)."
    }
  },
  "required": [],
  "additionalProperties": false
}
```

**Return type:** `{"events": [{title, summary, event_date, participants}], "count": int, "total_matching": int}`

---

### 2.4 `memory_remember`

**Description:** Store a new fact into long-term memory. Use sparingly — only for durable, important information the user explicitly stated or confirmed. Stored facts are recorded at low confidence and tagged as assistant-created so the user can review them.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "fact_text": {
      "type": "string",
      "description": "The fact to store, as a clear statement."
    },
    "fact_type": {
      "type": "string",
      "enum": ["decision", "preference", "milestone", "negation"],
      "description": "decision = a choice made; preference = a standing like/dislike or habit; milestone = a notable achievement; negation = something explicitly NOT true."
    }
  },
  "required": ["fact_text", "fact_type"],
  "additionalProperties": false
}
```

**Return type (write path):** `{"remembered": true, "fact_id": str, "fact_type": str, "confidence": float}`
**Return type (queue path):** `{"queued": true, "pending_fact_id": str, "fact_text": str, "fact_type": str}`

---

### 2.5 `memory_forget`

**Description:** Invalidate a previously stored fact by its id so it no longer appears in memory. Only use a fact_id you have seen in an earlier tool result.

**inputSchema:**
```json
{
  "type": "object",
  "properties": {
    "fact_id": {
      "type": "string",
      "description": "The id of the fact to invalidate."
    }
  },
  "required": ["fact_id"],
  "additionalProperties": false
}
```

**Return type:** `{"invalidated": bool, "fact_id": str}` or `{"invalidated": false, "reason": str}`

---

### 2.6 MCP Envelope Contract (critical design constraint)

The MCP tool `inputSchema` exposes **only** the semantic arguments above. `user_id`, `project_id`, and `session_id` are **never** MCP tool parameters — they come from the MCP call context (HTTP headers supplied by the chat-service client before calling). This matches the existing bespoke-path contract (design D3 in definitions.py) exactly. The MCP server must extract these from the request context, not from the tool arguments.

**MCP transport:** Streamable HTTP (JSON-RPC over HTTP). Mount point: `/mcp` on the same FastAPI app that already serves `/internal/*`.

**Auth on `/mcp`:** `X-Internal-Token` header (same token used by all `/internal/*` S2S routes). The MCP server must reject requests that omit or mismatched this header with HTTP 401.

**Context headers the chat-service client MUST set on every MCP session:**

| Header | Value | Purpose |
|---|---|---|
| `X-Internal-Token` | `settings.internal_service_token` | S2S auth |
| `X-User-Id` | `str(user_id)` | Scope — never from LLM args |
| `X-Project-Id` | `str(project_id)` or absent | Scope — None if no project |
| `X-Session-Id` | `session_id` | Rate-limit key for memory_remember |

---

## 3. C1 Build Plan — knowledge-service MCP Server Facade

### 3.1 New dependency

**File: `services/knowledge-service/requirements.txt`**

Add to the existing requirements list:
```
mcp[cli]>=1.9
```

FastMCP is distributed as part of the `mcp` package (the official MCP Python SDK) since v1.0. `mcp[cli]` includes the `fastmcp` subpackage and CLI tooling. No pyproject.toml needed — this service uses requirements.txt only.

### 3.2 Files to CREATE

#### 3.2.1 `services/knowledge-service/app/mcp/__init__.py`

Empty init file to make `app.mcp` a package.

```python
# MCP server facade package (ARCH-1 C1).
```

#### 3.2.2 `services/knowledge-service/app/mcp/server.py`

This is the core of C1. The file does four things:

1. Creates a `FastMCP` instance named `"knowledge-memory"`.
2. Registers all five memory tools using `@mcp_server.tool()` decorators.
3. Each tool handler: reads context headers from the MCP request context, constructs a `ToolContext`, calls the existing `execute_tool()` from `app.tools.executor`, and returns the result dict.
4. Exposes a `build_mcp_app()` factory that returns the ASGI-mountable app.

**Full structure:**

```python
"""ARCH-1 C1 — MCP server facade for knowledge-service memory tools.

Mounts at /mcp on the existing FastAPI app (app/main.py).
Transport: Streamable HTTP (JSON-RPC over HTTP).

Design constraints:
- Calls app.tools.executor.execute_tool() — NO logic duplication.
- user_id / project_id / session_id come from MCP context headers,
  never from LLM-supplied tool arguments (design D3).
- Auth: X-Internal-Token header checked before dispatch.
- Dual-run: existing /internal/tools/* endpoints are NOT removed.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any
from uuid import UUID

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp import Context as MCPContext

from app.config import settings
from app.deps import get_embedding_client, get_pending_facts_repo, get_projects_repo
from app.tools.definitions import (
    SEARCH_LIMIT_DEFAULT,
    SEARCH_LIMIT_MAX,
    TIMELINE_LIMIT_DEFAULT,
    TIMELINE_LIMIT_MAX,
)
from app.tools.executor import ToolContext, execute_tool, get_tools_redis

logger = logging.getLogger(__name__)

# --- Module-level FastMCP instance ---
# build_mcp_app() converts it to an ASGI app for mounting in main.py.
mcp_server = FastMCP("knowledge-memory")


# ── Context extraction helpers ────────────────────────────────────────


def _require_header(ctx: MCPContext, header: str) -> str:
    """Extract a required header from the MCP request context.
    Raises ValueError (surfaces as MCP tool error) when absent."""
    val = ctx.request_context.request.headers.get(header)
    if not val:
        raise ValueError(f"missing required context header: {header!r}")
    return val


def _optional_header(ctx: MCPContext, header: str) -> str | None:
    return ctx.request_context.request.headers.get(header) or None


async def _build_tool_context(ctx: MCPContext) -> ToolContext:
    """Build a ToolContext from MCP request headers.

    Raises ValueError when required headers are missing — FastMCP
    converts this to a tool-level error (success=False), not a 500.
    """
    raw_token = _require_header(ctx, "x-internal-token")
    if raw_token != settings.internal_service_token:
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

    # Resolve FastAPI dependencies manually (MCP handlers are not FastAPI
    # endpoints — they cannot use Depends()). Use the module-level getters
    # that back the FastAPI Depends() functions; these return process-level
    # singletons already initialised by main.py lifespan.
    from app.db.pool import get_knowledge_pool, get_glossary_pool  # noqa: PLC0415
    pool = get_knowledge_pool()
    projects_repo = get_projects_repo(pool)
    pending_facts_repo = get_pending_facts_repo(pool)
    embedding_client = get_embedding_client()

    return ToolContext(
        user_id=user_id,
        project_id=project_id,
        session_id=session_id,
        projects_repo=projects_repo,
        pending_facts_repo=pending_facts_repo,
        embedding_client=embedding_client,
        redis=get_tools_redis(),
    )


async def _dispatch(ctx: MCPContext, tool_name: str, tool_args: dict) -> dict:
    """Build ToolContext, call execute_tool, return result dict.

    A tool-level failure (ToolResult.success=False) returns
    {"success": False, "error": str} — FastMCP surfaces this as a
    tool result, not an exception. An infrastructure exception
    propagates as a FastMCP tool error (500-equivalent).
    """
    tool_ctx = await _build_tool_context(ctx)
    result = await execute_tool(tool_ctx, tool_name, tool_args)
    if result.success:
        return result.result or {}
    # Return error as a structured dict so the MCP client can inspect it.
    return {"success": False, "error": result.error}


# ── Tool registrations ────────────────────────────────────────────────


@mcp_server.tool(
    name="memory_search",
    description=(
        "Semantic search over the user's stored memory for the current "
        "project — chapter text, past chat turns, and glossary entries. "
        "Call this to find what is already known about a topic, character, "
        "place, or event before answering. Returns the most relevant text snippets."
    ),
)
async def memory_search(
    ctx: MCPContext,
    query: Annotated[str, "What to search for, in natural language."],
    limit: Annotated[
        int,
        f"Max snippets to return (default {SEARCH_LIMIT_DEFAULT}, max {SEARCH_LIMIT_MAX}).",
    ] = SEARCH_LIMIT_DEFAULT,
    source_type: Annotated[
        str | None,
        "Optional — restrict to one source: 'chapter', 'chat', or 'glossary'. Omit to search all.",
    ] = None,
) -> dict:
    return await _dispatch(ctx, "memory_search", {
        "query": query,
        "limit": limit,
        **({"source_type": source_type} if source_type is not None else {}),
    })


@mcp_server.tool(
    name="memory_recall_entity",
    description=(
        "Look up a specific entity (character, place, organization, item, etc.) "
        "by name and return its stored details plus its relationships to other "
        "entities. Use this when the user asks about a named thing and you need "
        "what memory holds on it."
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
        "Retrieve narrative events in order for the current project, optionally "
        "filtered by a date range or by an entity that took part. Use this to "
        "answer 'what happened' or 'when did' questions."
    ),
)
async def memory_timeline(
    ctx: MCPContext,
    from_date: Annotated[
        str | None,
        "Optional inclusive lower bound, ISO date (YYYY, YYYY-MM, or YYYY-MM-DD).",
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
        f"Max events to return (default {TIMELINE_LIMIT_DEFAULT}, max {TIMELINE_LIMIT_MAX}).",
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
        "durable, important information the user explicitly stated or confirmed. "
        "Stored facts are recorded at low confidence and tagged as assistant-created "
        "so the user can review them."
    ),
)
async def memory_remember(
    ctx: MCPContext,
    fact_text: Annotated[str, "The fact to store, as a clear statement."],
    fact_type: Annotated[
        str,
        "decision | preference | milestone | negation",
    ],
) -> dict:
    return await _dispatch(ctx, "memory_remember", {
        "fact_text": fact_text,
        "fact_type": fact_type,
    })


@mcp_server.tool(
    name="memory_forget",
    description=(
        "Invalidate a previously stored fact by its id so it no longer "
        "appears in memory. Only use a fact_id you have seen in an earlier tool result."
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

    FastMCP's streamable_http transport produces a Starlette/ASGI app.
    Calling this at module import time is safe because mcp_server is a
    module-level singleton; the FastMCP instance does not depend on the
    FastAPI lifespan.
    """
    return mcp_server.streamable_http_app()
```

**Key implementation notes:**

- `_build_tool_context()` resolves repos via the same module-level getter functions that back `app/deps.py`'s `Depends()` calls. These functions return singletons already initialised by the lifespan in `main.py` — no second initialisation.
- `get_projects_repo(pool)` and `get_pending_facts_repo(pool)` need to be checked against `deps.py` to confirm they accept a pool argument directly (not a coroutine). Verify this during BUILD before writing the final code. If `deps.py` uses `Depends(get_knowledge_pool)` as a FastAPI dependency, the MCP handler must call `ProjectsRepo(get_knowledge_pool())` directly.
- `memory_forget` tool name: the description says "fact_id you have seen" — double-check `FACT_TYPES` import is not needed in server.py (it is not; fact_type validation happens inside executor via ARG_MODELS).

### 3.3 Files to MODIFY

#### 3.3.1 `services/knowledge-service/app/main.py`

Add three lines in the correct locations. Do NOT disturb the existing lifespan logic, middleware stack, or router registrations.

**Import addition** (after the existing router imports, before `logger = ...`):
```python
from app.mcp.server import build_mcp_app
```

**Mount addition** (after `app.include_router(public_user_data.router)` — the last `include_router` call at the bottom):
```python
# ARCH-1 C1 — MCP server facade. Dual-run: /internal/tools/* retained.
# Streamable HTTP transport; auth via X-Internal-Token checked inside
# build_tool_context(). Mount AFTER all routers so FastAPI routes take
# precedence over the Starlette sub-app.
app.mount("/mcp", build_mcp_app())
```

**No lifespan changes required.** The MCP server uses only resources already initialised by the existing lifespan (pools, embedding client, projects/pending_facts repos, Redis).

#### 3.3.2 `services/knowledge-service/requirements.txt`

Add after the existing last dependency line:
```
mcp[cli]>=1.9
```

No version pinning beyond `>=1.9` — this matches the existing style in the file (e.g., `fastapi>=0.111`).

---

## 4. C2 Build Plan — chat-service MCP Client

### 4.1 New dependency

**File: `services/chat-service/requirements.txt`**

Add:
```
mcp>=1.9
```

Only the base `mcp` package is needed in chat-service (no CLI tools). Version must match C1's constraint.

### 4.2 New env var

**Name:** `USE_MCP_TOOLS`
**Type:** `bool`
**Default:** `false`
**Semantics:** When `true`, `execute_tool` calls in `stream_service.py` route through the MCP client path (`mcp_execute_tool()`). When `false` (default), the existing `knowledge_client.execute_tool()` bespoke HTTP path runs unchanged. The dual-run gate is in `_stream_with_tools()` in `stream_service.py`.

### 4.3 Files to MODIFY

#### 4.3.1 `services/chat-service/app/config.py`

Add one field to the `Settings` class, after the `knowledge_tool_timeout_s` field:

```python
# ARCH-2 C2 — MCP tool execution gate. When true, chat-service routes
# execute_tool() calls through the MCP client (mcp.client.streamable_http).
# false = legacy bespoke path (/internal/tools/execute). Dual-run default.
use_mcp_tools: bool = False
```

#### 4.3.2 `services/chat-service/app/client/knowledge_client.py`

Add the `mcp_execute_tool()` async function to the `KnowledgeClient` class. This sits alongside the existing `execute_tool()` method — do NOT replace or remove the existing method.

**Exact location:** after the existing `execute_tool()` method definition, before the module-level singleton section (`_client: KnowledgeClient | None = None`).

**Method signature and body:**

```python
async def mcp_execute_tool(
    self,
    *,
    user_id: str,
    session_id: str,
    tool_name: str,
    tool_args: dict,
    project_id: str | None = None,
) -> dict:
    """ARCH-2 C2 — execute a memory tool via MCP streamable HTTP transport.

    Returns the same dict shape as execute_tool() for drop-in compatibility:
      {"success": True, "result": dict}   on success
      {"success": False, "result": None, "error": str}  on tool or transport failure

    Context headers carry user_id / project_id / session_id — they never
    appear in tool_args (design D3). A transport or protocol failure returns
    success=False (graceful degradation, same contract as execute_tool()).
    """
    from mcp.client.streamable_http import streamablehttp_client  # noqa: PLC0415
    from mcp import ClientSession  # noqa: PLC0415

    mcp_url = f"{self._base_url}/mcp"
    headers = {
        "X-Internal-Token": self._http.headers["X-Internal-Token"],
        "X-User-Id": user_id,
        "X-Session-Id": session_id,
    }
    if project_id:
        headers["X-Project-Id"] = project_id

    try:
        async with streamablehttp_client(mcp_url, headers=headers) as (read, write, _):
            async with ClientSession(read, write) as mcp_session:
                await mcp_session.initialize()
                result = await mcp_session.call_tool(tool_name, tool_args)
    except Exception as exc:
        logger.warning("mcp_execute_tool transport error: %s", exc)
        return {
            "success": False,
            "result": None,
            "error": f"mcp tool backend unavailable: {type(exc).__name__}",
        }

    # FastMCP returns content as a list of TextContent/ImageContent items.
    # The knowledge-service handlers return JSON dicts serialised as the
    # text content of the first item.
    if not result.content:
        return {"success": False, "result": None, "error": "mcp tool returned empty content"}

    first = result.content[0]
    try:
        import json as _json  # noqa: PLC0415
        payload = _json.loads(first.text)
    except Exception as exc:
        logger.warning("mcp_execute_tool decode error: %s — raw: %s", exc, getattr(first, "text", "?")[:200])
        return {"success": False, "result": None, "error": "mcp tool returned unparseable content"}

    if isinstance(payload, dict) and payload.get("success") is False:
        # Server-side tool error propagated as structured dict
        return {
            "success": False,
            "result": None,
            "error": payload.get("error", "tool error"),
        }

    return {"success": True, "result": payload, "error": None}
```

**Import additions at the top of `knowledge_client.py`** — none required beyond what is already there. The `mcp` imports are deferred (inline) to avoid import-time failure when the `mcp` package is not yet installed in a given environment.

**Important:** `streamablehttp_client` opens a new connection per call. This matches the existing pattern (`execute_tool` also opens/closes per call via `self._http.post`). Connection pooling for the MCP path is a future optimisation, not an MVP requirement. If the MCP SDK provides a persistent session option in a later version, that can replace the per-call pattern.

#### 4.3.3 `services/chat-service/app/services/stream_service.py`

**Single change location:** inside `_stream_with_tools()`, at the `knowledge_client.execute_tool()` call site (line 293 in current file).

Replace the single line:
```python
envelope = await knowledge_client.execute_tool(
    user_id=user_id,
    session_id=session_id,
    project_id=project_id,
    tool_name=c["name"],
    tool_args=args_obj,
)
```

With the dual-run gate:
```python
# ARCH-2 C2 dual-run gate. USE_MCP_TOOLS=true routes through the MCP
# client (streamable HTTP); false = existing bespoke path. No other
# change to the loop — result envelope shape is identical for both paths.
if settings.use_mcp_tools:
    envelope = await knowledge_client.mcp_execute_tool(
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
        tool_name=c["name"],
        tool_args=args_obj,
    )
else:
    envelope = await knowledge_client.execute_tool(
        user_id=user_id,
        session_id=session_id,
        project_id=project_id,
        tool_name=c["name"],
        tool_args=args_obj,
    )
```

**No other changes to `stream_service.py`.** The rest of the tool-calling loop (`_reassemble_tool_calls`, `working.append`, `yield {"tool_call": ...}`) works identically for both paths because `mcp_execute_tool()` returns the same dict shape as `execute_tool()`.

**Add `settings` import check:** `stream_service.py` already imports `from app.config import settings` (line 35). No new import needed.

---

## 5. Test Plan

### 5.1 C1 Tests — knowledge-service MCP server

**File:** `services/knowledge-service/tests/test_mcp_server.py`

#### Test 1: `test_mcp_tools_list_returns_all_expected_names`

**What:** Call `tools/list` via the MCP protocol and verify all five tool names are present.

**How:**
```python
import pytest
from mcp.client.streamable_http import streamablehttp_client
from mcp import ClientSession

EXPECTED_TOOLS = {
    "memory_search",
    "memory_recall_entity",
    "memory_timeline",
    "memory_remember",
    "memory_forget",
}

@pytest.mark.anyio
async def test_mcp_tools_list_returns_all_expected_names(mcp_test_client):
    """tools/list must return all five memory tool names."""
    tools = await mcp_test_client.list_tools()
    names = {t.name for t in tools.tools}
    assert names == EXPECTED_TOOLS
```

**Fixture `mcp_test_client`:** spins up the FastMCP ASGI app via `httpx.AsyncClient` with an `ASGITransport`, setting the required context headers. Uses `build_mcp_app()` directly — no live DB required for `list_tools`. If the test suite already has a `TestClient` fixture for the main FastAPI app, mount the MCP app on it instead.

#### Test 2: `test_mcp_tools_call_memory_recall_entity_unknown`

**What:** Call `tools/call` for `memory_recall_entity` with a synthetic entity name that won't exist. Expect `{"found": false}` (not an exception).

**How:**
```python
@pytest.mark.anyio
async def test_mcp_tools_call_memory_recall_entity_unknown(mcp_test_client):
    """Calling memory_recall_entity for a non-existent entity returns found=false."""
    result = await mcp_test_client.call_tool(
        "memory_recall_entity",
        {"entity_name": "DefinitelyNotARealEntity_xyz123"},
    )
    assert result.content
    import json
    payload = json.loads(result.content[0].text)
    assert payload.get("found") is False
```

**Note:** This test requires a working DB connection (Neo4j + Postgres) because `memory_recall_entity` goes to Neo4j. Mark with `@pytest.mark.integration` and gate behind the existing integration test configuration. A unit test variant can mock `execute_tool` to return `ToolResult(success=True, result={"found": False})` and verify the MCP response encoding.

#### Test 3 (unit): `test_mcp_server_rejects_missing_internal_token`

**What:** Call any tool without the `X-Internal-Token` header. Expect the tool to return an error dict (not a 500, because `_require_header` raises `ValueError` which FastMCP converts to a tool-level error).

```python
@pytest.mark.anyio
async def test_mcp_server_rejects_missing_internal_token(mcp_test_app):
    """Missing X-Internal-Token returns a tool error, not a 5xx."""
    # mcp_test_app fixture: ASGI app without the auth header set
    result = await no_auth_client.call_tool("memory_search", {"query": "test"})
    import json
    payload = json.loads(result.content[0].text)
    assert payload.get("success") is False
    assert "token" in payload.get("error", "").lower()
```

### 5.2 C2 Tests — chat-service MCP client

**File:** `services/chat-service/tests/test_mcp_execute_tool.py`

#### Test 4: `test_mcp_execute_tool_result_formatting`

**What:** Mock the MCP ClientSession to return a `CallToolResult` with a TextContent item containing a JSON dict. Verify `mcp_execute_tool()` parses it into the expected `{"success": True, "result": dict}` shape.

```python
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.anyio
async def test_mcp_execute_tool_result_formatting():
    """mcp_execute_tool() returns success=True with parsed result dict on success."""
    from app.client.knowledge_client import KnowledgeClient

    client = KnowledgeClient(
        base_url="http://knowledge-service:8092",
        internal_token="test-token",
        timeout_s=0.5,
        retries=0,
    )
    fake_payload = {"hits": [{"text": "some text", "source_type": "chapter", "score": 0.9}], "count": 1}
    fake_text_content = MagicMock()
    fake_text_content.text = json.dumps(fake_payload)
    fake_result = MagicMock()
    fake_result.content = [fake_text_content]

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    mock_session.call_tool = AsyncMock(return_value=fake_result)

    with patch("mcp.client.streamable_http.streamablehttp_client") as mock_transport, \
         patch("mcp.ClientSession") as mock_session_cls:
        # Configure context managers
        mock_transport.return_value.__aenter__ = AsyncMock(return_value=(None, None, None))
        mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_session)
        mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.mcp_execute_tool(
            user_id="user-uuid-here",
            session_id="session-abc",
            tool_name="memory_search",
            tool_args={"query": "Elara"},
        )

    assert result["success"] is True
    assert result["result"] == fake_payload
    assert result.get("error") is None
```

#### Test 5: `test_mcp_execute_tool_transport_error_returns_failure`

**What:** Mock `streamablehttp_client` to raise `httpx.ConnectError`. Verify `mcp_execute_tool()` returns `success=False` without raising.

```python
@pytest.mark.anyio
async def test_mcp_execute_tool_transport_error_returns_failure():
    """Transport failure returns success=False, not an exception."""
    import httpx
    from app.client.knowledge_client import KnowledgeClient

    client = KnowledgeClient(
        base_url="http://knowledge-service:8092",
        internal_token="test-token",
        timeout_s=0.5,
        retries=0,
    )
    with patch("mcp.client.streamable_http.streamablehttp_client") as mock_transport:
        mock_transport.return_value.__aenter__ = AsyncMock(
            side_effect=httpx.ConnectError("refused")
        )
        mock_transport.return_value.__aexit__ = AsyncMock(return_value=False)

        result = await client.mcp_execute_tool(
            user_id="user-uuid",
            session_id="session-abc",
            tool_name="memory_search",
            tool_args={"query": "test"},
        )

    assert result["success"] is False
    assert "mcp tool backend unavailable" in result["error"]
```

#### Test 6: `test_use_mcp_tools_gate_in_stream_service`

**What:** Unit test for the dual-run gate. Mock `knowledge_client.execute_tool` and `knowledge_client.mcp_execute_tool`. When `settings.use_mcp_tools = False`, only the bespoke path is called. When `True`, only the MCP path is called.

```python
@pytest.mark.anyio
async def test_use_mcp_tools_gate_selects_correct_path():
    """When USE_MCP_TOOLS=false, bespoke path called; when true, MCP path called."""
    # This test patches settings.use_mcp_tools and both execute_tool methods,
    # then calls _stream_with_tools() with a mock LLM that emits one ToolCallEvent
    # followed by a DoneEvent. Asserts which execute method was awaited.
    #
    # Implementation note: _stream_with_tools is an async generator;
    # consume it fully with [chunk async for chunk in gen].
    # The mock loreweave_llm Client.stream() must yield:
    #   ToolCallEvent(index=0, id="call1", name="memory_search", arguments_delta='{"query":"x"}')
    #   DoneEvent(finish_reason="tool_calls")
    # on the first pass, then on the second pass (tool-free):
    #   TokenEvent(delta="answer")
    #   DoneEvent(finish_reason="stop")
    pass  # Full implementation during BUILD phase
```

---

## 6. Sequencing

The implementation follows a strict serial order. C2 depends on C1 being reachable at `/mcp` before the MCP client code is testable end-to-end.

```
Step 1: C1 — knowledge-service
  1a. Add mcp[cli]>=1.9 to requirements.txt
  1b. Create app/mcp/__init__.py
  1c. Create app/mcp/server.py (full implementation per section 3.2.2)
  1d. Verify deps.py repo getters work without Depends() — check ProjectsRepo/PendingFactsRepo constructors
  1e. Modify app/main.py — add import + app.mount("/mcp", build_mcp_app())
  1f. Run C1 unit tests (test_mcp_tools_list, test_mcp_server_rejects_missing_token)
  1g. Run C1 integration tests if Neo4j available (test_mcp_tools_call_memory_recall_entity_unknown)
  1h. Manual smoke: docker-compose up knowledge-service, curl /mcp with MCP protocol, verify tools/list

Step 2: C2 — chat-service
  2a. Add mcp>=1.9 to requirements.txt
  2b. Add use_mcp_tools: bool = False to config.py Settings
  2c. Add mcp_execute_tool() to KnowledgeClient in knowledge_client.py
  2d. Add dual-run gate to _stream_with_tools() in stream_service.py (single call site)
  2e. Run C2 unit tests (tests 4 + 5 + 6 per section 5.2)
  2f. Smoke: USE_MCP_TOOLS=false → existing bespoke test passes unchanged
      Smoke: USE_MCP_TOOLS=true → MCP path exercised (requires C1 running)

Step 3: VERIFY (both services)
  3a. Unit test suites green: knowledge-service + chat-service
  3b. Cross-service live smoke: docker-compose up both services, send a chat turn that
      triggers memory_search, confirm tool-call SSE event emitted and DB row written.
      Evidence string: "live smoke: USE_MCP_TOOLS=true memory_search call returned hits, SSE tool-call event observed"
  3c. Confirm USE_MCP_TOOLS=false still works (bespoke path not broken)
  3d. Confirm /internal/tools/execute still works (dual-run, bespoke path retained)

Step 4: REVIEW
  4a. Design compliance check: no LLM args carry user_id/project_id/session_id
  4b. Auth check: /mcp rejects missing/wrong X-Internal-Token
  4c. Dual-run check: both paths exercised; bespoke path untouched
  4d. No logic duplication: server.py only calls execute_tool(), no handler reimplementation
```

---

## 7. Risk Register and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| `deps.py` repo constructors require async pool getter — incompatible with sync call in `_build_tool_context()` | Medium | Build blocker for C1 | Check `deps.py` during 1d; if async, call `await get_knowledge_pool()` or use the sync singleton getter `get_knowledge_pool()` |
| FastMCP `streamable_http_app()` API differs in mcp>=1.9 from design assumption | Low | C1 mount breaks | Check FastMCP changelog; fallback: use `mcp_server.sse_server_lifespan()` with `app.mount` |
| `mcp.client.streamable_http.streamablehttp_client` import path changed between SDK versions | Low | C2 import error at runtime | Pin `mcp>=1.9,<2.0` if instability observed; check SDK changelog before writing import |
| MCP session per tool call has high latency vs bespoke path | Medium | Perf degradation | Acceptable at dual-run phase; connection pooling is a post-verify optimisation |
| `ToolCallEvent` from loreweave_llm SDK does not supply `arguments_delta` when MCP path is active | Low | Arguments missing | MCP path bypasses the loreweave_llm streaming loop entirely — tool args come from the MCP result, not from ToolCallEvents |
| `memory_remember` rate-limit Redis key uses session_id from MCP header — same as bespoke path | None | N/A | By design; both paths call the same `execute_tool()` which reads the same Redis key |

---

## 8. Deps.py Verification Checklist (complete before 1c)

Before writing `_build_tool_context()`, verify these facts from `app/deps.py` in knowledge-service:

- [ ] `get_projects_repo()` — confirm it accepts a pool positional arg (`ProjectsRepo(pool)`) or uses `Depends(get_knowledge_pool)`. If the latter, call `ProjectsRepo(get_knowledge_pool())` directly in `_build_tool_context()`.
- [ ] `get_pending_facts_repo()` — same check as above.
- [ ] `get_embedding_client()` — confirm it returns the process-level singleton (not a coroutine). The `KnowledgeClient` getter in chat-service follows this pattern.
- [ ] `get_tools_redis()` — already a sync process-level singleton in `app/tools/executor.py`. No change needed.
- [ ] `get_knowledge_pool()` — confirm it is a synchronous getter (not `async def`). The existing lifespan uses it synchronously in background task constructors.

---

## 9. Files Touched Summary

| File | Action | Service |
|---|---|---|
| `app/mcp/__init__.py` | CREATE | knowledge-service |
| `app/mcp/server.py` | CREATE | knowledge-service |
| `app/main.py` | MODIFY — add import + mount | knowledge-service |
| `requirements.txt` | MODIFY — add mcp[cli]>=1.9 | knowledge-service |
| `tests/test_mcp_server.py` | CREATE | knowledge-service |
| `app/client/knowledge_client.py` | MODIFY — add mcp_execute_tool() | chat-service |
| `app/services/stream_service.py` | MODIFY — dual-run gate at execute_tool call site | chat-service |
| `app/config.py` | MODIFY — add use_mcp_tools field | chat-service |
| `requirements.txt` | MODIFY — add mcp>=1.9 | chat-service |
| `tests/test_mcp_execute_tool.py` | CREATE | chat-service |
