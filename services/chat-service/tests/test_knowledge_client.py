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

import json
import os
from typing import Callable
from unittest.mock import AsyncMock, MagicMock, patch

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
    tool_timeout_s: float = 30.0,
) -> KnowledgeClient:
    """Build a KnowledgeClient with a MockTransport so tests don't touch
    the network. Pass `handler=None` for the rare test that just wants
    to inspect constructor kwargs without making a request.

    `tool_timeout_s` is exposed so the D-K21B-06 timeout-split regression
    tests can pass a non-default value and prove the override took."""
    transport = httpx.MockTransport(handler) if handler is not None else None
    return KnowledgeClient(
        base_url="http://knowledge-service:8092",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=1,
        tool_timeout_s=tool_timeout_s,
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
    async def test_current_chapter_id_forwarded_when_present(self):
        """M1b: an editor turn's open chapter rides the body for the
        working-scope boost."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(
            user_id="u", message="hi",
            current_chapter_id="00000000-0000-0000-0000-0000000000ab",
        )
        body = self._json_body(captured[0])
        assert body["current_chapter_id"] == "00000000-0000-0000-0000-0000000000ab"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_current_chapter_id_omitted_when_absent(self):
        """Non-editor turns (no chapter) never send the field → older
        knowledge-service byte-identical, and no empty-string 422."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", message="hi", current_chapter_id=None)
        body = self._json_body(captured[0])
        assert "current_chapter_id" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_context_length_forwarded_when_present(self):
        """Model-context-aware Mode-3 budget scaling: the session model's real
        resolved window rides the body so knowledge-service can scale its flat
        mode3_token_budget instead of every model getting the same cap."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", message="hi", context_length=1_000_000)
        body = self._json_body(captured[0])
        assert body["context_length"] == 1_000_000
        await client.aclose()

    @pytest.mark.asyncio
    async def test_context_length_omitted_when_absent(self):
        """Unknown window → never sent → older/current knowledge-service keeps
        its flat default (byte-identical)."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", message="hi", context_length=None)
        body = self._json_body(captured[0])
        assert "context_length" not in body
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

    @pytest.mark.asyncio
    async def test_project_ids_forwarded_to_body(self):
        """Track B B1(2): a non-empty project_ids set is forwarded verbatim so
        knowledge-service's builder routes to the multi-KG union."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(
            user_id="u", project_ids=["p1", "p2"], message="hi",
        )
        body = self._json_body(captured[0])
        assert body["project_ids"] == ["p1", "p2"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_project_ids_omitted_from_body(self):
        """An empty/None set is omitted — only the single-project / no-project
        path applies then."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", project_ids=[], message="hi")
        body = self._json_body(captured[0])
        assert "project_ids" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_grounding_true_omits_field_backcompat(self):
        """T5: grounding=True (default) omits the field so an older knowledge-service
        without the `grounding` param is byte-identical to before."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", message="hi")  # default grounding=True
        body = self._json_body(captured[0])
        assert "grounding" not in body
        await client.aclose()

    @pytest.mark.asyncio
    async def test_grounding_false_forwarded_to_body(self):
        """T5: the intent gate's gate-OUT decision is forwarded so the builder serves
        the light static path (skips the expensive retrieval)."""
        captured: list = []
        client = _make_client(_capture(captured))
        await client.build_context(user_id="u", message="give me a plan", grounding=False)
        body = self._json_body(captured[0])
        assert body["grounding"] is False
        await client.aclose()

    @staticmethod
    def _json_body(request: httpx.Request) -> dict:
        import json as _json
        return _json.loads(request.content.decode())


# ── headers ────────────────────────────────────────────────────────────────


class TestResolveBookId:
    """T5 (audit) — project→book_id resolution for the entity-presence gate."""

    @pytest.mark.asyncio
    async def test_resolves_and_caches(self):
        calls = {"n": 0}

        def handler(req: httpx.Request) -> httpx.Response:
            calls["n"] += 1
            assert "/internal/context/project-book/" in str(req.url)
            assert "user_id=u1" in str(req.url)
            return httpx.Response(200, json={"book_id": "book-123"})

        client = _make_client(handler)
        try:
            a = await client.resolve_book_id(user_id="u1", project_id="proj-9")
            b = await client.resolve_book_id(user_id="u1", project_id="proj-9")
        finally:
            await client.aclose()
        assert a == "book-123" and b == "book-123"
        assert calls["n"] == 1  # second call served from cache

    @pytest.mark.asyncio
    async def test_no_book_returns_none_cached(self):
        client = _make_client(_ok_response({"book_id": None}))
        try:
            assert await client.resolve_book_id(user_id="u", project_id="p") is None
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_failure_returns_none_not_cached(self):
        state = {"fail": True}

        def handler(_: httpx.Request) -> httpx.Response:
            if state["fail"]:
                return httpx.Response(500, text="boom")
            return httpx.Response(200, json={"book_id": "b"})

        client = _make_client(handler)
        try:
            assert await client.resolve_book_id(user_id="u", project_id="p") is None
            state["fail"] = False
            assert await client.resolve_book_id(user_id="u", project_id="p") == "b"  # retried
        finally:
            await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_project_id_returns_none(self):
        client = _make_client(_ok_response({"book_id": "b"}))
        try:
            assert await client.resolve_book_id(user_id="u", project_id="") is None
        finally:
            await client.aclose()


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


# ── P6 grounding port: gateway-first + retained knowledge fallback (H2) ──────


def _make_dual_client(handler: Callable[[httpx.Request], httpx.Response]) -> KnowledgeClient:
    """A client whose grounding gateway (tools_base_url) differs from knowledge
    (base_url) so the gateway-first → knowledge-fallback path is exercised."""
    return KnowledgeClient(
        base_url="http://knowledge-service:8092",
        tools_base_url="http://ai-gateway:8210",
        internal_token="t",
        timeout_s=0.5,
        retries=1,
        tool_timeout_s=30.0,
        transport=httpx.MockTransport(handler),
    )


class TestGroundingGatewayFallback:
    @pytest.mark.asyncio
    async def test_gateway_success_does_not_call_knowledge(self):
        calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(str(req.url))
            return httpx.Response(200, json={"mode": "static", "context": "GW", "recent_message_count": 50, "token_count": 1})

        client = _make_dual_client(handler)
        result = await client.build_context(user_id="u")
        assert result.context == "GW"
        assert all("ai-gateway" in u for u in calls)
        assert not any("knowledge-service" in u for u in calls)
        await client.aclose()

    @pytest.mark.asyncio
    async def test_gateway_outage_falls_back_to_knowledge_direct(self):
        def handler(req: httpx.Request) -> httpx.Response:
            if "ai-gateway" in str(req.url):
                return httpx.Response(502, text="gateway grounding upstream unavailable")  # outage
            return httpx.Response(200, json={"mode": "static", "context": "KN", "recent_message_count": 50, "token_count": 1})

        client = _make_dual_client(handler)
        result = await client.build_context(user_id="u")
        assert result.context == "KN"  # H2: degraded context via the retained direct path, not a broken turn
        await client.aclose()

    @pytest.mark.asyncio
    async def test_gateway_stable_404_degrades_without_fallback(self):
        calls: list[str] = []

        def handler(req: httpx.Request) -> httpx.Response:
            calls.append(str(req.url))
            if "ai-gateway" in str(req.url):
                return httpx.Response(404, text="project not found")  # stable signal
            return httpx.Response(200, json={"mode": "static", "context": "KN", "recent_message_count": 50, "token_count": 1})

        client = _make_dual_client(handler)
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"  # no context, but no pointless fallback
        assert not any("knowledge-service" in u for u in calls)  # knowledge-direct NOT called
        await client.aclose()

    @pytest.mark.asyncio
    async def test_gateway_auth_reject_falls_back_to_knowledge_direct(self):
        # A gateway token misconfig (401) is a host-access problem, not a stable
        # request problem — the direct path uses the same token and is accepted.
        def handler(req: httpx.Request) -> httpx.Response:
            if "ai-gateway" in str(req.url):
                return httpx.Response(401, text="invalid internal token")
            return httpx.Response(200, json={"mode": "static", "context": "KN", "recent_message_count": 50, "token_count": 1})

        client = _make_dual_client(handler)
        result = await client.build_context(user_id="u")
        assert result.context == "KN"  # recovered via the retained direct fallback
        await client.aclose()

    @pytest.mark.asyncio
    async def test_both_unreachable_degrades(self):
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(503, text="down")

        client = _make_dual_client(handler)
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"  # turn proceeds context-free, never errors
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# K21-B — execute_tool (POST /internal/tools/execute)
# ════════════════════════════════════════════════════════════════════════════
#
# execute_tool returns the {success, result, error} envelope. On any
# transport failure or non-200 it synthesises a success=False envelope so
# the tool-calling loop can carry on — it must NEVER raise.


class TestToolTimeoutScope:
    @pytest.mark.asyncio
    async def test_build_context_keeps_the_short_timeout(self):
        """D-K21B-06 companion — the longer tool timeout is scoped to
        execute_tool ONLY. build_context stays on the 0.5s client
        budget, so the chat hot path is not slowed by the tool fix."""
        captured: list = []
        client = _make_client(_capture(captured), tool_timeout_s=17.0)
        await client.build_context(user_id="u", message="hi")
        assert captured[0].extensions["timeout"]["read"] == 0.5
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# get_tool_definitions — MCP list-tools against the ai-gateway (P0)
# ════════════════════════════════════════════════════════════════════════════
#
# Fetches the federated catalog via MCP `list-tools` and converts each entry to
# an OpenAI function schema. Process-cached after the first success; a failure
# returns [] and is NOT cached — a later turn retries. The transport +
# ClientSession are module-level symbols in app.client.knowledge_client, so we
# patch them there (patch-where-it-is-used).


def _mcp_tool(name: str, description: str = "", input_schema: dict | None = None) -> MagicMock:
    t = MagicMock()
    t.name = name
    t.description = description
    t.inputSchema = input_schema if input_schema is not None else {"type": "object"}
    return t


def _patch_list_tools(*, tools=None, list_side_effect=None, transport_side_effect=None):
    """Wire the async-with transport + ClientSession chain so that

      async with streamablehttp_client(...) as (read, write, _):
          async with ClientSession(read, write) as s:
              await s.initialize()
              listed = await s.list_tools()

    runs against mocks. Returns (transport_patch, session_patch, transport_factory)."""
    transport_cm = MagicMock()
    if transport_side_effect is not None:
        transport_cm.__aenter__ = AsyncMock(side_effect=transport_side_effect)
    else:
        transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), None))
    transport_cm.__aexit__ = AsyncMock(return_value=False)
    transport_factory = MagicMock(return_value=transport_cm)

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    listed = MagicMock()
    listed.tools = tools if tools is not None else []
    if list_side_effect is not None:
        mock_session.list_tools = AsyncMock(side_effect=list_side_effect)
    else:
        mock_session.list_tools = AsyncMock(return_value=listed)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_cm)

    return (
        patch("app.client.knowledge_client.streamablehttp_client", transport_factory),
        patch("app.client.knowledge_client.ClientSession", session_factory),
        transport_factory,
    )


class TestGetToolDefinitions:
    @pytest.mark.asyncio
    async def test_success_converts_mcp_tools_to_openai_shape(self):
        schema = {"type": "object", "properties": {"query": {"type": "string"}}}
        tpatch, spatch, _ = _patch_list_tools(tools=[
            _mcp_tool("memory_search", "search memory", schema),
            _mcp_tool("memory_forget", "forget a fact"),
        ])
        client = _make_client()
        with tpatch, spatch:
            out = await client.get_tool_definitions()
        assert out == [
            {"type": "function", "function": {
                "name": "memory_search", "description": "search memory", "parameters": schema}},
            {"type": "function", "function": {
                "name": "memory_forget", "description": "forget a fact",
                # An empty-input tool MUST advertise properties:{} — OpenAI-compatible
                # providers (LM Studio) 400 the whole request on a missing `properties`
                # (live-smoke bug: glossary_list_system_standards had no properties).
                "parameters": {"type": "object", "properties": {}}}},
        ]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_caches_no_refetch_on_second_call(self):
        tpatch, spatch, factory = _patch_list_tools(tools=[_mcp_tool("memory_search")])
        client = _make_client()
        with tpatch, spatch:
            first = await client.get_tool_definitions()
            second = await client.get_tool_definitions()
        assert first == second
        assert first[0]["function"]["name"] == "memory_search"
        # Cached — the MCP transport was opened exactly once.
        assert factory.call_count == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_returns_empty_and_does_not_cache(self):
        # First call: connect fails → []. Second call (success) proves no caching of the failure.
        client = _make_client()
        tpatch, spatch, _ = _patch_list_tools(
            transport_side_effect=httpx.ConnectError("refused")
        )
        with tpatch, spatch:
            assert await client.get_tool_definitions() == []
        tpatch2, spatch2, _ = _patch_list_tools(tools=[_mcp_tool("memory_search")])
        with tpatch2, spatch2:
            second = await client.get_tool_definitions()
        assert second[0]["function"]["name"] == "memory_search"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_list_tools_error_returns_empty_and_does_not_cache(self):
        client = _make_client()
        tpatch, spatch, _ = _patch_list_tools(
            list_side_effect=RuntimeError("protocol boom")
        )
        with tpatch, spatch:
            assert await client.get_tool_definitions() == []
        tpatch2, spatch2, _ = _patch_list_tools(tools=[_mcp_tool("memory_search")])
        with tpatch2, spatch2:
            assert await client.get_tool_definitions() != []
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_list_is_cached(self):
        """An empty catalog is a valid success and gets cached — a process with
        no tools shouldn't re-list every turn."""
        tpatch, spatch, factory = _patch_list_tools(tools=[])
        client = _make_client()
        with tpatch, spatch:
            assert await client.get_tool_definitions() == []
            assert await client.get_tool_definitions() == []
        assert factory.call_count == 1
        await client.aclose()

    @pytest.mark.asyncio
    async def test_user_id_sends_x_user_id_header(self):
        # REG-P2-03 — the per-user overlay only federates when the gateway sees
        # X-User-Id. Passing user_id MUST put it on the wire; omitting it must NOT
        # (base inspection paths get the overlay-free catalog).
        client = _make_client()
        tpatch, spatch, factory = _patch_list_tools(tools=[_mcp_tool("u_aaa_x")])
        with tpatch, spatch:
            await client.get_tool_definitions(user_id="user-123")
        assert factory.call_args.kwargs["headers"]["X-User-Id"] == "user-123"
        tp2, sp2, f2 = _patch_list_tools(tools=[_mcp_tool("base")])
        with tp2, sp2:
            await client.get_tool_definitions()  # no user
        assert "X-User-Id" not in f2.call_args.kwargs["headers"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_per_user_cache_is_isolated(self):
        # Two users must NOT share a catalog cache entry (else A's overlay leaks to
        # B). And a repeat call for the same user is served from that user's cache.
        client = _make_client()
        t1, s1, _ = _patch_list_tools(tools=[_mcp_tool("u_aaa_toolA")])
        with t1, s1:
            a = await client.get_tool_definitions(user_id="u1")
        t2, s2, _ = _patch_list_tools(tools=[_mcp_tool("u_bbb_toolB")])
        with t2, s2:
            b = await client.get_tool_definitions(user_id="u2")
        assert a[0]["function"]["name"] == "u_aaa_toolA"
        assert b[0]["function"]["name"] == "u_bbb_toolB"  # u2 NOT served u1's cache
        # u1 again, within TTL → served from u1's cache, NOT re-fetched (would be toolC)
        t3, s3, f3 = _patch_list_tools(tools=[_mcp_tool("u_ccc_toolC")])
        with t3, s3:
            a2 = await client.get_tool_definitions(user_id="u1")
        assert a2[0]["function"]["name"] == "u_aaa_toolA"
        assert f3.call_count == 0  # cache hit — no transport opened
        await client.aclose()

    @pytest.mark.asyncio
    async def test_targets_gateway_mcp_url_with_internal_token(self):
        """The MCP transport opens the ai-gateway /mcp URL with the service token."""
        tpatch, spatch, factory = _patch_list_tools(tools=[])
        client = _make_client()
        with tpatch, spatch:
            await client.get_tool_definitions()
        # default tools_base_url == base_url in tests (no gateway URL passed)
        assert factory.call_args.args[0] == "http://knowledge-service:8092/mcp"
        assert factory.call_args.kwargs["headers"]["X-Internal-Token"] == "unit-test-token"
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# Wave C5 — MCP resources + prompts (federated via ai-gateway)
# ════════════════════════════════════════════════════════════════════════════
#
# Same degrade contract as get_tool_definitions / mcp_execute_tool: every
# failure path returns []/None, never raises into the turn. The transport +
# ClientSession are the same module-level symbols, patched where they are used.


def _patch_mcp_session(session_methods: dict, *, transport_side_effect=None):
    """Generalisation of _patch_list_tools for the Wave C5 methods: wires the
    async-with transport + ClientSession chain against a mock session whose
    methods come from `session_methods` (name → AsyncMock/return value).
    Returns (transport_patch, session_patch, transport_factory, mock_session)."""
    transport_cm = MagicMock()
    if transport_side_effect is not None:
        transport_cm.__aenter__ = AsyncMock(side_effect=transport_side_effect)
    else:
        transport_cm.__aenter__ = AsyncMock(return_value=(MagicMock(), MagicMock(), None))
    transport_cm.__aexit__ = AsyncMock(return_value=False)
    transport_factory = MagicMock(return_value=transport_cm)

    mock_session = AsyncMock()
    mock_session.initialize = AsyncMock()
    for method, value in session_methods.items():
        setattr(mock_session, method, value)
    session_cm = MagicMock()
    session_cm.__aenter__ = AsyncMock(return_value=mock_session)
    session_cm.__aexit__ = AsyncMock(return_value=False)
    session_factory = MagicMock(return_value=session_cm)

    return (
        patch("app.client.knowledge_client.streamablehttp_client", transport_factory),
        patch("app.client.knowledge_client.ClientSession", session_factory),
        transport_factory,
        mock_session,
    )


def _mcp_resource(uri: str, name: str = "", description: str = "", mime: str = "text/plain"):
    r = MagicMock()
    r.uri = uri
    r.name = name
    r.description = description
    r.mimeType = mime
    return r


def _mcp_template(uri_template: str, name: str = "", mime: str = "text/plain"):
    t = MagicMock()
    t.uriTemplate = uri_template
    t.name = name
    t.description = ""
    t.mimeType = mime
    return t


def _mcp_prompt(name: str, description: str = "", args: list | None = None):
    p = MagicMock()
    p.name = name
    p.description = description
    p.arguments = args or []
    return p


class TestListMcpResources:
    @pytest.mark.asyncio
    async def test_merges_concrete_resources_and_templates(self):
        listed = MagicMock()
        listed.resources = [_mcp_resource("knowledge://static", "static", "a static one")]
        templates = MagicMock()
        templates.resourceTemplates = [
            _mcp_template(
                "knowledge://project/{project_id}/summary", "project_summary", "text/plain",
            ),
        ]
        tpatch, spatch, _, _ = _patch_mcp_session({
            "list_resources": AsyncMock(return_value=listed),
            "list_resource_templates": AsyncMock(return_value=templates),
        })
        client = _make_client()
        with tpatch, spatch:
            out = await client.list_mcp_resources()
        assert out == [
            {"uri": "knowledge://static", "name": "static",
             "description": "a static one", "mime_type": "text/plain"},
            {"uri_template": "knowledge://project/{project_id}/summary",
             "name": "project_summary", "description": "", "mime_type": "text/plain"},
        ]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_returns_empty(self):
        tpatch, spatch, _, _ = _patch_mcp_session(
            {}, transport_side_effect=httpx.ConnectError("refused"),
        )
        client = _make_client()
        with tpatch, spatch:
            assert await client.list_mcp_resources() == []
        await client.aclose()

    @pytest.mark.asyncio
    async def test_templates_failure_still_returns_concrete_list(self):
        """A gateway that lists concrete resources but errors the templates
        sub-list still contributes the concrete entries (partial tolerance)."""
        listed = MagicMock()
        listed.resources = [_mcp_resource("knowledge://static")]
        tpatch, spatch, _, _ = _patch_mcp_session({
            "list_resources": AsyncMock(return_value=listed),
            "list_resource_templates": AsyncMock(side_effect=RuntimeError("no templates")),
        })
        client = _make_client()
        with tpatch, spatch:
            out = await client.list_mcp_resources()
        assert [e["uri"] for e in out] == ["knowledge://static"]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_targets_gateway_mcp_url_with_internal_token(self):
        listed = MagicMock()
        listed.resources = []
        templates = MagicMock()
        templates.resourceTemplates = []
        tpatch, spatch, factory, _ = _patch_mcp_session({
            "list_resources": AsyncMock(return_value=listed),
            "list_resource_templates": AsyncMock(return_value=templates),
        })
        client = _make_client()
        with tpatch, spatch:
            await client.list_mcp_resources()
        assert factory.call_args.args[0] == "http://knowledge-service:8092/mcp"
        assert factory.call_args.kwargs["headers"]["X-Internal-Token"] == "unit-test-token"
        await client.aclose()


class TestReadMcpResource:
    _URI = "knowledge://project/p-1/summary"

    @pytest.mark.asyncio
    async def test_success_maps_first_text_contents(self):
        content = MagicMock()
        content.uri = self._URI
        content.mimeType = "text/plain"
        content.text = "the story so far"
        result = MagicMock()
        result.contents = [content]
        tpatch, spatch, factory, session = _patch_mcp_session({
            "read_resource": AsyncMock(return_value=result),
        })
        client = _make_client()
        with tpatch, spatch:
            out = await client.read_mcp_resource(
                self._URI, user_id="u-1", session_id="s-1", project_id="p-1",
            )
        assert out == {"uri": self._URI, "mime_type": "text/plain", "text": "the story so far"}
        session.read_resource.assert_awaited_once_with(self._URI)
        # D3 — identity rides the envelope headers, never a tool/LLM arg.
        headers = factory.call_args.kwargs["headers"]
        assert headers["X-User-Id"] == "u-1"
        assert headers["X-Session-Id"] == "s-1"
        assert headers["X-Project-Id"] == "p-1"
        await client.aclose()

    @pytest.mark.asyncio
    async def test_transport_error_returns_none(self):
        tpatch, spatch, _, _ = _patch_mcp_session(
            {}, transport_side_effect=httpx.ConnectError("refused"),
        )
        client = _make_client()
        with tpatch, spatch:
            assert await client.read_mcp_resource(
                self._URI, user_id="u-1", session_id="s-1",
            ) is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_read_error_returns_none(self):
        """A downstream tenancy rejection (e.g. 'project not found') surfaces
        as an McpError from read_resource — degraded to None, never a raise."""
        tpatch, spatch, _, _ = _patch_mcp_session({
            "read_resource": AsyncMock(side_effect=RuntimeError("project not found")),
        })
        client = _make_client()
        with tpatch, spatch:
            assert await client.read_mcp_resource(
                self._URI, user_id="u-1", session_id="s-1",
            ) is None
        await client.aclose()

    @pytest.mark.asyncio
    async def test_empty_or_textless_contents_returns_none(self):
        empty = MagicMock()
        empty.contents = []
        tpatch, spatch, _, _ = _patch_mcp_session({
            "read_resource": AsyncMock(return_value=empty),
        })
        client = _make_client()
        with tpatch, spatch:
            assert await client.read_mcp_resource(
                self._URI, user_id="u-1", session_id="s-1",
            ) is None
        # A blob-only (no .text) contents item degrades the same way.
        blob = MagicMock(spec=[])  # no attributes at all → getattr(..., 'text', None) is None
        blob_result = MagicMock()
        blob_result.contents = [blob]
        tpatch2, spatch2, _, _ = _patch_mcp_session({
            "read_resource": AsyncMock(return_value=blob_result),
        })
        with tpatch2, spatch2:
            assert await client.read_mcp_resource(
                self._URI, user_id="u-1", session_id="s-1",
            ) is None
        await client.aclose()


class TestListMcpPrompts:
    @pytest.mark.asyncio
    async def test_success_maps_prompts_with_arguments(self):
        arg = MagicMock()
        arg.name = "project_id"
        arg.description = "the project"
        arg.required = True
        listed = MagicMock()
        listed.prompts = [_mcp_prompt("recap_story_so_far", "recap it", [arg])]
        tpatch, spatch, _, _ = _patch_mcp_session({
            "list_prompts": AsyncMock(return_value=listed),
        })
        client = _make_client()
        with tpatch, spatch:
            out = await client.list_mcp_prompts()
        assert out == [{
            "name": "recap_story_so_far",
            "description": "recap it",
            "arguments": [
                {"name": "project_id", "description": "the project", "required": True},
            ],
        }]
        await client.aclose()

    @pytest.mark.asyncio
    async def test_failure_returns_empty(self):
        tpatch, spatch, _, _ = _patch_mcp_session({
            "list_prompts": AsyncMock(side_effect=RuntimeError("boom")),
        })
        client = _make_client()
        with tpatch, spatch:
            assert await client.list_mcp_prompts() == []
        await client.aclose()


class TestGetMcpPrompt:
    @pytest.mark.asyncio
    async def test_success_maps_description_and_messages(self):
        msg = MagicMock()
        msg.role = "user"
        msg.content = MagicMock()
        msg.content.text = "Recap the story so far…"
        result = MagicMock()
        result.description = "recap"
        result.messages = [msg]
        tpatch, spatch, _, session = _patch_mcp_session({
            "get_prompt": AsyncMock(return_value=result),
        })
        client = _make_client()
        with tpatch, spatch:
            out = await client.get_mcp_prompt(
                "recap_story_so_far", {"project_id": "p-1"},
            )
        assert out == {
            "description": "recap",
            "messages": [{"role": "user", "text": "Recap the story so far…"}],
        }
        session.get_prompt.assert_awaited_once_with(
            "recap_story_so_far", {"project_id": "p-1"},
        )
        await client.aclose()

    @pytest.mark.asyncio
    async def test_failure_returns_none(self):
        tpatch, spatch, _, _ = _patch_mcp_session({
            "get_prompt": AsyncMock(side_effect=RuntimeError("unknown prompt")),
        })
        client = _make_client()
        with tpatch, spatch:
            assert await client.get_mcp_prompt("nope", {}) is None
        await client.aclose()


# ════════════════════════════════════════════════════════════════════════════
# K21-B — KnowledgeContext.tool_calling_enabled default (D9)
# ════════════════════════════════════════════════════════════════════════════


class TestToolCallingEnabledField:
    @pytest.mark.asyncio
    async def test_defaults_true_when_field_absent(self):
        """An older knowledge-service that omits tool_calling_enabled →
        the field defaults True so tool-calling stays enabled (the
        extra='ignore' + default-True design)."""
        payload = {
            "mode": "static",
            "context": "<memory/>",
            "recent_message_count": 50,
            "token_count": 0,
            # no tool_calling_enabled field
        }
        client = _make_client(_ok_response(payload))
        result = await client.build_context(user_id="u")
        assert result.tool_calling_enabled is True
        await client.aclose()

    @pytest.mark.asyncio
    async def test_false_when_project_opted_out(self):
        """When knowledge-service reports the project opted out, the
        field round-trips as False."""
        payload = {
            "mode": "static",
            "context": "<memory/>",
            "recent_message_count": 50,
            "token_count": 0,
            "tool_calling_enabled": False,
        }
        client = _make_client(_ok_response(payload))
        result = await client.build_context(user_id="u")
        assert result.tool_calling_enabled is False
        await client.aclose()

    @pytest.mark.asyncio
    async def test_true_round_trips_explicitly(self):
        payload = {
            "mode": "no_project",
            "context": "",
            "recent_message_count": 50,
            "token_count": 0,
            "tool_calling_enabled": True,
        }
        client = _make_client(_ok_response(payload))
        result = await client.build_context(user_id="u")
        assert result.tool_calling_enabled is True
        await client.aclose()

    @pytest.mark.asyncio
    async def test_degraded_context_leaves_tool_calling_enabled(self):
        """The client-side degraded fallback must leave tool_calling
        enabled (default True) — a knowledge-service outage shouldn't
        silently disable tools; get_tool_definitions then degrades the
        turn tool-free on its own if the schema fetch also fails."""
        client = _make_client(_raise(httpx.TimeoutException("boom")))
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        assert result.tool_calling_enabled is True
        await client.aclose()


# ── M4: init_working_memory (goal-authority write path, best-effort) ──────────


@pytest.mark.asyncio
async def test_init_working_memory_posts_charter():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["token"] = req.headers.get("X-Internal-Token")
        captured["body"] = json.loads(req.content)
        return httpx.Response(204)

    client = _make_client(handler)
    ok = await client.init_working_memory(
        session_id="s-1", user_id="u-1",
        charter={"goal": "g", "phases": ["warmup"], "checklist": [], "language": "vi"},
    )
    assert ok is True
    assert captured["url"].endswith("/internal/working-memory/init")
    assert captured["token"] == "unit-test-token"
    assert captured["body"]["charter"]["goal"] == "g"
    assert captured["body"]["session_id"] == "s-1"


@pytest.mark.asyncio
async def test_init_working_memory_swallows_failure():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    client = _make_client(handler)
    # Best-effort: a knowledge outage must not raise — the session anchors from
    # its own seed (EC-4).
    ok = await client.init_working_memory(
        session_id="s", user_id="u", charter={"goal": "g", "phases": ["x"], "language": "en"},
    )
    assert ok is False


@pytest.mark.asyncio
async def test_tick_working_memory_posts_turns_and_returns_status():
    captured = {}

    def handler(req: httpx.Request) -> httpx.Response:
        captured["url"] = str(req.url)
        captured["body"] = json.loads(req.content)
        return httpx.Response(200, json={"status": "updated"})

    client = _make_client(handler)
    status = await client.tick_working_memory(
        session_id="s-1", user_id="u-1",
        model_source="user_model", model_ref="m-1",
        recent_turns=[{"role": "user", "content": "hi"}],
    )
    assert status == "updated"
    assert captured["url"].endswith("/internal/working-memory/tick")
    assert captured["body"]["recent_turns"][0]["content"] == "hi"
    assert captured["body"]["model_ref"] == "m-1"


@pytest.mark.asyncio
async def test_tick_working_memory_swallows_failure():
    def handler(req: httpx.Request) -> httpx.Response:
        return httpx.Response(503)

    client = _make_client(handler)
    status = await client.tick_working_memory(
        session_id="s", user_id="u", model_source="user_model", model_ref="m", recent_turns=[],
    )
    assert status is None


# ── D-KNOWLEDGE-TOOL-ERRORS-NOT-ISERROR ───────────────────────────────────────


def test_error_envelope_decodes_c4_json_code_and_detail():
    """knowledge-service now RAISES on a tool failure and puts a C4-shaped JSON
    body in content[0].text. The stable code + detail must survive so a workflow
    can branch on KG_ENDPOINT_NOT_NODE rather than pattern-matching prose (C5)."""
    from app.client.knowledge_client import _error_envelope

    out = _error_envelope(
        '{"code":"KG_ENDPOINT_NOT_NODE","message":"endpoints are not nodes",'
        '"detail":{"missing":["b"]}}'
    )
    assert out["success"] is False
    assert out["error"] == "endpoints are not nodes"
    assert out["code"] == "KG_ENDPOINT_NOT_NODE"
    assert out["detail"] == {"missing": ["b"]}


def test_error_envelope_json_without_code_omits_it():
    from app.client.knowledge_client import _error_envelope

    out = _error_envelope('{"message":"boom"}')
    assert out == {"success": False, "result": None, "error": "boom"}


def test_error_envelope_plain_text_degrades():
    """Overlay/external tools and older services still send plain text — never raise."""
    from app.client.knowledge_client import _error_envelope

    out = _error_envelope("something went wrong")
    assert out == {"success": False, "result": None, "error": "something went wrong"}


def test_error_envelope_malformed_json_degrades_to_raw_text():
    from app.client.knowledge_client import _error_envelope

    out = _error_envelope('{"message": broken')
    assert out["success"] is False
    assert out["error"] == '{"message": broken'


def test_error_envelope_empty_has_fallback_message():
    from app.client.knowledge_client import _error_envelope

    assert _error_envelope("")["error"] == "mcp tool error"
