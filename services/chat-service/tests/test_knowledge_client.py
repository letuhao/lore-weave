"""Unit tests for the knowledge-service HTTP client.

K5-I7 fix: tests inject an `httpx.MockTransport` into the client via the
new constructor `transport=` kwarg instead of monkey-patching
`httpx.AsyncClient`. This decouples tests from the module's import style
— a refactor from `import httpx` to `from httpx import AsyncClient`
would have silently broken every `@patch(...)` target before. Now the
tests don't reference any internal import path at all.

Every failure path must return a degraded KnowledgeContext
(mode='degraded'), never raise — chat must keep working when
knowledge-service is unavailable.
"""
from __future__ import annotations

import os
from typing import Callable

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.client.knowledge_client import (  # noqa: E402
    DEGRADED_RECENT_MESSAGE_COUNT,
    MESSAGE_MAX_CHARS,
    KnowledgeClient,
    close_knowledge_client,
    get_knowledge_client,
    init_knowledge_client,
)


# ── helpers ────────────────────────────────────────────────────────────────


def _make_client(
    handler: Callable[[httpx.Request], httpx.Response] | None = None,
) -> KnowledgeClient:
    """Build a KnowledgeClient with a MockTransport so tests don't touch
    the network. Pass `handler=None` for the rare test that just wants
    to inspect constructor kwargs without making a request."""
    transport = httpx.MockTransport(handler) if handler is not None else None
    return KnowledgeClient(
        base_url="http://knowledge-service:8092",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=1,
        transport=transport,
    )


def _ok_response(payload: dict) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    return handler


def _status_response(status: int, body: str = "") -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(status, text=body)

    return handler


def _raise(exc: Exception) -> Callable[[httpx.Request], httpx.Response]:
    def handler(_: httpx.Request) -> httpx.Response:
        raise exc

    return handler


def _capture(captured: list, status: int = 200, body: dict | None = None) -> Callable[[httpx.Request], httpx.Response]:
    body_obj = body or {"mode": "no_project", "context": "", "recent_message_count": 50, "token_count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(status, json=body_obj)

    return handler


# ── happy path ─────────────────────────────────────────────────────────────


class TestKnowledgeClientHappyPath:
    @pytest.mark.asyncio
    async def test_no_project_mode_response_parses(self):
        payload = {
            "mode": "no_project",
            "context": '<memory mode="no_project"><instructions>x</instructions></memory>',
            "recent_message_count": 50,
            "token_count": 12,
        }
        client = _make_client(_ok_response(payload))
        result = await client.build_context(user_id="u", message="hello")
        assert result.mode == "no_project"
        assert result.recent_message_count == 50
        assert result.token_count == 12
        assert "<memory" in result.context
        await client.aclose()

    @pytest.mark.asyncio
    async def test_static_mode_with_project(self):
        captured: list = []
        client = _make_client(_capture(
            captured,
            body={"mode": "static", "context": "<memory mode=\"static\">...</memory>", "recent_message_count": 50, "token_count": 200},
        ))
        result = await client.build_context(
            user_id="u",
            project_id="00000000-0000-0000-0000-000000000001",
            message="who is Alice?",
        )
        assert result.mode == "static"

        # Inspect the captured request body via the MockTransport
        assert len(captured) == 1
        import json as _json
        body = _json.loads(captured[0].content.decode())
        assert body["project_id"] == "00000000-0000-0000-0000-000000000001"
        assert body["message"] == "who is Alice?"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_k18_9_split_fields_parsed(self):
        """K18.9: `stable_context` + `volatile_context` come back as
        plain strings. chat-service needs both to emit cache_control.
        Test payload obeys the server-side invariant
        context == stable + volatile (byte-for-byte)."""
        stable = "<memory><project/>\n"
        volatile = "</memory>"
        payload = {
            "mode": "static",
            "context": stable + volatile,
            "recent_message_count": 50,
            "token_count": 10,
            "stable_context": stable,
            "volatile_context": volatile,
        }
        client = _make_client(_ok_response(payload))
        result = await client.build_context(user_id="u")
        assert result.stable_context == stable
        assert result.volatile_context == volatile
        assert result.context == result.stable_context + result.volatile_context
        await client.aclose()

    @pytest.mark.asyncio
    async def test_k18_9_split_fields_default_empty_for_older_server(self):
        """Backward compat: older knowledge-service omits stable/
        volatile; client defaults to '' so chat-service falls back to
        the concat path."""
        payload = {
            "mode": "no_project",
            "context": "<memory/>",
            "recent_message_count": 50,
            "token_count": 5,
            # no stable_context / volatile_context fields
        }
        client = _make_client(_ok_response(payload))
        result = await client.build_context(user_id="u")
        assert result.stable_context == ""
        assert result.volatile_context == ""
        await client.aclose()

    @pytest.mark.asyncio
    async def test_k18_9_degraded_has_empty_split_fields(self):
        """Graceful-degradation path must not carry stale split fields
        — otherwise chat-service could emit an Anthropic cache_control
        pointing at nothing."""
        client = _make_client(_raise(httpx.TimeoutException("boom")))
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        assert result.stable_context == ""
        assert result.volatile_context == ""
        await client.aclose()


# ── graceful degradation ───────────────────────────────────────────────────


class TestKnowledgeClientGracefulDegradation:
    @pytest.mark.asyncio
    async def test_timeout_returns_degraded(self):
        client = _make_client(_raise(httpx.TimeoutException("boom")))
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        assert result.context == ""
        assert result.recent_message_count == DEGRADED_RECENT_MESSAGE_COUNT
        await client.aclose()

    @pytest.mark.asyncio
    async def test_connection_error_returns_degraded(self):
        client = _make_client(_raise(httpx.ConnectError("refused")))
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_5xx_retries_then_returns_degraded(self):
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(503, text="down")

        client = _make_client(handler)
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        # retries=1 → 2 total attempts
        assert call_count == 2
        await client.aclose()

    @pytest.mark.asyncio
    async def test_404_no_retry_returns_degraded(self):
        """404 = project not found. Stable problem, don't retry."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(404, text='{"detail":"project not found"}')

        client = _make_client(handler)
        result = await client.build_context(
            user_id="u", project_id="00000000-0000-0000-0000-000000000001"
        )
        assert result.mode == "degraded"
        assert call_count == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_501_mode3_returns_degraded_at_debug(self):
        """501 = Mode 3 not implemented (Track 2). Expected, log at debug."""
        call_count = 0

        def handler(_: httpx.Request) -> httpx.Response:
            nonlocal call_count
            call_count += 1
            return httpx.Response(501, text='{"detail":"Mode 3 not implemented"}')

        client = _make_client(handler)
        result = await client.build_context(
            user_id="u", project_id="00000000-0000-0000-0000-000000000001"
        )
        assert result.mode == "degraded"
        assert call_count == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_malformed_json_returns_degraded(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(200, content=b"not json", headers={"content-type": "application/json"})

        client = _make_client(handler)
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_unexpected_shape_returns_degraded(self):
        client = _make_client(_ok_response({"not_what_we_expected": True}))
        # Pydantic model_validate fails on missing 'mode' field → degraded
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        await client.aclose()


# ── body normalisation (K5-I1 / K5-I2 regression coverage) ─────────────────


class TestKnowledgeClientBodyNormalisation:
    @pytest.mark.asyncio
    async def test_empty_project_id_omitted_from_body(self):
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", project_id="", message="hi")
        body = self._json_body(captured[0])
        assert "project_id" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_session_id_omitted_from_body(self):
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", session_id="", message="hi")
        body = self._json_body(captured[0])
        assert "session_id" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_none_project_id_omitted_from_body(self):
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", project_id=None, message="hi")
        body = self._json_body(captured[0])
        assert "project_id" not in body
        assert body["user_id"] == "u"
        assert body["message"] == "hi"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_long_message_truncated_to_max(self):
        captured: list = []
        client = _make_client(_capture(captured))
        long_message = "x" * (MESSAGE_MAX_CHARS + 500)
        await client.build_context(user_id="u", message=long_message)
        body = self._json_body(captured[0])
        assert len(body["message"]) == MESSAGE_MAX_CHARS
        await client.aclose()

    @pytest.mark.asyncio
    async def test_short_message_not_truncated(self):
        captured: list = []
        client = _make_client(_capture(captured))
        short = "tell me about Alice"
        await client.build_context(user_id="u", message=short)
        body = self._json_body(captured[0])
        assert body["message"] == short
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_message_stays_empty(self):
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u")
        body = self._json_body(captured[0])
        assert body["message"] == ""
        await client.aclose()

    @staticmethod
    def _json_body(request: httpx.Request) -> dict:
        import json as _json
        return _json.loads(request.content.decode())


# ── headers ────────────────────────────────────────────────────────────────


class TestKnowledgeClientHeaders:
    @pytest.mark.asyncio
    async def test_internal_token_baked_into_request(self):
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u")
        assert captured[0].headers.get("X-Internal-Token") == "unit-test-token"
        await client.aclose()


# ── singleton lifecycle (K4-I1 lesson) ─────────────────────────────────────


class TestSingletonLifecycle:
    @pytest.mark.asyncio
    async def test_init_is_idempotent(self):
        await close_knowledge_client()
        first = init_knowledge_client()
        second = init_knowledge_client()
        assert first is second
        await close_knowledge_client()

    @pytest.mark.asyncio
    async def test_get_initialises_lazily(self):
        await close_knowledge_client()
        client = get_knowledge_client()
        assert client is not None
        client2 = get_knowledge_client()
        assert client is client2
        await close_knowledge_client()


# ── log-once-per-failure (K4-I4 lesson) ────────────────────────────────────


class TestSingleLogPerFailure:
    @pytest.mark.asyncio
    async def test_5xx_logs_only_once(self, caplog):
        import logging

        client = _make_client(_status_response(503, "down"))
        with caplog.at_level(logging.WARNING, logger="app.client.knowledge_client"):
            await client.build_context(user_id="u")

        unavailable = [r for r in caplog.records if "unavailable" in r.getMessage()]
        assert len(unavailable) == 1
        await client.aclose()


# ── K7e trace_id forwarding ───────────────────────────────────────────────


class TestTraceIdForwarding:
    @pytest.mark.asyncio
    async def test_forwards_trace_id_when_set(self):
        from app.middleware.trace_id import trace_id_var

        captured: list = []
        client = _make_client(_capture(captured))
        token = trace_id_var.set("abc123")
        try:
            await client.build_context(user_id="u", message="hi")
        finally:
            trace_id_var.reset(token)
        assert captured[0].headers.get("x-trace-id") == "abc123"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_omits_trace_id_when_unset(self):
        from app.middleware.trace_id import trace_id_var

        captured: list = []
        client = _make_client(_capture(captured))
        # Make sure no prior test leaked a value into this task.
        token = trace_id_var.set("")
        try:
            await client.build_context(user_id="u", message="hi")
        finally:
            trace_id_var.reset(token)
        # Empty contextvar → no header. Knowledge-service will mint its own.
        assert "x-trace-id" not in captured[0].headers
        await client.aclose()

    @pytest.mark.asyncio
    async def test_trace_id_forwarded_on_retry(self):
        """The header must be attached to every attempt, not just the
        first — otherwise a retry after a 5xx would desynchronise
        chat's view of the id from knowledge-service's."""
        from app.middleware.trace_id import trace_id_var

        captured: list = []

        def handler(request: httpx.Request) -> httpx.Response:
            captured.append(request)
            if len(captured) == 1:
                return httpx.Response(503, text="down")
            return httpx.Response(200, json={
                "mode": "no_project", "context": "", "recent_message_count": 50, "token_count": 0,
            })

        client = _make_client(handler)
        token = trace_id_var.set("retry-id")
        try:
            await client.build_context(user_id="u", message="hi")
        finally:
            trace_id_var.reset(token)
        assert len(captured) == 2
        assert all(r.headers.get("x-trace-id") == "retry-id" for r in captured)
        await client.aclose()
