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

    async def aclose(self) -> None:
        await self._http.aclose()

    async def build_context(
        self,
        *,
        user_id: str,
        session_id: str | None = None,
        project_id: str | None = None,
        message: str = "",
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
        """
        url = f"{self._base_url}/internal/context/build"

        # Truncate long messages at the client boundary.
        safe_message = message or ""
        if len(safe_message) > MESSAGE_MAX_CHARS:
            safe_message = safe_message[:MESSAGE_MAX_CHARS]

        body: dict = {
            "user_id": user_id,
            "message": safe_message,
        }
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
            # implemented yet" signal from K4b/K4c — don't retry.
            if resp.status_code == 501:
                logger.debug("knowledge build_context 501 (Mode 3 not implemented)")
                return _degraded()

            if resp.status_code >= 500:
                last_err_summary = f"{resp.status_code}"
                continue

            if resp.status_code == 404:
                # 404 = project not found (per K4b ProjectNotFound mapping).
                # Stable request problem — don't retry.
                logger.warning(
                    "knowledge build_context 404 (project not found) project_id=%s",
                    project_id,
                )
                return _degraded()

            if resp.status_code >= 400:
                logger.warning(
                    "knowledge build_context %d (no retry) body=%s",
                    resp.status_code, resp.text[:200],
                )
                return _degraded()

            try:
                data = resp.json()
            except Exception as exc:
                logger.warning("knowledge build_context decode failure: %s", exc)
                return _degraded()

            try:
                return KnowledgeContext.model_validate(data)
            except Exception as exc:
                logger.warning("knowledge build_context validate failure: %s", exc)
                return _degraded()

        # All attempts exhausted — single warning summarising the failure.
        logger.warning(
            "knowledge build_context unavailable after %d attempts: %s",
            attempts, last_err_summary or "unknown",
        )
        return _degraded()

    async def get_tool_definitions(self) -> list[dict]:
        """GET /internal/tools/definitions — the OpenAI tool schemas
        (K21-B D1). Cached process-wide after the first success.

        Returns ``[]`` on any failure; the caller then runs the chat turn
        tool-free. A failure is deliberately NOT cached, so a later turn
        retries — ``build_context`` already runs every turn, so one extra
        GET while knowledge-service is unreachable is negligible.
        """
        if self._tool_definitions is not None:
            return self._tool_definitions

        url = f"{self._base_url}/internal/tools/definitions"
        tid = current_trace_id()
        call_headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(url, headers=call_headers)
        except httpx.HTTPError as exc:
            logger.warning("knowledge tool definitions fetch failed: %s", exc)
            return []
        if resp.status_code != 200:
            logger.warning(
                "knowledge tool definitions fetch %d", resp.status_code
            )
            return []
        try:
            tools = resp.json().get("tools", [])
        except Exception as exc:
            logger.warning("knowledge tool definitions decode failed: %s", exc)
            return []
        if not isinstance(tools, list):
            logger.warning("knowledge tool definitions: unexpected shape")
            return []
        self._tool_definitions = tools
        return tools

    async def execute_tool(
        self,
        *,
        user_id: str,
        session_id: str,
        tool_name: str,
        tool_args: dict,
        project_id: str | None = None,
    ) -> dict:
        """POST /internal/tools/execute (K21-B).

        Returns the ``{success, result, error}`` envelope. On a transport
        failure or a non-200 it returns a synthesised ``success=False``
        envelope so the tool-calling loop can tell the LLM the tool
        failed and carry on — this never raises.
        """
        url = f"{self._base_url}/internal/tools/execute"
        body: dict = {
            "user_id": user_id,
            "session_id": session_id,
            "tool_name": tool_name,
            "tool_args": tool_args,
        }
        # Omit project_id when empty/None — a no-project chat is valid
        # and the executor handles a null project per Cycle A design D3.
        if project_id:
            body["project_id"] = project_id

        tid = current_trace_id()
        call_headers = {"X-Trace-Id": tid} if tid else None
        try:
            # Override the client-wide build_context budget — a memory
            # tool does real work and would ReadTimeout at 500ms (D-K21B-06).
            resp = await self._http.post(
                url, json=body, headers=call_headers, timeout=self._tool_timeout_s
            )
        except httpx.HTTPError as exc:
            logger.warning("knowledge execute_tool transport error: %s", exc)
            return {
                "success": False, "result": None,
                "error": f"tool backend unavailable: {type(exc).__name__}",
            }
        if resp.status_code != 200:
            logger.warning("knowledge execute_tool HTTP %d", resp.status_code)
            return {
                "success": False, "result": None,
                "error": f"tool backend error (HTTP {resp.status_code})",
            }
        try:
            return resp.json()
        except Exception as exc:
            logger.warning("knowledge execute_tool decode failed: %s", exc)
            return {
                "success": False, "result": None,
                "error": "tool backend returned an invalid response",
            }


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
