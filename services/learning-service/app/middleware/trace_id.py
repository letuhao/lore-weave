"""Trace-ID middleware + contextvar for learning-service.

Pure-ASGI clone of chat-service/knowledge-service trace_id middleware so the
service speaks the same X-Trace-Id protocol: adopt a sanitised inbound id or
mint a fresh 32-char hex one, store it in a per-task ContextVar, echo it on the
response. Not BaseHTTPMiddleware (which would leak the ContextVar across tasks).
"""

from __future__ import annotations

import re
import uuid
from contextvars import ContextVar

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

# Inbound X-Trace-Id is untrusted (reachable via the public gateway): cap
# length + restrict charset so a malicious id can't amplify log volume or be
# unsafe in downstream logs/filenames. Failures get a fresh id (no truncation).
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def new_trace_id() -> str:
    return uuid.uuid4().hex


def _sanitize(incoming: str) -> str:
    return incoming if incoming and _TRACE_ID_RE.match(incoming) else new_trace_id()


def current_trace_id() -> str:
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
