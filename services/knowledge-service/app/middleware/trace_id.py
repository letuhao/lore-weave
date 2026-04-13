from app.logging_config import new_trace_id, trace_id_var


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
        trace_id = incoming or new_trace_id()
        trace_id_var.set(trace_id)

        async def send_with_header(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-trace-id", trace_id.encode("latin-1")))
                message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_header)
