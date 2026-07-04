"""Tests for loreweave_internal_client (P3 SDK-first)."""
from __future__ import annotations

import httpx
import pytest

from loreweave_internal_client import (
    RETRYABLE_STATUSES,
    InternalClientError,
    build_internal_client,
    build_timeout,
    is_retryable_status,
    resolve_model_name,
)

# ── errors ────────────────────────────────────────────────────────────────


def test_is_retryable_status():
    assert RETRYABLE_STATUSES == {429, 502, 503}
    for code in (429, 502, 503):
        assert is_retryable_status(code)
    for code in (200, 400, 401, 403, 404, 409, 500, 501, None):
        assert not is_retryable_status(code)


def test_internal_client_error_derives_retryable():
    assert InternalClientError("x", status_code=503).retryable is True
    assert InternalClientError("x", status_code=404).retryable is False
    # A transport error (no status) is non-retryable by default…
    assert InternalClientError("x").retryable is False
    # …unless the raiser explicitly overrides (e.g. a connect timeout it deems retryable).
    assert InternalClientError("x", retryable=True).retryable is True
    assert InternalClientError("x", status_code=503, retryable=False).retryable is False


def test_build_timeout():
    t1 = build_timeout(5.0)
    assert t1.read == 5.0 and t1.connect == 5.0  # one bound for all phases
    t2 = build_timeout(30.0, connect_timeout_s=5.0)
    assert t2.read == 30.0 and t2.connect == 5.0  # split connect phase


# ── transport factory ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_build_internal_client_bakes_token_and_json():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200, json={"ok": True})

    client = build_internal_client(
        "http://svc:8000/", internal_token="itok", transport=httpx.MockTransport(handler)
    )
    async with client:
        r = await client.get("/internal/ping")
    assert r.status_code == 200
    assert seen["x-internal-token"] == "itok"
    assert seen["content-type"] == "application/json"
    # base_url trailing slash tolerated + joined
    assert "x-trace-id" not in seen  # no provider → no trace header


@pytest.mark.asyncio
async def test_build_default_transport_and_connect_split():
    # The PRODUCTION path — no transport override (transport=None default) — must
    # construct a valid client with the baked headers + a connect-split timeout.
    client = build_internal_client(
        "http://svc:8000", internal_token="itok", timeout_s=30.0, connect_timeout_s=5.0
    )
    async with client:
        assert client.headers["x-internal-token"] == "itok"
        assert client.headers["content-type"] == "application/json"
        assert str(client.base_url) == "http://svc:8000"
        assert client.timeout.read == 30.0 and client.timeout.connect == 5.0


@pytest.mark.asyncio
async def test_trace_id_injected_per_request_when_provider_set():
    captured: list[str | None] = []
    current = {"tid": "trace-abc"}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request.headers.get("x-trace-id"))
        return httpx.Response(200)

    client = build_internal_client(
        "http://svc:8000",
        internal_token="itok",
        trace_id_provider=lambda: current["tid"],
        transport=httpx.MockTransport(handler),
    )
    async with client:
        await client.get("/a")
        current["tid"] = "trace-def"  # a DIFFERENT trace on the next request…
        await client.get("/b")
        current["tid"] = None  # …and an absent trace → header omitted
        await client.get("/c")
    assert captured == ["trace-abc", "trace-def", None]


@pytest.mark.asyncio
async def test_extra_headers_baked():
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(request.headers)
        return httpx.Response(200)

    client = build_internal_client(
        "http://svc:8000",
        internal_token="itok",
        extra_headers={"X-Admin-Token": "adm"},
        transport=httpx.MockTransport(handler),
    )
    async with client:
        await client.get("/a")
    assert seen["x-admin-token"] == "adm"


# ── model-name resolver ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_resolve_model_name_none_on_missing_args():
    assert await resolve_model_name("http://pr:8000", None, "ref", internal_token="t") is None
    assert await resolve_model_name("http://pr:8000", "user_model", None, internal_token="t") is None


@pytest.mark.asyncio
async def test_resolve_model_name_happy_and_degrade(monkeypatch):
    calls: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["url"] = str(request.url)
        calls["token"] = request.headers.get("x-internal-token", "")
        if "good" in str(request.url):
            return httpx.Response(200, json={"provider_model_name": "  gpt-4o  "})
        if "blank" in str(request.url):
            return httpx.Response(200, json={"provider_model_name": ""})
        return httpx.Response(404, json={})

    # Patch the AsyncClient the resolver constructs so we can inject the mock transport.
    real_client = httpx.AsyncClient

    def _patched(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real_client(*args, **kwargs)

    monkeypatch.setattr("loreweave_internal_client._model_name.httpx.AsyncClient", _patched)

    # happy: trims whitespace
    assert await resolve_model_name("http://pr:8000", "user_model", "good", internal_token="tok") == "gpt-4o"
    assert calls["token"] == "tok"
    assert "/internal/models/user_model/good/info" in calls["url"]
    # blank name → None
    assert await resolve_model_name("http://pr:8000", "user_model", "blank", internal_token="tok") is None
    # non-200 → None (best-effort, never raises)
    assert await resolve_model_name("http://pr:8000", "user_model", "missing", internal_token="tok") is None
