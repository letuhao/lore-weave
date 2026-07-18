"""Tests for provider-registry and billing HTTP clients."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import httpx
import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")

from app.client.provider_client import ProviderRegistryClient
from app.client.billing_client import BillingClient
from app.client.embedding_client import EmbeddingClient, EmbeddingError


class TestProviderRegistryClient:
    @pytest.mark.asyncio
    @patch("app.client.provider_client.build_internal_client")
    async def test_resolve_success(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "provider_kind": "openai",
            "provider_model_name": "gpt-4",
            "base_url": "https://api.openai.com",
            "api_key": "sk-test",
            "context_length": 8192,
        }
        mock_resp.raise_for_status = MagicMock()

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        client = ProviderRegistryClient()
        creds = await client.resolve("user_model", "ref-123", "user-1")

        assert creds.provider_kind == "openai"
        assert creds.api_key == "sk-test"
        mock_http.get.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.client.provider_client.build_internal_client")
    async def test_resolve_404_raises_value_error(self, mock_client_cls):
        mock_resp = MagicMock()
        mock_resp.status_code = 404

        mock_http = AsyncMock()
        mock_http.get.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        client = ProviderRegistryClient()
        with pytest.raises(ValueError, match="not found"):
            await client.resolve("user_model", "ref-123", "user-1")


class TestBillingClient:
    @pytest.mark.asyncio
    @patch("app.client.billing_client.build_internal_client")
    async def test_log_usage_success(self, mock_client_cls):
        mock_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http.post.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        client = BillingClient()
        # Should not raise
        await client.log_usage(
            user_id="user-1",
            model_source="user_model",
            model_ref="ref-123",
            provider_kind="openai",
            input_tokens=100,
            output_tokens=50,
            session_id="sess-1",
            message_id="msg-1",
        )
        mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.client.billing_client.build_internal_client")
    async def test_log_usage_sends_internal_token_header(self, mock_client_cls):
        """D-CHAT-BILLING-01 regression-lock: usage-billing's middleware
        rejects calls without ``X-Internal-Token``. The original
        ``test_log_usage_success`` only asserted ``post.assert_awaited_once``
        and never inspected the headers kwarg — which is exactly how this
        bug shipped broken at birth (session-58 cycle-1 live smoke
        observation). A future refactor that drops the header must
        fail this test."""
        mock_http = AsyncMock()
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_http.post.return_value = mock_resp
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        client = BillingClient()
        await client.log_usage(
            user_id="user-1",
            model_source="user_model",
            model_ref="ref-123",
            provider_kind="openai",
            input_tokens=100,
            output_tokens=50,
            session_id="sess-1",
            message_id="msg-1",
        )
        # P3 SDK-first (W5): the token is now BAKED into the client by
        # build_internal_client (a default header on every request), not passed
        # per-request. The regression-lock intent is unchanged — the billing call
        # MUST carry X-Internal-Token — so assert the factory received the token.
        _args, kwargs = mock_client_cls.call_args
        assert kwargs.get("internal_token") == "test-internal-token"

    @pytest.mark.asyncio
    @patch("app.client.billing_client.build_internal_client")
    async def test_log_usage_swallows_errors(self, mock_client_cls):
        mock_http = AsyncMock()
        mock_http.post.side_effect = Exception("network error")
        mock_http.__aenter__ = AsyncMock(return_value=mock_http)
        mock_http.__aexit__ = AsyncMock(return_value=False)
        mock_client_cls.return_value = mock_http

        client = BillingClient()
        # Should not raise even on error
        await client.log_usage(
            user_id="user-1",
            model_source="user_model",
            model_ref="ref-123",
            provider_kind="openai",
            input_tokens=100,
            output_tokens=50,
            session_id="sess-1",
            message_id="msg-1",
        )


class TestEmbeddingClient:
    """chat-service's FIRST embedding-provider call site (design item 1,
    embeddings sub-item of docs/plans/2026-07-07-mcp-discovery-and-reliability-
    hardening.md) — ported from knowledge-service's `EmbeddingClient`. Unlike
    `ProviderRegistryClient`/`BillingClient` above, `EmbeddingClient` builds its
    `build_internal_client` ONCE in `__init__` (not per-call via `async with`),
    matching knowledge-service's/composition-service's own embedding client
    shape — so the mock is the http client directly, no `__aenter__` needed."""

    @pytest.mark.asyncio
    @patch("app.client.embedding_client.build_internal_client")
    async def test_embed_success(self, mock_build_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "embeddings": [[0.1, 0.2, 0.3]],
            "dimension": 3,
            "model": "bge-m3",
            "prompt_tokens": 4,
        }
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_build_client.return_value = mock_http

        client = EmbeddingClient("http://provider-registry-service:8085", "test-token")
        result = await client.embed(
            user_id="user-1", model_source="user_model", model_ref="ref-1", texts=["hello"],
        )
        assert result.embeddings == [[0.1, 0.2, 0.3]]
        assert result.dimension == 3
        assert result.model == "bge-m3"
        assert result.prompt_tokens == 4
        mock_http.post.assert_awaited_once()

    @pytest.mark.asyncio
    @patch("app.client.embedding_client.build_internal_client")
    async def test_embed_sends_internal_token_via_shared_factory(self, mock_build_client):
        """Mirrors D-CHAT-BILLING-01's regression-lock discipline: assert the
        factory actually received the token, not just that post() was called."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"embeddings": [[0.0]], "dimension": 1, "model": "m"}
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_build_client.return_value = mock_http

        EmbeddingClient("http://provider-registry-service:8085", "test-internal-token")
        _args, kwargs = mock_build_client.call_args
        assert kwargs.get("internal_token") == "test-internal-token"

    @pytest.mark.asyncio
    @patch("app.client.embedding_client.build_internal_client")
    async def test_embed_timeout_raises_retryable_embedding_error(self, mock_build_client):
        mock_http = AsyncMock()
        mock_http.post.side_effect = httpx.TimeoutException("slow provider")
        mock_build_client.return_value = mock_http

        client = EmbeddingClient("http://provider-registry-service:8085", "test-token")
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed(
                user_id="user-1", model_source="user_model", model_ref="ref-1", texts=["hi"],
            )
        assert exc_info.value.retryable is True

    @pytest.mark.asyncio
    @patch("app.client.embedding_client.build_internal_client")
    async def test_embed_non_200_raises_embedding_error_with_status_code(self, mock_build_client):
        mock_resp = MagicMock()
        mock_resp.status_code = 400
        mock_resp.text = '{"detail": "unsupported model"}'
        mock_resp.json.return_value = {"detail": "unsupported model"}
        mock_http = AsyncMock()
        mock_http.post.return_value = mock_resp
        mock_build_client.return_value = mock_http

        client = EmbeddingClient("http://provider-registry-service:8085", "test-token")
        with pytest.raises(EmbeddingError) as exc_info:
            await client.embed(
                user_id="user-1", model_source="user_model", model_ref="ref-1", texts=["hi"],
            )
        assert exc_info.value.status_code == 400
