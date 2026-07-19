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

import json
import logging
import re
import time
from typing import Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from app.config import settings
from app.middleware.trace_id import current_trace_id

# REG-P2-03 — per-user tool-catalog cache TTL. Short by design: the federation
# overlay changes the instant a user registers/removes an external MCP server, so a
# long cache would hide a just-registered server (or serve a just-removed one). 60s
# bounds the staleness window while keeping most turns cache-hot.
_TOOL_CATALOG_TTL_S = 60.0

# An external federated (overlay) tool name — u_/b_/s_<hash8>_… — matching the
# ai-gateway's OVERLAY_NAME_RE. Internal LoreWeave tools are unprefixed. External
# tools may return plain text (prose/markdown), not the JSON internal tools return.
_OVERLAY_TOOL_RE = re.compile(r"^[ubs]_[0-9a-f]{8}_")

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
    # W1 — per-section token split of `context` (glossary_entities / facts /
    # passages / summaries / instructions / ...), the nested detail of the
    # contextBudget frame's memory_knowledge category. Defaults {} when talking
    # to an older knowledge-service build (additive contract).
    sections: dict[str, int] = {}
    # K21-B — per-project tool-calling opt-out, surfaced from
    # knowledge-service `projects.tool_calling_enabled`. Defaults True so
    # an older knowledge-service that omits the field, the no-project
    # path, and the degraded path all leave tool-calling enabled.
    tool_calling_enabled: bool = True
    # WS-4C Half A — per-project canon auto-capture, surfaced from
    # knowledge-service `projects.canon_capture_enabled`. Defaults FALSE, the
    # opposite of tool_calling_enabled and deliberately so: capture spends the
    # user's BYOK tokens, so an older knowledge-service that omits the field, the
    # no-project path, and the degraded path must all leave capture OFF.
    canon_capture_enabled: bool = False
    # Interview-roleplay — rendered working_memory anchor (charter + state).
    # Pinned into the system block AND tail-injected by stream_service. "" when
    # the session has no working_memory block or on the degraded path; chat-service
    # then falls back to the session's working_memory_seed (EC-4). M4 populates it.
    working_memory: str = ""


def _degraded() -> KnowledgeContext:
    return KnowledgeContext(
        mode="degraded",
        context="",
        recent_message_count=DEGRADED_RECENT_MESSAGE_COUNT,
        token_count=0,
    )


def _error_envelope(err_text: str) -> dict:
    """Build the `{"success": False, ...}` envelope from an MCP isError payload.

    D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR — knowledge-service raises on a tool
    failure and puts a C4-shaped JSON body in `content[0].text`:
    ``{"code"?, "message", "detail"?}`` (the same shape ai-gateway writes). Decode
    it so a STABLE machine code (e.g. ``KG_ENDPOINT_NOT_NODE``) and its ``detail``
    (``{"missing": [...]}``) survive to the caller, letting a workflow branch on the
    code rather than pattern-match prose (contract C5).

    Anything that isn't such a JSON object (plain-text errors from overlay/external
    tools, or older services) degrades to the raw text — never raises.
    """
    text = (err_text or "").strip()
    if text.startswith("{"):
        try:
            body = json.loads(text)
        except (ValueError, TypeError):
            body = None
        if isinstance(body, dict) and "message" in body:
            out: dict = {
                "success": False,
                "result": None,
                "error": str(body.get("message") or "mcp tool error"),
            }
            if body.get("code") is not None:
                out["code"] = body["code"]
            if body.get("detail") is not None:
                out["detail"] = body["detail"]
            return out
    return {"success": False, "result": None, "error": text or "mcp tool error"}


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
        # K21-B — cache for the federated tool catalog. Sourced from the ai-gateway
        # `/mcp` MCP `tools/list` (see get_tool_definitions); the legacy
        # `/internal/tools/definitions` HTTP path was retired in KM0.
        # REG-P2-03 — the catalog is now PER-USER: the gateway appends the caller's
        # external-MCP federation overlay (u_/b_/s_ tools) when it sees `X-User-Id`,
        # so a single process-wide cache would leak one user's overlay to everyone.
        # Keyed by user_id ("" = the base/no-user catalog), with a SHORT TTL because
        # the overlay changes the moment a user registers/removes a server (aligns
        # with the gateway's own overlay Q-CACHE TTL). Value = (expiry_monotonic, schemas).
        self._tool_defs_cache: dict[str, tuple[float, list[dict]]] = {}
        # T5 (audit) — cache project_id → book_id for the entity-presence gate. A
        # stable mapping, so a plain dict (no TTL); only successes are cached so a
        # transient miss self-heals. `None` is a legitimate cached value (Mode-1
        # project with no book).
        self._project_book_cache: dict[str, str | None] = {}
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
        project_ids: list[str] | None = None,
        message: str = "",
        language: str | None = None,
        grounding: bool = True,
        current_chapter_id: str | None = None,
        context_length: int | None = None,
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
        # T5 (Context Budget Law D2) — the entity-presence gate's decision. Only send
        # when gating OUT (False); omit when True so an older knowledge-service (no
        # `grounding` field) is unaffected and the default full path stays byte-identical.
        if not grounding:
            body["grounding"] = False
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
        # Track B B1(2) — multi-KG: forward the project SET when present.
        # knowledge-service's builder gives project_ids precedence over
        # project_id (≥2 → the union mode, 1 → single, all-stale → 404). Empty
        # ids are omitted (only the single-project / no-project path applies).
        if project_ids:
            body["project_ids"] = list(project_ids)
        # M1b — the editor's open chapter, for the working-scope passage boost.
        # Truthy check omits empty strings (would 422 knowledge's UUID validator).
        # Only editor turns carry it; reader/glossary chat send nothing → no boost.
        if current_chapter_id:
            body["current_chapter_id"] = current_chapter_id
        # Model-context-aware Mode-3 budget scaling — the session model's real
        # resolved context window, so knowledge-service can scale its flat
        # mode3_token_budget instead of every model getting the same cap. Omitted
        # when unknown → an older/current knowledge-service keeps its flat default.
        if context_length and context_length > 0:
            body["context_length"] = context_length

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

    async def resolve_book_id(self, *, user_id: str, project_id: str) -> str | None:
        """T5 (audit) — the knowledge project's linked `book_id`, for the chat
        entity-presence gate (which needs the BOOK id, not the KNOWLEDGE project id a
        session carries). Cached per project_id (stable mapping). Returns ``None`` on
        a Mode-1/no-book project OR any failure — the gate then stays open
        (bias-to-include), so a knowledge outage never breaks the turn, it just
        forgoes the gate's savings. Uses `_base_url` (knowledge direct); this is a
        cheap owner-scoped read, not a grounding pull, so it doesn't go via the gateway."""
        if not project_id:
            return None
        if project_id in self._project_book_cache:
            return self._project_book_cache[project_id]
        url = f"{self._base_url}/internal/context/project-book/{project_id}"
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.get(url, params={"user_id": user_id}, headers=headers)
            if resp.status_code == 200:
                book_id = resp.json().get("book_id")
                self._project_book_cache[project_id] = book_id  # cache success (incl. None)
                return book_id
            logger.warning("resolve_book_id %d for project %s", resp.status_code, project_id)
        except Exception:  # noqa: BLE001 — degrade to gate-open, never raise into the turn
            logger.warning("resolve_book_id failed for project %s", project_id, exc_info=False)
        return None  # do NOT cache a failure — retry next turn

    async def init_working_memory(
        self, *, session_id: str, user_id: str, charter: dict
    ) -> bool:
        """POST /internal/working-memory/init — the goal-authority write path.

        Pushes the FROZEN charter so knowledge-service owns the evolving block
        (the executive then updates state). Best-effort: on any failure returns
        False and logs — the session still anchors from its own
        working_memory_seed (EC-4), so a knowledge outage never blocks start.
        """
        url = f"{self._base_url}/internal/working-memory/init"
        body = {"session_id": session_id, "user_id": user_id, "charter": charter}
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.post(url, json=body, headers=headers)
            if resp.status_code in (200, 204):
                return True
            logger.warning("init_working_memory non-2xx: %s", resp.status_code)
            return False
        except Exception:
            logger.warning("init_working_memory failed for session %s", session_id, exc_info=True)
            return False

    async def tick_working_memory(
        self, *, session_id: str, user_id: str,
        model_source: str | None, model_ref: str | None,
        recent_turns: list[dict],
    ) -> str | None:
        """POST /internal/working-memory/tick — run one executive pass.

        Sends the session's model (the executive runs on it) + the recent-turns
        window so knowledge-service needn't call back into chat. Best-effort:
        returns the status string on success, None on any failure (the anchor
        still holds from the existing block / seed).

        Uses the LONGER tool timeout: the executive makes an LLM call, so the
        build_context-sized default would disconnect mid-pass and could abort the
        server-side handler before it writes state.
        """
        url = f"{self._base_url}/internal/working-memory/tick"
        body = {
            "session_id": session_id, "user_id": user_id,
            "model_source": model_source, "model_ref": model_ref,
            "recent_turns": recent_turns,
        }
        tid = current_trace_id()
        headers = {"X-Trace-Id": tid} if tid else None
        try:
            resp = await self._http.post(
                url, json=body, headers=headers, timeout=self._tool_timeout_s,
            )
            if resp.status_code == 200:
                return resp.json().get("status")
            logger.warning("tick_working_memory non-200: %s", resp.status_code)
            return None
        except Exception:
            logger.warning("tick_working_memory failed for session %s", session_id, exc_info=True)
            return None

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

    async def get_tool_definitions(self, user_id: str | None = None) -> list[dict]:
        """Fetch the federated tool catalog from the ai-gateway via MCP
        ``list-tools`` and convert each entry to an OpenAI function schema
        (the shape the chat tool-loop advertises to the LLM).

        REG-P2-03 — pass ``user_id`` so the gateway appends the caller's external-MCP
        federation overlay (``u_``/``b_``/``s_`` tools). The result is cached PER-USER
        with a short TTL (``_TOOL_CATALOG_TTL_S``); omit ``user_id`` (base inspection
        paths) to get the overlay-free platform catalog. Without the user id the
        overlay never reaches the turn — the bug this fixes.

        Returns ``[]`` on any failure; the caller then runs the chat turn
        tool-free. A failure is deliberately NOT cached, so a later turn retries.
        """
        cache_key = user_id or ""
        cached = self._tool_defs_cache.get(cache_key)
        if cached is not None and time.monotonic() < cached[0]:
            return cached[1]
        if streamablehttp_client is None or ClientSession is None:
            logger.warning(
                "get_tool_definitions called but the 'mcp' package is not installed"
            )
            return []

        mcp_url = f"{self._tools_base_url}/mcp"
        headers = {"X-Internal-Token": self._http.headers["X-Internal-Token"]}
        # The per-user overlay is keyed on X-User-Id at the gateway; without it the
        # gateway returns only the base (platform) catalog.
        if user_id:
            headers["X-User-Id"] = user_id
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
        self._tool_defs_cache[cache_key] = (time.monotonic() + _TOOL_CATALOG_TTL_S, tools)
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
        #
        # D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR: knowledge-service now raises on a
        # tool failure, and its error text is the C4-shaped JSON body
        # {"code"?, "message", "detail"?} (the same shape ai-gateway puts in
        # content[0].text). Decode it so a stable `code` (e.g.
        # KG_ENDPOINT_NOT_NODE) and `detail` ({"missing": [...]}) reach the caller
        # — a workflow branches on the code, never on prose. Plain-text errors
        # (external/overlay tools, older services) fall back to the raw text.
        if getattr(result, "isError", False):
            err_text = ""
            if result.content:
                err_text = getattr(result.content[0], "text", "") or ""
            return _error_envelope(err_text)

        # FastMCP returns content as a list of TextContent/ImageContent items.
        # The knowledge-service handlers return JSON dicts serialised as the
        # text content of the first item.
        if not result.content:
            return {"success": False, "result": None, "error": "mcp tool returned empty content"}

        first = result.content[0]
        import json as _json  # noqa: PLC0415
        # #9B token-efficiency: heavy reads (e.g. glossary_book_ontology_read, ~42KB) now
        # return a SHORT PLACEHOLDER in content[0].text ("ok — see structuredContent") + the
        # real payload in `structuredContent`. Prefer structuredContent when present — otherwise
        # json.loads() of the placeholder fails with "unparseable content" and a working tool
        # reads as broken (the measured S02 blocker once book_id was being supplied).
        _sc = getattr(result, "structuredContent", None)
        if isinstance(_sc, dict) and _sc:
            payload = _sc
        else:
            try:
                payload = _json.loads(first.text)
            except Exception as exc:
                # External federated (overlay) tools may return PLAIN TEXT (prose/markdown),
                # which is a VALID result — e.g. a DeepWiki tool returning a repo's wiki
                # structure. Wrap it as {"text": ...} so the model can consume it. Internal
                # LoreWeave tools always return JSON, so a decode failure there IS an error
                # (never mask a real internal-tool bug as success).
                if _OVERLAY_TOOL_RE.match(tool_name):
                    text = getattr(first, "text", "") or ""
                    return {"success": True, "result": {"text": text}, "error": None}
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

        # ext-tasks (T1c(3)) — a capability-gated domain tool may return a durable
        # task HANDLE instead of a normal result (the confirm gate: open_gate). Surface
        # it as a task envelope the tool loop suspends on. FastMCP may nest a dict
        # return under `result`, so check both shapes. DORMANT until chat-service
        # declares tasks capability (no gate handle comes back before then).
        from app.services.task_detect import task_envelope_from_content  # noqa: PLC0415

        _task = task_envelope_from_content(payload)
        if _task is None and isinstance(payload, dict):
            _task = task_envelope_from_content(payload.get("result"))
        if _task is not None:
            return _task

        # Canonical {} empty-success contract: keep this byte-identical to
        # execute_tool's success path. A wire "null" yields payload=None after
        # json.loads — coerce it to {} so an empty success is {} on BOTH
        # transports (the MCP server's _dispatch already does the same).
        return {"success": True, "result": payload if payload is not None else {}, "error": None}

    # ── Wave C5 — MCP resources + prompts (federated via ai-gateway) ─────────
    # Same degrade contract as get_tool_definitions / mcp_execute_tool: any
    # transport or protocol failure returns empty/None — never raises into the
    # chat turn. Listings need only the service token (like tools/list);
    # read_mcp_resource carries the caller's envelope identity because the
    # downstream resource read is tenancy-gated (project ownership).

    async def list_mcp_resources(self) -> list[dict]:
        """Wave C5 — list the federated MCP resources from the ai-gateway:
        concrete resources (``resources/list``) plus resource TEMPLATES
        (``resources/templates/list`` — knowledge's project-scoped resources
        are ``{project_id}`` templates, so a concrete-only list would hide
        them). Each entry is a plain dict carrying ``uri`` (concrete) or
        ``uri_template`` (template) plus name/description/mime_type.

        Returns ``[]`` on any failure. Not cached — the listing is cheap and
        per-provider availability shifts between refreshes.
        """
        if streamablehttp_client is None or ClientSession is None:
            logger.warning("list_mcp_resources called but the 'mcp' package is not installed")
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
                    listed = await mcp_session.list_resources()
                    # Templates are tolerated independently: a gateway build
                    # without templates support still yields the concrete list.
                    try:
                        templates = await mcp_session.list_resource_templates()
                    except Exception as exc:  # noqa: BLE001 — degrade, don't raise
                        logger.warning("list_mcp_resources templates sub-list failed: %s", exc)
                        templates = None
        except Exception as exc:
            logger.warning("list_mcp_resources (mcp) failed: %s", exc)
            return []

        out: list[dict] = []
        for r in getattr(listed, "resources", None) or []:
            out.append({
                "uri": str(r.uri),
                "name": r.name or "",
                "description": r.description or "",
                "mime_type": r.mimeType or "",
            })
        for t in getattr(templates, "resourceTemplates", None) or []:
            out.append({
                "uri_template": t.uriTemplate,
                "name": t.name or "",
                "description": t.description or "",
                "mime_type": t.mimeType or "",
            })
        return out

    async def read_mcp_resource(
        self,
        uri: str,
        *,
        user_id: str,
        session_id: str,
        project_id: str | None = None,
    ) -> dict | None:
        """Wave C5 — read one federated MCP resource through the gateway.

        Identity rides the SAME envelope headers as mcp_execute_tool (design
        D3): the knowledge resources verify project ownership downstream, so
        the caller's user/session identity is mandatory, never an LLM arg.

        Returns ``{"uri", "mime_type", "text"}`` from the first contents item
        on success, or ``None`` on ANY failure (transport, protocol, tenancy
        rejection, blob-only content) — never raises into the turn.
        """
        if streamablehttp_client is None or ClientSession is None:
            logger.warning("read_mcp_resource called but the 'mcp' package is not installed")
            return None

        mcp_url = f"{self._tools_base_url}/mcp"
        headers = {
            "X-Internal-Token": self._http.headers["X-Internal-Token"],
            "X-User-Id": user_id,
            "X-Session-Id": session_id,
        }
        if project_id:
            headers["X-Project-Id"] = project_id
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
                    result = await mcp_session.read_resource(uri)
        except Exception as exc:
            logger.warning("read_mcp_resource failed for %s: %s", uri, exc)
            return None

        contents = getattr(result, "contents", None) or []
        if not contents:
            return None
        first = contents[0]
        text = getattr(first, "text", None)
        if text is None:
            # Blob (binary) resources have no text form — nothing usable for
            # the chat loop; treat as a degrade, not an error.
            return None
        return {
            "uri": str(getattr(first, "uri", uri)),
            "mime_type": getattr(first, "mimeType", "") or "",
            "text": text,
        }

    async def list_mcp_prompts(self) -> list[dict]:
        """Wave C5 — list the federated MCP prompts from the ai-gateway
        (``prompts/list``). Each entry is a plain dict: name, description, and
        the argument specs (name/description/required).

        Returns ``[]`` on any failure — the caller degrades prompt-free.
        """
        if streamablehttp_client is None or ClientSession is None:
            logger.warning("list_mcp_prompts called but the 'mcp' package is not installed")
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
                    listed = await mcp_session.list_prompts()
        except Exception as exc:
            logger.warning("list_mcp_prompts (mcp) failed: %s", exc)
            return []

        return [
            {
                "name": p.name,
                "description": p.description or "",
                "arguments": [
                    {
                        "name": a.name,
                        "description": a.description or "",
                        "required": bool(a.required),
                    }
                    for a in (p.arguments or [])
                ],
            }
            for p in getattr(listed, "prompts", None) or []
        ]

    async def get_mcp_prompt(
        self, name: str, arguments: dict[str, str] | None = None
    ) -> dict | None:
        """Wave C5 — render one federated MCP prompt (``prompts/get``).

        Prompts render canned instructions only (no stored data), so no
        envelope identity is needed. Returns ``{"description", "messages"}``
        — messages as ``[{"role", "text"}]`` — or ``None`` on any failure.
        """
        if streamablehttp_client is None or ClientSession is None:
            logger.warning("get_mcp_prompt called but the 'mcp' package is not installed")
            return None

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
                    result = await mcp_session.get_prompt(name, arguments or {})
        except Exception as exc:
            logger.warning("get_mcp_prompt failed for %s: %s", name, exc)
            return None

        return {
            "description": getattr(result, "description", "") or "",
            "messages": [
                {
                    "role": str(m.role),
                    "text": getattr(m.content, "text", "") or "",
                }
                for m in getattr(result, "messages", None) or []
            ],
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
