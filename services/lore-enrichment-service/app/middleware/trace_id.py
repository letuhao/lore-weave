"""Per-request trace-id middleware (RAID C18) — mirrors knowledge-service.

Pure ASGI middleware (NOT BaseHTTPMiddleware) so it is compatible with
streaming responses and contextvars: the asyncio task running the request owns
the ``trace_id`` ContextVar, so no explicit reset is needed — when the task
ends the context dies with it. This makes the trace id visible to uvicorn.access
logs that fire after the response is written.

The inbound ``X-Trace-Id`` is UNTRUSTED (the service can be reached through the
gateway), so it is validated against a charset + length whitelist; an invalid
value is replaced with a fresh id (never truncated — we don't echo attacker
input). The id is echoed back on the response ``X-Trace-Id`` header.
"""

from __future__ import annotations

import re

from app.logging_config import new_trace_id, trace_id_var

# Same cap + charset whitelist as chat-service / knowledge-service.
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _sanitize(incoming: str) -> str:
    return incoming if incoming and _TRACE_ID_RE.match(incoming) else new_trace_id()


class TraceIdMiddleware:
    """Set the trace_id contextvar once per request + echo it on the response."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return

        incoming = ""
        for name, value in scope.get("headers", []):
            if name == b"x-trace-id":
                try:
                    incoming = value.decode("latin-1")
                except Exception:
                    incoming = ""
                break
        trace_id = _sanitize(incoming)
        trace_id_var.set(trace_id)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
