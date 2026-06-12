import re

from app.logging_config import new_trace_id, trace_id_var

# K7e-R1: knowledge-service can be hit through the public gateway too
# (via /v1/knowledge/*), so the inbound X-Trace-Id is untrusted. Same
# cap + charset whitelist as chat-service. Invalid → regenerate
# (we never truncate attacker input).
_TRACE_ID_RE = re.compile(r"^[A-Za-z0-9._-]{1,128}$")


def _sanitize(incoming: str) -> str:
    return incoming if incoming and _TRACE_ID_RE.match(incoming) else new_trace_id()


class TraceIdMiddleware:
    """Pure ASGI middleware — compatible with streaming responses and contextvars.

    Sets the trace_id contextvar once per request. The asyncio task running
    the request owns the ContextVar, so no explicit reset is needed: when the
    task completes, the context dies with it. This avoids the
    BaseHTTPMiddleware contextvar-leak pitfall and makes the trace_id visible
    to uvicorn.access logs that fire after the response is written.
    """

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
