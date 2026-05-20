"""Tests for provider-registry and billing HTTP clients."""
from __future__ import annotations

import os
from unittest.mock import AsyncMock, patch, MagicMock

import pytest

os.environ.setdefault("DATABASE_URL", "postgresql://test:test@localhost/test")
os.environ.setdefault("JWT_SECRET", "test-secret-key-for-unit-tests")

from app.client.provider_client import ProviderRegistryClient
from app.client.billing_client import BillingClient


class TestProviderRegistryClient:
    @pytest.mark.asyncio
    @patch("app.client.provider_client.httpx.AsyncClient")
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
    @patch("app.client.provider_client.httpx.AsyncClient")
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
    @patch("app.client.billing_client.httpx.AsyncClient")
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
    @patch("app.client.billing_client.httpx.AsyncClient")
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
        # Header inspection — the bug surface.
        _args, kwargs = mock_http.post.call_args
        headers = kwargs.get("headers") or {}
        assert headers.get("X-Internal-Token") == "test-internal-token"

    @pytest.mark.asyncio
    @patch("app.client.billing_client.httpx.AsyncClient")
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
