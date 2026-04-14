"""K7e: end-to-end trace_id tests for knowledge-service.

Covers the three new behaviours:

  1. GlossaryClient forwards the contextvar trace_id on outbound calls
     via an injected httpx.MockTransport (same pattern as chat-service's
     test_knowledge_client.py — avoids the truststore/SSL issue that
     breaks the respx-based tests in this environment).
  2. GlossaryClient omits the header when the contextvar is empty.
  3. The FastAPI 500-handler returns JSON with `trace_id` + echoes the
     X-Trace-Id header.
"""
from __future__ import annotations

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.clients.glossary_client import GlossaryClient
from app.logging_config import trace_id_var
from app.main import _trace_id_500_handler
from app.middleware.trace_id import TraceIdMiddleware


# ── GlossaryClient trace_id forwarding ──────────────────────────────────


def _capture_handler(captured: list) -> "callable":
    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(200, json={"entities": []})

    return handler


def _make_client(handler) -> GlossaryClient:
    # Skip __init__ so we never construct a "real" httpx.AsyncClient —
    # this env's SSL truststore setup explodes on AsyncClient() with
    # a stray quote in SSL_CERT_FILE. We manually wire only the fields
    # select_for_context touches, and inject a MockTransport-backed
    # client that has no SSL context at all.
    gc = object.__new__(GlossaryClient)
    gc._base_url = "http://glossary-service:8088"
    gc._retries = 0
    gc._cb_fail_count = 0
    gc._cb_opened_at = None
    gc._http = httpx.AsyncClient(
        timeout=httpx.Timeout(0.5),
        headers={"X-Internal-Token": "unit-test-token"},
        transport=httpx.MockTransport(handler),
        verify=False,
    )
    return gc


@pytest.mark.asyncio
async def test_glossary_client_forwards_trace_id():
    from uuid import uuid4

    captured: list = []
    gc = _make_client(_capture_handler(captured))
    token = trace_id_var.set("kc-forward")
    try:
        await gc.select_for_context(
            user_id=uuid4(), book_id=uuid4(), query="x"
        )
    finally:
        trace_id_var.reset(token)
        await gc.aclose()
    assert captured[0].headers.get("x-trace-id") == "kc-forward"


@pytest.mark.asyncio
async def test_glossary_client_omits_trace_id_when_unset():
    from uuid import uuid4

    captured: list = []
    gc = _make_client(_capture_handler(captured))
    token = trace_id_var.set("")
    try:
        await gc.select_for_context(
            user_id=uuid4(), book_id=uuid4(), query="x"
        )
    finally:
        trace_id_var.reset(token)
        await gc.aclose()
    assert "x-trace-id" not in captured[0].headers


# ── 500 envelope ────────────────────────────────────────────────────────


def _app_with_500_handler() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)
    app.add_exception_handler(Exception, _trace_id_500_handler)

    @app.get("/boom")
    def boom():
        raise RuntimeError("kaboom")

    @app.get("/http-error")
    def http_error():
        # HTTPException keeps FastAPI's own envelope — our handler
        # should NOT catch it.
        raise HTTPException(status_code=404, detail="not found")

    return app


def test_500_handler_includes_trace_id_in_body_and_header():
    c = TestClient(_app_with_500_handler(), raise_server_exceptions=False)
    resp = c.get("/boom", headers={"X-Trace-Id": "env-test"})
    assert resp.status_code == 500
    body = resp.json()
    assert body["trace_id"] == "env-test"
    assert "detail" in body
    assert resp.headers["x-trace-id"] == "env-test"


def test_500_handler_does_not_swallow_httpexception():
    c = TestClient(_app_with_500_handler())
    resp = c.get("/http-error", headers={"X-Trace-Id": "env-test"})
    assert resp.status_code == 404
    assert resp.json() == {"detail": "not found"}
    # Middleware still echoes the trace id for 4xx.
    assert resp.headers["x-trace-id"] == "env-test"


# ── K7e-R1: input sanitization ──────────────────────────────────────────


def _ping_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/ping")
    def ping():
        return {"trace_id": trace_id_var.get()}

    return app


def test_oversize_incoming_id_is_replaced():
    import re

    c = TestClient(_ping_app())
    huge = "x" * 200
    resp = c.get("/ping", headers={"X-Trace-Id": huge})
    got = resp.json()["trace_id"]
    assert got != huge
    assert re.fullmatch(r"[0-9a-f]{32}", got)


def test_invalid_charset_incoming_id_is_replaced():
    import re

    c = TestClient(_ping_app())
    resp = c.get("/ping", headers={"X-Trace-Id": "has spaces!"})
    got = resp.json()["trace_id"]
    assert got != "has spaces!"
    assert re.fullmatch(r"[0-9a-f]{32}", got)


def test_max_length_id_is_kept():
    c = TestClient(_ping_app())
    ok = "y" * 128
    resp = c.get("/ping", headers={"X-Trace-Id": ok})
    assert resp.json()["trace_id"] == ok
