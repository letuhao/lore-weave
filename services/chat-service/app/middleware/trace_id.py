"""Trace-ID middleware + contextvar for chat-service.

Mirrors the ASGI pattern in knowledge-service/app/middleware/trace_id.py
so both sides of the chat → knowledge hop speak the same protocol:

  - inbound X-Trace-Id is adopted as-is when present
  - otherwise a fresh 32-char hex id is generated
  - the id is stored in a ContextVar owned by the request's asyncio task
  - the same id is echoed back on the response
  - outbound httpx clients read the ContextVar and forward the header

Pure ASGI (not BaseHTTPMiddleware) so the ContextVar is set in the
same task that runs the endpoint and streaming responses. Using
BaseHTTPMiddleware would run the endpoint in a separate task and
leak the ContextVar across unrelated requests — the same pitfall
knowledge-service's middleware docstring warns about.

Chat-service does not currently ship a structured JSON logger, so
this module stays small and self-contained: just the ContextVar,
the id generator, and the ASGI middleware. A future logging overhaul
can pull the ContextVar without touching this file.
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# K7e-R1: chat-service is reachable through the public gateway, so the
# inbound X-Trace-Id is untrusted input. Cap length and restrict charset
# so a malicious or buggy client cannot amplify into multi-service log
# volume by sending a 10KB id, and so the id stays safe to embed in
# structured logs / filenames / dashboards downstream. Anything that
# fails the check is replaced by a freshly generated id (we do NOT
# truncate attacker input — that would still propagate prefix bytes).
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _sanitize(incoming: str) -> str:
    return incoming if incoming and _TRACE_ID_RE.match(incoming) else new_trace_id()


def current_trace_id() -> str:
    """Read the trace id for the in-flight request.

    Returns "" when called outside a request (e.g. background tasks
    that started before any inbound request set the ContextVar). The
    KnowledgeClient treats "" as "no header to forward".
    """
    return trace_id_var.get()


class TraceIdMiddleware:
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
