"""Unit tests for chat-service TraceIdMiddleware."""
from __future__ import annotations

import os
import re

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.middleware.trace_id import (  # noqa: E402
    TraceIdMiddleware,
    current_trace_id,
    trace_id_var,
)


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TraceIdMiddleware)

    @app.get("/ping")
    def ping():
        return {"trace_id": current_trace_id()}

    return app


def test_generates_id_when_header_absent():
    c = TestClient(_build_app())
    resp = c.get("/ping")
    assert resp.status_code == 200
    body_id = resp.json()["trace_id"]
    header_id = resp.headers["x-trace-id"]
    assert body_id == header_id
    # 32-char hex (uuid4().hex)
    assert re.fullmatch(r"[0-9a-f]{32}", body_id)


def test_adopts_incoming_id():
    c = TestClient(_build_app())
    resp = c.get("/ping", headers={"X-Trace-Id": "caller-xyz"})
    assert resp.headers["x-trace-id"] == "caller-xyz"
    assert resp.json()["trace_id"] == "caller-xyz"


def test_contextvar_isolated_between_requests():
    """Two sequential requests must see their own ids, not each other's."""
    c = TestClient(_build_app())
    r1 = c.get("/ping", headers={"X-Trace-Id": "first"})
    r2 = c.get("/ping", headers={"X-Trace-Id": "second"})
    assert r1.json()["trace_id"] == "first"
    assert r2.json()["trace_id"] == "second"


def test_current_trace_id_outside_request_returns_empty():
    # Fresh contextvar read with no middleware in the stack.
    assert trace_id_var.get() == ""


# ── K7e-R1: input sanitization ──────────────────────────────────────────


def test_oversize_incoming_id_is_replaced():
    """A 200-char id exceeds the 128-char cap → middleware regenerates."""
    c = TestClient(_build_app())
    huge = "a" * 200
    resp = c.get("/ping", headers={"X-Trace-Id": huge})
    got = resp.json()["trace_id"]
    assert got != huge
    assert re.fullmatch(r"[0-9a-f]{32}", got)


def test_invalid_charset_incoming_id_is_replaced():
    """Spaces/punctuation outside [A-Za-z0-9._-] → regenerated."""
    c = TestClient(_build_app())
    resp = c.get("/ping", headers={"X-Trace-Id": "has spaces!"})
    got = resp.json()["trace_id"]
    assert got != "has spaces!"
    assert re.fullmatch(r"[0-9a-f]{32}", got)


def test_max_length_id_is_kept():
    """Exactly 128 chars of valid charset is kept verbatim."""
    c = TestClient(_build_app())
    ok = "a" * 128
    resp = c.get("/ping", headers={"X-Trace-Id": ok})
    assert resp.json()["trace_id"] == ok
