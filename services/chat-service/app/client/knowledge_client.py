"""HTTP client for knowledge-service's /internal/context/build endpoint.

Graceful degradation is the contract: every failure path (timeout,
transport error, 5xx, 4xx, decode error, unexpected shape) returns a
"degraded" KnowledgeContext with no memory and the fallback replay
budget (DEGRADED_RECENT_MESSAGE_COUNT, resolved from
`settings.recent_message_count` at import; default 50, env
`RECENT_MESSAGE_COUNT`). The caller never sees an exception — chat
must keep working when knowledge-service is unavailable.

Pattern follows app/clients/billing_client.py (long-lived module-level
singleton via get_knowledge_client()) and is structurally identical to
the GlossaryClient in knowledge-service so future maintainers see the
same shape on both sides of the wire.

Lessons baked in from K4 reviews:
  - K4-I1: idempotent init guard (don't leak the connection pool on
    double-init from test setup or hot reload)
  - K4-I4: log AT MOST one warning per failed call (no per-attempt
    spam during outages)
  - K4-I5: no dead `self._token` field; token lives in the headers
"""

import logging
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.middleware.trace_id import current_trace_id

# ARCH-2 C2 — MCP client transport for the USE_MCP_TOOLS dual-run path.
# Imported at module level (not lazily) so tests can patch these symbols at
# their point of use (`app.client.knowledge_client.streamablehttp_client` /
# `.ClientSession`). Guarded so a missing `mcp` package doesn't break module
# import for environments that never enable USE_MCP_TOOLS — mcp_execute_tool
# raises a clear error if the package is absent and the gate is on.
try:
    from mcp import ClientSession
    from mcp.client.streamable_http import streamablehttp_client
except ImportError:  # pragma: no cover - mcp is a hard requirement in prod
    ClientSession = None  # type: ignore[assignment,misc]
    streamablehttp_client = None  # type: ignore[assignment]

logger = logging.getLogger(__name__)

__all__ = [
    "KnowledgeContext",
    "KnowledgeClient",
    "init_knowledge_client",
    "close_knowledge_client",
    "get_knowledge_client",
    "DEGRADED_RECENT_MESSAGE_COUNT",
]

# D-T2-03 — paired with knowledge-service's settings.recent_message_count.
# Exported as a module-level constant for existing imports; value is
# resolved from settings at import time. Both services default to 50
# via the shared env var RECENT_MESSAGE_COUNT. Knowledge-service's
# authoritative value is what non-degraded responses return; this is
# the failsafe used only when knowledge-service is unreachable.
DEGRADED_RECENT_MESSAGE_COUNT = settings.recent_message_count

# Knowledge-service enforces max_length=4000 on its ContextBuildRequest.message
# field (K4a-I6). Long user messages get truncated here so we don't eat a
# pointless 422 → degraded cycle on every paste-heavy turn (K5-I2).
MESSAGE_MAX_CHARS = 4000


class KnowledgeContext(BaseModel):
    """Mirror of knowledge-service's ContextBuildResponse.

    `mode` may be one of:
      no_project / static / full   — successful build from knowledge-service
      degraded                      — synthesised on client-side failure

    K18.9: `stable_context` + `volatile_context` carry the split of
    `context` so chat-service can emit Anthropic cache_control markers
    on the stable segment (message-independent prefix: L0 + project
    instructions/summary). Fall back to `""` for both fields when
    talking to an older knowledge-service build — chat-service then
    uses the concat `context` path as before.
    """

    model_config = ConfigDict(extra="ignore")

    mode: str
    context: str = ""
    recent_message_count: int = DEGRADED_RECENT_MESSAGE_COUNT
    token_count: int = 0
    stable_context: str = ""
    volatile_context: str = ""
    # K21-B — per-project tool-calling opt-out, surfaced from
    # knowledge-service `projects.tool_calling_enabled`. Defaults True so
    # an older knowledge-service that omits the field, the no-project
    # path, and the degraded path all leave tool-calling enabled.
    tool_calling_enabled: bool = True


def _degraded() -> KnowledgeContext:
    return KnowledgeContext(
        mode="degraded",
        context="",
        recent_message_count=DEGRADED_RECENT_MESSAGE_COUNT,
        token_count=0,
    )


def _normalize_tool_parameters(input_schema: dict | None) -> dict:
    """Normalize an MCP tool's inputSchema to a valid OpenAI function-call
    `parameters` object. OpenAI-compatible providers (e.g. LM Studio) REQUIRE a
    `properties` object — a tool with an empty input (e.g. glossary_list_system_standards,
    whose Go input struct is empty) yields `{"type":"object"}` with no
    `properties`, which 400s the WHOLE request. Default the missing keys so an
    argument-less tool advertises `{"type":"object","properties":{}}`.
    """
    params = dict(input_schema) if isinstance(input_schema, dict) else {}
    params.setdefault("type", "object")
    params.setdefault("properties", {})
    return params


class KnowledgeClient:
    """Thin async wrapper around httpx.AsyncClient.

    One instance per chat-service process, shared across requests.
    Close via `await client.aclose()` on shutdown.
    """

    def __init__(
        self,
        base_url: str,
        internal_token: str,
        timeout_s: float,
        retries: int,
        *,
        tool_timeout_s: float = 30.0,
        tools_base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Construct the client.

        `timeout_s` is the client-wide default — sized for `build_context`,
        a fast read on the chat hot path. `tool_timeout_s` is the longer
        per-call timeout `execute_tool` overrides with: a memory tool does
        real work (`memory_remember` runs injection-neutralisation + a
        Neo4j write) and routinely exceeds the build_context budget
        (D-K21B-06 live-smoke finding).

        `transport` is an optional httpx transport to inject at test time
        (K5-I7 fix). Tests use `httpx.MockTransport(handler)` so they
        don't have to monkey-patch `httpx.AsyncClient`, which would
        couple them to the import style used in this module — a refactor
        from `import httpx` to `from httpx import AsyncClient` would
        silently break a `@patch("...httpx.AsyncClient")`.
        """
        self._base_url = base_url.rstrip("/")
        # ai-gateway P0: tool definitions + MCP execution target the gateway;
        # build_context (grounding) stays on _base_url (knowledge). Defaults to
        # _base_url so tests that omit it keep their existing single-host wiring.
        self._tools_base_url = (tools_base_url or base_url).rstrip("/")
        self._retries = max(0, retries)
        self._tool_timeout_s = tool_timeout_s
        client_kwargs: dict = {
            "timeout": httpx.Timeout(timeout_s),
            "headers": {"X-Internal-Token": internal_token},
        }
        if transport is not None:
            client_kwargs["transport"] = transport
        self._http = httpx.AsyncClient(**client_kwargs)
        # K21-B — process cache for GET /internal/tools/definitions.
        # None = not fetched yet; a list = the cached OpenAI schemas.
        self._tool_definitions: list[dict] | None = None
        # T4c — separate process cache for the ADMIN catalog (`/mcp/admin`). The
        # catalog is identical for every admin (only the per-request RS256 token
        # varies), so the CATALOG is cached but the token is NEVER part of the
        # cache key and is NEVER cached. Kept distinct from `_tool_definitions`
        # so admin tools can never bleed into the user/book `/mcp` catalog (E17).
        self._admin_tool_definitions: list[dict] | None = None
        # MCP-fanout C-FT/C-GW (H10) — catalog-level metadata from the most recent
        # successful list-tools (the gateway's `_meta`). Carries the partial-catalog
        # / per-provider availability signal so find_tools can distinguish
        # "no such tool" from "provider temporarily unavailable". None until a
        # successful fetch; {} when the gateway sends no signal yet (clean seam
        # for S-GATEWAY — see get_catalog_meta()).
        self._catalog_meta: dict | None = None

    async def aclose(self) -> None:
        await self._http.aclose()

    async def build_context(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        project_id: str | None = None,
        message: str = "",
        language: str | None = None,
    ) -> KnowledgeContext:
        """POST /internal/context/build.

        Returns a degraded KnowledgeContext on any failure — never raises.
        Chat-service treats `mode == "degraded"` as "no memory, fall back
        to plain history replay".

        Safety normalisations applied before sending:
          * message is truncated to MESSAGE_MAX_CHARS runes so an
            accidental paste doesn't 422 the request (K5-I2).
          * session_id / project_id are omitted when empty/None rather
            than sent as empty strings (which would 422 via UUID
            validation — K5-I1).

        P6 grounding port (H2): grounding is fetched via the ai-gateway
        (the single AI integration layer). On a GATEWAY OUTAGE (transport
        error / 5xx) it falls back to calling knowledge-service directly,
        so a gateway outage degrades context but never breaks the turn. A
        STABLE knowledge signal proxied through the gateway (404 / 501 /
        4xx) returns degraded WITHOUT the fallback (knowledge-direct would
        answer the same). Both unreachable → degraded.
        """
        # Truncate long messages at the client boundary.
        safe_message = message or ""
        if len(safe_message) > MESSAGE_MAX_CHARS:
            safe_message = safe_message[:MESSAGE_MAX_CHARS]

        body: dict = {
            "user_id": user_id,
            "message": safe_message,
        }
        # S6 — the display/target language for entity aliases (optional). Omitted
        # when unset → knowledge returns source-language aliases (back-compat).
        if language:
            body["language"] = language
        # Truthy checks (not `is not None`) so empty strings are omitted,
        # which prevents knowledge-service's UUID validator from 422-ing
        # the call.
        if session_id:
            body["session_id"] = session_id
        if project_id:
            body["project_id"] = project_id

        # K7e: forward the caller's trace_id so knowledge-service (and
        # glossary-service, one hop further) can stitch their logs to
        # the originating chat turn. Empty string → no header, which
        # lets knowledge-service generate its own id.
        tid = current_trace_id()
        call_headers = {"X-Trace-Id": tid} if tid else None

        # Primary = ai-gateway grounding; fallback = knowledge direct (H2).
        gateway_url = f"{self._tools_base_url}/internal/context/build"
        ctx = await self._build_context_at(gateway_url, body, call_headers, project_id)
        if ctx is not None:
            return ctx

        knowledge_url = f"{self._base_url}/internal/context/build"
        if knowledge_url != gateway_url:
            logger.info("grounding via gateway unavailable — falling back to knowledge direct")
            ctx = await self._build_context_at(knowledge_url, body, call_headers, project_id)
            if ctx is not None:
                return ctx

        # Gateway and direct both unreachable → degraded (turn proceeds tool/context-free).
        return _degraded()

    async def _build_context_at(
        self,
        url: str,
        body: dict,
        call_headers: dict | None,
        project_id: str | None,
    ) -> KnowledgeContext | None:
        """POST grounding at `url`, with retries.

        Returns a ``KnowledgeContext`` when the host answered — a real context on
        200, or a degraded context on a STABLE signal (501 Mode-3 / 404
        project-not-found / other 4xx / decode / validate failure), which the
        caller must NOT retry elsewhere. Returns ``None`` on an OUTAGE (transport
        error or 5xx after all retries) — the signal that the caller should try
        the fallback host (H2)."""
        attempts = self._retries + 1
        last_err_summary: str | None = None
        for _ in range(attempts):
            try:
                resp = await self._http.post(url, json=body, headers=call_headers)
            except httpx.TimeoutException:
                last_err_summary = "timeout"
                continue
            except httpx.HTTPError as exc:
                last_err_summary = f"transport: {type(exc).__name__}"
                continue

            # 501 is technically a 5xx but it's the stable "Mode 3 not
            # implemented yet" signal from K4b/K4c — don't retry, don't fall back.
            if resp.status_code == 501:
                logger.debug("build_context 501 (Mode 3 not implemented)")
                return _degraded()

            if resp.status_code >= 500:
                # Includes the gateway's 502-on-knowledge-outage → treat as OUTAGE
                # (retry here, then None so the caller falls back).
                last_err_summary = f"{resp.status_code}"
                continue

            if resp.status_code in (401, 403):
                # An auth rejection is a HOST-ACCESS problem (e.g. the gateway's
                # internal token is misconfigured), not a stable request problem —
                # the retained direct chat→knowledge path uses the same token and
                # may be accepted. Treat as an OUTAGE so the caller falls back
                # (H2). No retry — the token won't change between attempts.
                logger.warning("build_context %d (auth) at %s — falling back", resp.status_code, url)
                return None

            if resp.status_code == 404:
                # 404 = project not found (per K4b ProjectNotFound mapping).
                # Stable request problem — degraded, no fallback.
                logger.warning(
                    "build_context 404 (project not found) project_id=%s", project_id,
                )
                return _degraded()

            if resp.status_code >= 400:
                logger.warning(
                    "build_context %d (no retry) body=%s",
                    resp.status_code, resp.text[:200],
                )
                return _degraded()

            try:
                data = resp.json()
            except Exception as exc:
                logger.warning("build_context decode failure: %s", exc)
                return _degraded()

            try:
                return KnowledgeContext.model_validate(data)
            except Exception as exc:
                logger.warning("build_context validate failure: %s", exc)
                return _degraded()

        # All attempts exhausted → OUTAGE (None ⇒ caller falls back). Keep the
        # "unavailable" keyword the once-per-failure log guard keys on.
        logger.warning(
            "build_context unavailable at %s after %d attempts: %s",
            url, attempts, last_err_summary or "unknown",
        )
        return None

    async def get_tool_definitions(self) -> list[dict]:
        """Fetch the federated tool catalog from the ai-gateway via MCP
        ``list-tools`` and convert each entry to an OpenAI function schema
        (the shape the chat tool-loop advertises to the LLM). Cached
        process-wide after the first success.

        Returns ``[]`` on any failure; the caller then runs the chat turn
        tool-free. A failure is deliberately NOT cached, so a later turn
        retries.
        """
        if self._tool_definitions is not None:
            return self._tool_definitions
        if streamablehttp_client is None or ClientSession is None:
            logger.warning(
                "get_tool_definitions called but the 'mcp' package is not installed"
            )
            return []

        mcp_url = f"{self._tools_base_url}/mcp"
        headers = {"X-Internal-Token": self._http.headers["X-Internal-Token"]}
        tid = current_trace_id()
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            async with streamablehttp_client(
                mcp_url, headers=headers,
                timeout=self._tool_timeout_s, sse_read_timeout=self._tool_timeout_s,
            ) as (read, write, _):
                async with ClientSession(read, write) as mcp_session:
                    await mcp_session.initialize()
                    listed = await mcp_session.list_tools()
        except Exception as exc:
            logger.warning("get_tool_definitions (mcp list-tools) failed: %s", exc)
            return []

        tools = []
        for t in listed.tools:
            fn: dict = {
                "name": t.name,
                "description": t.description or "",
                "parameters": _normalize_tool_parameters(t.inputSchema),
            }
            # MCP-fanout C-TOOL: preserve the per-tool `_meta` (tier / scope /
            # synonyms / undo_hint) so the consumer can drive tier-based
            # advertising + find_tools recall WITHOUT it ever reaching the
            # provider — strip_tool_meta() removes it before the wire request.
            meta = getattr(t, "meta", None)
            if isinstance(meta, dict) and meta:
                fn["_meta"] = dict(meta)
            tools.append({"type": "function", "function": fn})
        # MCP-fanout H10: stash the gateway's catalog-level `_meta` (availability /
        # partial-catalog signal). The seam exists even when S-GATEWAY hasn't
        # populated it yet (then it's {} and find_tools degrades to "no such tool"
        # everywhere — never a false outage claim).
        cat_meta = getattr(listed, "meta", None)
        self._catalog_meta = dict(cat_meta) if isinstance(cat_meta, dict) else {}
        self._tool_definitions = tools
        return tools

    async def get_admin_tool_definitions(self, admin_token: str | None) -> list[dict]:
        """T4c — fetch the SYSTEM-TIER admin tool catalog from the gateway's
        SEPARATE ``/mcp/admin`` endpoint (NOT ``/mcp``), presenting the caller's
        RS256 ``admin:write`` token in ``X-Admin-Token``.

        Curation (E17/INV-T6): this is the ONLY method that dials ``/mcp/admin``;
        the user/book ``get_tool_definitions`` never does, so admin tool names
        never appear in a non-admin session's catalog. Conversely an admin
        session calls THIS, not ``get_tool_definitions``.

        The CATALOG is cached process-wide (identical for every admin); the
        ``admin_token`` is NEVER cached and NEVER logged (§6.7). No token, or any
        transport/auth failure (incl. a 401 from the transport gate) → ``[]`` so
        the turn degrades tool-free, same contract as the user path.
        """
        if not admin_token:
            return []
        if self._admin_tool_definitions is not None:
            return self._admin_tool_definitions
        if streamablehttp_client is None or ClientSession is None:
            logger.warning(
                "get_admin_tool_definitions called but the 'mcp' package is not installed"
            )
            return []

        mcp_url = f"{self._tools_base_url}/mcp/admin"
        headers = {
            "X-Internal-Token": self._http.headers["X-Internal-Token"],
            "X-Admin-Token": admin_token,
        }
        tid = current_trace_id()
        if tid:
            headers["X-Trace-Id"] = tid
        try:
            async with streamablehttp_client(
                mcp_url, headers=headers,
                timeout=self._tool_timeout_s, sse_read_timeout=self._tool_timeout_s,
            ) as (read, write, _):
                async with ClientSession(read, write) as mcp_session:
                    await mcp_session.initialize()
                    listed = await mcp_session.list_tools()
        except Exception as exc:
            # NOTE: log only the exception, never `headers` — `X-Admin-Token`
            # is a bearer credential and must not reach the logs (§6.7).
            logger.warning("get_admin_tool_definitions (mcp list-tools) failed: %s", exc)
            return []

        tools = [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description or "",
                    "parameters": _normalize_tool_parameters(t.inputSchema),
                },
            }
            for t in listed.tools
        ]
        self._admin_tool_definitions = tools
        return tools

    def get_catalog_meta(self) -> dict:
        """MCP-fanout H10 — the gateway's catalog-level `_meta` from the last
        successful list-tools, or ``{}`` if none was fetched / sent.

        S-GATEWAY (C-GW) is expected to populate a per-provider availability map
        here, e.g. ``{"unavailable_providers": ["book"], "partial": true}``, so a
        consumer's find_tools can tell "no such tool" from "provider temporarily
        down" (→ the agent says "try again," never "I can't"). Until that lands
        this returns ``{}`` (a clean, non-lying default). TODO(S-GATEWAY): pin the
        exact key shape at COMPOSE A.
        """
        return self._catalog_meta or {}

    async def mcp_execute_tool(
        self,
        *,
        user_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict,
        project_id: str | None = None,
        admin_token: str | None = None,
    ) -> dict:
        """ARCH-2 C2 — execute a memory tool via MCP streamable HTTP transport.

        Returns the same dict shape as execute_tool() for drop-in compatibility:
          {"success": True, "result": dict, "error": None}      on success
          {"success": False, "result": None, "error": str}      on tool or transport failure

        Context headers carry user_id / project_id / session_id — they never
        appear in tool_args (design D3). A transport or protocol failure returns
        success=False (graceful degradation, same contract as execute_tool()).

        T4c — when ``admin_token`` is set the call routes to the SEPARATE
        ``/mcp/admin`` endpoint with the RS256 token in ``X-Admin-Token`` and
        DOES NOT send ``X-User-Id``: admin authority is the verified RS256 token,
        never the user id (INV-T2). The token is never logged (§6.7).
        """
        if streamablehttp_client is None or ClientSession is None:
            logger.warning("mcp_execute_tool called but the 'mcp' package is not installed")
            return {
                "success": False,
                "result": None,
                "error": "mcp tool backend unavailable: mcp package not installed",
            }

        if admin_token:
            # System-tier admin tool: separate endpoint, RS256 authority, NO X-User-Id.
            mcp_url = f"{self._tools_base_url}/mcp/admin"
            headers = {
                "X-Internal-Token": self._http.headers["X-Internal-Token"],
                "X-Admin-Token": admin_token,
                "X-Session-Id": session_id,
            }
        else:
            mcp_url = f"{self._tools_base_url}/mcp"
            headers = {
                "X-Internal-Token": self._http.headers["X-Internal-Token"],
                "X-User-Id": user_id,
                "X-Session-Id": session_id,
            }
        if project_id and not admin_token:
            headers["X-Project-Id"] = project_id
        # K7e — mirror execute_tool: forward the caller's trace_id so
        # knowledge-service stitches its logs to the originating chat turn.
        # Omit when empty so knowledge-service mints its own.
        tid = current_trace_id()
        if tid:
            headers["X-Trace-Id"] = tid

        try:
            # Bind BOTH the connect timeout and sse_read_timeout to the same
            # tool budget execute_tool uses. sse_read_timeout MUST be set
            # explicitly: the tool RESULT rides the SSE read channel, so the
            # SDK default (300s) would let a stalled backend hang ~10x the
            # bespoke 30s ceiling. If this ever migrates to the new
            # 'streamable_http_client' (which ignores these kwargs), the budget
            # must move to an httpx.Timeout(read=budget) on a supplied client.
            async with streamablehttp_client(
                mcp_url,
                headers=headers,
                timeout=self._tool_timeout_s,
                sse_read_timeout=self._tool_timeout_s,
            ) as (read, write, _):
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

        # An MCP-level tool error (e.g. an auth ValueError raised inside the
        # server handler) surfaces as isError=True with the message in the
        # first text content item — map it to a success=False envelope.
        if getattr(result, "isError", False):
            err_text = ""
            if result.content:
                err_text = getattr(result.content[0], "text", "") or ""
            return {
                "success": False,
                "result": None,
                "error": err_text or "mcp tool error",
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
            logger.warning(
                "mcp_execute_tool decode error: %s — raw: %s",
                exc, getattr(first, "text", "?")[:200],
            )
            return {"success": False, "result": None, "error": "mcp tool returned unparseable content"}

        if isinstance(payload, dict) and payload.get("success") is False:
            # Server-side tool error propagated as a structured dict.
            return {
                "success": False,
                "result": None,
                "error": payload.get("error", "tool error"),
            }

        # Canonical {} empty-success contract: keep this byte-identical to
        # execute_tool's success path. A wire "null" yields payload=None after
        # json.loads — coerce it to {} so an empty success is {} on BOTH
        # transports (the MCP server's _dispatch already does the same).
        return {"success": True, "result": payload if payload is not None else {}, "error": None}


# ── module-level singleton managed by lifespan ─────────────────────────────

_client: KnowledgeClient | None = None


def init_knowledge_client() -> KnowledgeClient:
    """Instantiate the shared client from settings. Idempotent — a second
    call without a prior close_knowledge_client() returns the existing
    instance instead of leaking the previous httpx.AsyncClient pool.
    """
    global _client
    if _client is not None:
        return _client
    _client = KnowledgeClient(
        base_url=settings.knowledge_service_url,
        internal_token=settings.internal_service_token,
        timeout_s=settings.knowledge_client_timeout_s,
        retries=settings.knowledge_client_retries,
        tool_timeout_s=settings.knowledge_tool_timeout_s,
        # ai-gateway P0: route tools (definitions + MCP execute) through the gateway.
        tools_base_url=settings.ai_gateway_url,
    )
    return _client


async def close_knowledge_client() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None


def get_knowledge_client() -> KnowledgeClient:
    """Lazy accessor — initialises on first use if lifespan didn't.

    Allows graceful operation in test contexts where lifespan startup
    hasn't run.
    """
    global _client
    if _client is None:
        return init_knowledge_client()
    return _client
