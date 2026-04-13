"""Unit tests for the knowledge-service HTTP client.

Uses unittest.mock to stay consistent with test_clients.py — chat-service
doesn't have respx in its requirements. Every failure path must return
a degraded KnowledgeContext (mode='degraded'), never raise — chat must
keep working when knowledge-service is unavailable.
"""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")
os.environ.setdefault("MINIO_SECRET_KEY", "test-minio-secret")
os.environ.setdefault("INTERNAL_SERVICE_TOKEN", "test-internal-token")

from app.client.knowledge_client import (  # noqa: E402
    DEGRADED_RECENT_MESSAGE_COUNT,
    KnowledgeClient,
    KnowledgeContext,
    close_knowledge_client,
    get_knowledge_client,
    init_knowledge_client,
)


def _client() -> KnowledgeClient:
    return KnowledgeClient(
        base_url="http://knowledge-service:8092",
        internal_token="unit-test-token",
        timeout_s=0.5,
        retries=1,
    )


class TestKnowledgeClientHappyPath:
    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_no_project_mode_response_parses(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "mode": "no_project",
            "context": '<memory mode="no_project"><instructions>x</instructions></memory>',
            "recent_message_count": 50,
            "token_count": 12,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(user_id="u", message="hello")

        assert result.mode == "no_project"
        assert result.recent_message_count == 50
        assert result.token_count == 12
        assert "<memory" in result.context
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_static_mode_with_project(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "mode": "static",
            "context": '<memory mode="static">...</memory>',
            "recent_message_count": 50,
            "token_count": 200,
        }
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(
            user_id="u",
            project_id="00000000-0000-0000-0000-000000000001",
            message="who is Alice?",
        )
        assert result.mode == "static"
        # Verify project_id was sent in the body
        call_args = mock_http.post.call_args
        body = call_args.kwargs["json"]
        assert body["project_id"] == "00000000-0000-0000-0000-000000000001"
        assert body["message"] == "who is Alice?"
        await client.aclose()


class TestKnowledgeClientGracefulDegradation:
    """Every failure path must return a degraded context, never raise."""

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_timeout_returns_degraded(self, mock_client_cls):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.TimeoutException("boom"))
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        assert result.context == ""
        assert result.recent_message_count == DEGRADED_RECENT_MESSAGE_COUNT
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_connection_error_returns_degraded(self, mock_client_cls):
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_5xx_retries_then_returns_degraded(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "down"
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        # retries=1 → 2 total attempts
        assert mock_http.post.call_count == 2
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_404_no_retry_returns_degraded(self, mock_client_cls):
        """404 = project not found. Stable problem, don't retry."""
        mock_resp = MagicMock()
        mock_resp.status_code = 404
        mock_resp.text = '{"detail":"project not found"}'
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(
            user_id="u", project_id="00000000-0000-0000-0000-000000000001"
        )
        assert result.mode == "degraded"
        assert mock_http.post.call_count == 1  # no retry on 4xx
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_501_mode3_returns_degraded_at_debug(self, mock_client_cls):
        """501 = Mode 3 not implemented (Track 2). Expected, log at debug."""
        mock_resp = MagicMock()
        mock_resp.status_code = 501
        mock_resp.text = '{"detail":"Mode 3 not implemented"}'
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(
            user_id="u", project_id="00000000-0000-0000-0000-000000000001"
        )
        assert result.mode == "degraded"
        assert mock_http.post.call_count == 1
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_malformed_json_returns_degraded(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.side_effect = ValueError("not json")
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        await client.aclose()

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_unexpected_shape_returns_degraded(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"not_what_we_expected": True}
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        # Pydantic is lenient — extra="ignore" + all required fields have
        # defaults except `mode`. Missing `mode` → ValidationError → degraded.
        result = await client.build_context(user_id="u")
        assert result.mode == "degraded"
        await client.aclose()


class TestKnowledgeClientHeaders:
    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_internal_token_baked_into_headers(self, mock_client_cls):
        # Make the mocked client awaitable for aclose()
        mock_client_cls.return_value = AsyncMock()
        client = _client()
        # Verify httpx.AsyncClient was constructed with the X-Internal-Token header
        mock_client_cls.assert_called_once()
        kwargs = mock_client_cls.call_args.kwargs
        assert kwargs["headers"]["X-Internal-Token"] == "unit-test-token"
        await client.aclose()


class TestSingletonLifecycle:
    """K4-I1 lesson learned — init must be idempotent."""

    @pytest.mark.asyncio
    async def test_init_is_idempotent(self):
        # Reset state in case other tests left a client around
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
        # Second call returns the same instance
        client2 = get_knowledge_client()
        assert client is client2
        await close_knowledge_client()


class TestSingleLogPerFailure:
    """K4-I4 lesson learned — log AT MOST one warning per failed call,
    not one per retry attempt."""

    @pytest.mark.asyncio
    @patch("app.client.knowledge_client.httpx.AsyncClient")
    async def test_5xx_logs_only_once(self, mock_client_cls, caplog):
        import logging

        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "down"
        mock_http = AsyncMock()
        mock_http.post = AsyncMock(return_value=mock_resp)
        mock_client_cls.return_value = mock_http

        client = _client()
        with caplog.at_level(logging.WARNING, logger="app.client.knowledge_client"):
            await client.build_context(user_id="u")

        unavailable = [
            r for r in caplog.records if "unavailable" in r.getMessage()
        ]
        assert len(unavailable) == 1
        await client.aclose()
