"""loreweave_llm.Client — thin async wrapper over the gateway's
`/v1/llm/stream` and `/internal/llm/stream` endpoints.

Phase 1b deliverable. `submit_job()` lives in this file too as a stub
returning NotImplementedError; it ships in Phase 2.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncIterator
from typing import Literal

import httpx

from loreweave_llm.errors import (
    LLMAuthFailed,
    LLMDecodeError,
    LLMError,
    LLMInvalidRequest,
    LLMModelNotFound,
    LLMQuotaExceeded,
    LLMRateLimited,
    LLMUpstreamError,
    from_code,
)
from loreweave_llm.models import (
    DoneEvent,
    ErrorEvent,
    StreamEvent,
    StreamRequest,
    TokenEvent,
    UsageEvent,
)

logger = logging.getLogger(__name__)

AuthMode = Literal["jwt", "internal"]

# Default per-event read timeout — only the IDLE wait for the next SSE
# frame, NOT a wall-clock cap on the whole stream. The whole-stream
# timeout is None (unbounded) by design (P1 — streaming chat must have
# no wall-clock timeout).
_DEFAULT_IDLE_READ_TIMEOUT_S = 120.0


class Client:
    """SDK client for the LoreWeave LLM gateway.

    Two flavors of auth:
    - `auth_mode="jwt"` — pass `bearer_token` (used by FE / api-gateway-bff)
    - `auth_mode="internal"` — pass `internal_token` AND `user_id` (svc→svc)

    Construct one Client per process (it owns an httpx.AsyncClient
    connection pool). Close via `await client.aclose()` on shutdown.
    """

    def __init__(
        self,
        *,
        base_url: str,
        auth_mode: AuthMode = "internal",
        bearer_token: str | None = None,
        internal_token: str | None = None,
        user_id: str | None = None,
        idle_read_timeout_s: float = _DEFAULT_IDLE_READ_TIMEOUT_S,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if auth_mode == "jwt" and not bearer_token:
            raise ValueError("auth_mode='jwt' requires bearer_token")
        if auth_mode == "internal" and not (internal_token and user_id):
            raise ValueError("auth_mode='internal' requires internal_token and user_id")

        self._base_url = base_url.rstrip("/")
        self._auth_mode = auth_mode
        self._bearer_token = bearer_token
        self._internal_token = internal_token
        self._user_id = user_id

        # Whole-stream timeout = None (unbounded). Connect timeout = 5s
        # (fail fast if gateway is unreachable). Per-read timeout =
        # idle_read_timeout_s (longest gap between SSE frames before we
        # treat the stream as stalled — typical providers send at least a
        # keep-alive comment every 30-60s).
        timeout = httpx.Timeout(None, connect=5.0, read=idle_read_timeout_s)
        self._http = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        if self._http.is_closed:
            return
        await self._http.aclose()

    # ── Streaming (P1) ────────────────────────────────────────────────

    async def stream(self, request: StreamRequest) -> AsyncIterator[StreamEvent]:
        """Open a streaming chat session.

        Yields canonical `StreamEvent` instances (TokenEvent / UsageEvent /
        DoneEvent). On `event: error` from the gateway, raises an
        `LLMError` subclass keyed by the error code.

        **No wall-clock timeout.** The iterator runs until the gateway
        emits `done`, errors, or the consumer cancels via the standard
        async-iter close protocol.

        Usage:
            async for ev in client.stream(StreamRequest(...)):
                if isinstance(ev, TokenEvent):
                    print(ev.delta, end="", flush=True)
                elif isinstance(ev, UsageEvent):
                    metrics.add(ev.input_tokens, ev.output_tokens)
                elif isinstance(ev, DoneEvent):
                    break
        """
        if self._auth_mode == "jwt":
            url = f"{self._base_url}/v1/llm/stream"
            headers = {"Authorization": f"Bearer {self._bearer_token}"}
            params: dict[str, str] = {}
        else:
            url = f"{self._base_url}/internal/llm/stream"
            headers = {"X-Internal-Token": self._internal_token or ""}
            params = {"user_id": self._user_id or ""}

        body = request.to_request_body()

        async with self._http.stream(
            "POST",
            url,
            params=params,
            headers={**headers, "Accept": "text/event-stream"},
            json=body,
        ) as resp:
            if resp.status_code >= 400:
                # HTTP-level error — read body, classify, raise.
                await self._raise_http_error(resp)
            async for ev in self._iter_sse_events(resp):
                if isinstance(ev, ErrorEvent):
                    # SSE-frame error — translate to exception so the
                    # consumer doesn't have to re-implement error handling.
                    raise from_code(ev.code, ev.message)
                yield ev
                if isinstance(ev, DoneEvent):
                    return

    # ── Async jobs (P2) — Phase 2 deliverable ─────────────────────────

    async def submit_job(self, *args, **kwargs):  # pragma: no cover
        raise NotImplementedError("submit_job() lands in Phase 2 of the refactor plan")

    # ── Internals ─────────────────────────────────────────────────────

    async def _iter_sse_events(self, resp: httpx.Response) -> AsyncIterator[StreamEvent]:
        """Parse the gateway's SSE wire format (`event: <name>\\ndata: <json>\\n\\n`)
        into typed StreamEvent instances."""
        current_event = ""
        async for line in resp.aiter_lines():
            if line == "":
                current_event = ""
                continue
            if line.startswith(":"):
                # SSE comment — keep-alive, ignore.
                continue
            if line.startswith("event:"):
                current_event = line[len("event:") :].strip()
                continue
            if line.startswith("data:"):
                data = line[len("data:") :].strip()
                if not data:
                    continue
                try:
                    parsed = json.loads(data)
                except json.JSONDecodeError as exc:
                    raise LLMDecodeError(
                        f"gateway emitted non-JSON SSE data: {exc}",
                    ) from exc

                # The gateway always includes "event" inside the data
                # payload (matches the discriminator). If a producer ever
                # forgets, fall back to the SSE event-name line.
                if "event" not in parsed and current_event:
                    parsed["event"] = current_event

                yield self._dispatch_event(parsed)

    @staticmethod
    def _dispatch_event(parsed: dict) -> StreamEvent:
        """Build a typed StreamEvent from a parsed JSON payload."""
        kind = parsed.get("event")
        if kind == "token":
            return TokenEvent.model_validate(parsed)
        if kind == "usage":
            return UsageEvent.model_validate(parsed)
        if kind == "done":
            return DoneEvent.model_validate(parsed)
        if kind == "error":
            return ErrorEvent.model_validate(parsed)
        raise LLMDecodeError(f"unknown SSE event kind: {kind!r}")

    async def _raise_http_error(self, resp: httpx.Response) -> None:
        # Body is already partially consumed if streaming response, but
        # a 4xx returned BEFORE the SSE prelude is buffered — we can read
        # it normally.
        body_bytes = await resp.aread()
        try:
            body_json = json.loads(body_bytes.decode("utf-8"))
            code = body_json.get("code", "LLM_ERROR")
            message = body_json.get("message", "")
            retry_after_s = body_json.get("retry_after_s")
        except (UnicodeDecodeError, json.JSONDecodeError):
            code = "LLM_ERROR"
            message = body_bytes.decode("utf-8", errors="replace")[:500]
            retry_after_s = None

        if resp.status_code == 401:
            raise LLMAuthFailed(message, code=code, status_code=resp.status_code)
        if resp.status_code == 402:
            raise LLMQuotaExceeded(message, code=code, status_code=resp.status_code)
        if resp.status_code == 404:
            raise LLMModelNotFound(message, code=code, status_code=resp.status_code)
        if resp.status_code == 429:
            raise LLMRateLimited(
                message, retry_after_s=retry_after_s, status_code=resp.status_code
            )
        if resp.status_code in (502, 503, 504):
            raise LLMUpstreamError(message, code=code, status_code=resp.status_code)
        if 400 <= resp.status_code < 500:
            raise LLMInvalidRequest(message, code=code, status_code=resp.status_code)
        raise LLMError(message, code=code, status_code=resp.status_code)
